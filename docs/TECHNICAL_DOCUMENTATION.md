# التوثيق التقني الكامل — BTEC AI Assessment Assistant

> آخر تحديث: 2026-08-25. هذا التوثيق مبني على قراءة فعلية للكود الحالي في هذا الفرع (`main`)، وليس على النية الأصلية للمشروع. حيث يوجد تعارض بين هذا الملف و [README.md](../README.md) (الذي لا يزال يصف حالة T0.2 القديمة)، **صدّق هذا الملف**.

---

## 1. نظرة عامة

**الهدف**: أداة تساعد مدرّس مساقات BTEC (Pearson BTEC International Level 3 Applied Science) على تقييم تسليمات الطلاب مقابل معايير تقييم رسمية (P/M/D)، عبر اقتراح آلي بالذكاء الاصطناعي يراجعه المدرّس ويعتمده.

**المستخدم النهائي**: المدرّس، وليس الطالب ولا الإدارة.

**المشكلة المحلولة**: تقليل وقت القراءة والتحقق اليدوي لكل معيار في كل تسليم، عبر تزويد المدرّس بمسودة حكم (achieved/not achieved) + دليل مقتبس من نص الطالب + ملاحظة مسودة + درجة ثقة، لكل معيار — يبقى القرار النهائي للمدرّس دائمًا.

**نطاق النسخة الحالية (v1)**: تشغيل محلي بالكامل، بلا اتصال حقيقي بـ Moodle. البيانات (المعايير، التسليمات) يتم تحميلها يدويًا أو عبر seed script أو عبر زر رفع ملفات أضيف لاحقًا في portal.

---

## 2. حالة المشروع الفعلية (ليست كما في README.md)

| المكوّن | الحالة الفعلية |
|---|---|
| نماذج قاعدة البيانات (`app/models.py`) | ✅ مكتمل، 9 جداول، مُختبر |
| محرك التقييم بالذكاء الاصطناعي (`app/grading/`) | ✅ مكتمل وظيفيًا (prompt builder + LLM client + schemas + service)، مربوط بالواجهة |
| واجهة Streamlit (`portal/`) | ✅ 4 صفحات تعمل: Units → Assignments → Submissions → Submission Detail |
| رفع ملفات يدوي + استخراج نص | ✅ موجود لكنه *مؤقت* (داخل `3_Submissions.py` نفسها، وليس خط أنابيب رسمي) |
| ترتيب المعايير (P→M→D) + الدرجة المقترحة | ✅ مكتمل (`app/grading/grade_calculator.py`) |
| التحقق من الدليل الحرفي (`is_evidence_verified`) | ✅ مكتمل، تحذير بصري فقط، لا يرفض التقييم |
| التحقق من التغطية الكاملة للمعايير (`validate_full_coverage`) | ✅ مكتمل |
| **إخفاء هوية الطالب (pseudonymizer)** | ⚠️ **الوحدة موجودة ومُختبرة بمعزل، لكنها غير مستدعاة من أي مكان في مسار التقييم الفعلي** — انظر القسم 7 |
| استخراج نص رسمي من الملفات (`app/extractor/`) | ❌ فارغ تمامًا (`.gitkeep` فقط) |
| RAG (`app/rag/`) | ❌ فارغ عمدًا، معطّل بقرار توثّقه `prompt_builder.py` نفسها |
| اتصال Moodle حقيقي (`app/moodle_api.py`) | ❌ ملف فارغ (تعليق واحد فقط: "Placeholder... T1.1") |
| FastAPI (`app/main.py`) | ❌ هيكل عظمي فقط (`/health` endpoint)، غير مستخدم من أي مكان آخر في المشروع |
| `README.md` | ⚠️ قديم جدًا — يصف المشروع كأنه لا يزال في T0.2 (لا وظائف مطلقًا)، بينما الواقع متقدم كثيرًا |

---

## 3. المكدس التقني (Tech Stack)

- **الواجهة**: Streamlit (`portal/`) — متعددة الصفحات عبر آلية `pages/` القياسية في Streamlit.
- **API مستقبلي (غير مفعّل بعد)**: FastAPI (`app/main.py`) — لا علاقة له حاليًا بمسار التقييم.
- **قاعدة البيانات**: SQLite محليًا (`app_dev.db`، مستثناة من git عبر `.gitignore: *.db`)، عبر SQLModel/SQLAlchemy. `DATABASE_URL` في `.env` غير مستخدم فعليًا — `app/db.py` يبني مسار SQLite ثابتًا دائمًا (`PROJECT_ROOT/app_dev.db`)، بصرف النظر عن قيمة `.env`.
- **نموذج الذكاء الاصطناعي**: DeepSeek (`deepseek-chat`) عبر مكتبة `openai` الرسمية (متوافقة OpenAI API) مع `base_url="https://api.deepseek.com"`.
- **التحقق من المخرجات**: Pydantic v2 (`app/grading/schemas.py`).
- **استخراج النصوص**: `pdfplumber` (PDF)، `python-docx` (DOCX) — مستخدمة حاليًا فقط داخل `portal/pages/3_Submissions.py`، وليس في وحدة مخصصة.
- **الاختبارات**: pytest.

---

## 4. نموذج البيانات (`app/models.py`)

كل الجداول SQLModel (`table=True`)، قاعدة بيانات واحدة مشتركة (`app_dev.db`).

```
Unit ──< CriteriaSnapshot ──< Criterion
                │
                └──< AssignmentMap ──< Submission ──< SubmissionFile
                                            │
                                            └──< Evaluation ──< CriterionResult

AuditLog: جدول مستقل، يسجّل أفعال المدرّس (لا علاقة ربط مباشرة FK حاليًا، فقط entity_type/entity_id نصيًا)
```

| الجدول | الحقول الأساسية | ملاحظة |
|---|---|---|
| `Unit` | `zoho_unit_id` (unique)، `name` | المصدر المفترض للوحدات هو Zoho (حسب اسم الحقل)، لا يوجد تكامل Zoho فعلي في الكود بعد |
| `CriteriaSnapshot` | `unit_id`, `taken_at` | **لحظة تجميد** لمعايير وحدة معينة — انظر القسم 5 |
| `Criterion` | `snapshot_id`, `code` (مثل `P1`), `descriptor` | `UniqueConstraint(snapshot_id, code)` — لا يمكن تكرار نفس الكود في نفس الـ snapshot |
| `AssignmentMap` | `moodle_assign_id` (unique)، `snapshot_id` | يربط واجب Moodle بـ snapshot ثابت من المعايير |
| `Submission` | `assignment_map_id`, `moodle_submission_id`, `student_internal_id`, `submitted_at` | **لا يوجد اسم طالب حقيقي في القاعدة إطلاقًا** — فقط `student_internal_id` (مثل `S-1001`) |
| `SubmissionFile` | `submission_id`, `contenthash`, `filename`, `extract_status`, `extracted_text` | ملف واحد لكل تسليم في الاستخدام الحالي (لا حد صريح في الكود لكن لا مكان يُنشئ أكثر من ملف واحد) |
| `Evaluation` | `submission_id`, `prompt_version`, `model_id`, `status` (`draft`/`approved`) | `model_id` **مُخزَّن فقط كملصق نصي — لا يُستخدم فعليًا لاختيار النموذج** (انظر القسم 6.2) |
| `CriterionResult` | `evaluation_id`, `criterion_id`, `achieved`, `evidence_quote`, `feedback_draft`, `confidence`, `teacher_override`, `teacher_final_feedback`, **`is_evidence_verified`** (Optional[bool], افتراضي `None`) | `is_evidence_verified`: `None` = سجل قديم قبل هذه الميزة، `True`/`False` = مُحسوبة فعليًا |
| `AuditLog` | `timestamp`, `actor`, `action`, `entity_type`, `entity_id`, `details` | يُكتب سطر واحد فقط عند كل `approve_evaluation()` حاليًا |

### مبدأ الـ Snapshot (مهم جدًا)

`CriteriaSnapshot` يجمّد نسخة من المعايير في لحظة زمنية. `AssignmentMap` يشير إلى `snapshot_id` محدد وليس "أحدث نسخة". لماذا هذا مهم:

- معايير المنهج قد تتغير (تصحيح خطأ إملائي، تحديث رسمي من Pearson، إلخ).
- بدون snapshot، تعديل معيار اليوم قد يغيّر بأثر رجعي أساس تقييم واجب قُيِّم الشهر الماضي — وهذا غير مقبول من ناحية عدالة التقييم وقابلية التدقيق.
- مُختبر صراحة في [`tests/test_models.py::test_snapshot_immutability`](../tests/test_models.py) — ينشئ snapshot جديدًا بمعيار محدَّث لنفس الوحدة، ويؤكد أن `AssignmentMap` القديم ما زال يشير لنسخة `Criterion` الأصلية غير المعدَّلة.

---

## 5. تدفق العمل الكامل (End-to-End)

```
[Moodle]  ❌ غير موصول فعليًا بعد
    │
    ▼
[رفع يدوي عبر portal]  ✅  →  استخراج نص (pdfplumber/python-docx/txt) inline في 3_Submissions.py
    │                         → إنشاء Submission + SubmissionFile في القاعدة
    ▼
[4_Submission_Detail.py: زر "قيّم هذا التسليم (AI)"]
    │
    ▼
evaluate_submission()  (app/grading/evaluation_service.py)
    │
    ├─ build_prompt(criteria, submission_text)     ← حقن كامل وحرفي للمعايير (بدون RAG، انظر القسم 6.1)
    ├─ llm_evaluate(prompt)                         ← استدعاء DeepSeek، رسالة واحدة بلا تاريخ محادثة
    ├─ EvaluationResponse.model_validate_json(...)  ← تحقق Pydantic (بنية، مدى confidence، طول evidence_quote)
    ├─ validate_full_coverage(...)                  ← تحقق: لا نقص، لا تكرار، لا معيار مخترع
    ├─ لكل نتيجة: is_evidence_verified = evidence_quote in submission_text  ← تحذير console فقط عند الفشل، لا رفض
    └─ حفظ Evaluation(status="draft") + CriterionResult[] في القاعدة
    │
    ▼
[المدرّس في الواجهة]: يراجع كل بطاقة (مرتّبة P→M→D)، يرى الدرجة المقترحة الحيّة
    (calculate_suggested_grade، تتحدّث فورًا مع أي toggle قبل الاعتماد)
    │
    ├─ قد يبدّل achieved يدويًا
    ├─ قد يعدّل feedback_draft
    │
    ▼
[زر "اعتماد محلي"] → approve_evaluation()
    │
    ├─ يطبّق تعديلات المدرّس، يضبط teacher_override=True لكل حقل غُيِّر
    ├─ evaluation.status = "approved"
    └─ AuditLog(actor="teacher-local", action="approve_evaluation")
    │
    ▼
[إرجاع الدرجة/الملاحظة إلى Moodle]  ❌ غير موجود إطلاقًا في الكود
```

---

## 6. محرك التقييم بالتفصيل (`app/grading/`)

### 6.1. لماذا حقن المعايير كاملة وليس RAG؟

`prompt_builder.py` يبني الـ prompt من: `system_v1.md` + **كل** معايير الواجب (مرقّمة بالترتيب المُعطى، دون فرز) + ملاحظة صريحة أن RAG معطّل + نص التسليم كاملاً. الرمز التوثيقي الحرفي داخل الكود:

```python
RAG_NOTE = (
    "Note: the RAG layer (supporting excerpts from assignment guidance) is "
    "not enabled yet in this version (v1). It will be added later in M3."
)
```

هذا يؤكد أن تعطيل RAG **قرار مؤقت ومقصود لهذه النسخة (v1)** إلى حين M3، وليس افتراضًا دائمًا. المنطق: كل معيار هو بوابة نجاح/رسوب مستقلة يجب فحصها بالكامل وبدقة — أي استرجاع تقريبي (top-k) يخاطر بإسقاط معيار قصير لكنه حاسم. عدد المعايير لكل وحدة (12 في بيانات العيّنة) صغير بما يكفي ليدخل كاملاً في الـ context.

**ملاحظة**: ملف `sample_data/sustainable-energy-assignment-guidance.json` (السياق التربوي/سيناريو العمل لكل قسم A/B/C) **موجود لكنه غير مُحمَّل أو مُستخدم في أي prompt فعليًا اليوم** — فقط `scripts/load_sample_criteria.py` يقرأه كنص خام للتأكد من قابلية القراءة، دون حقنه في `build_prompt`. هذا هو ما تشير إليه ملاحظة "RAG غير مفعّل" — طبقة الـ RAG المستقبلية (M3) من المفترض أنها ستستخرج مقتطفات داعمة من هذا الملف بالذات.

### 6.2. استدعاء DeepSeek (`llm_client.py`)

```python
_client = OpenAI(api_key=os.getenv("LLM_API_KEY"), base_url="https://api.deepseek.com")

def evaluate(prompt: str) -> dict:
    response = _client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
```

- **لا تاريخ محادثة**: رسالة `user` واحدة فقط في كل استدعاء، عميل عديم الحالة (stateless)، لا سياق محفوظ بين الاستدعاءات.
- **لا fine-tuning ولا custom model IDs ولا تخزين سياق على جانب DeepSeek**: `model="deepseek-chat"` ثابت حرفيًا في الكود.
- **تفصيل مهم**: بارامتر `model_id` في توقيع `evaluate_submission()` (افتراضيًا `"deepseek-chat"`) **لا يُمرَّر فعليًا** لـ `llm_evaluate()` — فقط يُخزَّن كحقل نصي في سجل `Evaluation`. القيمة الفعلية المُرسَلة لـ DeepSeek مكتوبة بشكل منفصل وثابت داخل `llm_client.py` نفسه. لا يوجد مسار حالي لتغيير النموذج من الخارج.
- `temperature=0.2` (منخفضة نسبيًا، لصالح الاتساق) و`response_format={"type": "json_object"}` (يفرض JSON صالح من DeepSeek).

### 6.3. طبقة التحقق (`schemas.py`)

- `CriterionJudgment`: يتحقق أن `evidence_quote` ≥ 3 أحرف، `feedback_draft` غير فارغ، `confidence` ضمن [0.0, 1.0].
- `EvaluationResponse`: قائمة `criteria_results` غير فارغة.
- `validate_full_coverage(response, expected_codes)`: **دالة مستقلة، وليست pydantic validator**، تُستدعى يدويًا من `evaluation_service.py` بعد `model_validate_json`. تتحقق (بالترتيب): لا تكرار في `criterion_code` → لا معيار متوقَّع مفقود → لا معيار "مخترع" غير موجود في المعايير الأصلية. **ملاحظة تصميم**: لا يوجد فحص منفصل لـ "عدم تطابق العدد الكلي" لأنه رياضيًا مُغطّى دائمًا بأحد الفحوصات الثلاثة أعلاه (إن تساوى العدد ولا تكرار ولا نقص، فبالضرورة لا يوجد اختراع، والعكس صحيح).

### 6.4. `evaluation_service.py`

الدالتان الوحيدتان:

- **`evaluate_submission(session, submission_id, criteria, submission_text, model_id="deepseek-chat", prompt_version="v1")`**: تبني الـ prompt → تستدعي DeepSeek → تتحقق (schema + coverage) → تحسب `is_evidence_verified` لكل نتيجة (substring حرفي، بدون رفض عند الفشل، فقط `logger.warning(...)`) → تحفظ `Evaluation(status="draft")` و`CriterionResult[]`.
- **`approve_evaluation(session, evaluation_id, criterion_result_updates, actor="teacher-local")`**: تطبّق تعديلات المدرّس (تُفعّل `teacher_override=True` فقط إن تغيّرت القيمة فعليًا)، تضبط `status="approved"`، تكتب `AuditLog`. **لا تستدعي النموذج إطلاقًا** — عملية محلية بحتة على القاعدة.

### 6.5. الدرجة المقترحة (`grade_calculator.py`)

```python
def calculate_suggested_grade(results: list[dict]) -> str:
    # يستخرج المستوى من أول حرف بكل criterion_code (P/M/D) ديناميكيًا
    # لا قائمة ثابتة — يعمل مع أي عدد معايير لأي وحدة
```

- كل معايير P محققة؟ لا → `"NOT_YET_ACHIEVED"`
- P كاملة فقط → `"PASS"`
- P + M كاملة → `"MERIT"`
- P + M + D كاملة → `"DISTINCTION"`

تُستدعى **حيًا** من `4_Submission_Detail.py` بناءً على قيم `st.session_state` الحالية لكل toggle (وليس القيم المحفوظة أصلاً)، فتتحدّث فور أي تعديل يدوي قبل الاعتماد.

---

## 7. الخصوصية والأمان — ⚠️ فجوة حرجة موثّقة

### 7.1. ما هو مبني (`app/privacy/pseudonymizer.py`)

وحدة قائمة على regex بالكامل (لا NER حقيقي — موثّق صراحة في تعليق الملف كأنها "T3.4 draft"):

- `EMAIL_PATTERN` → يستبدل بـ `[EMAIL]`.
- `PHONE_CANDIDATE_PATTERN` (7–15 رقمًا فعليًا بعد تنظيف الفواصل) → `[PHONE]`.
- `NAME_PATTERN` (كلمتان إلى أربع كلمات تبدأ بحرف كبير متتالية) → `[NAME]`، **إلا** إذا كانت إحدى الكلمات ضمن `DOMAIN_EXCEPTION_WORDS` (قائمة يدوية من مصطلحات وحدة "Sustainable Energy" تحديدًا + أفعال الأمر + "Pearson"/"BTEC") — لتجنّب تحويل "Fossil Fuels" إلى `[NAME]` خطأً.
- مُختبرة جيدًا في [`tests/test_pseudonymizer.py`](../tests/test_pseudonymizer.py) (6 اختبارات: أسماء، إيميلات، هواتف، استثناء المصطلحات العلمية، نص مختلط، idempotency).

### 7.2. الفجوة الفعلية

```
grep -rn "pseudonymize" --include=*.py .
  → scripts/test_pseudonymizer_demo.py
  → tests/test_pseudonymizer.py
  → app/privacy/pseudonymizer.py
```

**لا استدعاء واحد لـ `pseudonymize()` من `evaluation_service.py` أو `prompt_builder.py` أو أي مسار فعلي في التطبيق.** بمعنى: نص التسليم الخام — بما قد يحتويه من أسماء طلاب حقيقية إن كتبها الطالب داخل إجابته، أو بيانات تواصل — **يُرسَل بالكامل إلى DeepSeek (خدمة خارجية) دون أي إخفاء هوية فعلي في النسخة الحالية**. الوحدة جاهزة ومُختبرة بمعزل تام، لكنها **غير مدمجة (wired) في الـ pipeline بعد**.

**قيود بنيوية إضافية مرتبطة بالخصوصية**:
- لا يوجد اسم طالب حقيقي مخزَّن في قاعدة البيانات نفسها (`student_internal_id` فقط مثل `S-1001`) — هذا مطبَّق ومُختبر.
- `.gitignore` يستثني `*.db` و`student_data/` و`private_data/` و`sample_data/real/` — القصد واضح ألا تُرفع بيانات حقيقية لـ git، لكن هذا لا يمنع تسريبها إلى DeepSeek وقت التشغيل.

**الخطر إن بقيت هذه الفجوة**: احتمال إرسال بيانات شخصية لطلاب إلى مزوّد ذكاء اصطناعي خارجي دون موافقة/معالجة كافية، وهو خرق امتثال/خصوصية محتمل يجب إغلاقه قبل أي استخدام مع بيانات طلاب حقيقيين.

### 7.3. مبدأ الحوكمة (غير قابل للكسر)

العبارة الحرفية المكرَّرة في كل صفحة portal وفي `prompts/system_v1.md`: **"اقتراح آلي — القرار للمدرّس"**. كل تقييم يبدأ `status="draft"` ولا يصبح نهائيًا إلا بفعل صريح (`approve_evaluation`)، وأي تغيير يدوي يُسجَّل كـ `teacher_override=True`. `system_v1.md` نفسه يفتتح بهذا المبدأ قبل أي تعليمة تقنية أخرى.

---

## 8. البرومبت (`prompts/system_v1.md`)

بنية الملف: دور النظام (المساعد ليس مصححًا نهائيًا) → منهجية BTEC (الحكم على العملية الذهنية عبر فعل الأمر: Describe/Explain/Analyse/Evaluate، لا على طول أو غنى المحتوى) → **6 قواعد صارمة بالإنجليزية**:

1. الدليل يجب أن يكون اقتباسًا حرفيًا فعليًا (verbatim substring) — لا اختلاق ولا إعادة صياغة.
2. كل حكم يجب أن يُبرَّر بدليل مباشر.
3. عند عدم اليقين → confidence منخفضة (< 0.5) بدل تخمين `achieved=true`.
4. الحكم صارم بناءً على فعل الأمر المطلوب فقط، بصرف النظر عن جودة/طول المحتوى.
5. يجب إرجاع حكم واحد بالضبط لكل معيار مذكور — لا حذف، حتى لو لم يوجد دليل مناسب (يُستخدم أقرب اقتباس متاح + confidence منخفضة).
6. **(أُضيفت لاحقًا)** لا يجوز منح معيار لمجرد ظهور كوده (P1/M1/D1) كعنوان أو ذكر في نص الطالب — الحكم على المحتوى الفعلي المكتوب فقط.

يتبعها مخطط JSON إلزامي، ومثال Few-shot كامل (marketing mix)، وتنبيه ختامي بأن الرد يجب أن يكون JSON فقط.

---

## 9. واجهة Streamlit (`portal/`)

تنقّل خطي إجباري عبر `st.session_state`:

```
Home.py
  └─ 1_Units.py           → session_state["selected_unit_id"]
       └─ 2_Assignments.py → session_state["selected_assignment_map_id"]
            └─ 3_Submissions.py → session_state["selected_submission_id"]
                                    (+ رفع ملف يدوي: PDF/DOCX/TXT → استخراج نص inline → Submission جديد)
                 └─ 4_Submission_Detail.py
                       - نص التسليم: مخفي افتراضيًا داخل st.expander (ملخص عدد الكلمات فقط ظاهر)
                       - Assessment Criteria: مرتّبة P→M→D رقميًا (ليس أبجديًا)
                       - الدرجة المقترحة: بارزة فوق البطاقات، حيّة مع كل toggle
                       - بطاقة لكل معيار: achieved toggle، اقتباس الدليل (+ تحذير إن is_evidence_verified=False)،
                         ملاحظة مسودة قابلة للتعديل، confidence
                       - زر "قيّم هذا التسليم (AI)" / "إعادة التقييم"
                       - زر "اعتماد محلي" (يظهر فقط إن status="draft")
```

كل صفحة تعرض `"اقتراح آلي — القرار للمدرّس"` وشريط بيئة (`APP_ENV`) أعلاها.

---

## 10. الاختبارات

| الملف | يغطي |
|---|---|
| `test_models.py` | إنشاء الجداول، إدراج/قراءة كل نموذج، **`test_snapshot_immutability`** |
| `test_schemas.py` | تحقق Pydantic + 4 اختبارات لـ `validate_full_coverage` |
| `test_prompt_builder.py` | احتواء الـ prompt على التعليمات/المعايير/النص/ملاحظة RAG |
| `test_evaluation_flow.py` | تدفق كامل (draft→approve)، **+ اختباري `is_evidence_verified` عبر `monkeypatch`** |
| `test_grade_calculator.py` | 4 حالات BTEC (DISTINCTION/MERIT/PASS/NOT_YET_ACHIEVED) |
| `test_pseudonymizer.py` | أسماء/إيميلات/هواتف/استثناءات علمية/idempotency |
| `test_portal_data.py` | صحة بيانات `seed_dev_db.py` |

**⚠️ تنبيه تشغيلي مهم**: `test_evaluation_flow.py` **يستدعي DeepSeek API الحقيقي فعليًا** (لا يوجد أي mock افتراضي لـ `llm_client`) — يتطلب `LLM_API_KEY` صالحًا في `.env`، ويستهلك حصة API حقيقية، وغير حتمي بطبيعته (لهذا استُخدم `monkeypatch` خصيصًا لاختباري `is_evidence_verified` لضمان نتيجة حتمية).

تشغيل الكل: `pytest -v` من جذر `teacher-ai/` (الحالة الحالية: **45/45 ناجح**).

---

## 11. الإعداد والتشغيل

```bash
# من داخل teacher-ai/ بعد تفعيل .venv
pip install -r requirements.txt   # (.venv موجود مسبقًا في هذا المستودع)
cp .env.example .env              # ثم عبّئ LLM_API_KEY على الأقل
python scripts/seed_dev_db.py     # يبني app_dev.db من الصفر ببيانات Sustainable Energy (12 معيار، 3 تسليمات)
streamlit run portal/Home.py      # الواجهة، على المنفذ 8501 افتراضيًا
```

متغيرات `.env` الفعلية المستخدمة: `APP_ENV` (يظهر في شريط الحالة فقط)، `LLM_API_KEY` (لـ DeepSeek). أما `DATABASE_URL` و`STAGING_MOODLE_*` فمعرَّفة في `.env.example` لكن **غير مقروءة من أي كود حاليًا** (تحضير مستقبلي فقط).

`app_dev.db` مستثناة من git (`*.db` في `.gitignore`) — كل بيئة تبني نسختها المحلية عبر seed script.

---

## 12. الفجوات المعروفة (Roadmap الفعلي المُستنتج من الكود)

بالترتيب التقريبي للأولوية من ناحية الجاهزية للاستخدام الحقيقي:

1. **دمج pseudonymizer في `evaluation_service.py`** قبل إرسال أي `submission_text` حقيقي لـ DeepSeek — أهم فجوة حرجة حاليًا (القسم 7).
2. **اتصال Moodle حقيقي** (سحب تسليمات + رفع درجات/ملاحظات نهائية) — `app/moodle_api.py` لا يزال فارغًا تمامًا.
3. **خط أنابيب استخراج رسمي** (`app/extractor/`) — منطق الاستخراج حاليًا مكانه الخطأ (داخل صفحة portal) وليس معزولاً/قابلاً لإعادة الاستخدام أو الاختبار المستقل.
4. **تفعيل RAG (M3)** لحقن مقتطفات من `sample_data/*-assignment-guidance.json` كسياق داعم، حسب ما توثقه `RAG_NOTE` نفسها.
5. **تحديث `README.md`** — لا يعكس أي شيء من الحالة الفعلية الموصوفة في هذا الملف.
6. **ربط أو حذف `app/main.py` (FastAPI)** — حاليًا هيكل عظمي معزول تمامًا لا يستخدمه أي جزء آخر من النظام.
7. **قراءة `DATABASE_URL` فعليًا** من `.env` بدل المسار الثابت في `app/db.py`، إن كان الانتقال من SQLite مخططًا له.

---

## 13. قرارات معمارية جوهرية (وسببها)

| القرار | السبب |
|---|---|
| حقن كل المعايير حرفيًا بدل RAG (v1) | كل معيار بوابة نجاح/رسوب مستقلة؛ الاسترجاع التقريبي يخاطر بإسقاط معيار حاسم. مؤقت حتى M3 (توثيق داخل الكود نفسه) |
| `CriteriaSnapshot` منفصل عن `Criterion` الحي | ضمان عدم تغيّر أساس التقييم بأثر رجعي لواجبات قُيِّمت مسبقًا |
| `student_internal_id` بدل اسم حقيقي في القاعدة | حماية أولية للخصوصية على مستوى التخزين (لكن غير كافية وحدها — القسم 7) |
| `is_evidence_verified` تحذير فقط، لا رفض | تجنّب تعطيل تقييم كامل بسبب اختلاف صياغي بسيط (مسافة/علامة ترقيم) في اقتباس صحيح المعنى |
| `validate_full_coverage` دالة مستقلة لا pydantic validator | تحتاج معرفة `expected_codes` من خارج الاستجابة نفسها (من قاعدة البيانات) — لا يمكن التحقق منها داخل الكلاس وحده |
| كل صفحة/تقييم يبدأ `draft` ولا يُعتمد إلا يدويًا | المبدأ الحاكم غير القابل للكسر: "اقتراح آلي — القرار للمدرّس" |
