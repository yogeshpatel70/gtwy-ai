# Pattern Learning - Quick Start Guide

## 🚀 5-Minute Setup

### Step 1: Initialize Database
```bash
python init_pattern_learning.py
```

This creates the necessary MongoDB indexes.

### Step 2: Restart Your Server
```bash
# Your existing start command
python index.py
# or
uvicorn index:app --reload
```

That's it! The system is now active. 🎉

---

## ✅ What's Happening Now

### Automatic Tracking
Every time your AI agent calls multiple tools:
```
User: "Search flights to Paris and check visa requirements"
AI: Calls search_flights → check_visa

✅ Sequence is automatically tracked in the background
```

### Pattern Detection (After ~5+ Similar Sequences)
```bash
# Option 1: Run manually
curl -X POST http://localhost:8000/api/patterns/detect/YOUR_ORG_ID/YOUR_BRIDGE_ID

# Option 2: Run background job (recommended)
python -m src.services.pattern_learning.background_detector
```

### View Detected Patterns
```bash
curl http://localhost:8000/api/patterns/pending/YOUR_ORG_ID/YOUR_BRIDGE_ID
```

Response:
```json
{
  "status": "success",
  "data": {
    "pending_patterns": 1,
    "patterns": [
      {
        "tools": ["search_flights", "check_visa", "book_hotel"],
        "frequency": 15,
        "confidence": 0.95,
        "estimated_savings_ms": 4000
      }
    ]
  }
}
```

### Approve Pattern
```bash
curl -X POST http://localhost:8000/api/patterns/approve \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "YOUR_ORG_ID",
    "bridge_id": "YOUR_BRIDGE_ID",
    "pattern_hash": "PATTERN_HASH_FROM_ABOVE"
  }'
```

### Verify Chain Created
```bash
curl http://localhost:8000/api/patterns/chains/YOUR_ORG_ID/YOUR_BRIDGE_ID
```

### Use Automatically
Next time the user makes a similar request:
```
User: "Find flights to Tokyo and check visa"

AI sees: 
- search_flights (original tool)
- check_visa (original tool)
- search_flights_check_visa_chain ⚡ OPTIMIZED

AI chooses: search_flights_check_visa_chain

Result: 50% faster! 🚀
```

---

## 🔄 Background Detection (Recommended)

### Option 1: Screen/tmux Session
```bash
# Start in background
screen -S pattern_detector
python -m src.services.pattern_learning.background_detector
# Detach: Ctrl+A, D
```

### Option 2: systemd Service
```bash
# Create /etc/systemd/system/pattern-detector.service
[Unit]
Description=GTWY Pattern Detector
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/gtwy-ai
ExecStart=/usr/bin/python3 -m src.services.pattern_learning.background_detector
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pattern-detector
sudo systemctl start pattern-detector
sudo systemctl status pattern-detector
```

### Option 3: Docker Compose
```yaml
services:
  gtwy-api:
    # ... your existing config
  
  pattern-detector:
    build: .
    command: python -m src.services.pattern_learning.background_detector
    environment:
      - MONGODB_CONNECTION_URI=${MONGODB_CONNECTION_URI}
      - MONGODB_DATABASE_NAME=${MONGODB_DATABASE_NAME}
    restart: always
```

---

## 📊 Monitoring

### Check Statistics
```bash
curl http://localhost:8000/api/patterns/analyze/YOUR_ORG_ID/YOUR_BRIDGE_ID
```

Response:
```json
{
  "total_sequences": 127,
  "unique_patterns": 8,
  "recommendations": [
    {
      "tools": ["search_flights", "check_visa"],
      "frequency": 23,
      "confidence": 0.92,
      "recommendation": "Create optimized chain"
    }
  ]
}
```

### Check Active Chains
```bash
curl http://localhost:8000/api/patterns/chains/YOUR_ORG_ID/YOUR_BRIDGE_ID
```

---

## 🧪 Testing

### 1. Trigger Same Sequence Multiple Times
```bash
# Call your agent 5+ times with similar queries that use the same tools
curl -X POST http://localhost:8000/chatbot/YOUR_ENDPOINT \
  -H "Content-Type: application/json" \
  -d '{"message": "Search flights and check visa for Paris"}'

# Repeat with variations:
# "Search flights and check visa for London"
# "Search flights and check visa for Tokyo"
# etc.
```

### 2. Detect Patterns
```bash
curl -X POST http://localhost:8000/api/patterns/detect/YOUR_ORG_ID/YOUR_BRIDGE_ID
```

### 3. Approve Pattern
```bash
# Get pattern hash from pending patterns
curl http://localhost:8000/api/patterns/pending/YOUR_ORG_ID/YOUR_BRIDGE_ID

# Approve it
curl -X POST http://localhost:8000/api/patterns/approve \
  -H "Content-Type: application/json" \
  -d '{"org_id": "YOUR_ORG_ID", "bridge_id": "YOUR_BRIDGE_ID", "pattern_hash": "HASH"}'
```

### 4. Test Optimization
```bash
# Make the same query again
curl -X POST http://localhost:8000/chatbot/YOUR_ENDPOINT \
  -H "Content-Type: application/json" \
  -d '{"message": "Search flights and check visa for Paris"}'

# The chain should be used automatically!
# Check response time - should be ~50% faster
```

---

## 🎯 Manual Tool Chaining

The AI can also manually chain tools:

```json
{
  "tool": "execute_sequence",
  "args": {
    "steps": [
      {
        "tool": "search_flights",
        "args": {
          "destination": "Paris",
          "dates": "2026-08-01"
        }
      },
      {
        "tool": "check_visa",
        "args": {
          "country": "{{step0.output.country_code}}"
        }
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

The AI will learn to use this when it needs to chain operations!

---

## 🔧 Configuration

### Tune Detection Sensitivity

Edit `src/services/pattern_learning/pattern_detector.py`:

```python
MIN_PATTERN_OCCURRENCES = 5  # Default: 5
# Lower = More patterns detected
# Higher = Only very frequent patterns

MIN_CONFIDENCE = 0.7         # Default: 0.7
# Lower = Less strict matching
# Higher = Only very consistent patterns
```

### Adjust Background Job Frequency

Edit `src/services/pattern_learning/background_detector.py`:

```python
DETECTION_INTERVAL_HOURS = 6  # Default: 6 hours
# Lower = More frequent detection
# Higher = Less resource usage
```

---

## 🐛 Troubleshooting

### Problem: No Sequences Being Tracked
**Solution:** Check if your tools are executing. Look in MongoDB:
```javascript
db.tool_execution_sequences.find({bridge_id: "YOUR_BRIDGE_ID"}).limit(5)
```

### Problem: No Patterns Detected
**Solution:** Need more usage. Default requires 5+ identical sequences.

### Problem: Chain Not Used by AI
**Solution:** 
1. Verify chain is active: `GET /api/patterns/chains/:bridge_id`
2. Restart server to reload tool registry
3. Check chain description is clear and prioritized

### Problem: Variable Resolution Errors
**Solution:** Check the data flow in the pattern. The fields must exist in the output.

---

## 📚 Full Documentation

- **Complete Guide:** `docs/PATTERN_LEARNING.md`
- **Implementation Details:** `PATTERN_LEARNING_IMPLEMENTATION.md`

---

## 🎉 You're Done!

The system is now:
- ✅ Tracking tool sequences
- ✅ Detecting patterns
- ✅ Generating chains
- ✅ Optimizing automatically

**Just use your AI agent normally, and it will get faster over time!** 🚀
