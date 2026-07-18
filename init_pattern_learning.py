"""
Initialize Pattern Learning System
Run this script once to set up database indexes
"""
import asyncio
from models.tool_pattern_models import create_indexes
from globals import logger


async def initialize():
    """Initialize pattern learning system"""
    try:
        logger.info("Initializing Pattern Learning System...")
        
        # Create database indexes
        logger.info("Creating database indexes...")
        await create_indexes()
        
        logger.info("✅ Pattern Learning System initialized successfully!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Start your GTWY-AI server")
        logger.info("2. Use tools normally - sequences will be tracked automatically")
        logger.info("3. Run background detector: python -m src.services.pattern_learning.background_detector")
        logger.info("4. Check for patterns: GET /api/patterns/pending/:org_id/:bridge_id")
        logger.info("5. Approve patterns: POST /api/patterns/approve")
        logger.info("")
        logger.info("See docs/PATTERN_LEARNING.md for full documentation")
        
    except Exception as error:
        logger.error(f"❌ Initialization failed: {error}")
        raise


if __name__ == "__main__":
    asyncio.run(initialize())
