"""
Database models for tool pattern learning and optimization
"""
from datetime import datetime
from typing import Any

from models.mongo_connection import db

# MongoDB Collections
tool_execution_sequences_collection = db["tool_execution_sequences"]
learned_tool_patterns_collection = db["learned_tool_patterns"]
generated_tool_chains_collection = db["generated_tool_chains"]
conversation_tool_calls_collection = db["conversation_tool_calls"]  # NEW: Individual tool calls


async def create_indexes():
    """Create indexes for pattern learning collections"""
    
    # Indexes for tool_execution_sequences
    await tool_execution_sequences_collection.create_index([
        ("org_id", 1),
        ("bridge_id", 1),
        ("timestamp", -1)
    ])
    await tool_execution_sequences_collection.create_index([("thread_id", 1)])
    
    # NEW: Indexes for conversation_tool_calls
    await conversation_tool_calls_collection.create_index([
        ("org_id", 1),
        ("bridge_id", 1),
        ("thread_id", 1),
        ("timestamp", -1)
    ])
    await conversation_tool_calls_collection.create_index([
        ("thread_id", 1),
        ("timestamp", -1)
    ])
    
    # Indexes for learned_tool_patterns
    await learned_tool_patterns_collection.create_index([
        ("org_id", 1),
        ("bridge_id", 1),
        ("pattern_hash", 1)
    ], unique=True)
    await learned_tool_patterns_collection.create_index([("status", 1)])
    await learned_tool_patterns_collection.create_index([("frequency", -1)])
    
    # Indexes for generated_tool_chains
    await generated_tool_chains_collection.create_index([
        ("org_id", 1),
        ("bridge_id", 1),
        ("name", 1)
    ], unique=True)
    await generated_tool_chains_collection.create_index([("is_active", 1)])
    
    print("Tool pattern indexes created successfully")


# Initialize indexes on module import (runs once)
# Note: In production, run this during deployment/migration
# asyncio.create_task(create_indexes())
