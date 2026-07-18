# Quick Testing Guide - Pattern Learning System

## 🚀 Quick Start (30 seconds)

### Test Without OpenAI (Recommended First)

```bash
python test_simple.py
```

This runs a complete test with mock data. No API key needed!

### Test With OpenAI (Real AI Conversations)

```bash
# Set your API key
export OPENAI_API_KEY=sk-your-key-here

# Run full test
python test_pattern_learning.py

# Or pass key directly
python test_pattern_learning.py --api-key sk-your-key-here
```

---

## 📋 What Gets Tested

Both tests verify:

✅ **Conversation-level tracking** - Tools tracked across AI turns  
✅ **Pattern detection** - Finds repeated sequences  
✅ **Data flow inference** - Auto-maps outputs to inputs  
✅ **Chain generation** - Creates optimized tools  
✅ **Database operations** - All collections working  

---

## 🎯 Expected Results

### Simple Test Output

```
✓ Individual tool calls tracked: 18
✓ Conversation sequences detected: 36
✓ Unique patterns learned: 3
✓ Optimized chains generated: 3

🎉 SUCCESS! Pattern learning system is working!
```

### OpenAI Test Output

```
✅ Conversation completed in 3 turns
🔧 Total tools called: 2
📋 Tool sequence: search_flights → check_visa

✅ Detected 1 unique patterns
✅ Created: search_flights_check_visa_chain

✅ ALL TESTS COMPLETED SUCCESSFULLY!
```

---

## 🐛 Troubleshooting

### "No module named 'openai'"
```bash
pip install openai motor pymongo
```

### "Connection refused" (MongoDB)
```bash
# Check MongoDB is running
# Verify MONGODB_CONNECTION_URI in config.py
```

### No patterns detected
```bash
# Lower thresholds in src/services/pattern_learning/pattern_detector.py
MIN_PATTERN_OCCURRENCES = 3  # Default: 5
```

---

## 📚 Full Documentation

- **Complete Testing Guide**: `TESTING_GUIDE.md`
- **System Overview**: `PATTERN_LEARNING_FLOW_DIAGRAM.md`
- **Quick Start**: `QUICK_START_PATTERN_LEARNING.md`
- **Implementation Details**: `PATTERN_LEARNING_IMPLEMENTATION.md`

---

## ✅ Success Indicators

After running tests, verify:

```javascript
// MongoDB
db.conversation_tool_calls.count()        // > 0
db.tool_execution_sequences.count()       // > 0
db.learned_tool_patterns.count()          // > 0
db.generated_tool_chains.count()          // > 0
```

---

## 🎉 That's It!

If both tests pass, your pattern learning system is **fully functional** and ready for production!

**Next:** Deploy to production and watch it optimize automatically. 🚀
