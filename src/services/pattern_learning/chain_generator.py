"""
Chain Generation Service
Automatically generates tool chains from learned patterns
"""
from datetime import datetime
from typing import Any

from models.tool_pattern_models import (
    learned_tool_patterns_collection,
    generated_tool_chains_collection
)
from globals import logger


async def generate_chain_from_pattern(
    org_id: str,
    bridge_id: str,
    pattern_hash: str,
    created_by: str = "auto"
) -> dict:
    """
    Generate an executable tool chain from a learned pattern
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        pattern_hash: Hash of the pattern to convert to chain
        created_by: Creator identifier ("auto" or user_id)
    
    Returns:
        Generated chain document or None if failed
    """
    try:
        # Get the pattern
        pattern = await learned_tool_patterns_collection.find_one({
            "org_id": org_id,
            "bridge_id": bridge_id,
            "pattern_hash": pattern_hash
        })
        
        if not pattern:
            logger.error(f"Pattern {pattern_hash} not found")
            return None
        
        # Generate chain name
        tool_names = pattern.get("tools", [])
        chain_name = "_".join(tool_names) + "_chain"
        
        # Check if chain already exists
        existing_chain = await generated_tool_chains_collection.find_one({
            "org_id": org_id,
            "bridge_id": bridge_id,
            "name": chain_name
        })
        
        if existing_chain:
            logger.info(f"Chain {chain_name} already exists")
            return existing_chain
        
        # Generate steps with variable mappings
        steps = _generate_chain_steps(pattern)
        
        # Generate parameters for the chain (user inputs)
        parameters = _generate_chain_parameters(pattern, steps)
        
        # Generate description
        description = _generate_chain_description(pattern)
        
        # Create chain document
        chain = {
            "org_id": org_id,
            "bridge_id": bridge_id,
            "name": chain_name,
            "description": description,
            "pattern_id": pattern.get("_id"),
            "pattern_hash": pattern_hash,
            "steps": steps,
            "parameters": parameters,
            "tools": tool_names,
            "created_at": datetime.utcnow(),
            "created_by": created_by,
            "usage_count": 0,
            "is_active": True,
            "auto_generated": True,
            "metadata": {
                "frequency": pattern.get("frequency"),
                "confidence": pattern.get("confidence"),
                "estimated_savings_ms": pattern.get("estimated_savings_ms")
            }
        }
        
        # Store chain
        result = await generated_tool_chains_collection.insert_one(chain)
        chain["_id"] = result.inserted_id
        
        # Update pattern with chain reference
        await learned_tool_patterns_collection.update_one(
            {"_id": pattern.get("_id")},
            {
                "$set": {
                    "chain_id": result.inserted_id,
                    "status": "chain_created"
                }
            }
        )
        
        logger.info(f"Generated chain: {chain_name} for pattern {pattern_hash}")
        
        return chain
        
    except Exception as error:
        logger.error(f"Error generating chain from pattern: {error}")
        return None


def _generate_chain_steps(pattern: dict) -> list:
    """
    Generate step definitions with variable mappings from pattern data
    
    Args:
        pattern: Pattern document with data_flow information
    
    Returns:
        List of step definitions
    """
    tools = pattern.get("tools", [])
    data_flow = pattern.get("data_flow", [])
    
    steps = []
    
    for i, tool_name in enumerate(tools):
        # Build args template for this step
        args_template = {}
        
        # Find data flow mappings that target this step
        for flow in data_flow:
            if flow["to_step"] == i:
                # This arg should come from a previous step
                from_step = flow["from_step"]
                from_field = flow["from_field"]
                to_arg = flow["to_arg"]
                
                # Create variable reference
                args_template[to_arg] = f"{{{{step{from_step}.output.{from_field}}}}}"
        
        # Args not covered by data flow will be marked as user inputs
        # These will be filled from the chain's input parameters
        # Note: We'll handle this in the parameter generation
        
        steps.append({
            "tool": tool_name,
            "args": args_template
        })
    
    return steps


def _generate_chain_parameters(pattern: dict, steps: list) -> dict:
    """
    Generate parameter schema for the chain
    This defines what inputs the user needs to provide
    
    Args:
        pattern: Pattern document
        steps: Generated step definitions
    
    Returns:
        OpenAI-style parameter schema
    """
    # For now, create a generic schema
    # In a more advanced version, we would analyze the first step's args
    # to determine what user inputs are needed
    
    tools = pattern.get("tools", [])
    first_tool = tools[0] if tools else "unknown"
    
    # Generic schema - can be enhanced by analyzing actual tool schemas
    return {
        "type": "object",
        "properties": {
            "input": {
                "type": "object",
                "description": f"Input parameters for the {first_tool} step and subsequent steps"
            }
        },
        "required": ["input"]
    }


def _generate_chain_description(pattern: dict) -> str:
    """
    Generate a human-readable description for the chain
    
    Args:
        pattern: Pattern document
    
    Returns:
        Description string
    """
    tools = pattern.get("tools", [])
    frequency = pattern.get("frequency", 0)
    savings_ms = pattern.get("estimated_savings_ms", 0)
    savings_sec = savings_ms / 1000
    
    tool_sequence = " → ".join(tools)
    
    description = (
        f"⚡ OPTIMIZED CHAIN: {tool_sequence}. "
        f"This chain executes {len(tools)} tools in sequence, automatically passing data between steps. "
        f"Use this instead of calling the tools separately. "
        f"Reduces latency by ~{savings_sec:.1f}s and eliminates {len(tools)-1} AI round-trips. "
        f"Based on {frequency} observed uses."
    )
    
    return description


async def get_active_chains(org_id: str, bridge_id: str) -> list:
    """
    Get all active tool chains for a bridge
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
    
    Returns:
        List of active chain documents
    """
    try:
        chains = await generated_tool_chains_collection.find({
            "org_id": org_id,
            "bridge_id": bridge_id,
            "is_active": True
        }).to_list(length=None)
        
        return chains
        
    except Exception as error:
        logger.error(f"Error getting active chains: {error}")
        return []


async def increment_chain_usage(chain_id: Any) -> None:
    """
    Increment usage counter for a chain
    
    Args:
        chain_id: Chain document ID
    """
    try:
        await generated_tool_chains_collection.update_one(
            {"_id": chain_id},
            {
                "$inc": {"usage_count": 1},
                "$set": {"last_used": datetime.utcnow()}
            }
        )
    except Exception as error:
        logger.error(f"Error incrementing chain usage: {error}")


async def deactivate_chain(org_id: str, bridge_id: str, chain_name: str) -> bool:
    """
    Deactivate a chain (soft delete)
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        chain_name: Name of chain to deactivate
    
    Returns:
        True if successful
    """
    try:
        result = await generated_tool_chains_collection.update_one(
            {
                "org_id": org_id,
                "bridge_id": bridge_id,
                "name": chain_name
            },
            {
                "$set": {
                    "is_active": False,
                    "deactivated_at": datetime.utcnow()
                }
            }
        )
        
        return result.modified_count > 0
        
    except Exception as error:
        logger.error(f"Error deactivating chain: {error}")
        return False


async def approve_pattern(org_id: str, bridge_id: str, pattern_hash: str) -> dict:
    """
    Approve a pattern and generate chain
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        pattern_hash: Pattern to approve
    
    Returns:
        Generated chain document
    """
    try:
        # Update pattern status
        await learned_tool_patterns_collection.update_one(
            {
                "org_id": org_id,
                "bridge_id": bridge_id,
                "pattern_hash": pattern_hash
            },
            {
                "$set": {
                    "status": "approved",
                    "approved_at": datetime.utcnow()
                }
            }
        )
        
        # Generate chain
        chain = await generate_chain_from_pattern(
            org_id,
            bridge_id,
            pattern_hash,
            created_by="user"
        )
        
        return chain
        
    except Exception as error:
        logger.error(f"Error approving pattern: {error}")
        return None


async def dismiss_pattern(org_id: str, bridge_id: str, pattern_hash: str) -> bool:
    """
    Dismiss a pattern suggestion
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        pattern_hash: Pattern to dismiss
    
    Returns:
        True if successful
    """
    try:
        result = await learned_tool_patterns_collection.update_one(
            {
                "org_id": org_id,
                "bridge_id": bridge_id,
                "pattern_hash": pattern_hash
            },
            {
                "$set": {
                    "status": "dismissed",
                    "dismissed_at": datetime.utcnow()
                }
            }
        )
        
        return result.modified_count > 0
        
    except Exception as error:
        logger.error(f"Error dismissing pattern: {error}")
        return False
