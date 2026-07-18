"""
Background Pattern Detection Job
Runs periodically to detect patterns across all bridges
"""
import asyncio
from datetime import datetime, timedelta
from typing import List

from models.tool_pattern_models import tool_execution_sequences_collection
from src.services.pattern_learning.pattern_detector import detect_patterns
from globals import logger


# Configuration
DETECTION_INTERVAL_HOURS = 6  # Run every 6 hours
MIN_SEQUENCES_FOR_DETECTION = 10  # Minimum sequences needed before analyzing


async def run_pattern_detection_job():
    """
    Background job that runs periodically to detect patterns
    Should be called from a scheduler (cron, celery, etc.)
    """
    logger.info("Starting pattern detection background job")
    
    try:
        # Find bridges with recent activity
        bridges_to_analyze = await _get_active_bridges()
        
        logger.info(f"Found {len(bridges_to_analyze)} bridges with recent activity")
        
        # Detect patterns for each bridge
        total_patterns = 0
        for bridge_info in bridges_to_analyze:
            org_id = bridge_info["org_id"]
            bridge_id = bridge_info["bridge_id"]
            
            try:
                patterns = await detect_patterns(org_id, bridge_id)
                total_patterns += len(patterns)
                
                if patterns:
                    logger.info(
                        f"Detected {len(patterns)} patterns for bridge {bridge_id}"
                    )
            except Exception as error:
                logger.error(
                    f"Error detecting patterns for bridge {bridge_id}: {error}"
                )
        
        logger.info(
            f"Pattern detection job completed. Total patterns detected: {total_patterns}"
        )
        
        return {
            "success": True,
            "bridges_analyzed": len(bridges_to_analyze),
            "patterns_detected": total_patterns
        }
        
    except Exception as error:
        logger.error(f"Error in pattern detection job: {error}")
        return {
            "success": False,
            "error": str(error)
        }


async def _get_active_bridges() -> List[dict]:
    """
    Get list of bridges with recent tool activity
    
    Returns:
        List of {"org_id": str, "bridge_id": str} dictionaries
    """
    try:
        # Look for bridges with activity in the last 24 hours
        cutoff_date = datetime.utcnow() - timedelta(hours=24)
        
        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": cutoff_date},
                    "sequence_length": {"$gte": 2}
                }
            },
            {
                "$group": {
                    "_id": {
                        "org_id": "$org_id",
                        "bridge_id": "$bridge_id"
                    },
                    "sequence_count": {"$sum": 1}
                }
            },
            {
                "$match": {
                    "sequence_count": {"$gte": MIN_SEQUENCES_FOR_DETECTION}
                }
            },
            {
                "$project": {
                    "org_id": "$_id.org_id",
                    "bridge_id": "$_id.bridge_id",
                    "sequence_count": 1,
                    "_id": 0
                }
            }
        ]
        
        cursor = tool_execution_sequences_collection.aggregate(pipeline)
        bridges = await cursor.to_list(length=None)
        
        return bridges
        
    except Exception as error:
        logger.error(f"Error getting active bridges: {error}")
        return []


async def run_continuous_detection_loop():
    """
    Run pattern detection in a continuous loop
    Useful for development or containerized deployments
    """
    logger.info("Starting continuous pattern detection loop")
    
    while True:
        try:
            await run_pattern_detection_job()
        except Exception as error:
            logger.error(f"Error in detection loop: {error}")
        
        # Wait for next interval
        await asyncio.sleep(DETECTION_INTERVAL_HOURS * 3600)


# Entry point for starting the background service
if __name__ == "__main__":
    asyncio.run(run_continuous_detection_loop())
