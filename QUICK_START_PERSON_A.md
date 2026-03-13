# 🚀 QUICK START GUIDE - Person A

## What You Have Now

I've prepared your complete Week 1 backend setup:

### ✅ Files Created

```
educational_chatbot/
├── backend/
│   ├── __init__.py              ← Makes backend a Python package
│   ├── llm_client.py            ← Handles OpenAI/Ollama calls
│   ├── conversation_manager.py  ← Main brain of the system
│   ├── prompts.py               ← All prompt templates
│   ├── test_api.py              ← Basic API test
│   └── manual_test.py           ← Interactive conversation test
├── .env.example                 ← Template for API keys
├── .gitignore                   ← Protects sensitive files
├── requirements.txt             ← Python dependencies
└── README_PERSON_A.md           ← Full documentation
```

---

## 🏃 Getting Started (15 minutes)

### Step 1: Set Up Environment (5 min)

```bash
# Navigate to project folder
cd educational_chatbot

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Mac/Linux
# OR on Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure API Key (2 min)

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your OpenAI API key
# Get it from: https://platform.openai.com/api-keys
```

Your `.env` should look like:
```
OPENAI_API_KEY=sk-proj-YOUR_ACTUAL_KEY_HERE
MODEL_NAME=gpt-4o-mini
```

### Step 3: Test Everything (8 min)

```bash
# Test 1: Basic API connection
python backend/test_api.py

# Test 2: Interactive conversation
python backend/manual_test.py
```

---

## 💬 How to Use the Interactive Test

When you run `python backend/manual_test.py`, you'll see:

```
🧑 STRUGGLING STUDENT:
   Hi! I'm trying to understand fraction division but I'm really confused...

👨‍🏫 YOU: _
```

**What you can do:**
- Type an explanation → student responds
- Type `mentor` → get coaching advice
- Type `summary` → see conversation stats
- Type `quit` → exit

**Example session:**
```
👨‍🏫 YOU: Let me try to explain with pizza...
🧑 STRUGGLING STUDENT: Oh, pizza! I like that idea! But how does that help with flipping?

👨‍🏫 YOU: mentor
🎓 MENTOR: Good use of a concrete example! Now connect the pizza to the division...

👨‍🏫 YOU: If you have half a pizza and each person gets a quarter, how many people...
🧑 STRUGGLING STUDENT: Oh! So it's 2 people! Is that why the answer is 2?
```

---

## 📝 Week 1 Tasks Checklist

### Day 1-2: Setup & Basic Testing
- [ ] Install Python environment
- [ ] Add API key to .env
- [ ] Run `test_api.py` successfully
- [ ] Run `manual_test.py` and have one conversation
- [ ] Understand how `llm_client.py` works

### Day 3-4: Struggling Student Agent
- [ ] Test the struggling student prompts
- [ ] Try different explanations and see how student responds
- [ ] Adjust prompts in `prompts.py` if needed
- [ ] Document what makes the student understand vs get confused

### Day 5-6: Mentor Agent
- [ ] Use the `mentor` command multiple times
- [ ] Test if mentor gives helpful advice
- [ ] Refine mentor prompts if needed
- [ ] Share your progress with Person B (they need your code!)

---

## 🔧 Common Issues & Solutions

### Issue: "OPENAI_API_KEY not found"
**Solution:** Make sure `.env` file exists and has the key

### Issue: "Rate limit exceeded"
**Solution:** You hit OpenAI's free tier limit. Wait a bit or add payment method.

### Issue: "Module not found"
**Solution:** Make sure you're in the `educational_chatbot` folder and venv is activated

### Issue: Student responses are inconsistent
**Solution:** Lower the temperature in `llm_client.py` (try 0.5 instead of 0.7)

### Issue: Too expensive
**Solution:** Use Ollama instead (free, local). See README_PERSON_A.md

---

## 💡 Tips for Success

### 1. Test Early, Test Often
Don't wait until Week 2. Run `manual_test.py` every day to see progress.

### 2. Iterate on Prompts
The prompts in `prompts.py` are a starting point. Adjust them based on what you see!

**Look for:**
- Is the student too easy? Make them more confused.
- Is the student too hard? Reduce the misconceptions.
- Is the mentor too directive? Make them more Socratic.

### 3. Keep It Simple
Don't over-engineer. The current code does everything you need for Week 1-2.

### 4. Document Your Findings
Keep notes on:
- Which explanations work well
- Which prompts need improvement
- Any edge cases you find

---

## 🤝 Coordination with Team

### What Person B Needs from You
By end of Week 1, share:
1. The `backend/` folder
2. Your `.env.example` (NOT .env!)
3. Instructions on how to run it

They'll build the UI on top of your `ConversationManager` class.

### What Person C Needs from You
Share examples of:
- Good vs bad explanations (for rubric testing)
- Typical student responses
- Mentor feedback samples

---

## 📚 Understanding the Code

### The Flow

1. **ConversationManager** is the main class
   - Manages two conversation streams
   - Keeps history separate

2. **LLMClient** is the API wrapper
   - Works with both OpenAI and Ollama
   - Hides complexity from other code

3. **Prompts** are all in one place
   - Easy to edit and experiment
   - Helper functions format them correctly

### Key Methods

```python
manager = ConversationManager()
initial = manager.start_conversation()           # Start fresh
response = manager.send_to_student("Hello!")     # Talk to student
advice = manager.consult_mentor("...", "...")    # Get coaching
summary = manager.get_conversation_summary()      # Get stats
```

---

## 🎯 Week 1 Success = This Working

By Friday, you should be able to:
1. ✅ Run the interactive test
2. ✅ Have a multi-turn conversation with the student
3. ✅ Get helpful mentor advice
4. ✅ See consistent character from the student
5. ✅ Share working code with Person B

**That's it! Keep it simple, test often, and iterate.**

---

## 📞 Need Help?

1. Check `README_PERSON_A.md` for detailed docs
2. Ask your team in WhatsApp group
3. Review the code comments - they explain everything
4. Test one piece at a time

**You've got this! 💪**

---

**Next Steps:**
```bash
# Start here:
python backend/test_api.py

# Then try:
python backend/manual_test.py

# Keep testing and iterating!
```
