# Plan: Address Teacher Feedback — UX Improvements (Sprint 4)

## Context
A real teacher used the chatbot and provided concrete feedback across 4 areas:
the bot is too passive/clueless, the lesson material order is confusing, numeric scores shouldn't be shown to students, and the teacher needs to control the bot's knowledge level.

**Target apps**: `teacher_app.py` + `student_app.py` (the cloud-ready split pair). Backend changes also benefit `gui_app.py` but we won't touch gui_app.py UI.

---

## Change 1: Bot Knowledge Level Selector (Teacher Setup)

**Why**: Teacher wants to configure bot difficulty — struggling (1), basic knowledge (2), advanced + slightly misleading (3).

### Files:
- **`backend/topic_config.py`** — Add `bot_knowledge_level: int = 1` field + accessor `get_bot_knowledge_level()`
- **`backend/topic_generator.py`** — Accept `bot_knowledge_level` param in `generate_topic_config()`, pass to persona builders, store in TopicConfig
- **`teacher_app.py`** — In `_screen_setup()` (line ~215), add a `st.selectbox` for bot knowledge level (3 options) before the Generate button. Pass value to `generator.generate_topic_config()`. Also store in session settings dict (line ~437) so student app can read it.
- **`session_manager.py`** — No changes needed (settings dict is already free-form)

---

## Change 2: Smarter Bot Behavior (3 Persona Variants)

**Why**: Teacher says bot is too clueless, doesn't ask for definitions, doesn't bring knowledge. Need 3 distinct behavior profiles.

### Files:
- **`backend/topic_generator.py`** — Rewrite `_build_student_persona()` and `_build_student_persona_he()` to accept `knowledge_level: int` and produce 3 variants:

**Level 1 (Struggling)**: Current behavior mostly preserved, but add:
- If teacher hasn't defined a key term, ask: "wait, what does [term] mean?"
- Occasionally ask about concept relationships: "so is [A] the same as [B]?"

**Level 2 (Basic Knowledge)**:
- Student understands basics, makes small errors in mechanism/conditions
- Proactively asks "how would you define X?"
- Brings up concept relationships: "My teacher said X relates to Y, is that right?"
- More engaged tone, less "huh?/what?" confusion

**Level 3 (Advanced + Misleading)**:
- References terms and concepts from the material
- Offers slightly wrong analogies: "So it's like [wrong analogy], right?" — waits for correction
- Challenges teacher: "But my textbook says [wrong thing], who's right?"
- Proactively connects concepts (sometimes correctly, sometimes wrong on purpose)

**Also**: Inject `key_concepts` and `key_terms` lists into the persona prompt (all levels) so the bot knows *what* to ask about. Currently only `student_specific_struggles` is injected.

---

## Change 3: Lesson Screen Restructure (Student App)

**Why**: Teacher wants: summary first → merged concepts+terms → analogies → misconceptions last.

### Files:
- **`student_app.py`** — Rewrite `_screen_lesson()` (lines 257-276) display order:
  1. **LESSON SUMMARY** — simple paragraph (first thing student sees, before concepts)
  2. **KEY CONCEPTS & TERMS** — merged into one section (concepts + terms together)
  3. **EXAMPLES & ANALOGIES** — dedicated section (currently exists but shown in column layout)
  4. **COMMON MISCONCEPTIONS** — last, with `st.warning()` styling

  Change from 2-column layout to single-column sequential layout.

- **`backend/topic_generator.py`** — Update `lesson_summary` description in `ENGLISH_GENERATION_PROMPT` (line 132) to: "A simple, clear summary paragraph of up to 300 words"

---

## Change 4: Verbal-Only Evaluation Display (Student App)

**Why**: Teacher says don't show numeric scores to students. Keep scores internally for save/cloud.

### Files:
- **`student_app.py`** — Rewrite `_screen_evaluation()` (lines 573-717):
  - **Remove from student view**: score gauge (`X/14`), `st.progress` bar, `st.metric` with total score, component score bars with `X/2`, improvement deltas
  - **Show instead**: Performance Level as header (verbal only: "Strong Understanding"), per-component verbal descriptor:
    - 0 → "Needs attention" / "דורש תשומת לב"
    - 1 → "Partially demonstrated" / "הודגם חלקית"
    - 2 → "Well demonstrated" / "הודגם היטב"
  - Keep evaluator `notes` as "Feedback" section
  - `_build_transcript()` (line 720) keeps full numeric data for file download + cloud save

- **`ui_helpers.py`** — Add:
  - `COMPONENT_LABELS_HE["concept_relationships"]` = "קשרים בין מושגים"
  - New helper function `verbal_score_label(score: int) -> str` mapping 0/1/2 to verbal EN/HE

- **`backend/evaluation_spec_template.json`** — Add new "concept_relationships" component:
  - id: `concept_relationships`, max_points: 2, priority: 8
  - Description: understanding how concepts relate (cause-effect, dependencies, hierarchies)
  - Update performance_levels score ranges for 8 components (max 16): L1=0-5, L2=6-11, L3=12-16
  - Soften "example" component: not mandatory, evaluated positively when well-placed

- **`student_app.py` `_screen_retrospective()`** (line 840-845): Remove numeric score display in the retrospective info bar (currently shows `{total_score}/{max_score}`)

---

## Implementation Order
1. `backend/topic_config.py` — add `bot_knowledge_level` field (foundation for everything)
2. `backend/evaluation_spec_template.json` — add concept_relationships component + update ranges
3. `backend/topic_generator.py` — 3 persona variants + concept injection + lesson prompt update
4. `ui_helpers.py` — add concept_relationships label + verbal_score_label helper
5. `teacher_app.py` — add knowledge level selector in setup + pass to generator + save in session
6. `student_app.py` — lesson screen restructure + verbal evaluation display + retrospective cleanup

## Verification
- Run teacher app: `py -3 -m streamlit run teacher_app.py`
- Run student app: `py -3 -m streamlit run student_app.py`
- Test all 3 knowledge levels: generate topic, check persona prompt in saved JSON
- Create session as teacher → join as student → verify lesson screen order (summary → concepts+terms → examples → misconceptions)
- Complete a chat → get evaluation → verify NO numeric scores shown, only verbal labels
- Download transcript → verify numbers still appear in saved file
- Cloud save → verify scores still saved to Google Sheets
- Test loading old sessions (backward compatibility — `bot_knowledge_level` defaults to 1)
- Test both EN and HE modes throughout
