"""
Sequential Tool Execution Engine
Handles execution of multiple tools in sequence with variable resolution
"""
import asyncio
import json
import re
from typing import Any

from globals import logger


def resolve_sequence_args(raw_args: dict, state: dict) -> dict:
    """
    Resolve {{stepN.output.field}} references in arguments
    
    Args:
        raw_args: Arguments with potential variable references
        state: Execution state containing outputs from previous steps
    
    Returns:
        Resolved arguments with variables replaced by actual values
    
    Examples:
        state = {"step0": {"output": {"country_code": "FR", "city": "Paris"}}}
        raw_args = {"country": "{{step0.output.country_code}}"}
        → {"country": "FR"}
    """
    if not isinstance(raw_args, dict):
        return raw_args
    
    resolved = {}
    
    for key, value in raw_args.items():
        resolved[key] = _resolve_value(value, state)
    
    return resolved


def _resolve_value(value: Any, state: dict) -> Any:
    """
    Recursively resolve a single value (handles strings, dicts, lists)
    """
    if isinstance(value, str):
        return _resolve_string(value, state)
    elif isinstance(value, dict):
        return {k: _resolve_value(v, state) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_value(item, state) for item in value]
    else:
        return value


def _resolve_string(value: str, state: dict) -> Any:
    """
    Resolve variable references in a string
    
    Supports:
    - {{step0.output.field}} - Direct field access
    - {{step0.output.nested.field}} - Nested field access
    - {{input.field}} - User input passthrough
    """
    # Pattern: {{stepN.output.path.to.field}} or {{input.field}}
    pattern = r'\{\{([^}]+)\}\}'
    matches = re.findall(pattern, value)
    
    if not matches:
        return value
    
    # If entire string is a single variable, return the value directly
    # This preserves types (e.g., numbers, booleans)
    if len(matches) == 1 and value == f"{{{{{matches[0]}}}}}":
        return _extract_value_from_path(matches[0], state)
    
    # Multiple variables or mixed content - do string substitution
    resolved = value
    for match in matches:
        extracted = _extract_value_from_path(match, state)
        # Convert to string for substitution
        resolved = resolved.replace(f"{{{{{match}}}}}", str(extracted) if extracted is not None else "")
    
    return resolved


def _extract_value_from_path(path: str, state: dict) -> Any:
    """
    Extract value from nested path like 'step0.output.country_code'
    
    Args:
        path: Dot-separated path (e.g., 'step0.output.country_code')
        state: State dictionary
    
    Returns:
        Extracted value or None if path not found
    """
    parts = path.strip().split('.')
    current = state
    
    try:
        for part in parts:
            if isinstance(current, dict):
                current = current[part]
            elif isinstance(current, list):
                # Support array indexing: step0.output[0]
                index = int(part)
                current = current[index]
            else:
                return None
        return current
    except (KeyError, IndexError, ValueError, TypeError):
        logger.warning(f"Could not resolve path: {path}")
        return None


async def execute_sequence(args: dict, tool_mapping: dict, context) -> dict:
    """
    Execute multiple tools in sequence with data flow between steps
    
    Args:
        args: Dictionary containing 'steps' array
        tool_mapping: Available tool mappings from context
        context: Service context (self) with access to org_id, thread_id, etc.
    
    Returns:
        Dictionary with response and status
    
    Example args:
    {
        "steps": [
            {
                "tool": "search_flights",
                "args": {"destination": "Paris", "dates": "2026-08-01"}
            },
            {
                "tool": "check_visa",
                "args": {"country": "{{step0.output.country_code}}"}
            }
        ]
    }
    """
    try:
        steps = args.get("steps", [])
        
        if not steps:
            return {
                "response": {"error": "No steps provided in sequence"},
                "status": 0
            }
        
        # Validate maximum steps to prevent abuse
        MAX_STEPS = 10
        if len(steps) > MAX_STEPS:
            return {
                "response": {"error": f"Maximum {MAX_STEPS} steps allowed in sequence"},
                "status": 0
            }
        
        state = {}
        execution_log = []
        
        # Execute each step sequentially
        for i, step in enumerate(steps):
            tool_name = step.get("tool")
            raw_args = step.get("args", {})
            
            if not tool_name:
                return {
                    "response": {"error": f"Step {i}: Missing tool name"},
                    "status": 0
                }
            
            # Resolve variable references from previous steps
            resolved_args = resolve_sequence_args(raw_args, state)
            
            logger.info(f"Sequence step {i}: Executing {tool_name} with args: {json.dumps(resolved_args)[:200]}")
            
            # Execute the tool
            result = await _execute_single_tool(
                tool_name,
                resolved_args,
                tool_mapping,
                context
            )
            
            # Check for errors
            if result.get("status") == 0:
                return {
                    "response": {
                        "error": f"Step {i} ({tool_name}) failed",
                        "details": result.get("response"),
                        "completed_steps": i
                    },
                    "status": 0
                }
            
            # Store result in state
            state[f"step{i}"] = {
                "output": result.get("response"),
                "metadata": result.get("metadata", {})
            }
            
            execution_log.append({
                "step": i,
                "tool": tool_name,
                "args": resolved_args,
                "output": result.get("response")
            })
        
        # Return final step output (or all steps if needed)
        final_output = state[f"step{len(steps)-1}"]["output"]
        
        return {
            "response": final_output,
            "metadata": {
                "type": "sequence",
                "steps_executed": len(steps),
                "execution_log": execution_log
            },
            "status": 1
        }
        
    except Exception as error:
        logger.error(f"Error in execute_sequence: {error}")
        return {
            "response": {"error": str(error)},
            "status": 0
        }


async def _execute_single_tool(
    tool_name: str,
    args: dict,
    tool_mapping: dict,
    context
) -> dict:
    """
    Execute a single tool by routing to the appropriate executor
    
    Args:
        tool_name: Name of the tool to execute
        args: Resolved arguments for the tool
        tool_mapping: Tool mapping dictionary
        context: Service context
    
    Returns:
        Execution result with response and status
    """
    from src.services.commonServices.baseService.utils import axios_work
    from src.services.mcp_gateway.client import call_mcp_tool
    from src.services.agents.agent_service import call_gtwy_agent
    from src.services.rag.rag_service import get_text_from_vectorsQuery
    from src.services.web_search.firecrawl_service import call_firecrawl_scrape
    from src.configs.constant import inbuild_tools
    
    # Handle Gemini tool name prefixes
    name = tool_name
    if name not in tool_mapping and isinstance(name, str) and "." in name:
        short_name = name.rsplit(".", 1)[-1]
        if short_name in tool_mapping:
            name = short_name
    
    tool_info = tool_mapping.get(name)
    
    if not tool_info:
        return {
            "response": f"Tool '{tool_name}' not found in mapping",
            "status": 0
        }
    
    tool_type = tool_info.get("type")
    
    try:
        # Route to appropriate executor based on tool type
        if tool_type == "RAG":
            resource_to_collection_mapping = tool_info.get("resource_to_collection_mapping", {})
            result = await get_text_from_vectorsQuery(
                {**args, "org_id": context.org_id},
                Flag=True,
                owner_id=context.owner_id,
                resource_to_collection_mapping=resource_to_collection_mapping
            )
        
        elif tool_type == "AGENT":
            agent_args = {
                "org_id": context.org_id,
                "bridge_id": tool_info.get("bridge_id"),
                "user": args.get("_query", args.get("user", "")),
                "variables": {key: value for key, value in args.items() if key not in ["_query", "user"]},
                "message_id": context.message_id
            }
            
            if context.stream_mode and context.streamer:
                agent_args["injected_streamer"] = context.streamer
                agent_args["nested_stream_call"] = True
            
            if tool_info.get("requires_thread_id", False):
                agent_args["thread_id"] = context.thread_id
                agent_args["sub_thread_id"] = context.sub_thread_id
            
            if tool_info.get("version_id"):
                agent_args["version_id"] = tool_info.get("version_id")
            
            if hasattr(context, "timer") and hasattr(context.timer, "getTime"):
                agent_args["timer_state"] = context.timer.getTime()
            
            if hasattr(context, "bridge_configurations") and context.bridge_configurations:
                agent_args["bridge_configurations"] = context.bridge_configurations
            
            result = await call_gtwy_agent(agent_args)
        
        elif tool_type == inbuild_tools.get("Gtwy_Web_Search"):
            result = await call_firecrawl_scrape(args)
        
        elif tool_type == "MCP":
            result = await call_mcp_tool(args, tool_info)
        
        else:
            # Standard API call
            result = await axios_work(args, tool_info)
        
        return result
        
    except Exception as error:
        logger.error(f"Error executing tool {tool_name}: {error}")
        return {
            "response": str(error),
            "status": 0
        }
