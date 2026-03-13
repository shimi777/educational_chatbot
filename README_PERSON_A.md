# Educational Chatbot - Backend Setup Guide (Person A)

## Week 1 Tasks Overview

**Your Mission:** Build the LLM backend that powers the dual-agent system (Struggling Student + Mentor)

### Day 1-2: Environment Setup & Basic API Test
- [x] Set up Python environment
- [x] Install dependencies
- [x] Test OpenAI API connection
- [ ] Create basic conversation function

### Day 3-4: Struggling Student Agent
- [ ] Write Struggling Student prompt template
- [ ] Test conversations with struggling student
- [ ] Handle conversation context

### Day 5-6: Mentor Agent & Orchestration
- [ ] Write Mentor Agent prompt template
- [ ] Build mode-switching logic
- [ ] Manage dual-context conversations

---

## Setup Instructions

### Step 1: Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
# On Mac/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install packages
pip install openai python-dotenv
```

### Step 2: Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create new secret key
3. Copy it (you won't see it again!)
4. Create `.env` file in project root:

```
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxx
```

**Cost Estimate:** Using gpt-4o-mini, ~$0.01-0.02 per conversation for testing

### Step 3: Test Your Setup

Run the test script to verify everything works:

```bash
python backend/test_api.py
```

You should see a response from the API.

---

## Alternative: Ollama Setup (Free, Local)

If you want to avoid API costs or work offline:

### Install Ollama

```bash
# Mac
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows - download from ollama.com
```

### Pull a Model

```bash
# Recommended: Llama 3.1 8B (good quality, runs on most laptops)
ollama pull llama3.1:8b

# Lighter option if needed:
ollama pull llama3.2:3b
```

### Test Ollama

```bash
python backend/test_ollama.py
```

---

## Project Structure

```
educational_chatbot/
├── backend/
│   ├── __init__.py
│   ├── llm_client.py          # Wrapper for OpenAI/Ollama
│   ├── conversation_manager.py # Main logic for dual agents
│   ├── prompts.py              # All prompt templates
│   ├── evaluator.py            # Scoring/feedback logic
│   └── test_api.py             # Quick API test
├── prompts/
│   ├── struggling_student.txt  # Student persona prompt
│   └── mentor_agent.txt        # Mentor persona prompt
├── tests/
│   └── test_conversations.json # Sample dialogues for testing
├── .env                         # API keys (DON'T COMMIT THIS!)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Key Files You'll Create This Week

### 1. `llm_client.py` - Abstraction layer for LLM calls
Handles both OpenAI and Ollama so frontend doesn't care which you use

### 2. `prompts.py` - All your prompt templates
- Struggling student persona
- Mentor agent persona
- System instructions

### 3. `conversation_manager.py` - The brain
- Manages conversation state
- Switches between student/mentor modes
- Tracks history

### 4. `evaluator.py` - Assessment logic
- Analyzes student-teacher explanations
- Scores based on rubric
- Generates feedback

---

## Testing Strategy

### Manual Testing (Week 1)
Use the test scripts to have conversations yourself:
```bash
python backend/manual_test.py
```

### Automated Testing (Week 2)
Test against known scenarios:
```bash
python -m pytest tests/
```

---

## Tips for Success

### Prompt Engineering Tips
1. **Be specific about role** - "You are a 10-year-old student struggling with..."
2. **Define limitations** - What the agent should NOT do
3. **Give examples** - Few-shot prompting helps consistency
4. **Test, iterate, test** - Prompts need refinement

### Managing Costs (OpenAI)
1. Use `gpt-4o-mini` not `gpt-4` ($0.15 vs $30 per million tokens!)
2. Limit `max_tokens` to ~300-500 for testing
3. Track usage on OpenAI dashboard
4. Budget ~$5-10 for entire project

### Common Issues
- **API key not working**: Check .env file location and spelling
- **Rate limits**: Free tier has limits, add small delays between calls
- **Inconsistent responses**: Make temperature lower (0.3-0.5)
- **Context too long**: Summarize old messages, keep recent ones

---

## Week 1 Success Criteria

By end of Week 1, you should have:
- ✅ Working API connection (OpenAI or Ollama)
- ✅ Basic conversation with "struggling student"
- ✅ Prompts that maintain character consistently
- ✅ Simple state management (history tracking)
- ✅ Code ready for Person B to integrate

---

## Next Steps (Week 2)

- Add the Mentor agent
- Build evaluation logic
- Optimize prompts based on testing
- Integrate with frontend

---

## Quick Start Commands

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file with your API key

# Test
python backend/test_api.py

# Run conversation
python backend/manual_test.py
```

---

## Questions?

Common questions and answers:

**Q: OpenAI or Ollama?**
A: OpenAI is easier to start, Ollama is free but needs setup. Start with OpenAI, switch later if needed.

**Q: Which model?**
A: gpt-4o-mini is perfect - cheap and good quality. Don't use gpt-4 for testing!

**Q: How to handle Hebrew?**
A: Both OpenAI and Ollama handle Hebrew well. No special setup needed.

**Q: What if I'm stuck?**
A: Check the test files, ask the team, or simplify - working simple > broken complex!
