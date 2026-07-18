# Pattern Learning & Tool Chain Optimization

## Overview

The Pattern Learning system automatically detects frequently used tool sequences and creates optimized chains to reduce AI round-trips and latency.

## Problem

**Current Flow (Inefficient):**
```
User Query → AI → Call Tool1 → AI → Call Tool2 → AI → Call Tool3 → AI → Response
         (4 AI calls, ~8+ seconds)
```

**Optimized Flow:**
```
User Query → AI → Call execute_sequence(Tool1→Tool2→Tool3) → AI → Response
         (2 AI calls, ~4 seconds - 50% faster!)
```

## How It Works

### 1. **Automatic Tracking**
Every time tools are executed, the system tracks:
- Which tools were called
- In what order
- What data flowed between them
- Total latency

### 2. **Pattern Detection**
Background job analyzes sequences to find patterns that:
- Occur frequently (5+ times by default)
- Show consistency (tools called in same order)
- Have clear data flow between steps

### 3. **Chain Generation**
When approved, the system:
- Creates an optimized chain tool
- Infers variable mappings automatically
- Adds it to the bridge's tool registry
- AI automatically prefers chains over individual tools

### 4. **Automatic Optimization**
Once a chain exists, the AI:
- Sees it in the tool list with priority description
- Calls the chain instead of separate tools
- Reduces latency and API costs

## Architecture

```
┌─────────────────────────────────────────────┐
│  Tool Execution (utils.py)                  │
│  - Tracks sequences in background           │
│  - Stores in tool_execution_sequences       │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Pattern Detection (background_detector.py) │
│  - Runs every 6 hours                       │
│  - Analyzes sequences                       │
│  - Identifies patterns                      │
│  - Stores in learned_tool_patterns          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  User Approval (API endpoints)              │
│  - GET /api/patterns/pending/:bridge_id     │
│  - POST /api/patterns/approve               │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Chain Generation (chain_generator.py)      │
│  - Creates chain definition                 │
│  - Infers variable mappings                 │
│  - Stores in generated_tool_chains          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Tool Registry (getConfiguration.py)        │
│  - Loads active chains                      │
│  - Adds to bridge tools                     │
│  - AI sees and uses chains                  │
└─────────────────────────────────────────────┘
```

## Database Collections

### `tool_execution_sequences`
Tracks individual tool execution sequences:
```javascript
{
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "thread_id": "thread_789",
  "timestamp": ISODate("2026-07-17T10:30:00Z"),
  "sequence": [
    {
      "tool": "search_flights",
      "args": {"destination": "Paris"},
      "output": {"country_code": "FR", "city": "Paris"}
    },
    {
      "tool": "check_visa",
      "args": {"country": "FR"},
      "output": {"required": false}
    }
  ],
  "pattern_hash": "md5_hash",
  "total_ai_calls": 3,
  "total_latency_ms": 5200
}
```

### `learned_tool_patterns`
Stores detected patterns:
```javascript
{
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "pattern_hash": "md5_hash",
  "tools": ["search_flights", "check_visa", "book_hotel"],
  "frequency": 15,
  "confidence": 0.95,
  "data_flow": [
    {
      "from_step": 0,
      "from_field": "country_code",
      "to_step": 1,
      "to_arg": "country"
    }
  ],
  "status": "pending_approval",
  "estimated_savings_ms": 4000
}
```

### `generated_tool_chains`
Stores active chains:
```javascript
{
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "name": "search_flights_visa_hotel_chain",
  "description": "⚡ OPTIMIZED: search_flights → check_visa → book_hotel...",
  "steps": [
    {
      "tool": "search_flights",
      "args": {"destination": "{{input.destination}}"}
    },
    {
      "tool": "check_visa",
      "args": {"country": "{{step0.output.country_code}}"}
    }
  ],
  "is_active": true,
  "usage_count": 42
}
```

## API Endpoints

### Analyze Patterns
```bash
GET /api/patterns/analyze/:org_id/:bridge_id
```

Returns insights about tool usage and recommendations.

### Detect Patterns
```bash
POST /api/patterns/detect/:org_id/:bridge_id
```

Manually trigger pattern detection for a bridge.

### Get Pending Patterns
```bash
GET /api/patterns/pending/:org_id/:bridge_id
```

Returns patterns awaiting approval.

### Approve Pattern
```bash
POST /api/patterns/approve
{
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "pattern_hash": "abc123..."
}
```

Approves a pattern and generates a chain.

### Dismiss Pattern
```bash
POST /api/patterns/dismiss
{
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "pattern_hash": "abc123..."
}
```

Dismisses a pattern suggestion.

### Get Active Chains
```bash
GET /api/patterns/chains/:org_id/:bridge_id
```

Returns all active chains for a bridge.

### Deactivate Chain
```bash
POST /api/patterns/chains/deactivate
{
  "org_id": "org_123",
  "bridge_id": "bridge_456",
  "chain_name": "search_flights_visa_hotel_chain"
}
```

Deactivates a chain.

## Execute Sequence Tool

The AI can also manually chain tools using `execute_sequence`:

```json
{
  "tool": "execute_sequence",
  "args": {
    "steps": [
      {
        "tool": "search_flights",
        "args": {"destination": "Paris", "dates": "2026-08-01"}
      },
      {
        "tool": "check_visa",
        "args": {"country": "{{step0.output.country_code}}"}
      },
      {
        "tool": "book_hotel",
        "args": {
          "city": "{{step0.output.city}}",
          "dates": "{{step0.output.dates}}"
        }
      }
    ]
  }
}
```

### Variable Resolution

Supports `{{stepN.output.field}}` syntax:
- `{{step0.output.country_code}}` - Direct field access
- `{{step0.output.data.nested.field}}` - Nested field access
- `{{input.field}}` - User input passthrough

## Configuration

### Pattern Detection Settings
Edit `src/services/pattern_learning/pattern_detector.py`:

```python
MIN_PATTERN_OCCURRENCES = 5  # Minimum frequency
MIN_CONFIDENCE = 0.7         # Minimum confidence score
ANALYSIS_WINDOW_DAYS = 7     # Days to analyze
```

### Background Job Settings
Edit `src/services/pattern_learning/background_detector.py`:

```python
DETECTION_INTERVAL_HOURS = 6       # How often to run
MIN_SEQUENCES_FOR_DETECTION = 10   # Min activity threshold
```

## Running the Background Detector

### Option 1: Continuous Loop (Development)
```bash
python -m src.services.pattern_learning.background_detector
```

### Option 2: Cron Job (Production)
```bash
# Run every 6 hours
0 */6 * * * cd /path/to/gtwy-ai && python -m src.services.pattern_learning.background_detector
```

### Option 3: Celery Task (Recommended)
```python
from celery import Celery
from src.services.pattern_learning.background_detector import run_pattern_detection_job

@celery.task
def detect_patterns_task():
    asyncio.run(run_pattern_detection_job())
```

## Database Indexes

Create indexes for optimal performance:

```python
from models.tool_pattern_models import create_indexes
await create_indexes()
```

Or manually:
```javascript
// MongoDB shell
use gtwy_ai_db;

// tool_execution_sequences indexes
db.tool_execution_sequences.createIndex({"org_id": 1, "bridge_id": 1, "timestamp": -1});
db.tool_execution_sequences.createIndex({"thread_id": 1});
db.tool_execution_sequences.createIndex({"pattern_hash": 1});

// learned_tool_patterns indexes
db.learned_tool_patterns.createIndex({"org_id": 1, "bridge_id": 1, "pattern_hash": 1}, {unique: true});
db.learned_tool_patterns.createIndex({"status": 1});
db.learned_tool_patterns.createIndex({"frequency": -1});

// generated_tool_chains indexes
db.generated_tool_chains.createIndex({"org_id": 1, "bridge_id": 1, "name": 1}, {unique: true});
db.generated_tool_chains.createIndex({"is_active": 1});
```

## Monitoring

### Check Pattern Detection Status
```bash
curl http://localhost:8000/api/patterns/analyze/org_123/bridge_456
```

### View Statistics
```python
from src.services.pattern_learning.pattern_tracker import get_sequence_statistics

stats = await get_sequence_statistics("org_123", "bridge_456")
print(f"Total sequences: {stats['total_sequences']}")
print(f"Unique patterns: {stats['unique_patterns']}")
```

## Benefits

✅ **50% Latency Reduction** - Eliminates AI round-trips  
✅ **Cost Savings** - Fewer AI API calls  
✅ **Automatic Learning** - System improves over time  
✅ **User Control** - Approve before deployment  
✅ **Transparent** - Clear visibility into optimizations  
✅ **Self-Improving** - Gets smarter with usage  

## Example Flow

### Week 1: Learning
```
Day 1-5: User calls tool1 → tool2 → tool3 (15 times)
System tracks each sequence
```

### Week 2: Detection
```
Background job runs
Detects pattern: tool1 → tool2 → tool3 (frequency: 15, confidence: 0.95)
Status: pending_approval
```

### Week 2: Approval
```
GET /api/patterns/pending/org_123/bridge_456
→ Shows detected pattern

POST /api/patterns/approve
→ Generates chain: tool1_tool2_tool3_chain
→ Chain added to bridge tools
```

### Week 3: Optimization
```
User: "Do the thing"
AI: Sees tool1_tool2_tool3_chain in tools
AI: Calls chain instead of 3 separate tools
Result: Response in 4s instead of 8s ✅
```

## Troubleshooting

### Patterns Not Being Detected
- Check if MIN_PATTERN_OCCURRENCES threshold is too high
- Verify sequences are being tracked in `tool_execution_sequences`
- Run pattern detection manually: `POST /api/patterns/detect/:bridge_id`

### Chains Not Appearing in Tools
- Verify chain is active: `GET /api/patterns/chains/:bridge_id`
- Check `add_learned_chains` is called in getConfiguration.py
- Ensure bridge_id matches exactly

### Variable Resolution Errors
- Check variable syntax: `{{stepN.output.field}}`
- Verify output structure matches expected fields
- Review execution logs for missing fields

## Future Enhancements

- [ ] ML-based pattern prediction
- [ ] Automatic confidence-based approval
- [ ] Chain versioning and A/B testing
- [ ] Cross-bridge pattern sharing
- [ ] Real-time pattern suggestions in UI
- [ ] Performance analytics dashboard
