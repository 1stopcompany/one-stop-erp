# Stage 3 — تجهيز ونقل One Stop ERP إلى MySQL

## نطاق الحزمة

هذه الحزمة لا تعدّل أي Model أو Migration. وهي تضيف:

- اختيار قاعدة البيانات من ملف `.env`: إما `sqlite` أو `mysql`.
- إعداد MySQL باستخدام `utf8mb4` و`STRICT_TRANS_TABLES` و`READ COMMITTED`.
- تعريف منفصل لقاعدة الاختبارات.
- ملف متطلبات MySQL باستخدام `mysqlclient==2.2.8`.
- أمر `database_inventory` لمقارنة عدد السجلات قبل النقل وبعده.
- ملفات مساعدة لتصدير بيانات SQLite واستيرادها إلى MySQL.

## 1. تطبيق الحزمة

انسخ محتويات الحزمة إلى جذر المشروع ووافق على استبدال الملفات. لا تستبدل `db.sqlite3`.

ثم نفّذ:

```bat
venv\Scripts\activate
pip install -r requirements-mysql.txt
py manage.py check
py manage.py test
```

في هذه المرحلة يبقى `DB_ENGINE=sqlite`، ولذلك يجب أن تستمر الاختبارات على قاعدة SQLite الحالية.

## 2. إنشاء قاعدة MySQL

افتح:

```text
scripts/mysql_setup.sql
```

غيّر `CHANGE_THIS_PASSWORD` إلى كلمة مرور قوية، ثم نفّذ الملف داخل MySQL Workbench باستخدام مستخدم إداري.

## 3. تصدير SQLite

تأكد أن ملف `.env` يحتوي:

```env
DB_ENGINE=sqlite
SQLITE_PATH=db.sqlite3
```

ثم من جذر المشروع:

```bat
scripts\01_export_sqlite_data.bat
```

يُنشئ هذا الأمر:

- `db_before_mysql.sqlite3`
- `sqlite_inventory.json`
- `sqlite_data.json`

ولا يحذف أو يعدّل قاعدة SQLite الأصلية.

## 4. التحويل إلى MySQL

انسخ إعدادات `.env.mysql.example` إلى ملف `.env`، وضع نفس كلمة المرور المستخدمة في MySQL:

```env
DB_ENGINE=mysql
DB_NAME=one_stop_erp
DB_USER=one_stop_user
DB_PASSWORD=YOUR_PASSWORD
DB_HOST=127.0.0.1
DB_PORT=3306
DB_TEST_NAME=test_one_stop_erp
```

ثم نفّذ:

```bat
scripts\02_import_mysql_data.bat
```

ينفذ السكربت بالتسلسل:

1. فحص اتصال Django بقاعدة MySQL.
2. إنشاء الجداول عبر Migrations الحالية.
3. تحميل بيانات SQLite.
4. مقارنة عدد السجلات لكل Model.
5. تشغيل الاختبارات الآلية على MySQL.

## 5. الرجوع الفوري إلى SQLite

عند ظهور أي مشكلة، أعد في `.env`:

```env
DB_ENGINE=sqlite
SQLITE_PATH=db.sqlite3
```

ثم نفّذ:

```bat
py manage.py check
py manage.py runserver
```

قاعدة SQLite تبقى محفوظة، لذلك الرجوع لا يحتاج استعادة بيانات.

## تنبيهات

- لا تنفذ `flush` على قاعدة SQLite.
- لا تنسخ `db.sqlite3` فوق أي ملف آخر.
- لا تشغّل سكربت الاستيراد مرتين على قاعدة MySQL تحتوي البيانات؛ قد تظهر قيود تكرار.
- عند إعادة التجربة من الصفر، احذف قاعدة `one_stop_erp` وأعد إنشائها، ثم نفّذ `migrate` و`loaddata` مرة واحدة.
