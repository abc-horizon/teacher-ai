# خطة الوصول لبيانات معايير BTEC في Moodle

> **اقرأ القسم 7 أولاً** — جولة تحقق حيّة لاحقة قلّصت النطاق المطلوب من SQL من سبعة جداول إلى **جدولين فقط** (`gradingform_btec_criteria` و`gradingform_btec_fillings`)، بعد أن ثبت أن حكم المدرّس النهائي والربط بين التسليم وتقييمه المتقدم صارا قابلين للسحب عبر API. الأقسام 1-6 أدناه صحيحة تاريخيًا لكن نطاق طلبها أوسع من اللازم الآن.

> **الحالة الحالية (محدَّثة)**: الموقع الصحيح هو `https://elearning.abchorizon.com` — كل محاولات `invalidtoken` السابقة كانت بسبب ضرب دومين خطأ (`lms.abchorizon.com`)، وليست مشكلة بالتوكن نفسه. توكن Web Services **يعمل الآن فعليًا** على `elearning.abchorizon.com` وتم استخدامه للتحقق الحي (انظر القسم 5). **لا نزال بلا أي وصول SQL مباشر لقاعدة بيانات Moodle** (لا `dbhost`/`dbname`/`dbuser`/`dbpass`) — وهذا ما زال يمنعنا تحديدًا من سحب نص معايير BTEC وأحكام المدرّسين التفصيلية، رغم أن كل شيء آخر (مواد، واجبات، تسليمات) بات قابلاً للسحب عبر API. القسم 1-4 مبني على قراءة الكود المصدري لإضافة `local_moodle_zoho_sync` محليًا فقط؛ القسم 5 مبني على استدعاءات API حقيقية منفَّذة فعليًا.

---

## 1. البنية المكتشفة كاملة

معايير BTEC (P1/M1/D1 مع نصوصها) وأحكام المدرّسين الفعلية عليها **موجودة داخل قاعدة بيانات Moodle نفسها**، عبر خمسة جداول مترابطة. لا يوجد أي Moodle Web Service API يكشف هذه البيانات — الوصول الوحيد الممكن هو SQL مباشر.

### السلسلة الكاملة (من التسليم حتى نص المعيار وحكم المدرّس)

```
mdl_assign_grades  (درجة تسليم طالب حقيقي)
        │  id = itemid
        ▼
mdl_grading_instances   (سجل التقييم المتقدم لهذا التسليم تحديدًا)
        │  definitionid
        ▼
mdl_grading_definitions   (تعريف نموذج التقييم: أي وحدة/طريقة)
        │  id = definitionid
        ▼
mdl_gradingform_btec_criteria   (معايير الوحدة: P1, M1, D1... + النص الكامل)
        │  id = criterionid
        ▼
mdl_gradingform_btec_fillings   (حكم المدرّس الفعلي لكل معيار على هذا التسليم تحديدًا)
```

### وصف كل جدول

| الجدول | المصدر | يحتوي |
|---|---|---|
| `mdl_grading_areas` | Moodle core | أين يوجد تقييم متقدم (أي واجب/context)، والطريقة النشطة (`activemethod`) |
| `mdl_grading_definitions` | Moodle core | تعريف نموذج تقييم واحد: `id`, `areaid`, `method` (='btec' لحالتنا), `name`, `description`, `status` — **لا يحتوي نص المعايير نفسها** |
| `mdl_grading_instances` | Moodle core | تقييم فعلي واحد منجز لتسليم واحد: `id`, `definitionid`, `itemid` (=`assign_grades.id`), `raterid` (من قيّم), `rawgrade`, `timemodified` |
| `mdl_gradingform_btec_criteria` | إضافة `gradingform_btec` (مخصصة) | **نص المعايير الفعلي**: `id`, `definitionid`, `shortname` (مثل "P1"), `description` (النص الكامل), `sortorder` |
| `mdl_gradingform_btec_fillings` أو `mdl_gradingform_btec_filling` (⚠️ الاسم غير مؤكد 100%، انظر القسم 2-ج) | إضافة `gradingform_btec` (مخصصة) | **حكم المدرّس الفعلي لكل معيار**: `instanceid` (=`grading_instances.id`), `criterionid` (=`gradingform_btec_criteria.id`), `score`, `remark` (ملاحظة المدرّس) |

**المصدر**: هذه البنية مستخرجة من دالة `extract_btec_learning_outcomes()` في `classes/data_extractor.php` ضمن كود إضافة `local_moodle_zoho_sync` (اطّلعنا على الكود المصدري محليًا فقط، لم نُشغّله).

**ملاحظة مهمة**: حتى مطوّر الإضافة نفسه لم يكن متأكدًا من اسم جدول الـ fillings بالضبط — كوده يتحقق من الاحتمالين معًا (`fillings` بصيغة الجمع، أو `filling` بالمفرد) قبل الاستخدام. يجب التحقق من الاسم الصحيح فعليًا (استعلام التحقق في القسم 2-ج).

---

## 2. الاستعلامات الجاهزة

> كل الاستعلامات أدناه **SELECT فقط** — لا تعديل ولا حذف ولا إدراج. البادئة `mdl_` هي الافتراضية لـ Moodle؛ إن كانت بادئة موقعكم مختلفة، استبدلها بالفعلية.

### أ. معايير كل الوحدات (definitions + criteria)

```sql
SELECT
    gd.id           AS definition_id,
    gd.name         AS unit_name,
    gd.status,
    gc.id           AS criterion_id,
    gc.shortname    AS code,              -- مثل P1, M1, D1
    UPPER(LEFT(gc.shortname, 1)) AS level, -- P / M / D
    gc.description  AS criterion_text,
    gc.sortorder
FROM mdl_grading_definitions gd
JOIN mdl_gradingform_btec_criteria gc ON gc.definitionid = gd.id
WHERE gd.method = 'btec'
ORDER BY gd.id, gc.sortorder;
```

### ب. أحكام المدرّسين الفعلية لتسليم معيّن (fillings)

**الخطوة 1** — إيجاد سجل التقييم المتقدم لتسليم محدد (استبدل `:assign_grade_id` بقيمة `mdl_assign_grades.id` الحقيقية):

```sql
SELECT gi.id AS instance_id, gi.definitionid, gi.raterid, gi.timemodified
FROM mdl_grading_instances gi
JOIN mdl_grading_definitions gd ON gd.id = gi.definitionid
WHERE gi.itemid = :assign_grade_id
  AND gd.method = 'btec'
ORDER BY gi.timemodified DESC
LIMIT 1;
```

**الخطوة 2** — التفصيل الكامل لكل معيار لهذا التسليم (استبدل `:instance_id` و `:definitionid` بالقيم من الخطوة 1):

```sql
SELECT
    gc.shortname                  AS code,
    UPPER(LEFT(gc.shortname, 1))  AS level,
    gc.description                AS criterion_text,
    f.score,
    f.remark                      AS teacher_feedback
FROM mdl_gradingform_btec_criteria gc
LEFT JOIN mdl_gradingform_btec_fillings f
       ON f.criterionid = gc.id AND f.instanceid = :instance_id
WHERE gc.definitionid = :definitionid
ORDER BY gc.sortorder;
```

### ج. التحقق من اسم جدول الـ fillings الصحيح (شغّله أولاً قبل استعلام "ب")

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name LIKE '%gradingform_btec_filling%';
```

سيرجع إما `mdl_gradingform_btec_fillings` أو `mdl_gradingform_btec_filling` — استخدم الاسم الفعلي الظاهر في استعلام "ب" أعلاه.

---

## 3. ما نحتاجه بالضبط من مدير النظام

### أ. بيانات اتصال بقاعدة بيانات (قراءة فقط — SELECT حصرًا)

- `dbhost`
- `dbname`
- `dbuser` — بصلاحية **SELECT فقط**، لا `INSERT`/`UPDATE`/`DELETE`/`DROP`
- `dbpass`
- نوع القاعدة (MySQL/MariaDB أو PostgreSQL) ورقم المنفذ إن كان غير افتراضي

### ب. الجداول المحددة التي نحتاج صلاحية `SELECT` عليها فقط (وليس القاعدة كاملة)

| الجدول | لماذا |
|---|---|
| `mdl_grading_areas` | تحديد أين التقييم المتقدم مفعّل |
| `mdl_grading_definitions` | تعريف نماذج التقييم (id, method, name) |
| `mdl_grading_instances` | ربط تسليم الطالب بتقييمه المتقدم |
| `mdl_gradingform_btec_criteria` | نص معايير BTEC الفعلي (P1/M1/D1) |
| `mdl_gradingform_btec_fillings` (أو `_filling`) | حكم المدرّس الفعلي لكل معيار |
| `mdl_assign_grades` | لإيجاد `itemid` الرابط بين تسليم طالب محدد والتقييم المتقدم |
| `mdl_assign` | اسم/تفاصيل الواجب المرتبط (اختياري، للسياق فقط) |

**لسنا بحاجة** لأي صلاحية على `mdl_user` أو أي جدول بيانات شخصية للطلاب — أسماء/معرّفات الطلاب سنحصل عليها لاحقًا عبر Moodle Web Services API (`core_enrol_get_enrolled_users`) وليس عبر SQL مباشر، تقليلًا لنطاق الوصول المطلوب.

---

## 4. البدائل إن تعذّر منح وصول SQL مباشر

إن كانت سياسة الأمان لا تسمح بمنح بيانات اتصال قاعدة البيانات مباشرة، البدائل بالأولوية:

1. **تصدير CSV**: يشغّل مدير النظام الاستعلامين (أ) و(ب) أعلاه بنفسه ويرسل النتيجة كملف CSV — لا حاجة لإعطائنا أي بيانات اتصال بالقاعدة إطلاقًا. هذا **الخيار الأبسط والأكثر أمانًا** من جهته.
2. **حساب قراءة محدود عبر أداة إدارة قاعدة بيانات موجودة أصلاً** (مثل phpMyAdmin) إن كان متاحًا له فعلاً — يشغّل هو الاستعلامات ويشاركنا لقطة (screenshot) أو نسخ النتيجة النصية.
3. **تفعيل توكن Web Services صالح مع صلاحية `moodle/grade:managegradingforms`**: هذا يعطينا `core_grading_get_definitions` عبر API (نجحت سابقًا في وصول اختباري) — لكنها تكشف فقط تعريف النموذج (اسم/حالة)، **وليس** نص المعايير ولا أحكام المدرّسين، لأن هذين مخزّنان في جداول مخصصة (`gradingform_btec_*`) لا تغطيها أي دالة API متاحة حاليًا. هذا الخيار وحده **غير كافٍ**.
4. **الرجوع لـ Zoho كمصدر أصلي**: بما أن التعليق الحرفي في كود الإضافة يقول إن Moodle يستقبل المعايير من "Backend" أصلاً، قد يكون الأسهل فعليًا طلب هذه البيانات من فريق/نظام Zoho مباشرة بدل المرور عبر Moodle كوسيط.

---

## 5. نتائج التحقق الحي (Live، عبر API فعلي — ليس قراءة كود فقط)

نفَّذنا استدعاءات API حقيقية (قراءة فقط) على `https://elearning.abchorizon.com` للتحقق من صحة البنية أعلاه على بيانات حقيقية:

| المعرّف | القيمة | كيف حصلنا عليه |
|---|---|---|
| `course_id` | **373** | `core_course_get_courses` (شورت نيم: "2526T2 L3 U28 Sustainable Energy") |
| `cmid` (course module id) | **1640** | `core_course_get_contents(courseid=373)` |
| `assign_id` (instance) | **333** | نفس الاستدعاء أعلاه، حقل `instance` |
| `definition_id` | **16005** | `core_grading_get_definitions(cmids=[1640], areaname='submissions')` — `method='btec'`, `status=20` (READY) |

**التسليمات** (`mod_assign_get_submissions(assignmentids=[333])`) — **24 تسليمًا حقيقيًا**:
- الحالة (`status`): 6 `submitted`، 3 `reopened`، 15 `new`
- التصحيح (`gradingstatus`): 17 `released`، 7 `notmarked`

**تقييم BTEC المتقدم** (`core_grading_get_gradingform_instances(definitionid=16005)`) — **15 مثيل تقييم فعلي**:
- كلها بحالة `status=1`
- **`rawgrade` فارغ (`None`) في كل الـ15** — أي أن حقل الدرجة الموحّدة العام بـ Moodle core لا يُستخدم لطريقة `btec` المخصصة؛ الدرجة/الحكم الفعلي (وربما التفصيل لكل معيار) يُخزَّن حصرًا في جداول الإضافة المخصصة (`gradingform_btec_fillings`) التي لا تكشفها هذه الدالة ولا أي دالة أخرى.

**الخلاصة العملية لهذا القسم**: الوصول لـ Moodle عبر API أصبح كاملاً وشغّالًا للمواد/الواجبات/التسليمات — لكن نص المعايير وتفصيل الحكم لكل معيار **ما زالا غير قابلين للسحب إلا عبر SQL مباشر**، بالضبط كما توقّعنا في الأقسام 1-4، والآن مؤكَّد على بيانات إنتاج حقيقية وليس افتراضًا نظريًا.

---

## 6. البنية المعمارية الأوسع (Zoho ← Backend API ← Moodle plugin)

من قراءة كود إضافة `local_moodle_zoho_sync` بالكامل، اتضح أن Moodle ليس طرفًا مباشرًا مع Zoho — يوجد خادم وسيط ثالث ("Backend API"):

```
Zoho (المصدر الأصلي للمعايير)
   │
   ▼  (Backend يتصل بـ Zoho ويجلب/يعالج البيانات)
Backend API  ── خادم REST مخصص، مسار /api/v1/...
   │
   ▼  (يستدعي دالة Moodle Web Service التالية)
local_moodle_zoho_sync_create_btec_definition  (Moodle plugin)
   │
   ▼  (يكتب مباشرة في قاعدة بيانات Moodle)
mdl_grading_definitions + mdl_gradingform_btec_criteria
```

نقاط مهمة:
- **`/api/v1/btec/sync-templates` دالة كتابة/مزامنة، وليست قراءة** — زر "Sync from Zoho" في `ui/admin2/btec.php` يستدعيها بـ `POST`، وهي تُنشئ/تُحدّث تعريفات ومعايير حقيقية في Moodle. لا يجوز استدعاؤها من طرفنا (تحتوي وظيفيًا على create/update رغم أن اسمها لا يحتوي هذه الكلمات حرفيًا).
- **لا توجد أي نقطة `GET` معروفة على الـ Backend لقراءة معايير BTEC** — كل ما وجدناه بالكود مسارات كتابة (`sync-templates`, `sync-student`, `submit_grade`, إلخ).
- **`backend_url` و `api_token` الخاصان بهذا الـ Backend غير موجودين في كود الإضافة إطلاقًا** — هما قيمتا إعداد محفوظتان داخل جدول `mdl_config_plugins` بقاعدة بيانات Moodle نفسها (`get_config('local_moodle_zoho_sync', 'backend_url')`). أي أن الوصول لهما يتطلب نفس وصول SQL المطلوب أصلاً في القسم 3 — لا يفتح مسارًا بديلًا مستقلاً.

---

## 7. تحقق حي ثانٍ — تقليص نطاق ما نحتاجه من SQL

جولة تحقق حيّة جديدة (قراءة فقط) على `elearning.abchorizon.com` و`lms.abchorizon.com` أعادت رسم الحدود: **جزء مما ظننّاه SQL-only صار قابلاً للسحب عبر API**، وبقي جزء واحد فقط فعليًا محصورًا بـ SQL.

### أ. حكم المدرّس النهائي بـ BTEC — صار متاحًا عبر API (لم يكن معروفًا سابقًا)

`gradereport_user_get_grade_items(courseid, userid)` يُرجع لبند الواجب:

| الحقل | القيمة الحقيقية المرصودة |
|---|---|
| `graderaw` | `4` |
| `gradeformatted` / `lettergradeformatted` | `"Distinction"` |
| `grademin` / `grademax` | `1` / `4` |
| `rangeformatted` | `"Refer–Distinction"` |
| `gradedategraded` | timestamp التصحيح |

أي أن سلّم BTEC هو **1=Refer، 2=Pass، 3=Merit، 4=Distinction**، والحكم النهائي للمدرّس مقروء بالنص الصريح. هذا يعطينا مجموعة مرجعية (ground truth) لمقارنة حكم الـ AI بحكم المدرّس البشري — **دون أي SQL**.

### ب. الربط بين تسليم الطالب وتقييمه المتقدم — متاح عبر API

- `mod_assign_get_grades(assignmentids)` → `id` (= `mdl_assign_grades.id`، أي `itemid`)، `userid`، `grade`، `grader`.
- `core_grading_get_gradingform_instances(definitionid)` → `id` (= instance_id)، `itemid`، `raterid`، `timemodified`.

الربط على `itemid` يعيد بناء حلقتين من السلسلة في القسم 1 بالكامل عبر API. مثال حقيقي مرصود: `itemid=813` → grade `4.00000` (Distinction)، grader `8181` → instance `2111`.

**تأكيد**: `rawgrade` لا يزال `null` في كل المثائل — الدرجة الفعلية تأتي من `mod_assign_get_grades` / grade report، لا من هذه الدالة.

### ج. دوال إضافات مكتشفة على الموقع (لم تكن في القسم 6)

عائلة `local_mzi_*` موجودة فعليًا على `elearning` بالتوكن الحالي: `create_btec_definition`، `delete_btec_definition`، `submit_grade`، `delete_grade`، `enrol_users`، `get_moodle_ids`. كلها **كتابة/حذف** ما عدا `get_moodle_ids`.

- ⚠️ لا يجوز استدعاء أي منها من طرفنا (تُنشئ/تُحدّث/تحذف بيانات إنتاج حقيقية).
- `local_mzi_get_moodle_ids` هي دالة القراءة الوحيدة، لكنها مُعامِل-إجباري ولم نتمكن من استنتاج توقيعها (كل المحاولات ترجع `invalidparameter`)؛ ومن اسمها فهي مُعيِّن IDs (Zoho↔Moodle) ولا تكشف نص معايير.
- `core_grading_get_definitions` تأكّد نهائيًا أنها **لا** تُرجع نص المعايير: الاستجابة الخام لـ `cmid=1640` تحتوي `method='btec'`، `name='Sustainable Energy'`، `status=20` — ولا أي مفتاح `btec` أو مصفوفة معايير.

### د. ما بقي SQL-only فعليًا (النطاق المُقلَّص)

بعد ما سبق، الفجوة الوحيدة الباقية هي **جدولان فقط**:

| الجدول | ما نحتاجه منه | لماذا لا بديل |
|---|---|---|
| `mdl_gradingform_btec_criteria` | `shortname` (P1/M1/D1) + `description` (نص المعيار الكامل) + `sortorder` + `definitionid` | لا تكشفه أي دالة API؛ حاليًا نُحاكيه بملفات ثابتة في `sample_data/` مربوطة يدويًا بالمادة في `CRITERIA_FILE_BY_COURSE_KEY` |
| `mdl_gradingform_btec_fillings` (أو `_filling`) | `instanceid`، `criterionid`، `score`، `remark` | تفصيل حكم المدرّس **لكل معيار** — الحكم الكلي فقط هو المتاح عبر API (القسم 7-أ) |

الجداول الخمسة الأخرى المطلوبة في القسم 3-ب (`grading_areas`، `grading_definitions`، `grading_instances`، `assign_grades`، `assign`) **لم تبقَ ضرورية** — كلها صارت قابلة للسحب عبر API كما في 7-أ و7-ب. يمكن تقليص طلب صلاحية `SELECT` إلى الجدولين أعلاه فقط، وهو طلب أضيق بكثير وأسهل موافقةً من مدير النظام.

### هـ. ملاحظة على سلّم الدرجات: خطأ إملائي في إعداد الموقع

سلّم BTEC على `elearning` يحمل خطأً في التسمية: المستوى 3 مكتوب **"Miret"** بدل "Merit" (مرصود حيًّا في `gradeformatted`). لهذا `fetch_btec_verdicts()` تستنتج الحكم من `graderaw` الرقمي (3 → `MERIT`) ولا تثق بالنص، مع الاحتفاظ بالنص الأصلي في `verdict_label` للعرض فقط. أي تصحيح للخطأ في Moodle لاحقًا لن يكسر شيئًا.

---

## 8. ما هو مبني فعليًا الآن (كود، مُختبَر)

| المكوّن | الملف | الحالة |
|---|---|---|
| وحدة SQL للقراءة فقط | `app/extractor/moodle_db.py` | ✅ مبنية، تعمل بلا اتصال (تُبلّغ "not configured" بدل الانهيار) |
| سلسلة تقييم BTEC عبر API | `app/extractor/sync.py` | ✅ مبنية ومتحقَّق منها **حيًّا** على بيانات إنتاج |
| ترجيح القاعدة على الملفات الثابتة | `app/extractor/importer.py:resolve_criteria` | ✅ مبني، يرجّح SQL ثم يسقط للملف |
| أداة تشخيص | `scripts/check_moodle_db.py` | ✅ أمر واحد يُثبت أن الوصول يعمل ويحسم اسم جدول fillings |
| اختبارات | `tests/test_moodle_db.py`, `tests/test_btec_grading_chain.py` | ✅ 40 اختبارًا جديدًا، الحصيلة 92 ناجحًا |

### عقد السلامة في `moodle_db.py` (لا يجوز إضعافه)

1. `_query()` ترفض أي جملة ليست `SELECT`/`SHOW` — الحرس يعمل **قبل** فتح أي اتصال، فحتى تعديل مستقبلي بحسن نيّة ("تحديث واحد فقط لتعليم المزامنة…") يفشل بصوت عالٍ.
2. `autocommit=False` — لا شيء يمكن أن يُثبَّت.
3. كلمة المرور لا تُسجَّل ولا تظهر في أي رسالة خطأ ولا في `describe_config()` (حتى طولها محجوب).
4. `mdl_user` لا يُستعلم إطلاقًا — أسماء الطلاب تأتي من API.

### مبدأ الـ Snapshot محفوظ

`get_or_create_snapshot()` تُرجع snapshot موجودًا كما هو دون لمسه (`source="existing"`). أي أن تفعيل وصول SQL **لا يعيد كتابة معايير تقييمات ماضية** — التقييم القديم يبقى مفهومًا مقابل نص المعايير الذي صُحّح عليه فعلاً.

### الشفافية للمدرّس

`sync_course()` تُرجع الآن `criteria_source` بإحدى القيم: `moodle_sql:def=<id>` أو `fixture:<file>` أو `existing` أو `none`، وواجهة `1_Units.py` تُظهر تنبيهًا صريحًا عند الاعتماد على ملف محلي — فلا يحدث أن يثق مدرّس بتقييم مبني على نص معايير قديم دون أن يعلم.

### ما يتبقّى لتشغيل مسار SQL

الخطوة الوحيدة الباقية **ليست كودًا**: قاعدة Moodle مربوطة بـ `localhost` على السيرفر، والمفتاح الخاص لـ SSH **غير موجود على جهاز التطوير** (`~/.ssh/` يحتوي `known_hosts` فقط)، فلا يمكن فتح النفق من هنا. المطلوب:

```bash
# على جهاز التطوير — توليد مفتاح محلي
ssh-keygen -t ed25519 -C "btek-dev-tunnel" -f ~/.ssh/btek_tunnel

# على السيرفر — إضافة المفتاح العام مقيَّدًا بتمرير منفذ MariaDB فقط
# في ~/.ssh/authorized_keys للمستخدم المخصص للنفق:
restrict,permitopen="127.0.0.1:3306" ssh-ed25519 AAAA... btek-dev-tunnel

# على جهاز التطوير — فتح النفق (يبقى مفتوحًا أثناء العمل)
ssh -N -i ~/.ssh/btek_tunnel -L 3307:127.0.0.1:3306 <tunnel-user>@<server>
```

ثم في `.env`: `MOODLE_DB_HOST=127.0.0.1` و `MOODLE_DB_PORT=3307` وبقية قيم `MOODLE_DB_*`، وتشغيل `scripts/check_moodle_db.py`.

## 8. الوصول ممنوح ومُثبَت حيًّا (2026-08-27)

انتهى الجزء التنظيمي. الخادم `195.35.25.188` (CloudPanel) يستضيف **الموقعين**،
وكلٌّ منهما بقاعدة مستقلة:

| | elearning (الحقيقي) | lms (الاختبار) |
|---|---|---|
| `config.php` | `/home/abchorizon-elearning/htdocs/elearning.abchorizon.com/` | `/home/abchorizon-lms/htdocs/lms.abchorizon.com/` |
| `dbname` | **`dbelearning`** | `moodle_db` |
| إصدار Moodle | 5.0.2 | 5.1.1 |
| بادئة الجداول | `mdl_` | `mdl_` |
| صفوف معايير BTEC | **15,298** | 1,459 |
| نماذج BTEC | **331** | 102 |
| مقررات | 225 | 497 |

الحساب: `btec_ro` بصلاحية **SELECT فقط** على `dbelearning` و`moodle_db`
و`btec_fixture`. لا صلاحية كتابة إطلاقًا.

### ⚠️ فخّان مُثبَتان عمليًا — لا يجوز نسيانهما

**١. الصلاحية تحتاج `localhost` وليس `127.0.0.1` فقط.**
`skip_name_resolve=OFF` على هذا الخادم، فالاتصال الوارد عبر النفق على
`127.0.0.1` يراه MariaDB باسم **`localhost`**. المنح على `'btec_ro'@'127.0.0.1'`
وحده يفشل برسالة `Access denied` مضلِّلة. المنح الصحيح على **الاثنين**:

```sql
GRANT SELECT ON dbelearning.* TO 'btec_ro'@'localhost';    -- الأساسي
GRANT SELECT ON dbelearning.* TO 'btec_ro'@'127.0.0.1';
```

**٢. `MOODLE_DB_NAME` يجب أن يطابق الموقع الذي جاء منه `definition_id`.**
مُثبَت بالاستعلام المباشر: `definition_id=16005` موجود في `dbelearning`
(«Sustainable Energy»، `method=btec`، `status=20`، **12 معيارًا**:
P1-P6 / M1-M3 / D1-D3)، ويُرجع **صفر صفوف** في `moodle_db`. والخطورة أن الفشل
**صامت**: `resolve_criteria()` في `app/extractor/importer.py` تبتلع الخطأ وترجع
إلى ملف `sample_data/`، فيظن المستخدم أن الربط الحقيقي يعمل وهو يقرأ ملفًا
محليًا. يكشف ذلك حقل `criteria_source` (`moodle_sql:def=…` مقابل `fixture:…`).

هذا قيد معماري قائم: `MOODLE_DB_*` إعداد **واحد**، بينما
`app/extractor/moodle_client.py` يعرّف عميلين (`default_client`=elearning و
`lms_client`=lms). العمل على الموقعين معًا يتطلب قاعدة لكل موقع.

### ملاحظة على استعلامات الاستكشاف (لا تمسّ كودنا الحالي)

عند تعداد نماذج التقييم، المرور عبر `context(70) → course_modules → assign`
يُسقط النماذج على مستوى النظام (`contextlevel 10`) — 100 من أصل 331 في
`dbelearning`. الصحيح `LEFT JOIN` من `grading_definitions`.

**لا ينطبق على `app/extractor/moodle_db.py`**: استعلاماه يرشّحان
`gradingform_btec_criteria` على `definitionid` مباشرة بلا أي join عبر
`context`، و`definition_id` يأتي من `core_grading_get_definitions(cmids=[…])`
أي مرتبطًا بتكليف بالضرورة — فالقوالب على مستوى النظام خارج النطاق المقصود
أصلًا، لأننا نصحّح تكليفات فعلية لا قوالب.

### ما تبقّى: النفق فقط

المنفذ `3306` محجوب من الخارج (مُثبَت: `TimeoutError`)، و`22` مفتوح. لا يوجد
مفتاح SSH خاص على جهاز التطوير (`~/.ssh` فيه `known_hosts` فقط) — ومفتاح
`ealert-server` نصفه الخاص على **الخادم** لا على جهاز التطوير. فالنفق يُفتح
بكلمة مرور من جهاز التطوير:

```bash
ssh -f -N -L 3307:127.0.0.1:3306 root@195.35.25.188
```

`-f` تُرسل الاتصال للخلفية **بعد** المصادقة، فيبقى إدخال كلمة المرور ممكنًا.
ثم `.venv/Scripts/python.exe scripts/check_moodle_db.py`.

---

⚠️ **تحذير على القاعدة الصحيحة**: بيانات BTEC الحقيقية على **elearning**، أما `moodle_db` في إعداد `lms.abchorizon.com` فهي قاعدة موقع الاختبار. توجيه `MOODLE_DB_NAME` لقاعدة `lms` سيُرجع صفر معايير للتعريف `16005` (لأنه معرّف من elearning) — وهذا بالضبط ما تكشفه الخطوة 4 في أداة التشخيص.
