# Stage 4 — البنية المشتركة لتتبع تقدم المشروع (BOQ هرمي + سجل أحداث)

## الهدف من هاي الحزمة

هاي الخطوة الأولى ضمن خطة تطوير وحدة `reports` لتغطية:
- التقرير اليومي (Daily Site Report)
- التقرير الشهري لـ EDGE
- التقرير الفني والمالي الشهري للمالك

الثلاثة كلهم بيحتاجوا نفس الأساس: (1) جدول "تفصيل الإنجاز حسب البنود" بنسب
وزنية من قيمة العقد، و(2) سجل موحّد للأحداث/التأخيرات/RFI/NCR. هاي الحزمة
تضيف هاد الأساس بس — **ما زالت ما بتعدل** نماذج/واجهات التقرير اليومي أو
الشهري نفسها؛ هاد الشغل جاي بمرحلة تانية.

## شو المضاف

### 1. `reports/progress_models.py` (جديد)

- **`ProjectPhase`** — البند الرئيسي (مثال: "أعمال القواعد والجسور الرابطة")
  بنسبة وزنية من قيمة العقد الكلية.
- **`ProjectPhaseSubItem`** — البند الفرعي تحت كل بند رئيسي (نسبته الوزنية
  أيضاً من قيمة العقد الكلية، ومجموع نسب البنود الفرعية = نسبة البند الرئيسي).
- **`ProjectPhaseProgressEntry`** — قراءة نسبة إنجاز تراكمية لبند فرعي
  بتاريخ معيّن (ممكن تُربط بتقرير يومي أو شهري اختيارياً).
- **`calculate_project_progress(project, as_of_date, contract_value)`** —
  دالة جاهزة بترجع: نسبة الإنجاز الكلية للمشروع + تفصيل لكل بند رئيسي
  (نسبة تنفيذه + قيمته المالية المُنجزة) + كل بند فرعي — نفس شكل جدول
  "10. BOQ Progress Breakdown by Item" بتقرير EDGE، وجدول "نسبة الإنجاز
  الحالية" بتقرير المالك، بالضبط.

تم اختبار الحساب فعلياً ببيانات مشروع طالب العمايرة الحقيقية: بند
"التصميم والترخيص" (6%) و"الحفريات" (4%) عند اكتمالهم 100% بيطلعوا
492,000 و328,000 شيكل — نفس الأرقام الموجودة بالتقرير الفعلي بالضبط.

### 2. `reports/site_event_models.py` (جديد)

**`SiteEvent`** — سجل موحّد لـ: Delay / Site Instruction / RFI / NCR /
HSE Incident / Near Miss. كل حدث مرتبط بالمشروع (وبالتقرير اليومي اللي
اتسجل فيه لو موجود)، وفيه: المرجع، الوصف، الإجراء المطلوب، المسؤول
(مستخدم داخلي أو جهة خارجية نصياً)، تاريخ الاستحقاق، الحالة، الأثر
الزمني بالساعات.

فيه دالتين جاهزتين للاستخدام بالتقرير الشهري لاحقاً:
- `SiteEvent.for_period(project, start, end)` — كل الأحداث بفترة معيّنة.
- `SiteEvent.hse_summary_for_period(...)` — عدّاد جاهز لقسم HSE
  (حوادث، Near Miss، إجراءات تصحيحية مفتوحة/مغلقة).

### 3. حقل `contract_value` على `Project`

مطلوب لتحويل النسب المئوية لمبالغ مالية (تقرير المالك تحديداً). اختياري
(`null=True`) حتى ما يأثر على مشاريع موجودة بدون قيمة عقد مسجّلة.

## إصلاحات جانبية (اكتشفتها أثناء الشغل، مش إضافات جديدة)

لاحظت وأصلحت مشكلتين موجودتين مسبقاً بالكود:

1. **`master_data_admin.py` و`email_admin.py` ما كانوا مسجلين إطلاقاً
   بلوحة إدارة Django.** الملفين موجودين وفيهم كود كامل (WorkforceCategory,
   LaborClassification, EquipmentMaster, BillOfQuantities القديم,
   EmailReminder...) لكن Django ما بيكتشف غير `admin.py` تلقائياً، وما
   كان في استيراد لهذول الملفين من أي مكان — يعني كانوا "كود ميت" من
   يوم ما انكتبوا. تم ربطهم الآن من `reports/admin.py`.

2. **تعارض اسم:** موديل `BillOfQuantities` بوحدة `reports` (لتسجيل
   استهلاك المواد اليومي) كان عنده نفس الاسم بالظبط زي موديل
   `BillOfQuantities` الموجود أصلاً بوحدة `procurement` (BOQ الرسمي
   المرتبط بالمشتريات والتسعير)، وكانوا بيستخدموا نفس `related_name`
   ('boq_items') على Project — هذا كان رح يمنع أي Migration جديدة من
   الشغل بمجرد ما حاولت أربط `master_data_models.py` بالتطبيق. تم تغيير
   اسمه إلى **`ReportMaterialItem`** (مع تحديث كل الإشارات إله بـ
   `structured_forms.py` و`master_data_admin.py`) لأنه مفهوم مختلف تماماً
   عن BOQ المشتريات الرسمي.

نتيجة هالإصلاحين: كل نماذج "Master Data" (فئات العمالة، المعدات،
البنود اليومية) بقت شغالة فعلياً لأول مرة — قبل هيك كانت موجودة بالكود
بس مالها جداول بقاعدة البيانات.

## طريقة التطبيق

1. انسخ محتويات هاي الحزمة إلى جذر مشروع ERP ووافق على استبدال الملفات:
   - `reports/progress_models.py` (جديد)
   - `reports/site_event_models.py` (جديد)
   - `reports/progress_admin.py` (جديد)
   - `reports/admin.py` (معدّل)
   - `reports/models.py` (معدّل)
   - `reports/master_data_models.py` (معدّل — إعادة تسمية فقط)
   - `reports/master_data_admin.py` (معدّل — إعادة تسمية فقط)
   - `reports/structured_forms.py` (معدّل — إعادة تسمية فقط)
   - `reports/migrations/0002_equipmentmaster_workforcecategory_and_more.py` (جديد)
   - `projects/models.py` (معدّل)
   - `projects/migrations/0002_project_contract_value.py` (جديد)

2. فعّل البيئة الافتراضية ونفّذ:

   ```bat
   venv\Scripts\activate
   py manage.py check
   py manage.py migrate
   ```

   بما إن `.env` عندك مضبوط أصلاً `DB_ENGINE=mysql`، الأمر رح يشتغل
   مباشرة على قاعدة MySQL الحالية بدون ما يلمس أي جدول موجود — كل
   العمليات هنا "إضافة" فقط (نماذج وحقول جديدة)، ما في أي حذف أو تعديل
   لبيانات موجودة.

3. تأكد النتيجة:

   ```bat
   py manage.py check
   ```

   المفروض تطلع "System check identified no issues".

## طريقة الاستخدام (تجريبياً من لوحة الإدارة)

1. افتح `/django-admin/` → **Project Phases** → أضف بند رئيسي لمشروع
   (مثلاً: كود "1"، الاسم "التصميم والترخيص"، نسبة 6.000) وأضف بنوده
   الفرعية من نفس الصفحة (inline).
2. أضف قراءات تقدم من **Phase Progress Entries** لكل بند فرعي (نسبة
   تراكمية بتاريخ معيّن).
3. أضف قيمة العقد لمشروعك من صفحة **Projects** (حقل Contract value).
4. من كود بايثون أو shell:

   ```python
   from reports.progress_models import calculate_project_progress
   from projects.models import Project

   project = Project.objects.get(project_symbol='OSA-F')
   result = calculate_project_progress(project, contract_value=project.contract_value)
   print(result['overall_percentage'])   # نسبة الإنجاز الكلية للمشروع
   for row in result['phases']:
       print(row['phase'], row['execution_percentage'], row['earned_value'])
   ```

   هاد بالضبط الشكل اللي رح تُبنى عليه جداول "BOQ Progress Breakdown"
   بتقرير EDGE، والجدول المالي بتقرير المالك، بالمرحلة الجاية.

5. سجّل أحداث/تأخيرات من **Site Events** — كل حدث مرتبط بمشروع
   وبتقرير يومي اختيارياً.

## الخطوة الجاية المقترحة

بعد ما تتأكد إن هاي البنية شغالة عندك، الخطوة المنطقية التالية (حسب
الخطة اللي تحكينا فيها) هي وحدة **التقرير اليومي** نفسها: عمالة بالاسم
مع أوقات دخول/خروج، قسم QA/QC & HSE، وخطة اليوم التالي — وربطها
بموديلات `SiteEvent` و`ProjectPhaseProgressEntry` الجديدة عشان تتغذى
منها مباشرة.
