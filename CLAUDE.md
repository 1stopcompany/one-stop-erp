# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

One Stop ERP is a Django monolith for a construction/contracting company, covering HR & GPS-based
timesheets, procurement, cost control, CRM, safety, equipment, subcontractors, accounting, and
daily/monthly site reporting. There is no `.git` repository initialized in this checkout.

## Commands

**Setup**
```bash
pip install -r requirements.txt      # installs Django 5.2.4, DRF, Channels, Celery, PyMySQL/mysqlclient, etc.
cp .env.example .env                 # then edit DB_ENGINE/DB_* or DJANGO_* values
python manage.py migrate
python manage.py createsuperuser
```
- `.env` selects the database via `DB_ENGINE=sqlite` or `DB_ENGINE=mysql` (see `config/settings.py`). With
  `mysql`, `DB_NAME`/`DB_USER`/`DB_PASSWORD` are required or startup raises `ImproperlyConfigured`.
  `.env.sqlite.example` / `.env.mysql.example` are ready-made templates for each backend; the checked-in
  `.env` currently points at MySQL. `requirements-sqlite.txt` / `requirements-mysql.txt` are the
  per-backend dependency subsets used by `run_windows.bat` / `run_linux.sh`.
- With `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` must be overridden from the insecure default or startup
  raises `ImproperlyConfigured`.

**Run**
```bash
python manage.py runserver
```
- `run_windows.bat` / `run_linux.sh` are convenience scripts: install `requirements-sqlite.txt`, run
  `check`/`migrate`/`collectstatic`, then `runserver`.

**Tests**
```bash
python manage.py test                          # all apps
python manage.py test reports                  # one app
python manage.py test reports.tests.SomeTestCase.test_method   # single test
```
- `pytest` / `pytest-django` are listed in `requirements.txt` but there is no `pytest.ini`/`pyproject.toml`
  configuring them — tests are actually Django `TestCase` subclasses in each app's `tests.py`, run via
  `manage.py test`, not `pytest`.

**Lint/format** (tools are in `requirements.txt`, no config files present, so defaults apply)
```bash
black .
isort .
flake8 .
```

**Other management commands**
```bash
python manage.py drf_create_token <username>   # issue a DRF auth token
python manage.py database_inventory            # core app
python manage.py seed_itemmaster               # procurement app
python manage.py load_master_data              # reports app
python manage.py send_reminders                # reports app (email reminder system)
```

## Architecture

- **`config/`** is the Django project package: `settings.py`, `urls.py` (top-level route table — one
  `include()` per app, each mounted at `/<app_name>/`), `wsgi.py`/`asgi.py`, `celery.py` (Celery app that
  autodiscovers `tasks.py` in every installed app), (the main dashboard is `core/views.py` -> `templates/erp_dashboard.html`, routed at `/Dashboard/`).
  - Celery is wired up in `config/celery.py` and tasks exist (`cost_control/tasks.py`,
    `procurement/tasks.py`), but `settings.py` sets no `CELERY_*` broker/backend config — treat async
    tasks as not actually runnable until that's added.
  - `config/asgi.py` only calls `get_asgi_application()`; it does not build a Channels
    `ProtocolTypeRouter`/`URLRouter`. `timesheets/routing.py` defines websocket consumers
    (`ws/location/`, `ws/employee/<id>/`) but they are not mounted anywhere, so the websocket endpoints
    documented in `README.md` are not actually live in this codebase as-is.
- **Custom user model**: `AUTH_USER_MODEL = 'accounts.CustomUser'` (`accounts/models.py`). Authorization
  throughout the codebase is done via `CustomUser.role` (`admin` / `project_manager` / `site_engineer`)
  and its `is_admin()`/`is_project_manager()`/`is_site_engineer()` helpers, not via Django groups/permissions.
- **App layout** (`INSTALLED_APPS` in `config/settings.py`): `core`, `accounts`, `projects`, `reports` are
  loaded first as shared/foundation apps; `procurement`, `cost_control`, `timesheets`, `crm`, `equipment`,
  `safety`, `subcontractors`, `accounting`, `blueprints` are the feature modules. Each feature app owns its
  own `models.py`, `urls.py`, `admin.py`, `migrations/`, and is mounted at a matching URL prefix in
  `config/urls.py`.
- **`reports/`** is the largest app and is not just `models.py` — daily/monthly report models are split
  across `models.py`, `progress_models.py` (BOQ phase/sub-item hierarchy + `ProjectPhasePhoto`),
  `master_data_models.py`, `site_event_models.py`, `daily_detail_models.py` (named-worker attendance,
  activity progress, QA/QC & HSE, next-day plan — the real daily site-report template's fields),
  `owner_financial_models.py` (owner payment report + material/equipment price tracking), and
  `structured_forms.py` (all in the same app/migration history), plus a separate email reminder subsystem
  (`email_models.py`, `email_service.py`, `email_templates.py`, `email_admin.py`). Each of these has a
  matching `..._admin.py` file imported into `admin.py` — when changing report data models, check the
  matching model **and** admin file, not just `models.py`. `BaseReport.report_date` (shared by Daily/Monthly/Owner
  Financial reports) is an ordinary editable field, not `auto_now_add` — a site engineer filling in the report the
  next morning sets it to the day the report actually covers; `created_at` (also on `BaseReport`, still `auto_now_add`)
  keeps the real filing timestamp regardless. `DailyReportForm` is the only one of the three that currently exposes
  `report_date` as a form field (the other two forms don't include it, so they still just take the model's default of
  today). **Outgoing email** (`EMAIL_HOST`/`EMAIL_HOST_USER`/
  `EMAIL_HOST_PASSWORD`/etc. in `.env`) is optional — unset, `EMAIL_BACKEND` defaults to printing emails to the
  console in dev (`DJANGO_DEBUG=True`) or silently dropping them in production, rather than failing; set real SMTP
  credentials to actually deliver reminder emails. `python manage.py check_overdue_daily_reports` (`--days N`,
  default 2; `--dry-run` to preview) emails a project's own site engineer when its most recent `DailyReport.report_date`
  is N+ calendar days old (or none exists yet) for every project `projects.readiness.ready_projects()` considers usable
  — reusing `EmailService.send_overdue_report_reminder` (an `overdue`-type `ReminderTemplate`, auto-created with a
  plain default the first time this command runs if none exists yet, editable in Admin) rather than the older generic
  `send_reminders`/`EmailReminder` schedule system, whose `send_batch_reminders` filters recipients by a
  `CustomUser.is_site_engineer` field that doesn't exist (role is a `role` choice + `is_site_engineer()` method) and
  would raise `FieldError` if actually invoked — a pre-existing bug, left alone since `check_overdue_daily_reports`
  doesn't go through it. Neither command runs on a schedule by itself (no Celery broker configured, see below) — an
  OS-level scheduler (Windows Task Scheduler / cron) needs to call it periodically. `DailyReportActivityProgress` and
  `ProjectPhaseProgressEntry` are kept in sync automatically (see `DailyReportActivityProgress.save()`);
  `OwnerFinancialReport`'s payment formula (`amount_due()` etc.) is reverse-engineered from and verified
  against a real signed report — see the docstring in `owner_financial_models.py` before changing it.
  `python manage.py seed_daily_report_demo` (`reports/daily_report_demo.py`, DEMOCC only; `--clear` to remove) seeds six
  daily reports spanning the whole draft → submitted → engineering_approved → approved/rejected workflow, each with every
  section the Daily Report page renders (workforce, equipment, activities, materials, visitors, photo attachments,
  BOQ-linked activity progress, named worker attendance, QA/QC & HSE, site events, next-day plan); its activity-progress
  figures line up with the seeded schedule's A3005/A3010. `generate_daily_report_pdf` (`reports/utils.py`) prints the Daily
  Report in the real company template's shape (form OS-FRM-SITE-DR-02): bilingual Arabic/English, portrait A4, Times New
  Roman, section-accent colors plus RAG status coloring, the same seven numbered sections in the same order, with
  `DailyReportWorkerAttendance` rows grouped and subtotalled by `labor_classification` (trade) in section 2 —
  `add_daily_worker_attendance`/`edit_daily_worker_attendance` (`reports/api_views.py`) reject a row with no trade
  selected (400) so that grouping stays meaningful; the field itself stays nullable on the model so historical/imported
  rows aren't broken. Section 1's table also prints each activity's BOQ sub-item and linked crew(s); section 2's prints
  each worker's crew, and section 3B's (Plant & Equipment) prints which activity each piece of equipment was used for
  -- all the same data the web page's tables show, kept in sync as a matter of course. The "Today's Labor Cost vs.
  Productivity" table (`daily_labor_productivity_summary`, same crew grouping and cost estimate as the web page's own
  copy under Worker Attendance -- see above) prints right after section 2's subtotals. When adding columns to a
  `hdr_table` in this function, keep the narrowest column's ratio at 0.035+ of `page_width` (roughly 19pt+) --
  reportlab's `Paragraph.wrap()` throws a `LayoutError` with a nonsensical multi-billion-point cell height for a header
  label wrapped into a column only a few points wide, rather than a normal "text too long" failure, which was hit and
  fixed while adding these columns. A Site Photo Log annex (the report's own `ReportAttachment` photos, videos and "other" attachments
  -- non-photo ones as a captioned placeholder box since they aren't a displayable image) prints at the end, followed by
  its own separate "ANNEX — SUPPORTING DOCUMENTS" page for `attachment_type='document'` rows specifically (listed by
  description/location/date, not embedded as an image) rather than mixed into the photo grid. When that document is
  itself a PDF, its actual pages are merged into the generated report (via PyMuPDF/`fitz`, already a dependency for the
  AI assistant's document reading) right after a divider page naming it, so the printed report carries the document
  itself and not just a reference row -- a non-PDF upload (Word, image, ...) or a PDF that fails to open stays listed
  in the table only. The header's
  KPI strip (Workers / Man-Hours / Activities / Equipment / Open Issues) is drawn as small flat vector icon badges
  (`_kpi_icon()`) rather than an emoji or an external icon font, so it renders identically on any machine reportlab runs
  on. The Man-Hours card itself splits into Staff vs. Workers hours (`kpi_split_card()`), computed from each attendance
  row's `labor_classification.category.is_staff_category` (`master_data_models.WorkforceCategory`; "Project Management" is
  seeded as staff, "Work Force"/"عمالة عامة" are not — set/changed from the Admin panel, no code change needed for a new
  category). `DailyReport.work_hours_note` is a free-text note the site engineer can also set (inline-edited on the detail
  page, same pattern as `remarks`, via `reports:api_update_daily_work_hours_note`) for anything the staff/workers split
  alone doesn't capture — printed in a highlighted box right under the manpower table. The Daily Report detail page's own
  "Workforce" section (aggregate category/designation/count, `DailyWorkForce`) was removed from the UI as a duplicate of
  the named worker-attendance table in section 2, which is the real source of manpower data on the form; `DailyWorkForce`
  itself was NOT deleted, since `reports/services/monthly_report_generator.py` still aggregates its historical
  `workforce_total` figures into monthly executive-summary text — old rows keep reading correctly with no code change.
  `DailyEquipment` is chosen from `EquipmentMaster` (`equipment_master` FK, required going forward) rather than typed as a
  free-text name, and linked to one of the report's own `DailyReportActivityProgress` entries (`activity` FK, nullable via
  `SET_NULL`) via the "Used For (Activity)" field, so equipment usage stays tied to real master data and a specific piece
  of logged work rather than floating on its own; `equipment_name` is auto-populated from `equipment_master` on save and
  kept only so pre-existing rows from before this list existed still display. `add_daily_equipment`
  (`reports/api_views.py`) requires both fields (400 if either is missing).
  **Layout**: the report's nine child-record sections (Activity Progress, Worker Attendance, Equipment, Materials,
  Visitors, Attachments, QA/QC & HSE, Site Events, Next Day Plan) render as one Bootstrap accordion
  (`#dailyReportSectionsAccordion`) instead of always-expanded cards stacked down the page, in that order by default
  (Activity Progress first since its BOQ-linked activities are what Crews and worker attendance actually link to — see
  below) — Activity Progress open, the rest collapsed; each section's own "Add" button moved from its old card-header
  into the top of its `accordion-body` since a header can't nest a second button inside the accordion's own toggle
  button. The old free-text "Daily Activities" section (`DailyActivity`, Type/Location/Description, no BOQ link) was
  removed from the page as a duplicate of Activity Progress (`DailyReportActivityProgress`, the real BOQ-linked one) --
  `DailyActivity` itself is kept, unreachable from the UI now, only because `reports/services/monthly_report_generator.py`
  still reads its historical rows into monthly narrative text; new reports simply never create new `DailyActivity` rows.
  **Reordering**: each section header has move-up/move-down buttons (next to, not inside, the accordion's own toggle
  button, which can't nest a second button); the resulting order saves per-user (`CustomUser.daily_report_section_order`,
  a JSON list of section keys) via `reports:api_save_daily_report_section_order`, and applies to every Daily Report that
  user opens, not just the one being viewed when it was reordered -- an unset preference falls back to the page's
  built-in default order above.
  **Worker attendance names come from a reusable roster, not free text**: `DailyReportWorkerAttendance.worker_name`
  must now be sourced from one of two real, reusable identities when a new row is added — an HR `timesheets.Employee`
  (the existing "HR Employee" picker) or `timesheets.DailyWorker`, the shared day-labor roster already used for
  cross-project payroll aggregation (`timesheets.services.daily_worker_payroll_service`) — `add_daily_worker_attendance`
  (`reports/api_views.py`) rejects a new row with neither set (400), and fills `worker_name` from whichever was picked.
  If the worker isn't on the roster yet, "+ Add New Worker" on the Add Worker Attendance modal opens a small form (name,
  national ID, trade, daily rate, and a required ID/identity document upload — `DailyWorker.id_document`, a `FileField`
  added for this) that POSTs to `reports:api_add_daily_worker` (not report-scoped; the roster is shared company-wide,
  the same one `timesheets:daily_worker_list`/`daily_worker_add` manages — that form and view were updated to handle
  the file too); on success the new worker is immediately selectable and attendance entry continues without losing the
  in-progress form. Editing an existing (possibly historical, free-text-only) row does NOT force this — `daily_worker`
  stays optional on edit so old rows aren't broken, but the Edit modal offers an optional "Link to Day-Labor Roster"
  picker to retroactively attach one. On Add (not Edit), the HR-employee and day-labor pickers are a single searchable
  "Worker *" text field (`workerSearchData`, a plain-JS combined+filterable list built from `project_employees` and
  `daily_workers`) instead of two separate always-visible `<select>`s — that split UI made it unclear which list to use
  and had no way to search a long roster by name; typing filters both lists together by substring, and picking a match
  sets whichever of the two hidden `employee`/`daily_worker` fields applies.
  **HR staff auto-list + auto-fill**: the HR-employee half of that search list is not limited to `Employee.project ==
  this project` — it also always includes the project's own manager and site engineer (matched via `Employee.user`),
  since their own HR record's `project` field is often unset even though they clearly belong on this project's report.
  Picking an HR employee also auto-fills Labor Classification (from `timesheets.Position.default_labor_classification`,
  an optional FK admin can set per position — seeded for Site Engineer/Project Manager/Office Engineer) and defaults
  Contractor/Company to "One Stop", since staff aren't subcontracted — so marking your own presence is really just
  pick-name-then-Add. **Crews**: `DailyReportCrew` (`reports/daily_detail_models.py`) is a named group of workers on one
  report — for a project big enough to have several crews working the same day — tied to one `DailyReportActivityProgress`
  (which of "Daily Works / Progress"'s logged activities it's executing) and, if subcontracted, to a `SubcontractorAgreement`
  for this project (its `contractor_name` auto-fills from `agreement.vendor.name`) or a plain typed contractor name for an
  in-house crew. `DailyReportWorkerAttendance.crew` (optional) puts a worker under one; its own `contractor_name`/
  `activity_location` are then always re-derived from the crew on save (`reports:api_add_daily_crew`, "+ Add New Crew" on
  the Add Worker Attendance modal) rather than typed per worker. A worker not part of any crew (e.g. HR staff marking
  their own presence solo) keeps typing/picking these directly as before. The Activity Progress table shows each row's
  linked crew(s) in its own "Crew(s)" column (`item.crews.all`, the reverse of `DailyReportCrew.activity`). A small
  "Crews on this report" table at the top of Worker Attendance (Name / Linked Activity / Contractor / Edit / Delete)
  lets a crew created before its activity was logged (or without one by mistake) be fixed after the fact --
  `reports:api_edit_daily_crew` re-saves every worker already under that crew too, so their own
  contractor_name/activity_location (and the cost-vs-productivity summary below) pick up the fix immediately rather
  than only applying to workers added after the edit. **Delete guards**: both `crew`->`activity` and
  `DailyReportWorkerAttendance`->`crew` are `SET_NULL`, not `CASCADE` -- nothing would technically vanish if a crew or
  an activity were deleted out from under what still points to it, but it would silently orphan that link rather than
  reading as a real choice. `reports:api_delete_daily_crew` refuses (400, with a count) while any worker attendance row
  is still under that crew; `reports:api_delete_activity_progress` refuses while any `DailyReportCrew` or
  `DailyEquipment` still links to that activity. Both ask for the dependents to be unlinked/removed first.
  **Labor cost vs. productivity**: `reports/services/daily_labor_summary.py::daily_labor_productivity_summary(report)`
  groups today's worker-attendance rows by their **crew** (a "No Crew" bucket for solo workers) rather than by activity
  directly, so a crew with no activity linked yet (or two different crews that happen to share one) still shows up by
  its own name instead of collapsing into one undifferentiated bucket; each crew's row still carries its own linked
  activity (if any) for that activity's `quantity_today`/`unit`. Pairs each crew's man-hours and an on-the-spot
  estimated labor cost (day laborer: `DailyWorker.hourly_rate` x hours; HR employee:
  `salary / salary_structure.monthly_working_hours` x hours, no overtime/weekend/holiday multipliers), shown as a small
  table under Worker Attendance ("Today's Labor Cost vs. Productivity") with Crew and Activity as separate columns plus
  a cost-per-unit column. This is a same-day cost signal for the report page, explicitly not a payroll figure — it
  doesn't reconcile against `timesheets.services.payroll_service`'s real payslip rules.
  **Activity history + auto-calculated cumulative**: "Add Activity Progress"'s `activity_description` is a searchable
  history picker (`activity_history` in the view context — one row per distinct activity name already used on this
  project, most recent first) instead of retyping the same activity fresh each day; typing still accepts a brand-new
  name freely. `quantity_cumulative` auto-calculates when left at 0
  (`DailyReportActivityProgress.cumulative_before(project, activity_description, report_date)`, an exact-name match
  summed fresh from every earlier report's `quantity_today` on this project — self-correcting even if an older row's
  cumulative was ever hand-edited) plus this entry's own `quantity_today`, the same "auto-fill only when left at
  default" rule `total_hours` already uses for worker attendance; an explicit nonzero value is still respected, so
  seeding/import code that sets it directly (`daily_report_demo.py`, `services/daily_report_excel_importer.py`) is
  unaffected.
- **`procurement/`** similarly splits into two concerns sharing one app/migrations: core procurement
  (vendors, BOQ, PR/PO — `models.py`, `forms.py`, `views.py`) and a material-tracking subsystem
  (`models_materials.py`, `forms_materials.py`, `serializers_materials.py`, `services_materials.py`,
  `views_materials.py`), documented separately in `MATERIAL_TRACKING_GUIDE.md`.
- **Project BOQ → cost control**: pricing lives on the project's own BOQ, NOT on catalogue items. `reports.ProjectPhase`
  (main item, with an optional `section`) and `ProjectPhaseSubItem` each carry `unit`, `quantity`, `budget_unit_price`
  (cost) and `contract_unit_price` (sell), edited in "Manage BOQ" (`templates/reports/boq_editor.html`,
  `reports/api_views.py`). Sub-items are the priced lines; a phase priced as a whole is carried by one automatic
  `is_whole` sub-item (`ProjectPhase.sync_whole_item()`) so progress can be recorded on it. Weights can be derived from
  contract prices (`recalculate_weights_from_contract`). Purchases are charged to a sub-item through the "BOQ item" on
  requisition/order lines (`PurchaseRequisitionLine.sub_item`, `PurchaseOrderLine.sub_item`). Everything Cost Control shows
  (committed = issued POs, actual = receipts at PO prices, earned value = budget × sub-item progress, CPI, forecast, unit
  cost) is computed live in `cost_control/services.py::project_cost_summary`; nothing is stored. The old item-level BOQ
  (`BillOfQuantities`) and its Budget sync were removed; `cost_control.Budget` and `CostForecast` are legacy and unused.
  `import_faten_boq` loads the FATEN tender BOQ (units and quantities) into the FTN project. **Subcontractor ("Musana'a")
  agreements** (`subcontractors/models.py`, second procurement track alongside PR→RFQ→PO): a `SubcontractorAgreement` is a
  signed contract with a `procurement.Vendor` (same vendor list as ordinary purchasing) who executes a defined scope of BOQ
  work — its `SubcontractorAgreementLine` rows each charge a `reports.ProjectPhaseSubItem` directly (no PR/RFQ step), and
  it's paid over time via `SubcontractorAgreementPayment` rather than received in one shot like a PO. Draft → Active (needs
  at least one line) → Completed/Terminated (`subcontractors/views.py::agreement_status_update`); only a draft/active
  agreement counts as committed. `subcontractors/services.py::spending_by_sub_item` feeds committed (= each line's value)
  and actual (= payments so far, prorated across an agreement's lines by their share of its total value, since a Musana'a
  payment is certified against overall progress rather than booked per line) into `cost_control`'s own
  `spending_by_sub_item`, so an agreement shows up in Cost Control exactly like a PO does. Managed from the project page
  ("BOQ & Cost" dropdown) and `subcontractors:agreement_list`; same permission as the workflow pages (admin, engineering
  manager, or that project's own manager); `subcontractors:agreement_list` groups agreements by project (active/draft
  ones first within each project) with a project-picker to start a new one and, per project, a "New Agreement" button for
  whoever manages that project -- `subcontractors:agreement_edit` lets the same people fix an agreement's vendor/scope/
  dates/document after creation, not just its lines/payments/status. `python manage.py seed_subcontractor_agreements_demo` (DEMOCC only, needs
  `seed_costing_demo` run first; `--clear` to remove) seeds one agreement in each state (draft / active / completed /
  terminated) so their effect on Cost Control can be seen. **Standard Terms & Conditions**
  (`subcontractors.SubcontractorGeneralTerms`, a singleton loaded via `.load()`, page `subcontractors:general_terms`):
  the company's own general contract terms, penalty/liquidated-damages clauses, code of conduct, and safety commitment
  that apply to every Musana'a agreement company-wide (not per-agreement or per-project, same relationship as
  `core.SpecificationVolume`) — seeded with real bilingual example clauses in migration `0002`. Shown inline (expanded by
  default, collapsible) on every agreement's own detail page, not just linked out, so it reads as part of the agreement;
  `subcontractors:general_terms` is still where it's edited. Editing is admin/engineering-manager only; anyone who can see
  an agreement can read it. `subcontractors/pdf.py::generate_subcontractor_agreement_pdf` (`subcontractors:agreement_pdf`,
  "Download PDF" on the detail page and a PDF icon per row on the list) prints one agreement standalone — header, scope,
  BOQ lines, payments — with the Standard Terms & Conditions always printed LAST, on their own page(s), after everything
  specific to that agreement; matches `generate_daily_report_pdf`'s own look exactly (same portrait A4 layout, calm
  section-accent palette, Times New Roman, table/cell sizing) and reuses `reports/utils.py`'s Arabic-capable
  fonts/shaping (`_t`/`rtl_paragraph`) rather than registering its own. **Single-language, chosen once**:
  `SubcontractorAgreement.language` (`ar`/`en`, set on the agreement form, shown as a badge on the list/detail pages) —
  the PDF never mixes both languages on the page. For Arabic this also flips table layout, not just text alignment:
  `maybe_rtl()` reverses each header/data row (and its column widths) so the first logical column prints on the page's
  right edge, like a real Arabic form; `_language_only()` picks just the Arabic (or English) paragraph blocks out of
  `SubcontractorGeneralTerms`' bilingual fields before printing. Text normalizes `\r\n` to `\n` first, since a Windows
  checkout can hand a migration's triple-quoted string CRLF endings that silently defeat a blank-line split.
- **Project start-up flow** (`projects/workflow.py`, `ProjectStage.KEYS`, five strictly-ordered stages): new
  projects start as `planning`; completing the last stage makes them `active`. Projects that were already running
  are grandfathered (all stages complete). 1) **insurance**. 2) **tender documents**. 3) **drawings** — an
  engineering drawing approved for construction in `blueprints/`, a fully priced BOQ, and an uploaded approval
  document from each of government / municipality / civil defense (`ProjectRegulatoryApproval`, one row per
  body — upload only, no separate review workflow). 4) **schedule** — at least one `reports.ScheduleTask`
  imported for the project (see the Schedule/Gantt bullet below). 5) **plans** — one uploaded document
  (`ProjectManagementPlan`, upload only like tender documents) per required category: ESHS, Quality, Risk,
  Technical Approach and Methodology, Project Team, Code of Conduct, and Site Management and Logistics, the
  last of which additionally needs its own 6-point checklist (`ProjectManagementPlan.CHECKLIST_FIELDS`)
  fully checked before it counts as done. Completing stage 5 is what starts the work (project becomes Active).
- **Project readiness — no work without insurance and a priced BOQ** (`projects/readiness.py`, `guard.py`, `middleware.py`): a project
  is ready when it is past Planning, has an unexpired insurance policy with its document, and its BOQ is fully priced (every item has
  quantity, cost price and contract price > 0; no empty phases). Completed/archived projects are exempt. While a **web request** is
  served, saving any operational record of a not-ready project (`guard.GUARDED`: reports and their rows, progress, PR/PO/receipts,
  stock movements with a project, GPS check-ins) raises `ProjectNotReady`; the middleware answers with a message + redirect to the
  Workflow page (403 JSON for AJAX/API). Setup records (`guard.EXEMPT`: project, insurance, tender docs, drawings, BOQ, milestones) are
  never blocked. Code outside a request (commands, shell, tests) is not enforced; use `readiness.request_scope()` to test enforcement
  and `readiness.suspended()` to bypass. A test fails if a model with a FK to `Project` is in neither list. Not covered:
  `bulk_create`/`QuerySet.update`, and the safety app (no project link). Pickers use `readiness.ready_projects()`. Tests that need a
  working project use `projects.testing.make_ready()`. **`?project=<id>` on a report create page** (from a project's own
  "Reports" page or its "Daily/Monthly/Owner Financial" buttons) only pre-selects that project if it's actually ready and
  the user is assigned to it — `DailyReportCreateView`/`MonthlyReportCreateView`/`OwnerFinancialReportCreateView`'s
  `get()` (`reports/views.py::_redirect_if_requested_project_unusable`) checks this upfront and redirects back with a
  clear reason (to that project's Workflow page if not ready, its own page if not assigned) instead of silently falling
  back to showing a different project pre-selected in the picker, which used to look like the link was simply broken.
- **A project's own Reports page** (`projects:project_reports`, `projects/views.py::ProjectReportsView`, "Reports" button
  on the project page): every Daily/Monthly/Owner Financial report on that one project in one paginated, filterable
  (type, status) list, instead of only the top-10 preview on the project page or filtering the site-wide Reports list by
  project by hand. `projects/views.py::project_reports()` normalizes all three report types into one shape and is shared
  with `ProjectDetailView`'s own "Recent Reports" preview, so the two never show different things.
- **AI assistant** (`ai_assistant/`, mounted at `/ai/`, "AI Assistant" button on the project page and BOQ editor): two jobs,
  both stored as `AIRun` rows and run in a background thread (`jobs.py`; `AI_RUN_IN_BACKGROUND=False` makes it synchronous, as in
  tests). (1) *Read a document into a draft BOQ* — a tender document, drawing revision or uploaded file goes to Claude
  (`claude.py`, `documents.py`, `extraction.py`: structured JSON output, "transcribe don't estimate"), the answer is cleaned
  (`clean_draft`) and shown as a draft; `importer.import_draft` creates `ProjectPhase`/`ProjectPhaseSubItem` rows only when a person
  presses Import, never overwrites an existing item number, and imports prices only if asked. (2) *Project review* (`review.py`) —
  a tool-using agent with read-only, single-project tools; `health.py` holds the rule-based checks it (and the page) starts from —
  those need no API key. Needs `ANTHROPIC_API_KEY` in `.env`; documents leave the company to Anthropic's API. Model is
  `AI_ASSISTANT_MODEL` (default `claude-opus-5`). Tests use a fake client (`ai_assistant/tests.py`), so live Claude behaviour is
  not covered by them. Access: admin / engineering manager / the project's manager (read + import); general manager (view + review).
  **Two providers**, chosen by `AI_PROVIDER` in `.env`: `anthropic` (default; `claude.py`) or `ollama` (`ollama.py`, an open model on
  the company's own machine — no outside company, no per-use fee). Everything else calls `llm.py`, which dispatches; a new provider means
  implementing `read_document`, `structured`, `agent_reply`, `is_configured`, `model_name`. The local one reads PDFs as page text (or page
  pictures for a vision model, `OLLAMA_PDF_MODE`), reads long documents in chunks sized to `OLLAMA_NUM_CTX` (Ollama silently truncates
  otherwise) and caps tool results to fit; its tests (`tests_ollama.py`) replace `ollama._post`, so real Ollama behaviour is unverified.
  **Drawing analysis** (`takeoff.py`, `edge.py`, `triggers.py`; run kind `drawing_takeoff`): a drawing revision, tender document or upload is
  read for the materials/quantities it WRITES (never measured — items without a printed quantity are listed with none) and for a fixed
  checklist of green-building (EDGE) design facts (`edge.POINTS`; "missing" is computed in code, the model can only fill known points). The
  link to pricing is plain code (`takeoff.link_to_boq`: validated BOQ code, unit-normalised, summed per line, priced at the BOQ cost price).
  It starts automatically after a drawing upload when a provider is set up (`AI_AUTO_ANALYZE_DRAWINGS`, on by default; `blueprints/views.py`
  calls `triggers.auto_analyze_revision`, which never raises) and from the "Analyze" button on the drawings page. `edge.project_edge_data`
  merges all analyzed documents into the project's EDGE summary page. The app does NOT compute EDGE savings — that is the official EDGE app.
  A floating **chat bubble** (`templates/ai_assistant/_chat_widget.html`, included from `base.html` for admin / engineering manager /
  general manager / project manager) chats about one project via `chat.py` using the same read-only tools; the browser keeps the
  history (sessionStorage), the server stores nothing, and it is limited to 40 questions per user per hour.
- **Project schedule (Gantt, Primavera-style)** (`reports/schedule_models.py::ScheduleTask`, `reports/services/schedule_view.py`,
  `templates/reports/schedule.html`, page `reports:project_schedule`, button "Schedule" on the project page): the page only DRAWS the
  stored schedule — WBS table on the left (Activity ID, name with expand/collapse, duration, start, finish, %, float, predecessors),
  time-scaled bars on the right in SVG drawn by plain JS (critical in red, progress overlay, summary brackets, milestone diamonds, baseline
  bars, relationship arrows FS/SS/FF/SF, Friday shading, data-date line, zoom Fit/Quarter/Month/Week/Day, WBS level buttons, print).
  Data comes from an imported MS Project schedule (`import_ms_project_schedule`) and the project's `ProjectMilestone` rows; nothing is
  scheduled in the browser. `reports/services/cpm.py` is a small CPM engine (Saturday–Thursday week, FS/SS/FF/SF + lag, float,
  critical path) used by `seed_schedule_demo` (`reports/schedule_demo.py`, DEMOCC only); there is no in-app schedule editor and no
  Primavera XER/MS Project XML import yet.
- **Company Standards & Specifications** (`core/models.py` `SpecificationVolume`/`SpecificationSection`, page
  `core:specifications_list`, "Standards & Specs" in the sidebar and dashboard): the company's own master
  specification book ("One Stop Standards and Specifications"), company-wide and not tied to any project —
  Design-Build projects are built to it by default; Tender-type projects come with their own drawings and
  specifications from the client/consultant instead. Each `SpecificationVolume` is one uploaded volume
  (currently Volume I: General Requirements, Volume II: Site Works through Landscaping, Volume III:
  Equipment through Electrical); its `SpecificationSection` rows are a browsable/searchable index of the
  volume's own numbered sections (e.g. "01010 - Summary of Work"), each also carrying its own extracted body
  text in `SpecificationSection.content` — clicking a section opens a popup (fetched as JSON from
  `core:specification_section_detail`) showing that text, with a "Download as PDF" button
  (`core:specification_section_pdf`, `core/pdf.py::generate_specification_section_pdf`) that generates a
  small standalone PDF of just that section, not the whole volume. Admin or the engineering manager can
  add/delete volumes and add/edit sections in-app ("Add section" on a volume card, "Edit this section" in the
  popup — `core.forms.SpecificationSectionForm`, `core:specification_section_add`/`_edit`), or by re-running the
  one-off extraction the original 92 real sections were seeded from, which parses each volume's own
  "NNNNN – Title" headings out of its .docx. A `Project.delivery_type`-style field to formally distinguish
  Design-Build from Tender projects has been discussed but not built yet. **Per-project applicability**:
  `Project.applicable_spec_sections` (M2M to `SpecificationSection`) marks which of the standard's sections
  actually apply to a given project, based on its own nature (e.g. no subcontractors on this job -> that
  section stays off) — toggled on the project's own "Specifications" page (`projects:project_specifications`,
  button on the project page; `projects.views_specifications`), same permission as the workflow pages (admin,
  engineering manager, or that project's own manager); read access and the section popup/PDF are open to
  anyone who can see the project.
- **Warehouses** (`procurement/models.py` `Warehouse`/`StockLevel`/`StockMovement`, rules in
  `procurement/services_warehouse.py`): all stock changes go through `record_movement()`; PO receipts feed stock via signals.
- **`timesheets/`** implements GPS attendance/geofencing: `Employee`/`Department`/`Position` models, with
  business logic in `services/Location_Service.py` and `services/work_hours.py` (see the websocket caveat
  above).
- **APIs**: there is no single project-wide API app, and no single API style — `timesheets`,
  `procurement`, `cost_control` use real DRF `serializers.py` + `api_views.py`/`api_urls.py`; `reports/api_views.py`
  is plain Django function views returning `JsonResponse` directly (no serializers, no DRF), used for the
  AJAX add/delete calls each report detail template makes into its own child rows (workforce, activities,
  worker attendance, price-comparison items, phase photos, ...) — don't assume DRF conventions apply there.
  Token auth is via DRF's `rest_framework.authtoken` (`POST /api-token-auth/`).
- **Media files**: `config/urls.py` imports `django.conf.urls.static.static` but historically never called
  it — uploaded files (`ReportAttachment`, `ProjectPhasePhoto`, ...) saved fine but 404'd when served back
  in development. Fixed by appending `static(MEDIA_URL, document_root=MEDIA_ROOT)` when `DEBUG` is on;
  production still serves media via the web server, not Django. **Static files** (CSS/JS/images under
  `STATIC_URL`, not uploads) ARE served by Django itself in production too, via `whitenoise` --
  `WhiteNoiseMiddleware` right after `SecurityMiddleware`, `STORAGES["staticfiles"]` set to
  `whitenoise.storage.CompressedStaticFilesStorage` (compression only, not the stricter
  `CompressedManifestStaticFilesStorage`, so `collectstatic` can't fail a first deploy over a template
  referencing a static file that doesn't literally exist on disk) -- chosen because shared hosting without
  root/sysadmin access (e.g. cPanel's "Setup Python App"/Passenger) often gives no separate way to point the
  web server straight at `STATIC_ROOT`. **Storage backend**: `config/settings.py`'s
  `STORAGES["default"]` is local disk (`FileSystemStorage`) unless `DROPBOX_APP_KEY` is set in `.env`, in
  which case every upload — insurance/tender documents, drawings, daily/monthly report attachments, project
  phase photos — goes to the company's own Dropbox instead (`storages.backends.dropbox.DropboxStorage`; see
  `.env.example` for how to get `DROPBOX_APP_KEY`/`DROPBOX_APP_SECRET`/`DROPBOX_OAUTH2_REFRESH_TOKEN` from
  the Dropbox App Console). Switching an existing server over needs
  `python manage.py migrate_media_to_dropbox` run first (`core/management/commands/`) — it copies every file
  already on local disk up to Dropbox at the exact relative path the database already stores, so old files
  don't become unreachable the moment `DROPBOX_APP_KEY` goes live; safe to re-run, already-uploaded files are
  skipped. Note: `DropboxStorage.url()` calls the Dropbox API for a fresh temporary link on every access (no
  caching), so a page rendering many attachments at once — a report's photo list, the photo-log annex in
  `generate_daily_report_pdf` — makes one Dropbox API round-trip per file shown.
- **Logging**: `config/settings.py` writes Django logs to `debug.log` at the project root (file handler)
  and to the console.
