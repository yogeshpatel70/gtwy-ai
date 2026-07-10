import asyncio
import json
import uuid

from json_repair import repair_json

import globals as _globals
from globals import logger
from src.configs.constant import redis_keys

from ..cache_service import find_in_cache, acquire_lock, delete_in_cache, find_in_cache_with_prefix, make_json_serializable, release_lock
from ..commonServices.baseService.baseService import sendResponse
from ..commonServices.queueService.queueLogService import sub_queue_obj
from ..commonServices.queueService.queueMetricsService import metrics_queue_obj
from src.utils.alert_template import create_response_format
from .ai_middleware_format import process_batch_results
from .batch_script_utils import get_batch_result_handler, is_finalized_batch_item, get_batch_result_data
from .helper import Helper
from globals import *
from .token_calculation import TokenCalculator


async def repeat_function():
    while _globals.is_ready:
        await check_batch_status()
        await asyncio.sleep(900)
    logger.info("Batch cron stopped — server is shutting down")


# ---------------------------------------------------------------------------
# JSON validation helpers
# ---------------------------------------------------------------------------

def _is_json_mode(response_type):
    """Return True when the batch was configured to produce JSON output."""
    return (
        isinstance(response_type, dict)
        and response_type.get("type") in ("json_object", "json_schema")
    )


def _validate_and_repair_json_results(formatted_results):
    """
    Walk formatted_results and attempt to validate / repair JSON content for
    every item whose ``data.content`` is a string.

    Returns:
        good_results   – items that are already valid JSON (or were repaired).
        failed_items   – items whose JSON could not be repaired; these need a
                         retry sub-batch.
    """
    good_results = []
    failed_items = []

    for item in formatted_results:
        # Error items (no data.content) pass through unchanged
        if item.get("error") or item.get("status_code", 200) >= 400:
            good_results.append(item)
            continue

        content = (item.get("data") or {}).get("content")
        if not isinstance(content, str):
            # Non-string content (None, dict…) — pass through
            good_results.append(item)
            continue

        # 1. Try to parse as-is
        try:
            json.loads(content)
            good_results.append(item)
            continue
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. Attempt structural repair
        try:
            repaired = repair_json(content)
            # Confirm the repaired string is actually valid JSON
            json.loads(repaired)
            item["data"]["content"] = repaired
            item["json_repaired"] = True
            good_results.append(item)
        except Exception:
            # Repair also failed — schedule a retry sub-batch for this message
            failed_items.append(item)

    return good_results, failed_items


# ---------------------------------------------------------------------------
# Retry sub-batch creation
# ---------------------------------------------------------------------------

async def create_json_retry_batch(failed_items, batch_data, service, apikey):
    """
    Submit a new batch containing only the messages that returned
    non-parsable JSON. Uses the ai_config_mapping stored in Redis at batch
    creation time — which already contains the fully provider-formatted request
    body per message_id — so no reconstruction is needed.

    The new batch shares the same webhook / config as the original so the user
    gets a second webhook call when retried results are ready.

    Args:
        failed_items  – list of formatted_result dicts for messages that need retry
        batch_data    – original Redis cache entry for the parent batch
        service       – LLM service name ('openai', 'anthropic', …)
        apikey        – API key for the service
    """
    try:
        parent_batch_id = batch_data.get("id")
        # ai_config_mapping: { message_id → full provider-specific request body }
        ai_config_mapping = batch_data.get("ai_config_mapping") or {}
        model = batch_data.get("model")
        org_id = batch_data.get("org_id")
        bridge_id = batch_data.get("bridge_id")
        version_id = batch_data.get("version_id", "")
        thread_id = batch_data.get("thread_id")
        meta = batch_data.get("meta")
        webhook = batch_data.get("webhook") or {}
        response_type = batch_data.get("response_type")

        if not ai_config_mapping:
            logger.error(
                f"Retry sub-batch for {parent_batch_id}: no ai_config_mapping stored in cache. "
                "Cannot reconstruct retry batch."
            )
            return

        # Collect the message_ids that need retrying
        retry_message_ids = []
        for item in failed_items:
            msg_id = item.get("message_id")
            if not msg_id:
                continue
            if msg_id not in ai_config_mapping:
                logger.warning(
                    f"Retry sub-batch: message_id={msg_id} not found in ai_config_mapping "
                    f"for batch {parent_batch_id}. Skipping."
                )
                continue
            retry_message_ids.append(msg_id)

        if not retry_message_ids:
            logger.warning(
                f"Retry sub-batch for {parent_batch_id}: no retryable messages resolved. Aborting."
            )
            return

        logger.info(
            f"Creating JSON retry sub-batch for {parent_batch_id}: "
            f"{len(retry_message_ids)} message(s) — {retry_message_ids}"
        )

        # Build provider-specific batch requests directly from ai_config_mapping.
        # Each value is already in the exact format the provider's API expects.
        # We just need to wrap them back in the correct envelope per provider.

        if service == "anthropic":
            from ..commonServices.anthropic.anthropic_run_batch import create_batch_requests as anthropic_create
            from ..cache_service import store_in_cache

            batch_requests = []
            new_message_id_mapping = {}
            new_ai_config_mapping = {}
            new_message_mappings = []

            for old_msg_id in retry_message_ids:
                new_msg_id = str(uuid.uuid4())
                request_params = ai_config_mapping[old_msg_id]
                batch_requests.append({
                    "custom_id": new_msg_id,
                    "params": request_params,
                })
                new_ai_config_mapping[new_msg_id] = request_params
                new_message_mappings.append({"message_id": new_msg_id})

            message_batch = await anthropic_create(batch_requests, apikey, model)
            new_batch_id = message_batch.id
            batch_json = {
                "id": new_batch_id,
                "processing_status": message_batch.processing_status,
                "request_counts": {
                    "processing": message_batch.request_counts.processing,
                    "succeeded": message_batch.request_counts.succeeded,
                    "errored": message_batch.request_counts.errored,
                    "canceled": message_batch.request_counts.canceled,
                    "expired": message_batch.request_counts.expired,
                },
                "created_at": message_batch.created_at,
                "expires_at": message_batch.expires_at,
                "apikey": apikey,
                "webhook": webhook,
                "batch_variables": None,
                "message_id_mapping": {item["message_id"]: idx for idx, item in enumerate(new_message_mappings)},
                "service": service,
                "model": model,
                "org_id": org_id,
                "bridge_id": bridge_id,
                "version_id": version_id,
                "thread_id": thread_id,
                "meta": meta,
                "response_type": response_type,
                "ai_config_mapping": new_ai_config_mapping,
            }
            cache_key = f"{redis_keys['batch_']}{new_batch_id}"
            await store_in_cache(cache_key, batch_json, ttl=86400)

        elif service in ("openai", "groq", "mistral"):
            from ..cache_service import store_in_cache

            if service == "openai":
                from ..commonServices.openAI.openai_run_batch import create_batch_file, process_batch_file
            elif service == "groq":
                from ..commonServices.groq.groq_run_batch import create_batch_file, process_batch_file
            else:
                from ..commonServices.Mistral.mistral_run_batch import create_batch_file, process_batch_file

            results = []
            new_message_id_mapping = {}
            new_ai_config_mapping = {}
            new_message_mappings = []

            for old_msg_id in retry_message_ids:
                new_msg_id = str(uuid.uuid4())
                body_data = ai_config_mapping[old_msg_id]

                if service == "openai":
                    request_obj = {
                        "custom_id": new_msg_id,
                        "method": "POST",
                        "url": "/v1/responses",
                        "body": body_data,
                    }
                elif service == "groq":
                    request_obj = {
                        "custom_id": new_msg_id,
                        "method": "POST",
                        "url": "/v1/chat/completions",
                        "body": body_data,
                    }
                else:  # mistral
                    request_obj = {
                        "custom_id": new_msg_id,
                        "body": body_data,
                    }

                results.append(json.dumps(request_obj))
                new_ai_config_mapping[new_msg_id] = body_data
                new_message_mappings.append({"message_id": new_msg_id})

            batch_input_file = await create_batch_file(results, apikey)

            if service == "mistral":
                batch_file = await process_batch_file(batch_input_file, apikey, model)
                new_batch_id = batch_file.id
                batch_json = {
                    "id": new_batch_id,
                    "status": batch_file.status,
                    "created_at": batch_file.created_at,
                    "model": model,
                    "apikey": apikey,
                    "webhook": webhook,
                    "batch_variables": None,
                    "message_id_mapping": {item["message_id"]: idx for idx, item in enumerate(new_message_mappings)},
                    "service": service,
                    "uploaded_file_id": batch_input_file.id,
                    "org_id": org_id,
                    "bridge_id": bridge_id,
                    "version_id": version_id,
                    "thread_id": thread_id,
                    "meta": meta,
                    "response_type": response_type,
                    "ai_config_mapping": new_ai_config_mapping,
                }
            else:
                batch_file = await process_batch_file(batch_input_file, apikey)
                new_batch_id = batch_file.id
                batch_json = {
                    "id": new_batch_id,
                    "status": batch_file.status,
                    "created_at": batch_file.created_at,
                    "model": model,
                    "apikey": apikey,
                    "webhook": webhook,
                    "batch_variables": None,
                    "message_id_mapping": {item["message_id"]: idx for idx, item in enumerate(new_message_mappings)},
                    "service": service,
                    "org_id": org_id,
                    "bridge_id": bridge_id,
                    "version_id": version_id,
                    "thread_id": thread_id,
                    "meta": meta,
                    "response_type": response_type,
                    "ai_config_mapping": new_ai_config_mapping,
                }

            cache_key = f"{redis_keys['batch_']}{new_batch_id}"
            await store_in_cache(cache_key, batch_json, ttl=86400)

        elif service == "gemini":
            from ..commonServices.Google.gemini_run_batch import create_batch_file, process_batch_file
            from ..cache_service import store_in_cache

            batch_requests = []
            new_message_id_mapping = {}
            new_ai_config_mapping = {}
            new_message_mappings = []

            for old_msg_id in retry_message_ids:
                new_msg_id = str(uuid.uuid4())
                request_content = ai_config_mapping[old_msg_id]
                batch_entry = {
                    "key": new_msg_id,
                    "request": request_content,
                }
                batch_requests.append(json.dumps(batch_entry))
                new_ai_config_mapping[new_msg_id] = request_content
                new_message_mappings.append({"message_id": new_msg_id})

            uploaded_file = await create_batch_file(batch_requests, apikey)
            batch_job = await process_batch_file(uploaded_file, apikey, model)
            new_batch_id = batch_job.name
            batch_json = {
                "id": new_batch_id,
                "state": batch_job.state,
                "create_time": batch_job.create_time,
                "model": model,
                "apikey": apikey,
                "webhook": webhook,
                "batch_variables": None,
                "message_id_mapping": {item["message_id"]: idx for idx, item in enumerate(new_message_mappings)},
                "service": service,
                "uploaded_file": uploaded_file.name,
                "org_id": org_id,
                "bridge_id": bridge_id,
                "version_id": version_id,
                "thread_id": thread_id,
                "meta": meta,
                "response_type": response_type,
                "ai_config_mapping": new_ai_config_mapping,
            }
            cache_key = f"{redis_keys['batch_']}{new_batch_id}"
            await store_in_cache(cache_key, batch_json, ttl=86400)

        else:
            logger.error(
                f"Retry sub-batch: unknown service '{service}' for batch {parent_batch_id}. Aborting."
            )
            return

        logger.info(
            f"JSON retry sub-batch submitted for {parent_batch_id} → new batch_id={new_batch_id}. "
            "Results will be delivered to the same webhook when the retry batch completes."
        )

    except Exception as err:
        logger.error(
            f"Unexpected error in create_json_retry_batch (parent={batch_data.get('id')}): {err}",
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Main batch status poller
# ---------------------------------------------------------------------------

async def check_batch_status():
    try:
        print("Batch Script running...")
        batch_ids = await find_in_cache_with_prefix(redis_keys["batch_"])
        if batch_ids is None:
            return

        for batch_data in batch_ids:
            apikey = batch_data.get('apikey')
            webhook = batch_data.get('webhook')
            batch_id = batch_data.get('id')
            batch_variables = batch_data.get('batch_variables')
            message_id_mapping = batch_data.get('message_id_mapping', {})
            service = batch_data.get('service')
            model = batch_data.get('model')
            org_id = batch_data.get('org_id')
            bridge_id = batch_data.get('bridge_id')
            version_id = batch_data.get('version_id')
            thread_id = batch_data.get('thread_id')
            meta = batch_data.get('meta')
            # Stored at batch creation time for JSON validation + retry
            response_type = batch_data.get('response_type')

            cache_key = f"{redis_keys['batch_']}{batch_id}"

            # ── Step 1: acquire lock ──────────────────────────────────────────
            lock_acquired = await acquire_lock(batch_id)
            if not lock_acquired:
                logger.info(f"Batch {batch_id} is already being processed, skipping...")
                continue

            try:
                # ── Step 2: double-checked locking ────────────────────────────
                still_exists = await find_in_cache(cache_key)
                if still_exists is None:
                    logger.info(f"Batch {batch_id} already completed by another pod, skipping...")
                    continue

                if webhook.get("url") is not None:
                    response_format = create_response_format(
                        webhook.get("url"), webhook.get("headers")
                    )

                batch_result_handler = get_batch_result_handler(service)
                results, is_completed = await batch_result_handler(batch_id, apikey)

                if is_completed:
                    if results:
                        # Pre-compute cost per message_id from raw batch results
                        item_costs = {}
                        for raw_item in results:
                            msg_id, result_data, _status_code, has_error = get_batch_result_data(raw_item, service)
                            if msg_id and not has_error and result_data and model:
                                try:
                                    temp_calculator = TokenCalculator(service, {})
                                    temp_calculator.calculate_usage(result_data)
                                    cost_breakdown = temp_calculator.calculate_total_cost(model, service)
                                    item_costs[msg_id] = cost_breakdown.get("total_cost", 0) * 0.5
                                except Exception as cost_error:
                                    logger.error(f"Error calculating batch cost for message {msg_id}: {str(cost_error)}")

                        formatted_results = await process_batch_results(
                            results, service, batch_id, batch_variables, message_id_mapping
                        )

                        if not all(is_finalized_batch_item(item) for item in formatted_results):
                            logger.info(
                                f"Batch {batch_id} has non-finalized items. Will retry on next poll."
                            )
                            continue

                        # ── Step 3: JSON validation + repair (json_object / json_schema mode) ──
                        failed_json_items = []
                        if _is_json_mode(response_type):
                            formatted_results, failed_json_items = _validate_and_repair_json_results(
                                formatted_results
                            )
                            if failed_json_items:
                                logger.warning(
                                    f"Batch {batch_id}: {len(failed_json_items)} message(s) returned "
                                    f"non-parsable JSON after repair attempt. "
                                    f"Submitting retry sub-batch."
                                )

                        has_success = any(
                            item.get("status_code") is None or item.get("status_code", 200) < 400
                            for item in formatted_results
                        )

                        # Attach pre-computed cost to each formatted result's usage
                        for item in formatted_results:
                            msg_id = item.get("message_id")
                            item_usage = item.get("usage")
                            if item_usage is not None:
                                item_usage["cost"] = item_costs.get(msg_id, 0)

                        webhook_response = None
                        webhook_error = None

                        # ── Step 4: delete cache BEFORE webhook call ───────────
                        await delete_in_cache(cache_key)
                        logger.info(f"Batch {batch_id} removed from cache before webhook dispatch")

                        # ── Step 5: fire webhook for good (+ repaired) results ─
                        if webhook.get('url') is not None:
                            # Include partial=True flag in meta when some messages
                            # are being retried so the caller knows a second
                            # webhook will follow.
                            webhook_meta = meta
                            if failed_json_items:
                                webhook_meta = dict(meta) if isinstance(meta, dict) else {}
                                webhook_meta["partial"] = True
                                webhook_meta["retry_count"] = len(failed_json_items)
                            try:
                                webhook_response = await sendResponse(
                                    response_format,
                                    data=formatted_results,
                                    success=has_success,
                                    meta=webhook_meta,
                                )
                                logger.info(f"Batch {batch_id} - webhook sent")
                            except Exception as webhook_err:
                                webhook_error = str(webhook_err)
                                logger.error(f"Error sending webhook for batch {batch_id}: {webhook_error}")

                        # ── Step 6: submit retry sub-batch in background ───────
                        if failed_json_items:
                            asyncio.create_task(
                                create_json_retry_batch(
                                    failed_items=failed_json_items,
                                    batch_data=batch_data,
                                    service=service,
                                    apikey=apikey,
                                )
                            )

                        batch_updates = []
                        metrics_data = []

                        for formatted_result in formatted_results:
                            message_id = formatted_result.get('message_id')
                            if not message_id:
                                continue

                            data = formatted_result.get('data', {})
                            usage = formatted_result.get('usage', {})
                            status_code = formatted_result.get('status_code')
                            error = formatted_result.get('error')
                            is_success = status_code is None or status_code < 400

                            if is_success:
                                llm_message = data.get('content')
                                chatbot_message = data.get('content')
                                error_message = None
                            else:
                                llm_message = None
                                chatbot_message = None
                                if isinstance(error, dict):
                                    error_message = error.get('message', str(error))
                                elif error:
                                    error_message = str(error)
                                else:
                                    error_message = "Unknown error occurred"

                            input_tokens = usage.get('input_tokens') or 0 if usage else 0
                            output_tokens = usage.get('output_tokens') or 0 if usage else 0
                            total_tokens = usage.get('total_tokens') or 0 if usage else 0
                            individual_cost = item_costs.get(message_id, 0)

                            update_data = {
                                'llm_message': llm_message,
                                'chatbot_message': chatbot_message,
                                'status': is_success,
                                'error': error_message,
                                'finish_reason': data.get('finish_reason'),
                                'tokens': {
                                    'input_tokens': input_tokens,
                                    'output_tokens': output_tokens,
                                    'total_tokens': total_tokens,
                                    'expected_cost': individual_cost,
                                } if usage else None,
                                'batch_data': {
                                    'status': 'completed',
                                    'batch_id': batch_id,
                                    'webhook_response': webhook_response,
                                    'webhook_error': webhook_error,
                                    'webhook_url': webhook.get('url'),
                                    'webhook_headers': Helper.mask_headers(webhook.get('headers')),
                                }
                            }

                            batch_updates.append({
                                'batch_id': batch_id,
                                'message_id': message_id,
                                'update_data': update_data,
                            })

                            if org_id and model:
                                metrics_data.append({
                                    'org_id': org_id,
                                    'bridge_id': bridge_id or '',
                                    'version_id': version_id or '',
                                    'thread_id': thread_id or '',
                                    'model': model,
                                    'input_tokens': float(input_tokens),
                                    'output_tokens': float(output_tokens),
                                    'total_tokens': float(total_tokens),
                                    'apikey_id': '',
                                    'latency': 0,
                                    'success': is_success,
                                    'cost': individual_cost,
                                    'time_zone': 'Asia/Kolkata',
                                    'service': service,
                                })

                        if batch_updates:
                            try:
                                await sub_queue_obj.publish_message(
                                    make_json_serializable({'update_batch_history': batch_updates})
                                )
                                logger.info(
                                    f"Published {len(batch_updates)} batch history updates for batch {batch_id}"
                                )
                            except Exception as queue_error:
                                logger.error(f"Error publishing batch history for batch {batch_id}: {queue_error}")

                        if metrics_data:
                            try:
                                await metrics_queue_obj.publish_message(
                                    make_json_serializable({'save_metrics': metrics_data})
                                )
                                logger.info(
                                    f"Published {len(metrics_data)} metrics for batch {batch_id}"
                                )
                            except Exception as metrics_error:
                                logger.error(f"Error publishing metrics for batch {batch_id}: {metrics_error}")

                    else:
                        # No results but completed — send generic error webhook
                        error_response = [{
                            "batch_id": batch_id,
                            "error": {"message": "Batch completed but no results were returned", "type": "no_results"},
                            "status_code": 500,
                        }]

                        await delete_in_cache(cache_key)
                        logger.info(f"Batch {batch_id} (no results) removed from cache")

                        if webhook.get('url') is not None:
                            try:
                                await sendResponse(response_format, data=error_response, success=False)
                                logger.info(f"Batch {batch_id} no-results webhook sent")
                            except Exception as webhook_err:
                                logger.error(f"Error sending no-results webhook for batch {batch_id}: {webhook_err}")

                else:
                    logger.info(f"Batch {batch_id} still in progress")

            except Exception as error:
                logger.error(f"Error processing batch {batch_id}: {error}")
            finally:
                await release_lock(batch_id)

    except Exception as error:
        logger.error(f"An error occurred while checking batch status: {error}")
