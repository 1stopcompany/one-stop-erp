# Stage 3.2 — تصحيح مقارنة بيانات MySQL

سبب التوقف أن سكربت التصدير يستبعد عمدًا السجلات التالية من ملف النقل:

- `admin.logentry`
- `sessions.session`
- `auth.permission`
- `contenttypes.contenttype`

لكن أداة المقارنة القديمة كانت لا تزال تقارن بعضها، لذلك ظهر اختلاف في:

- `admin.logentry`: قبل 6 وبعد 0
- `sessions.session`: قبل 2 وبعد 0

هذه ليست خسارة في بيانات المشاريع أو المستخدمين أو المشتريات. الجلسات مؤقتة، وسجلات Django الإدارية مستبعدة من ملف النقل أصلًا، بينما الصلاحيات وأنواع المحتوى يعاد إنشاؤها بواسطة migrations.

## التطبيق

انسخ مجلدي `core` و`scripts` إلى جذر مشروع ERP ووافق على الاستبدال.

لا تعِد تشغيل `02_import_mysql_data.bat`؛ البيانات تم تحميلها بالفعل.

نفّذ فقط:

```bat
scripts\03_verify_mysql_migration.bat
```

النتيجة المطلوبة:

```text
Inventory comparison passed ...
Ran 11 tests
OK
MySQL data verification and tests completed successfully.
```
