"""
Pattern Learning Controller
Endpoints for managing tool patterns and chains
"""
from typing import Any

from globals import logger
from src.services.pattern_learning.pattern_detector import detect_patterns, analyze_sequences
from src.services.pattern_learning.chain_generator import (
    approve_pattern,
    dismiss_pattern,
    get_active_chains,
    deactivate_chain
)
from src.services.pattern_learning.pattern_tracker import get_sequence_statistics
from models.tool_pattern_models import learned_tool_patterns_collection


async def analyze_bridge_patterns(org_id: str, bridge_id: str) -> dict:
    """
    Analyze tool usage patterns for a bridge
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
    
    Returns:
        Analysis results with recommendations
    """
    try:
        # Get analysis
        analysis = await analyze_sequences(org_id, bridge_id)
        
        # Get statistics
        stats = await get_sequence_statistics(org_id, bridge_id)
        
        return {
            "success": True,
            "data": {
                **analysis,
                "statistics": stats
            }
        }
        
    except Exception as error:
        logger.error(f"Error analyzing patterns: {error}")
        return {
            "success": False,
            "error": str(error)
        }


async def detect_bridge_patterns(org_id: str, bridge_id: str) -> dict:
    """
    Detect and store patterns for a bridge
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
    
    Returns:
        Detected patterns
    """
    try:
        patterns = await detect_patterns(org_id, bridge_id)
        
        return {
            "success": True,
            "data": {
                "patterns_detected": len(patterns),
                "patterns": patterns
            }
        }
        
    except Exception as error:
        logger.error(f"Error detecting patterns: {error}")
        return {
            "success": False,
            "error": str(error)
        }


async def get_pending_patterns(org_id: str, bridge_id: str) -> dict:
    """
    Get patterns pending approval
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
    
    Returns:
        List of pending patterns
    """
    try:
        patterns = await learned_tool_patterns_collection.find({
            "org_id": org_id,
            "bridge_id": bridge_id,
            "status": "pending_approval"
        }).sort("frequency", -1).to_list(length=None)
        
        return {
            "success": True,
            "data": {
                "pending_patterns": len(patterns),
                "patterns": patterns
            }
        }
        
    except Exception as error:
        logger.error(f"Error getting pending patterns: {error}")
        return {
            "success": False,
            "error": str(error)
        }


async def approve_pattern_controller(org_id: str, bridge_id: str, pattern_hash: str) -> dict:
    """
    Approve a pattern and generate chain
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        pattern_hash: Pattern to approve
    
    Returns:
        Generated chain
    """
    try:
        chain = await approve_pattern(org_id, bridge_id, pattern_hash)
        
        if chain:
            return {
                "success": True,
                "data": {
                    "message": "Pattern approved and chain created",
                    "chain": chain
                }
            }
        else:
            return {
                "success": False,
                "error": "Failed to generate chain"
            }
        
    except Exception as error:
        logger.error(f"Error approving pattern: {error}")
        return {
            "success": False,
            "error": str(error)
        }


async def dismiss_pattern_controller(org_id: str, bridge_id: str, pattern_hash: str) -> dict:
    """
    Dismiss a pattern suggestion
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        pattern_hash: Pattern to dismiss
    
    Returns:
        Success status
    """
    try:
        success = await dismiss_pattern(org_id, bridge_id, pattern_hash)
        
        return {
            "success": success,
            "data": {
                "message": "Pattern dismissed" if success else "Pattern not found"
            }
        }
        
    except Exception as error:
        logger.error(f"Error dismissing pattern: {error}")
        return {
            "success": False,
            "error": str(error)
        }


async def get_active_chains_controller(org_id: str, bridge_id: str) -> dict:
    """
    Get active tool chains for a bridge
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
    
    Returns:
        List of active chains
    """
    try:
        chains = await get_active_chains(org_id, bridge_id)
        
        return {
            "success": True,
            "data": {
                "active_chains": len(chains),
                "chains": chains
            }
        }
        
    except Exception as error:
        logger.error(f"Error getting active chains: {error}")
        return {
            "success": False,
            "error": str(error)
        }


async def deactivate_chain_controller(org_id: str, bridge_id: str, chain_name: str) -> dict:
    """
    Deactivate a tool chain
    
    Args:
        org_id: Organization ID
        bridge_id: Bridge ID
        chain_name: Name of chain to deactivate
    
    Returns:
        Success status
    """
    try:
        success = await deactivate_chain(org_id, bridge_id, chain_name)
        
        return {
            "success": success,
            "data": {
                "message": "Chain deactivated" if success else "Chain not found"
            }
        }
        
    except Exception as error:
        logger.error(f"Error deactivating chain: {error}")
        return {
            "success": False,
            "error": str(error)
        }
