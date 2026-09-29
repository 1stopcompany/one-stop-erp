# Stage 2 Installation and Test Steps

## 1. Back up the current working source

From the ERP project folder:

```bat
copy db.sqlite3 db_before_stage2_patch.sqlite3
```

## 2. Apply the patch

Extract the Stage 2 patch into the ERP project root and allow Windows to replace files. The patch does not contain `db.sqlite3`.

## 3. Create the local environment file

Only when `.env` does not already exist:

```bat
copy .env.example .env
```

Open `.env` and replace `DJANGO_SECRET_KEY` with a long random value. Keep the same value between restarts so existing sessions remain valid.

## 4. Verify the project

```bat
venv\Scripts\activate
pip install -r requirements-sqlite.txt
py manage.py check
py manage.py makemigrations --check --dry-run
py manage.py test
```

Expected results:

```text
System check identified no issues
No changes detected
Ran 11 tests
OK
```

The test runner creates and deletes a separate temporary test database. It does not modify the working `db.sqlite3` data.

## 5. Run the ERP

```bat
py manage.py runserver
```

Review the following areas:

- User list, user creation, and profile.
- Project floors.
- Procurement lists, forms, and detail pages.
- Cost Control lists, forms, dashboards, and chart APIs.
- Timesheets geofences and location pages.
- Logout from the top-right user menu.
