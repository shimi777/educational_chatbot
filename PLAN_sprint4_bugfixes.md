# Sprint 4 — Bug Fixes Plan
## שלוש בעיות מרכזיות + פתרונות

---

## באג 1: ציון הערכה תמיד 0

### שורש הבעיה
שני ניתוקים מבניים:

**ניתוק A — הערכת הודעה בודדת במקום שיחה שלמה:**
- `conversation_manager.py:400` מעריך רק את `teacher_messages[-1]` (ההודעה האחרונה)
- ההודעה האחרונה בצ'אט בדרך כלל קצרה ("האם הבנת?", "בוא ננסה דוגמה") — לא מכילה אף רכיב מוערך
- התוצאה: ה-LLM נותן 0 לכל רכיב כי אין מה להעריך

**ניתוק B — Rubric אקדמי שלא מתאים להקשר פדגוגי:**
- `evaluation_spec_template.json` מגדיר 7 רכיבים אקדמיים: `core_statement`, `formal_form`, `conditions`, `mechanism`, `distinctions`, `example`, `misconceptions`
- `formal_form` מחפש "Equation, theorem statement, algorithm/pseudocode" — דבר שסטודנט שמלמד ילד לא יכתוב בצ'אט
- `conditions` מחפש "Necessary Conditions / Assumptions" — גם לא מתאים לשיחת הוראה

**בעיית משנה — performance_levels עם floating-point noise:**
- `min_score_inclusive: 4.069999999999999` — ערכים עשרוניים שגורמים לסיווג שגוי בגבולות

### תיקונים

#### קובץ: `backend/conversation_manager.py`

**שינוי 1 — שורה ~400: שרשור כל הודעות המורה:**
```python
# לפני:
after_eval = self._evaluate_explanation_with_llm(teacher_messages[-1], spec)

# אחרי:
combined_explanation = "\n\n---\n\n".join(teacher_messages)
after_eval = self._evaluate_explanation_with_llm(combined_explanation, spec)
```

**שינוי 2 — שורה ~406: שרשור גם ב-before (השוואת שיפור):**
```python
# לפני:
before_eval = self._evaluate_explanation_with_llm(teacher_messages[0], spec)

# אחרי — הערכת החצי הראשון vs. כל ההסברים:
midpoint = len(teacher_messages) // 2
early_text = "\n\n---\n\n".join(teacher_messages[:midpoint])
before_eval = self._evaluate_explanation_with_llm(early_text, spec)
```

#### קובץ: `backend/evaluation_spec_template.json`

**שינוי 3 — החלפת הרכיבים לרכיבים פדגוגיים:**

7 רכיבים חדשים (סולם 0–2 נשמר):
| key | label | description |
|-----|-------|-------------|
| `core_concept` | Core Concept Delivery | Did the teacher communicate the main idea correctly and clearly? |
| `examples` | Use of Examples | Did the teacher use concrete, relatable examples or analogies? |
| `check_understanding` | Checking Understanding | Did the teacher ask questions or check if the student followed? |
| `misconception_handling` | Misconception Handling | Did the teacher identify and address a student misconception? |
| `adaptation` | Adaptive Teaching | Did the teacher adjust their approach when the student showed confusion? |
| `age_appropriate_language` | Age-Appropriate Language | Did the teacher avoid jargon and use language suitable for the student's age? |
| `encouragement` | Encouragement & Patience | Did the teacher show patience, warmth, and encouragement? |

**שינוי 4 — תיקון performance_levels לערכים שלמים:**
```json
{ "name": "Limited Understanding",    "min_score": 0,  "max_score": 4  },
{ "name": "Developing Understanding", "min_score": 5,  "max_score": 9  },
{ "name": "Strong Understanding",     "min_score": 10, "max_score": 14 }
```

---

## באג 2: Verbosity — תשובות ארוכות מדי של ה-Student Bot

### שורש הבעיה
- `_build_student_persona()` ב-`topic_generator.py:168` לא מכיל שום הנחיה על אורך תשובה
- `max_tokens=300` ב-`conversation_manager.py:132` מאפשר ~225 מילים — יותר מדי לילד בן 10
- ההנחיות מעודדות ריבוי התנהגויות בכל תשובה (confusion + questions + understanding + politeness)
- ה-RLHF default של LLMs גורם להיות מנומס ומפורט

### תיקונים

#### קובץ: `backend/topic_generator.py`

**שינוי 5 — החלפת `_build_student_persona()` (שורה 168):**

שינויים מפתח בפרומפט:
1. הוספת `RESPONSE LENGTH: 1–3 sentences MAX`
2. הוספת `One thought per message. Ask ONE question or express ONE confusion.`
3. הוספת `You are NOT a helpful assistant. You are a confused kid.`
4. הוספת `NEVER: Be excessively polite`
5. הסרת `EXAMPLES OF GOOD RESPONSES` (שנגועות בתרגום פגום)
6. הוספת דוגמאות קצרות inline

**שינוי 6 — הורדת `max_tokens` ב-`conversation_manager.py:132`:**
```python
# לפני:
max_tokens=300

# אחרי:
max_tokens=150
```

---

## באג 3: עברית פגומה ("מתבל" במקום "מתבלבל")

### שורש הבעיה
- `_build_student_persona()` בונה prompt **באנגלית** גם עבור עברית — כותרות כמו "YOUR CHARACTER:", "HOW TO BEHAVE:" נשארות באנגלית
- ה-LLM מקבל system prompt מעורב שפות → מייצר עברית פגומה
- תרגום ה-`student_example_responses` ע"י LLM יצר מילים חתוכות ("מתבל") שנשרפו לתוך ה-persona
- אין בדיקת תקינות על ה-Hebrew output

### תיקונים

#### קובץ: `backend/topic_generator.py`

**שינוי 7 — הוספת `_build_student_persona_he()` — פונקציה נפרדת לעברית:**

פונקציה חדשה שבונה את כל ה-persona בעברית מלאה:
- כל הכותרות בעברית ("אישיות:", "אורך תשובה:", "הקשיים שלך:", "איך לענות:", "אסור:")
- דוגמאות inline בעברית תקנית
- אותן הנחיות verbosity כמו באנגלית

**שינוי 8 — בנפרד, `_build_mentor_prompt_he()` — mentor prompt בעברית מלאה:**

אותו רעיון: כותרות בעברית, הנחיות בעברית, בלי ערבוב שפות.

**שינוי 9 — `_build_topic_config()` שורה ~514: שימוש בפונקציות הנפרדות:**
```python
# לפני:
student_persona_he = _build_student_persona(he_data, target_age)
mentor_prompt_he = _build_mentor_prompt(he_data, target_age)

# אחרי:
student_persona_he = _build_student_persona_he(he_data, target_age)
mentor_prompt_he = _build_mentor_prompt_he(he_data, target_age)
```

---

## סיכום קבצים שישתנו

| קובץ | שינויים |
|-------|---------|
| `backend/conversation_manager.py` | שרשור הודעות (שינוי 1, 2), הורדת max_tokens (שינוי 6) |
| `backend/evaluation_spec_template.json` | רכיבים פדגוגיים + performance_levels (שינוי 3, 4) |
| `backend/topic_generator.py` | persona EN מחודש (שינוי 5), persona HE חדש (שינוי 7), mentor HE חדש (שינוי 8), build_topic_config (שינוי 9) |

## סדר ביצוע
1. תיקון evaluation (שינויים 1–4) — פותר את ציון 0
2. תיקון verbosity (שינויים 5–6) — מקצר תשובות
3. תיקון עברית (שינויים 7–9) — מייצר עברית טבעית

## בדיקה
- כתיבת `_sprint4_test.py` שמריץ evaluation על טקסט דוגמה ומוודא ציון > 0
- בדיקה ידנית בצ'אט: תשובת תלמיד ≤ 3 משפטים
- בדיקה ידנית בעברית: אין ערבוב שפות ב-persona
