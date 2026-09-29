"""
Import real "One Stop Daily Site Report" Excel files (the native site-report
template used on the ground, sheet 'التقرير اليومي') into the matching
DailyReport + child rows (activity progress, worker attendance, materials,
equipment, QA/QC & HSE, site events, next-day plan).

The template is printed to Excel per calendar day and stored as one .xlsx
per day; the ~10 fixed section headers (numbered "1." through "7.", in
Arabic + English) always appear in column A, but their exact row number
shifts from file to file (blank rows get trimmed differently per day), so
sections are located by searching for their marker text rather than by a
fixed row number.
"""

import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.db import transaction

from ..models import DailyReport, DailyMaterial, DailyEquipment, DailyVisitor
from ..daily_detail_models import (
    DailyReportWorkerAttendance, DailyReportActivityProgress, DailyReportQAQC,
    DailyReportNextDayPlan,
)
from ..site_event_models import SiteEvent
from accounts.models import CustomUser
from timesheets.models import Employee

WEATHER_MAP = {
    'مشمس': 'sunny', 'sunny': 'sunny',
    'ممطر': 'rainy', 'rainy': 'rainy',
    'غائم': 'cloudy', 'cloudy': 'cloudy',
    'عاصف': 'windy', 'windy': 'windy',
    'مختلط': 'mixed', 'mixed': 'mixed',
    'عاصفة': 'stormy', 'stormy': 'stormy',
}

ACTIVITY_STATUS_MAP = {
    'جارٍ التنفيذ': 'in_progress', 'جاري التنفيذ': 'in_progress', 'قيد التنفيذ': 'in_progress',
    'مكتمل': 'completed', 'منجز': 'completed', 'منتهي': 'completed',
    'لم يبدأ': 'not_started',
    'متأخر': 'delayed',
    'متوقف': 'on_hold', 'معلق': 'on_hold',
}

EVENT_TYPE_MAP = {
    'تأخير': 'delay', 'delay': 'delay',
    'تعليمة': 'site_instruction', 'si': 'site_instruction', 'site instruction': 'site_instruction',
    'rfi': 'rfi',
    'ncr': 'ncr',
    'شبه حادث': 'near_miss', 'near miss': 'near_miss', 'قريب من الحادث': 'near_miss',
    'حادث': 'hse_incident', 'hse': 'hse_incident',
}

READINESS_MAP = {
    'جاهز': 'ready', 'ready': 'ready',
    'غير جاهز': 'not_ready', 'not ready': 'not_ready',
    'معلق': 'pending', 'pending': 'pending',
}

# Real signature names on this project's daily reports don't always match
# the CustomUser.get_full_name() spelling (Arabic on the sheet vs. the
# Latin name a login account was created with) -- map the known aliases.
NAME_ALIASES = {
    'ehab': ['ايهاب عمرو', 'إيهاب عمرو', 'ايهاب امرو', 'إيهاب امرو'],
}


class DailyReportImportError(ValueError):
    pass


def _norm(v):
    if v is None:
        return ''
    return str(v).strip()


def _row_contains(values, marker):
    return any(v is not None and marker in str(v) for v in values)


def _to_decimal(v, default=Decimal('0')):
    if v is None or v == '':
        return default
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip().replace(',', '')
    if not s:
        return default
    try:
        return Decimal(s)
    except InvalidOperation:
        return default


def _q2(v):
    """Round a Decimal to 2 decimal places (matches this app's DecimalField scales)."""
    if v is None:
        return None
    return v.quantize(Decimal('0.01'))


def _to_int(v, default=0):
    d = _to_decimal(v, default=None)
    if d is None:
        return default
    try:
        return int(round(float(d)))
    except (ValueError, TypeError):
        return default


def _to_time(v):
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, str) and v.strip():
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.strptime(v.strip(), fmt).time()
            except ValueError:
                continue
    return None


def _to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v.strip():
        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
            try:
                return datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                continue
    return None


def _map_choice(value, mapping, default=''):
    text = _norm(value)
    if not text:
        return default
    for key, mapped in mapping.items():
        if key in text:
            return mapped
    return default


def _load_data_rows(ws):
    """All non-blank rows as (row_number, [cell values]), in sheet order."""
    rows = []
    for row in ws.iter_rows():
        values = [c.value for c in row]
        if any(v is not None for v in values):
            rows.append((row[0].row, values))
    return rows


def _find_marker_row(data_rows, marker, after=0):
    for row_num, values in data_rows:
        if row_num > after and _row_contains(values, marker):
            return row_num
    return None


def _section_data_rows(ws, data_rows, start_marker, end_marker, header_offset=1):
    """
    Rows strictly between (start_marker's row + header_offset) and
    end_marker's row (or end of sheet), read directly via ws.cell() so
    every column -- including ones openpyxl trimmed from a merged/blank
    tail -- is available by fixed 1-based column index.
    """
    start_row = _find_marker_row(data_rows, start_marker)
    if start_row is None:
        return []
    end_row = _find_marker_row(data_rows, end_marker, after=start_row) if end_marker else None
    data_start = start_row + header_offset + 1
    data_end = (end_row - 1) if end_row else max(rn for rn, _ in data_rows)
    out = []
    for row_num in range(data_start, data_end + 1):
        values = [ws.cell(row=row_num, column=c).value for c in range(1, 11)]
        if any(v is not None for v in values):
            out.append(values)
    return out


def parse_daily_report_workbook(path):
    """Parse the 'التقرير اليومي' sheet into a plain dict of extracted data."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    if 'التقرير اليومي' not in wb.sheetnames:
        raise DailyReportImportError(f'{path}: sheet "التقرير اليومي" not found.')
    ws = wb['التقرير اليومي']
    data_rows = _load_data_rows(ws)

    date_row = _find_marker_row(data_rows, 'التاريخ')
    if date_row is None:
        raise DailyReportImportError(f'{path}: could not locate the report date row.')
    report_date = _to_date(ws.cell(row=date_row, column=3).value)
    if report_date is None:
        raise DailyReportImportError(f'{path}: could not parse the report date value.')
    weather_raw = ws.cell(row=date_row, column=10).value

    employer_row = _find_marker_row(data_rows, 'العميل')
    site_engineer_name = _norm(ws.cell(row=employer_row, column=9).value) if employer_row else ''

    result = {
        'report_date': report_date,
        'weather': _map_choice(weather_raw, WEATHER_MAP, default='sunny'),
        'site_engineer_name': site_engineer_name,
        'activities': [],
        'workers': [],
        'materials': [],
        'equipment': [],
        'qaqc': None,
        'site_events': [],
        'next_day_plan': [],
        'summary_text': '',
    }

    # ---- 1. Activity progress ----
    for v in _section_data_rows(ws, data_rows, '1. الأعمال المنفذة', '2. العمالة'):
        description = _norm(v[1])
        if not description:
            continue
        # Progress % is stored as a 0-1 fraction in most files (Excel's
        # own "%" number format) but occasionally as a plain 0-100 number
        # -- treat anything > 1 as already being a percentage.
        raw_pct = _to_decimal(v[7])
        completion_percentage = min(raw_pct * 100 if raw_pct <= 1 else raw_pct, Decimal('100'))
        result['activities'].append({
            'activity_description': description,
            'location': _norm(v[2]),
            'unit': _norm(v[3]),
            'total_quantity': _q2(_to_decimal(v[4], default=None)),
            'quantity_today': _q2(_to_decimal(v[5])),
            'quantity_cumulative': _q2(_to_decimal(v[6])),
            'completion_percentage': _q2(completion_percentage),
            'status': _map_choice(v[8], ACTIVITY_STATUS_MAP, default='in_progress'),
            'reference_notes': _norm(v[9])[:255],
        })

    # ---- 2. Worker attendance ----
    for v in _section_data_rows(ws, data_rows, '2. العمالة وساعات العمل', '3A. المواد الموردة'):
        worker_name = _norm(v[1])
        if not worker_name:
            continue
        trade = _norm(v[2])
        result['workers'].append({
            'worker_name': worker_name,
            'trade': trade,
            'contractor_name': _norm(v[3])[:150],
            'activity_location': _norm(v[4])[:255],
            'time_in': _to_time(v[5]),
            'time_out': _to_time(v[6]),
            'break_hours': _q2(_to_decimal(v[7])),
            'overtime_hours': _q2(_to_decimal(v[8])),
            'total_hours': _q2(_to_decimal(v[9])),
        })

    # ---- 3A/3B Materials + Equipment (side by side in the same rows) ----
    for v in _section_data_rows(ws, data_rows, '3A. المواد الموردة', '4. الجودة والسلامة'):
        material_name = _norm(v[1])
        if material_name:
            qty = _to_decimal(v[3], default=None)
            unit = _norm(v[2])
            supplier_status = _norm(v[4])
            if qty is None:
                # Real sheets sometimes put a qualitative note ("كاملة" =
                # "complete") instead of a number in the Received Qty.
                # column -- keep that information in the description
                # rather than silently dropping it, and fall back to 0
                # for the model's required decimal field.
                extra = ' / '.join(x for x in [_norm(v[3]), supplier_status] if x)
                if extra:
                    material_name = f'{material_name} ({extra})'
                qty = Decimal('0')
            result['materials'].append({
                'material_description': material_name[:255],
                'quantity': _q2(qty),
                'unit': (unit or 'unit')[:50],
            })

        equipment_name = _norm(v[6])
        if equipment_name:
            result['equipment'].append({
                'equipment_name': equipment_name[:255],
                'hours_worked': max(0, min(24, _to_int(v[8]))),
            })

    # ---- 4. QA/QC & HSE (three fixed rows right after the section marker) ----
    qaqc_row = _find_marker_row(data_rows, '4. الجودة والسلامة')
    if qaqc_row:
        inspection_text = ws.cell(row=qaqc_row + 1, column=3).value
        toolbox_text = ws.cell(row=qaqc_row + 1, column=7).value
        incident_text = _norm(ws.cell(row=qaqc_row + 1, column=10).value)
        ir_mir_ref = _norm(ws.cell(row=qaqc_row + 2, column=3).value)
        ppe_status = _norm(ws.cell(row=qaqc_row + 2, column=7).value)
        ncr_hse_ref = _norm(ws.cell(row=qaqc_row + 2, column=10).value)
        qa_notes = _norm(ws.cell(row=qaqc_row + 3, column=3).value)

        inspection_status = 'not_applicable'
        text = _norm(inspection_text)
        if text:
            if any(k in text for k in ('سليم', 'passed', 'ناجح')):
                inspection_status = 'passed'
            elif any(k in text for k in ('فشل', 'failed', 'راسب')):
                inspection_status = 'failed'
            elif any(k in text for k in ('pending', 'معلق')):
                inspection_status = 'pending'

        result['qaqc'] = {
            'inspection_status': inspection_status,
            'ir_mir_test_reference': ir_mir_ref[:100],
            'toolbox_talk_conducted': _norm(toolbox_text) in ('نعم', 'Yes', 'yes'),
            'incident_occurred': 'حادث' in incident_text and 'شبه' not in incident_text and 'لا' not in incident_text,
            'near_miss_occurred': 'شبه حادث' in incident_text,
            'ppe_site_cleanliness_status': ppe_status[:100],
            'ncr_hse_reference': ncr_hse_ref[:100],
            'notes': qa_notes,
        }

    # ---- 5. Site events ----
    for v in _section_data_rows(ws, data_rows, '5. الأحداث والتعليمات والتأخيرات', '6. خطة اليوم التالي'):
        description = _norm(v[3])
        if not description:
            continue
        result['site_events'].append({
            'event_type': _map_choice(v[1], EVENT_TYPE_MAP, default='other'),
            'reference': _norm(v[2])[:50],
            'description': description,
            'required_action': _norm(v[4]),
            'responsible_party': _norm(v[5])[:150],
            'target_date': _to_date(v[6]),
            'status': 'closed' if 'مغلق' in _norm(v[7]) or 'closed' in _norm(v[7]).lower() else 'open',
            'time_impact_hours': _q2(_to_decimal(v[8], default=None)),
            'remarks': _norm(v[9]),
        })

    # ---- 6. Next day plan ----
    for v in _section_data_rows(ws, data_rows, '6. خطة اليوم التالي', '7. ملخص اليوم'):
        activity = _norm(v[1])
        if not activity:
            continue
        result['next_day_plan'].append({
            'planned_activity': activity,
            'location': _norm(v[2])[:255],
            'manpower_required': _to_int(v[3], default=None) if v[3] is not None else None,
            'resources_required': _norm(v[4]),
            'requirement_notes': _norm(v[5])[:255],
            'responsible_party': _norm(v[6])[:150],
            'priority': _map_choice(v[7], {'high': 'high', 'عالية': 'high', 'medium': 'medium', 'متوسطة': 'medium', 'low': 'low', 'منخفضة': 'low'}),
            'readiness': _map_choice(v[8], READINESS_MAP),
            'remarks': _norm(v[9]),
        })

    # ---- 7. Summary / sign-off ----
    summary_row = _find_marker_row(data_rows, '7. ملخص اليوم')
    if summary_row:
        summary_text = _norm(ws.cell(row=summary_row + 1, column=1).value)
        result['summary_text'] = summary_text

    return result


def _match_user(name_text, users):
    target = _norm(name_text)
    target = re.sub(r'^(م\.|مهندس|eng\.|Eng\.)\s*', '', target).strip()
    if not target:
        return None
    for u in users:
        for username, aliases in NAME_ALIASES.items():
            if u.username == username and any(a in target or target in a for a in aliases):
                return u
    for u in users:
        full = (u.get_full_name() or '').strip()
        if full and (full in target or target in full):
            return u
    return None


@transaction.atomic
def import_daily_report_excel(path, project):
    """
    Parse one daily-report .xlsx and create/update the matching DailyReport
    (by project + report_date) and all of its child rows. Existing child
    rows for that report are replaced with the freshly-parsed ones (the
    Excel file is the source of truth for that day). Returns the
    DailyReport instance and a small stats dict.
    """
    parsed = parse_daily_report_workbook(path)
    report_date = parsed['report_date']

    users = list(CustomUser.objects.filter(role__in=['site_engineer', 'project_manager', 'admin']))
    site_engineer = _match_user(parsed['site_engineer_name'], users) or project.manager

    existing = (
        DailyReport.objects.filter(project=project, report_date=report_date)
        .order_by('id').first()
    )
    # Only overwrite a report that's still a draft -- one that's already
    # been submitted/reviewed/approved is live production data, not a
    # placeholder, so it's left alone and a fresh report is created
    # instead of silently rewriting an approved record.
    if existing and existing.status != 'draft':
        existing = None
    if existing:
        report = existing
        report.weather_conditions = parsed['weather']
        report.remarks = parsed['summary_text']
        if site_engineer:
            report.site_engineer = site_engineer
        report.save()
        # This Excel file is the authoritative source for the day -- drop
        # whatever placeholder/child rows exist so re-importing is safe
        # to run more than once without piling up duplicates.
        report.activity_progress_entries.all().delete()
        report.worker_attendance.all().delete()
        report.daily_materials.all().delete()
        report.equipment.all().delete()
        report.next_day_plan.all().delete()
        DailyReportQAQC.objects.filter(report=report).delete()
    else:
        report = DailyReport.objects.create(
            project=project,
            site_engineer=site_engineer,
            weather_conditions=parsed['weather'],
            remarks=parsed['summary_text'],
        )
        # report_date is auto_now_add -- .update() bypasses that so the
        # historical date from the Excel file actually sticks.
        DailyReport.objects.filter(pk=report.pk).update(report_date=report_date)
        report.refresh_from_db()

    for a in parsed['activities']:
        DailyReportActivityProgress.objects.create(report=report, **a)

    project_employees = {
        e.full_name.strip(): e
        for e in Employee.objects.filter(project=project)
    }

    for w in parsed['workers']:
        employee = None
        for full_name, emp in project_employees.items():
            if full_name and (full_name in w['worker_name'] or w['worker_name'] in full_name):
                employee = emp
                break
        notes = f"Trade: {w['trade']}" if w['trade'] else ''
        DailyReportWorkerAttendance.objects.create(
            report=report,
            worker_name=w['worker_name'],
            employee=employee,
            contractor_name=w['contractor_name'],
            activity_location=w['activity_location'],
            time_in=w['time_in'],
            time_out=w['time_out'],
            break_hours=w['break_hours'],
            overtime_hours=w['overtime_hours'],
            total_hours=w['total_hours'],
            notes=notes,
        )

    for m in parsed['materials']:
        DailyMaterial.objects.create(report=report, **m)

    for eq in parsed['equipment']:
        DailyEquipment.objects.create(report=report, **eq)

    if parsed['qaqc']:
        DailyReportQAQC.objects.create(report=report, **parsed['qaqc'])

    for ev in parsed['site_events']:
        SiteEvent.objects.create(project=project, daily_report=report, event_date=report_date, **ev)

    for order, p in enumerate(parsed['next_day_plan']):
        DailyReportNextDayPlan.objects.create(report=report, order=order, **p)

    stats = {
        'activities': len(parsed['activities']),
        'workers': len(parsed['workers']),
        'materials': len(parsed['materials']),
        'equipment': len(parsed['equipment']),
        'site_events': len(parsed['site_events']),
        'next_day_plan': len(parsed['next_day_plan']),
        'was_update': existing is not None,
    }
    return report, stats
