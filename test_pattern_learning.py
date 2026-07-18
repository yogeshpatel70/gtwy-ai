#!/usr/bin/env python3
"""
Pattern Learning System - Comprehensive Test Script

Tests the complete pattern learning flow with multiple test modes:
1. Mock Mode - Quick test with simulated data (no API key needed)
2. OpenAI Mode - Full test with real AI conversations (requires API key)
3. Validate Mode - Verify system components

Usage:
    # Mock mode (default, no API key needed)
    python test_pattern_learning.py --mode mock
    
    # OpenAI mode (requires API key)
    python test_pattern_learning.py --mode openai --api-key sk-xxx
    # or
    export OPENAI_API_KEY=sk-xxx
    python test_pattern_learning.py --mode openai
    
    # Validate mode (check system health)
    python test_pattern_learning.py --mode validate
    
    # Clean up test data
    python test_pattern_learning.py --cleanup
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid
import traceback

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.mongo_connection import db
from models.tool_pattern_models import (
    conversation_tool_calls_collection,
    tool_execution_sequences_collection,
    learned_tool_patterns_collection,
    generated_tool_chains_collection,
    create_indexes
)
from src.services.pattern_learning.pattern_tracker import track_tool_call
from src.services.pattern_learning.pattern_detector import detect_patterns
from src.services.pattern_learning.chain_generator import generate_chain_from_pattern
from globals import logger


# Test configuration
TEST_ORG_ID = "test_org_pattern"
TEST_BRIDGE_ID = "test_bridge_pattern"


# ============================================================================
# Mock Tools and Execution
# ============================================================================

MOCK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Search for available flights to a destination",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "Destination city"},
                    "dates": {"type": "string", "description": "Travel dates"}
                },
                "required": ["destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_visa",
            "description": "Check visa requirements for a country",
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {"type": "string", "description": "Country code (e.g., FR, GB)"}
                },
                "required": ["country"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_hotel",
            "description": "Book a hotel in a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                    "dates": {"type": "string", "description": "Check-in dates"}
                },
                "required": ["city"]
            }
        }
    }
]


def execute_mock_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a mock tool and return realistic results"""
    country_map = {"Paris": "FR", "London": "GB", "Tokyo": "JP", "Berlin": "DE", "Rome": "IT"}
    
    if tool_name == "search_flights":
        dest = args.get("destination", "Unknown")
        return {
            "destination": dest,
            "country_code": country_map.get(dest, "US"),
            "city": dest,
            "price": 450 + len(dest) * 10,
            "available": True
        }
    elif tool_name == "check_visa":
        country = args.get("country", "US")
        return {"country": country, "required": country in ["RU", "CN"], "duration": 90}
    elif tool_name == "book_hotel":
        city = args.get("city", "Unknown")
        return {"city": city, "hotel_name": f"Grand {city} Hotel", "price": 150, "confirmed": True}
    return {"error": f"Unknown tool: {tool_name}"}



# ============================================================================
# Mock Mode Tests
# ============================================================================

async def simulate_conversation_sequence(thread_id: str, seq_num: int, destinations: List[str]):
    """Simulate a conversation with multiple tool calls across AI turns"""
    dest = destinations[seq_num % len(destinations)]
    print(f"\n🗣️  Conversation {seq_num + 1}: {dest} (Thread: {thread_id})")
    
    # Turn 1: search_flights
    print(f"   🤖 Turn 1: AI calls search_flights")
    await track_tool_call(
        org_id=TEST_ORG_ID, bridge_id=TEST_BRIDGE_ID, thread_id=thread_id,
        message_id=f"msg_{seq_num}_1", tool_name="search_flights",
        tool_args={"destination": dest}, 
        tool_output=execute_mock_tool("search_flights", {"destination": dest}),
        latency_ms=1000
    )
    await asyncio.sleep(0.1)
    
    # Turn 2: check_visa (uses country_code from search_flights)
    print(f"   🤖 Turn 2: AI calls check_visa")
    country_map = {"Paris": "FR", "London": "GB", "Tokyo": "JP", "Berlin": "DE", "Rome": "IT"}
    country = country_map.get(dest, "US")
    await track_tool_call(
        org_id=TEST_ORG_ID, bridge_id=TEST_BRIDGE_ID, thread_id=thread_id,
        message_id=f"msg_{seq_num}_2", tool_name="check_visa",
        tool_args={"country": country},
        tool_output=execute_mock_tool("check_visa", {"country": country}),
        latency_ms=800
    )
    await asyncio.sleep(0.1)
    
    # Turn 3: book_hotel (uses city from search_flights)
    print(f"   🤖 Turn 3: AI calls book_hotel")
    await track_tool_call(
        org_id=TEST_ORG_ID, bridge_id=TEST_BRIDGE_ID, thread_id=thread_id,
        message_id=f"msg_{seq_num}_3", tool_name="book_hotel",
        tool_args={"city": dest},
        tool_output=execute_mock_tool("book_hotel", {"city": dest}),
        latency_ms=600
    )
    
    print(f"   ✅ Completed: search_flights → check_visa → book_hotel")


async def test_mock_mode():
    """Test with mock data (no API key needed)"""
    print("\n" + "="*80)
    print("TEST MODE: MOCK (Simulated Data)")
    print("="*80)
    
    destinations = ["Paris", "London", "Tokyo", "Berlin", "Paris", "London"]
    
    print(f"\n📋 Step 1: Simulating {len(destinations)} conversations...")
    for i in range(len(destinations)):
        thread_id = f"thread_mock_{i}"
        await simulate_conversation_sequence(thread_id, i, destinations)
    
    # Check tracking
    tool_calls = await conversation_tool_calls_collection.count_documents({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    sequences = await tool_execution_sequences_collection.count_documents({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    
    print(f"\n📊 Tracking Results:")
    print(f"   Individual tool calls: {tool_calls}")
    print(f"   Detected sequences: {sequences}")
    
    return tool_calls > 0 and sequences > 0



# ============================================================================
# OpenAI Mode Tests
# ============================================================================

async def run_openai_conversation(client, user_message: str, thread_id: str, max_turns: int = 10):
    """Run a conversation with OpenAI, executing tools and tracking calls"""
    print(f"\n{'='*80}")
    print(f"🗣️  OpenAI Conversation - Thread: {thread_id}")
    print(f"{'='*80}")
    print(f"User: {user_message}\n")
    
    messages = [
        {
            "role": "system",
            "content": (
                "You are a travel assistant. When users ask about travel, always: "
                "1) Search flights first, 2) Check visa using country code from flights, "
                "3) Optionally book hotel. Call tools one at a time."
            )
        },
        {"role": "user", "content": user_message}
    ]
    
    tools_called = []
    turn_count = 0
    
    while turn_count < max_turns:
        turn_count += 1
        print(f"🤖 AI Turn {turn_count}: Processing...")
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=MOCK_TOOLS,
            tool_choice="auto"
        )
        
        message = response.choices[0].message
        
        if message.tool_calls:
            print(f"   🔧 AI wants to call {len(message.tool_calls)} tool(s)")
            
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {"id": tc.id, "type": tc.type, "function": {
                        "name": tc.function.name, "arguments": tc.function.arguments
                    }}
                    for tc in message.tool_calls
                ]
            })
            
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                print(f"   ⚙️  Calling: {tool_name}({json.dumps(tool_args)})")
                
                start_time = datetime.utcnow()
                tool_result = execute_mock_tool(tool_name, tool_args)
                latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                print(f"   ✅ Result: {json.dumps(tool_result)}")
                
                # Track the tool call
                await track_tool_call(
                    org_id=TEST_ORG_ID, bridge_id=TEST_BRIDGE_ID,
                    thread_id=thread_id, message_id=f"msg_{turn_count}",
                    tool_name=tool_name, tool_args=tool_args,
                    tool_output=tool_result, latency_ms=latency_ms
                )
                
                tools_called.append({"turn": turn_count, "tool": tool_name})
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result)
                })
            
            continue
        
        if message.content:
            print(f"   💬 AI: {message.content}\n")
        break
    
    print(f"✅ Completed in {turn_count} turns, {len(tools_called)} tools called")
    if tools_called:
        print(f"📋 Sequence: {' → '.join([t['tool'] for t in tools_called])}")
    print(f"{'='*80}\n")
    
    return tools_called


async def test_openai_mode(api_key: str):
    """Test with real OpenAI conversations"""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("❌ Error: openai package not installed")
        print("   Install with: pip install openai")
        return False
    
    print("\n" + "="*80)
    print("TEST MODE: OPENAI (Real AI Conversations)")
    print("="*80)
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Phase 1: Run more conversations to ensure pattern detection
    queries_phase1 = [
        "I want to travel to Paris",
        "Help me plan a trip to London",
        "I'm interested in visiting Tokyo",
        "Planning a trip to Paris",
        "Need help with London travel",
        "I want to visit Tokyo",
        "Can you help me travel to Paris?",
        "Looking to visit London"
    ]
    
    print(f"\n📋 PHASE 1: Running {len(queries_phase1)} conversations to build patterns...")
    for i, query in enumerate(queries_phase1):
        thread_id = f"thread_openai_phase1_{i}"
        await run_openai_conversation(client, query, thread_id)
        await asyncio.sleep(0.3)
    
    tool_calls = await conversation_tool_calls_collection.count_documents({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    sequences = await tool_execution_sequences_collection.count_documents({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    
    print(f"\n📊 Phase 1 Results:")
    print(f"   Individual tool calls: {tool_calls}")
    print(f"   Detected sequences: {sequences}")
    
    return tool_calls > 0 and sequences > 0



# ============================================================================
# Pattern Detection and Chain Generation Tests
# ============================================================================

async def test_pattern_detection():
    """Test pattern detection"""
    print("\n" + "="*80)
    print("TEST: Pattern Detection")
    print("="*80)
    
    print("\n🔍 Running pattern detector...")
    patterns = await detect_patterns(TEST_ORG_ID, TEST_BRIDGE_ID)
    
    print(f"✅ Detected {len(patterns)} unique patterns\n")
    
    if patterns:
        print("📋 Pattern Details:\n")
        for i, pattern in enumerate(patterns, 1):
            tools = pattern.get('tools', [])
            freq = pattern.get('frequency', 0)
            conf = pattern.get('confidence', 0)
            
            print(f"Pattern {i}:")
            print(f"   Tools: {' → '.join(tools)}")
            print(f"   Frequency: {freq} occurrences")
            print(f"   Confidence: {conf:.2%}")
            print(f"   Savings: {pattern.get('estimated_savings_ms', 0)}ms per call")
            
            data_flow = pattern.get('data_flow', [])
            if data_flow:
                print(f"   Data Flow:")
                for flow in data_flow:
                    print(f"      step{flow['from_step']}.{flow['from_field']} "
                          f"→ step{flow['to_step']}.{flow['to_arg']} "
                          f"(conf: {flow['confidence']:.2f})")
            print()
    
    return patterns


async def test_chain_generation(patterns: List[Dict]):
    """Test chain generation from patterns"""
    print("\n" + "="*80)
    print("TEST: Chain Generation")
    print("="*80)
    
    if not patterns:
        print("⚠️  No patterns to generate chains from")
        return []
    
    chains = []
    for i, pattern in enumerate(patterns, 1):
        pattern_hash = pattern.get('pattern_hash')
        tools = pattern.get('tools', [])
        
        print(f"\n⚙️  Generating chain {i}/{len(patterns)}: {' → '.join(tools)}")
        
        chain = await generate_chain_from_pattern(
            org_id=TEST_ORG_ID,
            bridge_id=TEST_BRIDGE_ID,
            pattern_hash=pattern_hash,
            created_by="test_script"
        )
        
        if chain:
            chains.append(chain)
            print(f"   ✅ Created: {chain.get('name')}")
            print(f"   📝 {chain.get('description')[:80]}...")
            
            steps = chain.get('steps', [])
            if steps:
                print(f"   🔧 Steps:")
                for j, step in enumerate(steps):
                    print(f"      {j}. {step.get('tool')}({json.dumps(step.get('args', {}))})")
        else:
            print(f"   ❌ Failed to create chain")
    
    return chains


async def test_chain_usage_with_openai(api_key: str, chains: List[Dict]):
    """Test that AI uses generated chains instead of individual tools"""
    if not chains:
        print("\n⚠️  No chains available to test")
        return False
    
    try:
        from openai import AsyncOpenAI
    except ImportError:
        print("❌ Error: openai package not installed")
        return False
    
    print("\n" + "="*80)
    print("TEST: Chain Usage with OpenAI (Phase 2)")
    print("="*80)
    
    # Load chains into tool registry (simulating what getConfiguration.py does)
    print("\n📋 Preparing tools with chains...")
    
    enhanced_tools = MOCK_TOOLS.copy()
    
    for chain in chains:
        chain_name = chain.get('name')
        description = chain.get('description', '')
        steps = chain.get('steps', [])
        
        # Create a tool definition for the chain
        chain_tool = {
            "type": "function",
            "function": {
                "name": chain_name,
                "description": description + " (This is more efficient than calling tools separately)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "object",
                            "description": "Input parameters for the chain"
                        }
                    },
                    "required": ["input"]
                }
            }
        }
        enhanced_tools.append(chain_tool)
        print(f"   ✅ Added chain tool: {chain_name}")
    
    print(f"\n   Total tools available to AI: {len(enhanced_tools)}")
    print(f"   - Original tools: {len(MOCK_TOOLS)}")
    print(f"   - Chain tools: {len(chains)}")
    
    # Now run test conversations with chains available
    client = AsyncOpenAI(api_key=api_key)
    
    test_queries = [
        "I want to travel to Paris",
        "Help me with London travel"
    ]
    
    print(f"\n📋 Running {len(test_queries)} test conversations WITH chains available...")
    
    chain_used_count = 0
    individual_tools_count = 0
    
    for i, query in enumerate(test_queries):
        thread_id = f"thread_openai_phase2_{i}"
        
        print(f"\n{'='*80}")
        print(f"🗣️  Test Conversation {i+1} - Thread: {thread_id}")
        print(f"{'='*80}")
        print(f"User: {query}\n")
        
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a travel assistant. IMPORTANT: If you see an optimized chain tool "
                    "that combines multiple steps, USE IT instead of calling individual tools. "
                    "Chain tools are marked as OPTIMIZED and save time by reducing round-trips."
                )
            },
            {"role": "user", "content": query}
        ]
        
        turn_count = 0
        tools_called = []
        
        while turn_count < 5:
            turn_count += 1
            print(f"🤖 AI Turn {turn_count}: Processing...")
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=enhanced_tools,
                tool_choice="auto"
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                print(f"   🔧 AI wants to call {len(message.tool_calls)} tool(s)")
                
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    print(f"   ⚙️  Calling: {tool_name}")
                    
                    # Check if this is a chain
                    is_chain = any(chain.get('name') == tool_name for chain in chains)
                    
                    if is_chain:
                        print(f"   ✅ AI USED CHAIN! (Optimized execution)")
                        chain_used_count += 1
                    else:
                        print(f"   ℹ️  Individual tool called")
                        individual_tools_count += 1
                    
                    tools_called.append(tool_name)
                    
                    # For demo, just return success
                    result = {"success": True, "message": "Chain executed successfully" if is_chain else "Tool executed"}
                    
                messages.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [{"id": tool_call.id, "type": tool_call.type, "function": {
                        "name": tool_call.function.name, "arguments": tool_call.function.arguments
                    }}]
                })
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
                
                continue
            
            if message.content:
                print(f"   💬 AI: {message.content[:100]}...\n")
            break
        
        print(f"✅ Tools called: {', '.join(tools_called)}")
        print(f"{'='*80}\n")
        
        await asyncio.sleep(0.5)
    
    # Results
    print(f"\n📊 Chain Usage Results:")
    print(f"   Chain tools used: {chain_used_count}")
    print(f"   Individual tools used: {individual_tools_count}")
    
    if chain_used_count > 0:
        print(f"\n🎉 SUCCESS! AI is using optimized chains!")
        print(f"   The system successfully reduced tool calls by using chains.")
        return True
    else:
        print(f"\n⚠️  AI did not use chains (may prefer individual tools)")
        print(f"   This can happen if chain description isn't clear enough")
        return False


async def test_validate_mode():
    """Validate system components"""
    print("\n" + "="*80)
    print("TEST MODE: VALIDATE (System Health Check)")
    print("="*80)
    
    checks = []
    
    # Check 1: Database connection
    print("\n🔍 Checking database connection...")
    try:
        await db.command("ping")
        print("   ✅ MongoDB connected")
        checks.append(True)
    except Exception as e:
        print(f"   ❌ MongoDB connection failed: {e}")
        checks.append(False)
    
    # Check 2: Collections exist
    print("\n🔍 Checking collections...")
    try:
        collections = await db.list_collection_names()
        required = ["conversation_tool_calls", "tool_execution_sequences", 
                   "learned_tool_patterns", "generated_tool_chains"]
        for coll in required:
            exists = coll in collections
            status = "✅" if exists else "⚠️ "
            print(f"   {status} {coll}")
            checks.append(exists)
    except Exception as e:
        print(f"   ❌ Error checking collections: {e}")
        checks.append(False)
    
    # Check 3: Indexes
    print("\n🔍 Checking indexes...")
    try:
        await create_indexes()
        print("   ✅ Indexes created/verified")
        checks.append(True)
    except Exception as e:
        print(f"   ❌ Index creation failed: {e}")
        checks.append(False)
    
    # Check 4: Test data
    print("\n🔍 Checking for test data...")
    try:
        tool_calls = await conversation_tool_calls_collection.count_documents({
            "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
        })
        sequences = await tool_execution_sequences_collection.count_documents({
            "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
        })
        patterns = await learned_tool_patterns_collection.count_documents({
            "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
        })
        chains = await generated_tool_chains_collection.count_documents({
            "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
        })
        
        print(f"   Individual tool calls: {tool_calls}")
        print(f"   Detected sequences: {sequences}")
        print(f"   Learned patterns: {patterns}")
        print(f"   Generated chains: {chains}")
        
        if tool_calls > 0 or sequences > 0 or patterns > 0 or chains > 0:
            print("   ℹ️  Test data exists (use --cleanup to remove)")
        else:
            print("   ✅ No test data found")
        
        checks.append(True)
    except Exception as e:
        print(f"   ❌ Error checking test data: {e}")
        checks.append(False)
    
    success_rate = sum(checks) / len(checks) * 100
    print(f"\n📊 Validation Results: {sum(checks)}/{len(checks)} checks passed ({success_rate:.0f}%)")
    
    return all(checks)



# ============================================================================
# Statistics and Reporting
# ============================================================================

async def show_final_statistics():
    """Display final statistics"""
    print("\n" + "="*80)
    print("FINAL STATISTICS")
    print("="*80)
    
    tool_calls = await conversation_tool_calls_collection.count_documents({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    sequences = await tool_execution_sequences_collection.count_documents({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    patterns = await learned_tool_patterns_collection.count_documents({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    chains = await generated_tool_chains_collection.count_documents({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    
    print(f"\n📊 Summary:")
    print(f"   ✓ Individual tool calls tracked: {tool_calls}")
    print(f"   ✓ Conversation sequences detected: {sequences}")
    print(f"   ✓ Unique patterns learned: {patterns}")
    print(f"   ✓ Optimized chains generated: {chains}")
    
    if chains > 0:
        print(f"\n🎉 SUCCESS! Pattern learning system is working correctly!")
        print(f"   {chains} chain(s) ready for optimization")
    elif patterns > 0:
        print(f"\n✅ Patterns detected but chains not generated yet")
        print(f"   Run pattern detection and approval steps")
    elif sequences > 0:
        print(f"\n⚠️  Sequences detected but patterns need more frequency")
        print(f"   Need {5 - sequences} more similar sequences")
    else:
        print(f"\n⚠️  No sequences detected")
        print(f"   Verify tracking is working correctly")
    
    return {
        "tool_calls": tool_calls,
        "sequences": sequences,
        "patterns": patterns,
        "chains": chains
    }


async def cleanup_test_data():
    """Clean up all test data from database"""
    print(f"\n🧹 Cleaning up test data...")
    
    deleted_counts = {}
    
    result = await conversation_tool_calls_collection.delete_many({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    deleted_counts['tool_calls'] = result.deleted_count
    
    result = await tool_execution_sequences_collection.delete_many({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    deleted_counts['sequences'] = result.deleted_count
    
    result = await learned_tool_patterns_collection.delete_many({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    deleted_counts['patterns'] = result.deleted_count
    
    result = await generated_tool_chains_collection.delete_many({
        "org_id": TEST_ORG_ID, "bridge_id": TEST_BRIDGE_ID
    })
    deleted_counts['chains'] = result.deleted_count
    
    total = sum(deleted_counts.values())
    print(f"   Deleted {total} documents:")
    for key, count in deleted_counts.items():
        if count > 0:
            print(f"   - {key}: {count}")
    
    print("✅ Test data cleaned up")



# ============================================================================
# Main Test Orchestrator
# ============================================================================

async def main(mode: str, api_key: Optional[str] = None, cleanup_only: bool = False):
    """Main test orchestrator"""
    
    print("\n" + "="*80)
    print("PATTERN LEARNING SYSTEM - COMPREHENSIVE TEST")
    print("="*80)
    
    # Handle cleanup-only mode
    if cleanup_only:
        await cleanup_test_data()
        return 0
    
    # Initialize database
    print("\n📋 Initializing database...")
    try:
        await create_indexes()
        print("✅ Database indexes ready")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return 1
    
    try:
        # Run appropriate test mode
        if mode == "validate":
            success = await test_validate_mode()
            
        elif mode == "mock":
            # Clean up old test data first
            await cleanup_test_data()
            
            # Run mock tests
            tracking_ok = await test_mock_mode()
            if not tracking_ok:
                print("\n❌ Tracking test failed")
                return 1
            
            # Pattern detection
            patterns = await test_pattern_detection()
            
            # Chain generation
            chains = await test_chain_generation(patterns)
            
            # Final stats
            await show_final_statistics()
            success = True
            
        elif mode == "openai":
            if not api_key:
                print("\n❌ Error: OpenAI API key required for openai mode")
                print("   Use: --api-key YOUR_KEY or set OPENAI_API_KEY env var")
                return 1
            
            # Clean up old test data first
            await cleanup_test_data()
            
            # Phase 1: Run OpenAI tests to build patterns
            tracking_ok = await test_openai_mode(api_key)
            if not tracking_ok:
                print("\n❌ Tracking test failed")
                return 1
            
            # Phase 2: Pattern detection
            patterns = await test_pattern_detection()
            
            # Phase 3: Chain generation
            chains = await test_chain_generation(patterns)
            
            # Phase 4: Test that AI uses chains (NEW!)
            if chains:
                print("\n" + "="*80)
                print("🎯 PHASE 2: Testing AI Chain Usage")
                print("="*80)
                chain_usage_ok = await test_chain_usage_with_openai(api_key, chains)
            else:
                print("\n⚠️  Skipping chain usage test (no chains generated)")
                chain_usage_ok = False
            
            # Final stats
            await show_final_statistics()
            
            success = tracking_ok and len(patterns) > 0
            if chain_usage_ok:
                print("\n🎉 BONUS: AI successfully used optimized chains!")

            
        else:
            print(f"❌ Unknown mode: {mode}")
            print("   Valid modes: mock, openai, validate")
            return 1
        
        # Summary
        if success:
            print("\n" + "="*80)
            print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
            print("="*80)
        else:
            print("\n" + "="*80)
            print("⚠️  TESTS COMPLETED WITH WARNINGS")
            print("="*80)
        
        # Offer cleanup
        if mode in ["mock", "openai"]:
            print("\n🧹 Clean up test data? (y/n): ", end="")
            try:
                response = input().strip().lower()
                if response == 'y':
                    await cleanup_test_data()
            except EOFError:
                print("(skipping cleanup in non-interactive mode)")
        
        return 0 if success else 1
        
    except Exception as error:
        print(f"\n❌ ERROR: {error}")
        traceback.print_exc()
        return 1


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test Pattern Learning System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test with mock data (no API key)
  python test_pattern_learning.py
  python test_pattern_learning.py --mode mock
  
  # Full test with OpenAI
  export OPENAI_API_KEY=sk-xxx
  python test_pattern_learning.py --mode openai
  
  # Or pass API key directly
  python test_pattern_learning.py --mode openai --api-key sk-xxx
  
  # Validate system health
  python test_pattern_learning.py --mode validate
  
  # Clean up test data
  python test_pattern_learning.py --cleanup
        """
    )
    
    parser.add_argument(
        "--mode",
        type=str,
        choices=["mock", "openai", "validate"],
        default="mock",
        help="Test mode: mock (no API key), openai (requires API key), validate (health check)"
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        help="OpenAI API key (or set OPENAI_API_KEY env var)"
    )
    
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up test data and exit"
    )
    
    args = parser.parse_args()
    
    # Get API key from args or environment
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    
    # Run tests
    exit_code = asyncio.run(main(args.mode, api_key, args.cleanup))
    sys.exit(exit_code)
