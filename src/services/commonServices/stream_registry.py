"""
In-memory registry for in-flight streaming chat tasks.

Maps `message_id -> asyncio.Task` so an HTTP client can request abort of a
running stream by message_id. Cancelling the task tears down the upstream
HTTPX/SDK connection to the model provider, which stops output-token billing
for the remainder of the generation.

Single-process only. For multi-worker deployments, swap this for a Redis-backed
pub/sub channel keyed by message_id (publish "abort" event, each worker
listens and cancels its local task if it owns that message_id).
"""
from __future__ import annotations

import asyncio
from typing import Dict

from globals import logger

_active_streams: Dict[str, asyncio.Task] = {}


def register(message_id: str, task: asyncio.Task) -> None:
    """Track a streaming task; auto-unregisters when the task finishes."""
    if not message_id or task is None:
        return
    _active_streams[message_id] = task

    def _cleanup(_t: asyncio.Task) -> None:
        # Drop the entry whether the task succeeded, failed, or was cancelled.
        _active_streams.pop(message_id, None)

    task.add_done_callback(_cleanup)


def abort(message_id: str) -> bool:
    """Request cancellation of the stream for `message_id`.

    Returns True if a matching in-flight stream was found and cancellation was
    requested; False otherwise.
    """
    task = _active_streams.get(message_id)
    if task is None:
        return False
    if task.done():
        return False
    logger.info(f"stream_registry: aborting stream message_id={message_id}")
    task.cancel()
    return True


def is_active(message_id: str) -> bool:
    task = _active_streams.get(message_id)
    return task is not None and not task.done()
