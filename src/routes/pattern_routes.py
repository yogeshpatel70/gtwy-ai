"""
API Routes for Pattern Learning and Chain Management
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from src.controllers.pattern_controller import (
    analyze_bridge_patterns,
    detect_bridge_patterns,
    get_pending_patterns,
    approve_pattern_controller,
    dismiss_pattern_controller,
    get_active_chains_controller,
    deactivate_chain_controller
)
from globals import logger


router = APIRouter(prefix="/api/patterns", tags=["Pattern Learning"])


class PatternApprovalRequest(BaseModel):
    org_id: str
    bridge_id: str
    pattern_hash: str


class ChainDeactivationRequest(BaseModel):
    org_id: str
    bridge_id: str
    chain_name: str


@router.get("/analyze/{org_id}/{bridge_id}")
async def analyze_patterns_endpoint(org_id: str, bridge_id: str):
    """
    Analyze tool usage patterns for a bridge
    
    Returns insights and recommendations for chain creation
    """
    try:
        result = await analyze_bridge_patterns(org_id, bridge_id)
        
        if result.get("success"):
            return {
                "status": "success",
                "data": result.get("data")
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))
            
    except Exception as error:
        logger.error(f"Error in analyze patterns endpoint: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@router.post("/detect/{org_id}/{bridge_id}")
async def detect_patterns_endpoint(org_id: str, bridge_id: str):
    """
    Run pattern detection for a bridge
    
    Analyzes recent tool sequences and identifies patterns
    """
    try:
        result = await detect_bridge_patterns(org_id, bridge_id)
        
        if result.get("success"):
            return {
                "status": "success",
                "data": result.get("data")
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))
            
    except Exception as error:
        logger.error(f"Error in detect patterns endpoint: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/pending/{org_id}/{bridge_id}")
async def get_pending_patterns_endpoint(org_id: str, bridge_id: str):
    """
    Get patterns pending approval for a bridge
    
    Returns patterns that have been detected but not yet approved/dismissed
    """
    try:
        result = await get_pending_patterns(org_id, bridge_id)
        
        if result.get("success"):
            return {
                "status": "success",
                "data": result.get("data")
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))
            
    except Exception as error:
        logger.error(f"Error in get pending patterns endpoint: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@router.post("/approve")
async def approve_pattern_endpoint(request: PatternApprovalRequest):
    """
    Approve a pattern and generate a tool chain
    
    Body:
    {
        "org_id": "org_123",
        "bridge_id": "bridge_456",
        "pattern_hash": "abc123..."
    }
    """
    try:
        result = await approve_pattern_controller(
            request.org_id,
            request.bridge_id,
            request.pattern_hash
        )
        
        if result.get("success"):
            return {
                "status": "success",
                "data": result.get("data")
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))
            
    except Exception as error:
        logger.error(f"Error in approve pattern endpoint: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@router.post("/dismiss")
async def dismiss_pattern_endpoint(request: PatternApprovalRequest):
    """
    Dismiss a pattern suggestion
    
    Body:
    {
        "org_id": "org_123",
        "bridge_id": "bridge_456",
        "pattern_hash": "abc123..."
    }
    """
    try:
        result = await dismiss_pattern_controller(
            request.org_id,
            request.bridge_id,
            request.pattern_hash
        )
        
        if result.get("success"):
            return {
                "status": "success",
                "data": result.get("data")
            }
        else:
            raise HTTPException(status_code=404, detail=result.get("error"))
            
    except Exception as error:
        logger.error(f"Error in dismiss pattern endpoint: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/chains/{org_id}/{bridge_id}")
async def get_active_chains_endpoint(org_id: str, bridge_id: str):
    """
    Get active tool chains for a bridge
    
    Returns all active (non-deactivated) chains
    """
    try:
        result = await get_active_chains_controller(org_id, bridge_id)
        
        if result.get("success"):
            return {
                "status": "success",
                "data": result.get("data")
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))
            
    except Exception as error:
        logger.error(f"Error in get active chains endpoint: {error}")
        raise HTTPException(status_code=500, detail=str(error))


@router.post("/chains/deactivate")
async def deactivate_chain_endpoint(request: ChainDeactivationRequest):
    """
    Deactivate a tool chain
    
    Body:
    {
        "org_id": "org_123",
        "bridge_id": "bridge_456",
        "chain_name": "search_flights_visa_hotel_chain"
    }
    """
    try:
        result = await deactivate_chain_controller(
            request.org_id,
            request.bridge_id,
            request.chain_name
        )
        
        if result.get("success"):
            return {
                "status": "success",
                "data": result.get("data")
            }
        else:
            raise HTTPException(status_code=404, detail=result.get("error"))
            
    except Exception as error:
        logger.error(f"Error in deactivate chain endpoint: {error}")
        raise HTTPException(status_code=500, detail=str(error))
