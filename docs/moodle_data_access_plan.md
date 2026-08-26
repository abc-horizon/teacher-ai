# خطة الوصول لبيانات معايير BTEC في Moodle

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
