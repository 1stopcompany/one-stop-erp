# One Stop ERP — Stage 1 Stabilization

Database migration to MySQL is intentionally deferred. SQLite remains the working database for this stage.

## Completed fixes

- Removed duplicate `UserListView` and `UserDetailView` definitions.
- Removed use of Django's default `User` model; the project now consistently uses `accounts.CustomUser`.
- Corrected namespaced redirects for user management.
- Corrected project URL names and floor redirects.
- Rebuilt project cost summary API against the actual `cost_control.Budget` relationship and fields.
- Removed the obsolete `projects.MonthlyReport` model, which had no database table and conflicted with the reporting module.
- Project details now load monthly reports from `reports.MonthlyReport`.
- Removed broken nested API classes from `projects.views`.
- Fixed Timesheets redirects, permissions, duplicate imports, and access protection for sensitive views.
- Rebuilt location check-in, check-out, location update, and geofence service logic.
- Fixed report project selection that referenced a nonexistent `site_engineers` field.
- Corrected invalid report URL names in templates.
- Moved Django security-sensitive settings to environment variables with safe local defaults.
- Removed `celery` from `INSTALLED_APPS`; Celery remains an external dependency/service.
- Added `.env.example`, `.gitignore`, and `requirements-sqlite.txt`.
- Changed the dashboard copyright year to a dynamic year.

## Validation performed

- All Python source files compile successfully.
- No duplicate top-level classes or functions remain.
- Existing SQLite database was preserved; a Stage 1 backup copy is included.

## Runtime validation still required on the project machine

```bash
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements-sqlite.txt
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py runserver
```

Do not run new migrations until the output of `makemigrations --check --dry-run` has been reviewed.
