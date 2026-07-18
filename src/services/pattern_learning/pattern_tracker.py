"""
Pattern Tracking Service
Tracks tool execution sequences for pattern learning
"""
import hashlib
from datetime import datetime
from typing import Any

from models.tool_pattern_models import tool_execution_sequences_collection
from globals import logger


async def track_tool_call(
    org_id: str,
    bridge_id: str,
    thread_id: str,
    message_id: str,
    tool_name: str,
    tool_args: dict,
    tool_output: Any,
    latency_ms: float = None
) -> bool:
    """
    Track a single tool call in a conversation thread
    This builds up the conversation-level tool sequence
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge/Agent ID
        thread_id: Conversation thread ID
        message_id: Message ID
        tool_name: Name of tool executed
        tool_args: Tool arguments
        tool_output: Tool output
        latency_ms: Execution time in milliseconds
    
    Returns:
        True if successfully tracked, False otherwise
    """
    try:
        from models.mongo_connection import db
        conversation_tools_collection = db["conversation_tool_calls"]
        
        # Store individual tool call with conversation context
        tool_call_doc = {
            "org_id": org_id,
            "bridge_id": bridge_id,
            "thread_id": thread_id,
            "message_id": message_id,
            "timestamp": datetime.utcnow(),
            "tool": tool_name,
            "args": tool_args,
            "output": tool_output,
            "latency_ms": latency_ms
        }
        
        await conversation_tools_collection.insert_one(tool_call_doc)
        
        # Now check if we should analyze the conversation for patterns
        await _analyze_conversation_pattern(
            org_id, bridge_id, thread_id, conversation_tools_collection
        )
        
        return True
        
    except Exception as error:
        logger.error(f"Error tracking tool call: {error}")
        return False


async def _analyze_conversation_pattern(
    org_id: str,
    bridge_id: str,
    thread_id: str,
    collection
) -> None:
    """
    Analyze recent tool calls in a conversation to detect patterns
    
    This looks at the last N tool calls in the thread to identify
    sequences that cross multiple AI turns
    """
    try:
        # Get last 10 tool calls in this conversation
        recent_calls = await collection.find({
            "org_id": org_id,
            "bridge_id": bridge_id,
            "thread_id": thread_id
        }).sort("timestamp", -1).limit(10).to_list(length=10)
        
        if len(recent_calls) < 2:
            return
        
        # Reverse to get chronological order
        recent_calls.reverse()
        
        # Look for sequences in a sliding window
        # Check last 2, 3, 4 tool calls for patterns
        for window_size in range(2, min(6, len(recent_calls) + 1)):
            sequence = recent_calls[-window_size:]
            
            tool_names = [call["tool"] for call in sequence]
            
            # Calculate time span
            time_span_seconds = (sequence[-1]["timestamp"] - sequence[0]["timestamp"]).total_seconds()
            
            # Only consider sequences within reasonable time window (e.g., 5 minutes)
            if time_span_seconds > 300:  # 5 minutes
                continue
            
            # Create sequence record
            sequence_data = []
            for call in sequence:
                sequence_data.append({
                    "tool": call["tool"],
                    "args": call.get("args", {}),
                    "output": call.get("output"),
                    "latency_ms": call.get("latency_ms")
                })
            
            # Count AI round-trips (one per tool + initial + final)
            ai_call_count = len(sequence) + 1
            
            # Store in tool_execution_sequences
            pattern_doc = {
                "org_id": org_id,
                "bridge_id": bridge_id,
                "thread_id": thread_id,
                "timestamp": sequence[-1]["timestamp"],
                "sequence": sequence_data,
                "tool_names": tool_names,
                "pattern_hash": _generate_pattern_hash(tool_names),
                "total_ai_calls": ai_call_count,
                "total_latency_ms": sum(call.get("latency_ms", 0) for call in sequence),
                "sequence_length": len(sequence),
                "time_span_seconds": time_span_seconds,
                "source": "conversation"  # Mark as conversation-level pattern
            }
            
            # Check if this exact sequence already exists (avoid duplicates)
            existing = await tool_execution_sequences_collection.find_one({
                "org_id": org_id,
                "bridge_id": bridge_id,
                "pattern_hash": pattern_doc["pattern_hash"],
                "timestamp": {"$gte": sequence[0]["timestamp"]}
            })
            
            if not existing:
                await tool_execution_sequences_collection.insert_one(pattern_doc)
                logger.info(f"Detected conversation pattern: {' → '.join(tool_names)}")
        
    except Exception as error:
        logger.error(f"Error analyzing conversation pattern: {error}")


async def track_tool_sequence(
    org_id: str,
    bridge_id: str,
    thread_id: str,
    message_id: str,
    tools_executed: dict,
    total_latency_ms: float = None
) -> bool:
    """
    Track tool executions - now tracks individual tools for conversation-level patterns
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge/Agent ID
        thread_id: Conversation thread ID
        message_id: Message ID
        tools_executed: Dictionary of tool execution data from tool_call_logs
        total_latency_ms: Total execution time in milliseconds
    
    Returns:
        True if successfully tracked, False otherwise
    """
    try:
        # Track each tool individually to build conversation-level patterns
        for tool_call_id, tool_data in tools_executed.items():
            if not isinstance(tool_data, dict):
                continue
            
            tool_name = tool_data.get("name")
            if not tool_name:
                continue
            
            await track_tool_call(
                org_id=org_id,
                bridge_id=bridge_id,
                thread_id=thread_id,
                message_id=message_id,
                tool_name=tool_name,
                tool_args=tool_data.get("args", {}),
                tool_output=_extract_output(tool_data),
                latency_ms=tool_data.get("latency_ms")
            )
        
        return True
        
    except Exception as error:
        logger.error(f"Error tracking tool sequence: {error}")
        return False


def _extract_output(tool_data: dict) -> Any:
    """
    Extract output from tool execution data
    Handles different response formats
    """
    # Try different possible locations for output
    if "data" in tool_data:
        data = tool_data["data"]
        if isinstance(data, dict):
            return data.get("response", data)
        return data
    
    if "response" in tool_data:
        return tool_data["response"]
    
    return None


def _generate_pattern_hash(tool_names: list) -> str:
    """
    Generate a unique hash for a tool sequence pattern
    Used to group similar sequences together
    
    Args:
        tool_names: List of tool names in order
    
    Returns:
        Hash string representing the pattern
    """
    pattern_string = "→".join(tool_names)
    return hashlib.md5(pattern_string.encode()).hexdigest()


async def get_recent_sequences(
    org_id: str,
    bridge_id: str,
    days: int = 7,
    limit: int = 1000
) -> list:
    """
    Retrieve recent tool execution sequences for pattern analysis
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        days: Number of days to look back
        limit: Maximum number of sequences to return
    
    Returns:
        List of sequence documents
    """
    try:
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        cursor = tool_execution_sequences_collection.find(
            {
                "org_id": org_id,
                "bridge_id": bridge_id,
                "timestamp": {"$gte": cutoff_date},
                "sequence_length": {"$gte": 2}  # Only sequences with 2+ tools
            }
        ).sort("timestamp", -1).limit(limit)
        
        sequences = await cursor.to_list(length=limit)
        
        return sequences
        
    except Exception as error:
        logger.error(f"Error retrieving sequences: {error}")
        return []


async def get_sequence_statistics(org_id: str, bridge_id: str, days: int = 7) -> dict:
    """
    Get statistics about tool sequences for a bridge
    
    Returns:
        Dictionary with statistics
    """
    try:
        from datetime import timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {
                "$match": {
                    "org_id": org_id,
                    "bridge_id": bridge_id,
                    "timestamp": {"$gte": cutoff_date}
                }
            },
            {
                "$group": {
                    "_id": "$pattern_hash",
                    "count": {"$sum": 1},
                    "tool_names": {"$first": "$tool_names"},
                    "avg_latency": {"$avg": "$total_latency_ms"},
                    "total_ai_calls": {"$sum": "$total_ai_calls"}
                }
            },
            {
                "$sort": {"count": -1}
            },
            {
                "$limit": 20
            }
        ]
        
        cursor = tool_execution_sequences_collection.aggregate(pipeline)
        patterns = await cursor.to_list(length=20)
        
        total_sequences = await tool_execution_sequences_collection.count_documents({
            "org_id": org_id,
            "bridge_id": bridge_id,
            "timestamp": {"$gte": cutoff_date}
        })
        
        return {
            "total_sequences": total_sequences,
            "unique_patterns": len(patterns),
            "top_patterns": patterns
        }
        
    except Exception as error:
        logger.error(f"Error getting sequence statistics: {error}")
        return {
            "total_sequences": 0,
            "unique_patterns": 0,
            "top_patterns": []
        }
