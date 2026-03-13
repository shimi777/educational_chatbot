# Educational Chatbot — Team Guide
## Newton's First Law | החוק הראשון של ניוטון

---

## Project Overview

This is an **AI-powered educational chatbot** that helps student-teachers practice explaining **Newton's First Law of Motion** to a struggling 10-year-old student.

### How It Works

The system has **three AI agents**:

| Agent | Role | Description |
|-------|------|-------------|
| **Struggling Student** | Learner | AI role-plays a confused 10-year-old with common physics misconceptions |
| **Mentor Coach** | Teaching advisor | Gives the student-teacher pedagogical feedback on their explanations |
| **Evaluator** | Performance scorer | Rates the student-teacher's overall performance on a rubric (1-5) |

### User Flow

```
1. User opens the app (gui_app.py)
2. The struggling student presents their confusion about Newton's First Law
3. User (student-teacher) types explanations to help the student
4. Timer starts counting down (10 minutes)
5. User can ask the Mentor for coaching tips at any time
6. When time is up (or user clicks "Get Evaluation"), the AI evaluates performance
7. User sees scores: Clarity, Examples, Terminology, Adaptation + Overall
```

### Features
- **Bilingual**: Toggle between English and Hebrew (עברית)
- **10-minute timer**: Starts on first message, auto-evaluates when time expires
- **Performance evaluation**: Rubric-based scoring of the full conversation
- **Mentor coaching**: On-demand pedagogical advice

---

## Project Structure

```
educational_chatbot/
├── gui_app.py                     ← Main GUI application (Sophia)
├── backend/
│   ├── __init__.py                ← Package exports
│   ├── prompts.py                 ← All AI prompts EN + HE (Bareket)
│   ├── conversation_manager.py    ← Conversation orchestration + evaluation (Bareket)
│   ├── llm_client.py              ← OpenAI API wrapper
│   ├── test_api.py                ← API connection test
│   └── manual_test.py             ← CLI test (alternative to GUI)
├── .env                           ← API key (DO NOT SHARE!)
├── .env.example                   ← Template for .env
├── requirements.txt               ← Python dependencies
└── TEAM_GUIDE.md                  ← This file
```

---

## Team Roles & Responsibilities

---

### Bareket — Content & Evaluation
**Files you own:** `backend/prompts.py`, `backend/conversation_manager.py`

#### What You're Responsible For

**1. Prompt Content (`backend/prompts.py`)**

This file contains ALL the AI prompts that define how the agents behave. You control:

- **Struggling Student persona** — How the student behaves, what misconceptions they have, how they react to good/bad explanations
- **Mentor Coach persona** — What teaching advice it gives, what it flags as good/bad pedagogy
- **Evaluation rubric** — The scoring criteria and weights
- **Hebrew translations** — All prompts exist in English AND Hebrew

Key constants you may want to adjust:

| Constant | What It Does |
|----------|-------------|
| `STRUGGLING_STUDENT_SYSTEM_EN` / `_HE` | Defines the student's character, struggles, and behavior rules |
| `STRUGGLING_STUDENT_INITIAL_EN` / `_HE` | The student's opening message (their first question) |
| `MENTOR_AGENT_SYSTEM_EN` / `_HE` | Defines the mentor's coaching style and what to look for |
| `EVALUATION_PROMPT_EN` / `_HE` | The rubric criteria and scoring format |

**Current student misconceptions** (you can change these):
1. "Objects need constant force to keep moving"
2. "Heavier objects fall faster"
3. "A book on a table has no forces on it"
4. "Objects naturally stop on their own"

**Current evaluation rubric:**
| Criterion | Weight |
|-----------|--------|
| Clarity | 40% |
| Use of Examples | 30% |
| Correct Terminology | 20% |
| Adaptation | 10% |

**2. Evaluation Logic (`backend/conversation_manager.py`)**

You own the `evaluate_performance()` method. It:
- Takes the **full conversation history** (all teacher + student messages)
- Sends it to the AI with the evaluation rubric prompt
- Returns scores + feedback text

If you want to change how evaluation works (e.g., add criteria, change scoring format), edit:
- The `EVALUATION_PROMPT_EN` / `_HE` in `prompts.py` (the rubric text)
- The `evaluate_performance()` method in `conversation_manager.py` (the logic)
- The `get_evaluation_messages()` function in `prompts.py` (how the conversation transcript is formatted for the AI)

#### How to Test Your Changes

```bash
# Quick prompt test (no API call)
python backend/prompts.py

# Interactive CLI test (uses API)
python backend/manual_test.py
# Type 'evaluate' to test evaluation
# Type 'mentor' to test mentor coaching

# Full GUI test
python gui_app.py
```

#### Tips for Prompt Tuning
- **Student too easy?** Add more misconceptions to `STRUGGLING_STUDENT_SYSTEM`
- **Student too hard?** Reduce the number of struggles, make examples of "showing understanding" more frequent
- **Mentor too vague?** Add more specific example responses to `MENTOR_AGENT_SYSTEM`
- **Evaluation too harsh/lenient?** Adjust the criteria descriptions in `EVALUATION_PROMPT`
- **Hebrew quality poor?** The prompts include `LANGUAGE_INSTRUCTION` that forces the AI to respond in Hebrew — make sure the Hebrew prompt text itself reads naturally

---

### Sophia — GUI (User Interface)
**File you own:** `gui_app.py`

#### What You're Responsible For

The entire **tkinter GUI** — the visual application that users interact with.

**Current GUI layout:**

```
+------------------------------------------------------------------+
| [English/עברית]  Educational Chatbot — Newton's First Law  10:00 |
| Timer starts when you send your first message                     |
+------------------------------------------------------------------+
|                                                                   |
|  CHAT DISPLAY (scrollable, color-coded)                          |
|  Student: (blue) | You: (green) | System: (red/gray)            |
|                                                                   |
+------------------------------------------------------------------+
| [Type your explanation here...                    ] [Send]        |
+------------------------------------------------------------------+
| [Ask Mentor] [Get Evaluation] [Show Summary] [New Conversation]  |
+------------------------------------------------------------------+
| Mentor / Evaluation:                                              |
| (bottom panel — shows mentor advice, evaluation scores, summary) |
+------------------------------------------------------------------+
| [EN] Turn 3 | Explanations: 3 | Mentor consultations: 1         |
+------------------------------------------------------------------+
```

**Key components you control:**

| Component | What It Does |
|-----------|-------------|
| `_setup_ui()` | Builds all widgets (buttons, text areas, labels) |
| `_toggle_language()` | Switches all UI labels between EN/HE |
| `_start_timer()` / `_tick_timer()` / `_on_time_up()` | 10-minute countdown timer |
| `_on_send()` | Sends teacher message to AI student |
| `_on_ask_mentor()` | Gets coaching advice from AI mentor |
| `_on_evaluate()` | Triggers performance evaluation |
| `_on_new_conversation()` | Resets everything for a new session |

**How the GUI talks to the backend:**

The GUI uses `ConversationManager` — you don't need to touch AI/API code:

```python
from backend.conversation_manager import ConversationManager

# Initialize
self.manager = ConversationManager(lang="en")  # or "he"

# Start conversation — returns student's first message
initial_msg = self.manager.start_conversation()

# Send teacher message — returns student response
response = self.manager.send_to_student("My explanation here...")

# Get mentor advice — returns coaching text
advice = self.manager.consult_mentor(teacher_msg, student_msg)

# Get evaluation — returns scores + feedback text
evaluation = self.manager.evaluate_performance()

# Get stats
summary = self.manager.get_conversation_summary()
# Returns: {"turns": 3, "student_messages": 3, "mentor_consultations": 1, "is_active": True}

# Change language mid-session
self.manager.set_language("he")
```

**Important: Threading**

All API calls are run in background threads so the GUI doesn't freeze:
```python
def _on_send(self, event=None):
    # ... prepare message ...
    def api_call():
        response = self.manager.send_to_student(text)
        self.root.after(0, lambda: self._on_student_response(response))
    threading.Thread(target=api_call, daemon=True).start()
```

**Rule:** NEVER call `self.manager.send_to_student()` / `consult_mentor()` / `evaluate_performance()` directly on the main thread — always use `threading.Thread` + `self.root.after()`.

#### How to Test Your Changes

```bash
# Run the GUI
python gui_app.py

# Test checklist:
# 1. Send a message → student responds
# 2. Click "Ask Mentor" → advice appears in bottom panel
# 3. Click "Get Evaluation" → scores appear in bottom panel
# 4. Click language toggle → UI switches to Hebrew, conversation restarts
# 5. Wait for timer to expire → input locks, evaluation auto-triggers
# 6. Click "New Conversation" → everything resets
```

#### UI Improvement Ideas
- Add font size controls
- Add a "save conversation" button (export to text file)
- Add visual progress bar for the timer
- Improve RTL (right-to-left) text alignment for Hebrew
- Add keyboard shortcuts (Ctrl+M for mentor, Ctrl+E for evaluation)

---

## Setup Instructions (For All Team Members)

### Step 1: Install Python Dependencies

```bash
cd educational_chatbot

# Create virtual environment (one time)
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### Step 2: Configure API Key

Create a `.env` file (copy from `.env.example`):

```
OPENAI_API_KEY=sk-proj-YOUR-KEY-HERE
MODEL_NAME=gpt-4o-mini
```

Get your key from: https://platform.openai.com/api-keys

**NEVER commit the `.env` file to git!**

### Step 3: Test

```bash
# Test API connection
python backend/test_api.py

# Test with GUI
python gui_app.py
```

---

## How to Run the App

```bash
cd educational_chatbot
python gui_app.py
```

That's it! The GUI window will open.

**Alternative (CLI mode):**
```bash
python backend/manual_test.py
```

---

## Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.10+ | Standard Python, no special version needed |
| AI Model | OpenAI gpt-4o-mini | Supports English + Hebrew, ~$0.01 per conversation |
| GUI | tkinter | Built into Python, no extra install |
| API Client | openai Python SDK | `pip install openai` |
| Config | python-dotenv | Loads `.env` file |

---

## Common Issues & Solutions

| Problem | Solution |
|---------|----------|
| "OPENAI_API_KEY not found" | Create `.env` file with your API key |
| "Module not found" | Make sure venv is activated: `venv\Scripts\activate` |
| GUI freezes when clicking Send | This shouldn't happen (threading is used). If it does, check for errors in the terminal |
| Hebrew text looks wrong | tkinter handles Unicode natively on Windows — should work automatically |
| "Rate limit exceeded" | Wait 1 minute, or check your OpenAI account billing |
| Timer doesn't start | Timer starts on first message send, not on app launch |
| Evaluation says "No conversation" | You need to send at least one message before evaluating |

---

## Cost Estimate

Using **gpt-4o-mini**:
- ~$0.01-0.02 per conversation session
- Evaluation adds ~$0.005
- Budget: **$5-10 for entire project** (hundreds of test sessions)

---

## Key API Methods Reference

```python
class ConversationManager:
    def __init__(self, lang="en")           # Create manager ("en" or "he")
    def set_language(self, lang)             # Switch language
    def start_conversation(self) -> str      # Start new session, returns student's first message
    def send_to_student(self, msg) -> str    # Send explanation, returns student response
    def consult_mentor(self, explanation, student_context) -> str  # Get coaching advice
    def evaluate_performance(self) -> str    # Get rubric scores for full conversation
    def get_conversation_summary(self) -> dict  # Get stats (turns, messages, consultations)
    def get_student_history(self) -> list    # Get full chat history
    def get_last_student_message(self) -> str  # Get most recent student message
```
