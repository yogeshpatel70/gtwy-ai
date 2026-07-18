# Conversation-Level Pattern Tracking

## 🎯 The Key Insight

We're not tracking tools called **in the same AI turn** (that's rare).  
We're tracking tools called **across multiple AI turns** in a conversation (this is the problem!).

---

## ❌ Wrong Understanding (Batch-Level)

```
User: "Search flights and check visa"
  ↓
AI Turn 1: Calls Tool1 AND Tool2 together
  ↓
Track: [Tool1, Tool2] as one batch
```

**This is NOT the problem!** If AI calls multiple tools in one turn, there's no round-trip delay.

---

## ✅ Correct Understanding (Conversation-Level)

```
User: "Search flights to Paris and check visa"
  ↓
AI Turn 1: "I need to search flights first"
  → Calls Tool1: search_flights
  ↓
[NEW] Track: Tool1 in thread_123

AI Turn 2: "Now I have country code, check visa"
  → Calls Tool2: check_visa  
  ↓
[NEW] Track: Tool2 in thread_123
[NEW] Analyze: Last 2 tools = [Tool1, Tool2]
[NEW] Pattern Detected! ✅
```

**This IS the problem!** Multiple AI round-trips cause 4+ seconds of delay.

---

## 🔄 How It Works Now

### 1. Individual Tool Tracking

Every time a tool executes:

```python
# In process_data_and_run_tools()
await track_tool_call(
    org_id="org_123",
    bridge_id="bridge_456",
    thread_id="thread_789",  # ← Same thread ties calls together
    message_id="msg_001",
    tool_name="search_flights",
    tool_args={"destination": "Paris"},
    tool_output={"country_code": "FR", "city": "Paris"},
    latency_ms=1000
)
```

Stored in `conversation_tool_calls` collection:

```javascript
{
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "thread_id": "thread_789",  // Links tools in same conversation
  "message_id": "msg_001",
  "timestamp": ISODate("2026-07-17T10:30:00Z"),
  "tool": "search_flights",
  "args": {"destination": "Paris"},
  "output": {"country_code": "FR", "city": "Paris"},
  "latency_ms": 1000
}
```

### 2. Conversation Analysis

After each tool call, analyze the conversation:

```python
async def _analyze_conversation_pattern(org_id, bridge_id, thread_id):
    # Get last 10 tools in this thread
    recent_calls = get_last_10_tools(thread_id)
    
    # Look for sequences: last 2, last 3, last 4, etc.
    for window_size in [2, 3, 4, 5]:
        sequence = recent_calls[-window_size:]
        
        # Check time span (ignore if > 5 minutes apart)
        if time_span > 300_seconds:
            continue
        
        # Create pattern
        pattern = {
            "tools": ["search_flights", "check_visa"],
            "ai_round_trips": 2,  // Tool1 → AI → Tool2
            "source": "conversation"
        }
        
        # Store in tool_execution_sequences
        store_pattern(pattern)
```

---

## 📊 Example Flow

### Conversation Timeline

```
10:30:00 - User: "Search flights to Paris and check visa requirements"
           ↓
10:30:02 - AI Processing (analyzing request)
           ↓
10:30:04 - Tool Call: search_flights(destination="Paris")
           [TRACKED] → conversation_tool_calls
           [ANALYZED] → Only 1 tool so far, no pattern yet
           ↓
10:30:05 - Tool Result: {country_code: "FR", city: "Paris"}
           ↓
10:30:06 - AI Processing (analyzing result, deciding next step)
           ↓
10:30:08 - Tool Call: check_visa(country="FR")
           [TRACKED] → conversation_tool_calls
           [ANALYZED] → Last 2 tools: ["search_flights", "check_visa"]
           [DETECTED] → Pattern found! Time span: 4 seconds ✅
           [STORED] → tool_execution_sequences
           ↓
10:30:09 - Tool Result: {required: false}
           ↓
10:30:10 - AI Processing (formatting response)
           ↓
10:30:12 - Response: "Flights to Paris from $450. No visa required."

Total Time: 12 seconds
AI Calls: 3 (initial, after tool1, after tool2)
Pattern: ["search_flights", "check_visa"] detected
```

### After 5+ Similar Conversations

```
Pattern Database:
{
  "pattern_hash": "abc123...",
  "tools": ["search_flights", "check_visa"],
  "frequency": 15,
  "confidence": 0.95,
  "data_flow": [
    {
      "from": "search_flights.output.country_code",
      "to": "check_visa.args.country"
    }
  ],
  "avg_time_span": 4.2_seconds,
  "avg_ai_round_trips": 2
}
```

---

## 🔍 Sliding Window Detection

```
Conversation Tools: [A, B, C, D, E]

When tool E executes:
├─ Check window of 2: [D, E]
├─ Check window of 3: [C, D, E]
├─ Check window of 4: [B, C, D, E]
└─ Check window of 5: [A, B, C, D, E]

Each window is checked:
1. Time span < 5 minutes? ✓
2. Already recorded? Skip
3. New pattern? Store it! ✓
```

This catches patterns of different lengths:
- 2-tool patterns: `[Tool1, Tool2]`
- 3-tool patterns: `[Tool1, Tool2, Tool3]`
- 4-tool patterns: `[Tool1, Tool2, Tool3, Tool4]`
- etc.

---

## 📈 Why This Matters

### Before (Without Pattern Learning)

```
User asks about Paris travel
  ↓
AI Call 1 (2s): "Search flights"
  ↓
Tool: search_flights (1s)
  ↓
AI Call 2 (2s): "Check visa"
  ↓
Tool: check_visa (0.8s)
  ↓
AI Call 3 (2s): "Format response"
  ↓
Total: 7.8 seconds, 3 AI calls
```

### After (With Pattern Learning & Chain)

```
User asks about London travel
  ↓
AI Call 1 (2s): "Use optimized chain"
  ↓
Chain: search_flights → check_visa (1.8s)
  ↓
AI Call 2 (2s): "Format response"
  ↓
Total: 3.8 seconds, 2 AI calls
Saved: 4 seconds, 1 AI call ✅
```

---

## 🗄️ Database Structure

### collection: `conversation_tool_calls`
Individual tool calls with conversation context

```javascript
{
  "_id": ObjectId("..."),
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "thread_id": "thread_789",  // Conversation identifier
  "message_id": "msg_001",
  "timestamp": ISODate("2026-07-17T10:30:04Z"),
  "tool": "search_flights",
  "args": {"destination": "Paris"},
  "output": {"country_code": "FR", "city": "Paris"},
  "latency_ms": 1000
}
```

### collection: `tool_execution_sequences`
Detected patterns from conversation analysis

```javascript
{
  "_id": ObjectId("..."),
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "thread_id": "thread_789",
  "timestamp": ISODate("2026-07-17T10:30:08Z"),
  "sequence": [
    {
      "tool": "search_flights",
      "args": {"destination": "Paris"},
      "output": {"country_code": "FR", "city": "Paris"},
      "latency_ms": 1000
    },
    {
      "tool": "check_visa",
      "args": {"country": "FR"},
      "output": {"required": false},
      "latency_ms": 800
    }
  ],
  "tool_names": ["search_flights", "check_visa"],
  "pattern_hash": "abc123...",
  "total_ai_calls": 3,  // Initial + per tool + final
  "sequence_length": 2,
  "time_span_seconds": 4,
  "source": "conversation"  // Marks as conversation-level pattern
}
```

---

## 🎯 Key Differences

| Aspect | Batch-Level (Wrong) | Conversation-Level (Correct) |
|--------|-------------------|---------------------------|
| **Tracking Unit** | All tools in one AI turn | Each tool individually |
| **Linking** | By message_id | By thread_id |
| **Pattern Detection** | Immediate (same batch) | Sliding window analysis |
| **Problem Solved** | None (no round-trips in batch) | AI round-trip delays |
| **Time Span** | 0 seconds (simultaneous) | 0-300 seconds (conversation) |

---

## 💡 Example Scenarios

### Scenario 1: Simple 2-Tool Pattern

```
Turn 1: User → AI → search_flights
        [Track: search_flights in thread_789]

Turn 2: AI → check_visa
        [Track: check_visa in thread_789]
        [Analyze: Last 2 = [search_flights, check_visa]]
        [Pattern: ✅ Detected!]
```

### Scenario 2: Complex 3-Tool Pattern

```
Turn 1: User → AI → search_flights
        [Track: search_flights in thread_789]

Turn 2: AI → check_visa
        [Track: check_visa]
        [Analyze: [search_flights, check_visa] ✅]

Turn 3: AI → book_hotel
        [Track: book_hotel]
        [Analyze: [check_visa, book_hotel] ✅]
        [Analyze: [search_flights, check_visa, book_hotel] ✅]
```

### Scenario 3: Time-Based Filtering

```
Turn 1 (10:00): search_flights
Turn 2 (10:01): check_visa
        [Pattern: ✅ Time span: 60s < 300s]

Turn 1 (10:00): search_flights  
Turn 2 (10:10): check_visa
        [Pattern: ❌ Time span: 600s > 300s]
        [Reason: Too much time between calls]
```

---

## 🚀 Impact

With conversation-level tracking:
- ✅ Detects **actual** AI round-trip patterns
- ✅ Works for sequential tool calls (most common)
- ✅ Handles multi-step workflows
- ✅ Time-aware (ignores old tools)
- ✅ Thread-aware (per conversation)

**Result:** System learns the patterns that actually cause delays and optimizes them! 🎉
