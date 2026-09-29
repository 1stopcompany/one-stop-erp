# One Stop ERP — Stage 2 Change Log

## Scope

Stage 2 stabilizes the current SQLite/Django application before any MySQL work. It does not add or alter database models, tables, or migrations.

## Configuration and environment

- `config/settings.py` now loads `.env` automatically through `python-dotenv` before reading Django settings.
- Added reusable boolean and comma-separated environment-variable parsers.
- Added a production safeguard: Django refuses to start with the development secret key when `DJANGO_DEBUG=False`.
- `config/__init__.py` no longer installs PyMySQL globally or contains a stray MySQL `DATABASES` definition.
- Celery startup is optional, so local Django checks can run even when Celery is not installed.
- Updated `.env.example` for safe local setup.
- Windows and Linux startup scripts now install `requirements-sqlite.txt`, not the MySQL requirements file.
- Removed demo passwords from startup-script output.

## Authentication and access control

- Fixed the main navigation logout action to submit a POST request, matching the POST-only logout view.
- Added `LoginRequiredMixin` to procurement item create and update views.
- Updated the footer year to render dynamically.

## URL and template stability

- Retained the Cost Control chart API and report-detail route fix.
- Added the missing lowercase Procurement dashboard template for Linux compatibility.
- Added missing routed templates for:
  - User management and profile.
  - Project floors.
  - Report project selection and monthly approval.
  - Procurement BOQ, PR, PO, vendors, receipts, details, and deletion confirmation.
  - Cost Control budgets, forecasts, reports, alerts, forms, and deletion confirmation.
  - Timesheets login, documents, notes, geofences, location tracking, and location history.
- Reworked the shared procurement form so item-code JavaScript runs only on Item Master forms. It no longer throws JavaScript errors on BOQ, PR, PO, vendor, or receipt forms.
- Corrected Timesheets templates to use the actual view context and model field names.

## Automated regression tests

Added 11 Django test methods covering:

- Root and dashboard redirects.
- Main authenticated ERP pages and module dashboards.
- Anonymous access protection.
- Login, invalid login, POST-only logout, and audit-log creation.
- Cost Control dashboard rendering.
- Cost Control chart URL registration and missing-project validation.

The page smoke test covers 48 named routes using subtests.

## Validation performed

- Python syntax compilation completed successfully across the project.
- Static template-reference audit found no missing templates among the currently routed Stage 2 views.
- The unused `procurement/views_materials.py` prototype remains outside `procurement/urls.py`; its prototype templates were not activated in this stage.

## Database impact

- No model changes.
- No migration files added.
- Do not run `makemigrations` for this patch.
- Existing SQLite data is not included or replaced by this patch.
