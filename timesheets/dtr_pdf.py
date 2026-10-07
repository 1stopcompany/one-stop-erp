"""
PDF of an employee's Daily Time Record for one month, on the same formal page as the payroll and wages sheets: Times New Roman, right to
left, the banner with the title in the middle and the logo on the left, a navy header row, banded lines coloured by the day's status,
the day's split over projects (hours and overtime per project) in its own column, the month's totals, the hours per project and the
signature boxes. It tries to fit one A4 page (tighter spacing and a smaller font step by step) and only runs on to a second page when
even the tightest layout does not fit -- the page is always used to its edges.

Columns (right to left on the page):
    التاريخ | اليوم | الحالة | الدخول | الخروج | الاستراحة | الساعات | إضافي | تأخير | نقص | المشاريع (تفصيل الساعات) | ملاحظات
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME as BOLD, MR_FONT_NAME as FONT, _ARABIC_RE, _t, rtl_paragraph

from .payroll_sheet_excel import BAND, COMPANY_AR, COMPANY_EN, NAVY, TOTAL_FILL, month_label

NAVY_C = colors.HexColor('#' + NAVY)
GRID_C = colors.HexColor('#BFBFBF')

STATUS_AR = {
    'present': 'حاضر', 'absent': 'غائب', 'on_leave': 'إجازة مدفوعة', 'unpaid_leave': 'إجازة غير مدفوعة',
    'rest_day': 'عطلة أسبوعية', 'holiday': 'عطلة رسمية',
}
STATUS_FILL = {
    'absent': '#FBE3E3', 'unpaid_leave': '#FFE7C7', 'on_leave': '#E1EEFB', 'rest_day': '#ECECEC', 'holiday': '#ECECEC',
}
DAYS_AR = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']   # Monday = 0

HEADER_LINES = [
    ['التاريخ'], ['اليوم'], ['الحالة'], ['الدخول'], ['الخروج'], ['استراحة', '(س)'], ['الساعات', '(س)'], ['إضافي', '(س)'],
    ['تأخير', '(د)'], ['نقص', '(د)'], ['المشاريع - تفصيل الساعات'], ['ملاحظات'],
]
WEIGHTS = [9, 8.5, 11, 6, 6, 6.5, 6.5, 6, 5.5, 5.5, 28, 11]

# Spacing levels, roomy first. The first that gives a single page is used; the last one is used (and may need a second page) otherwise.
LEVELS = [
    {'pad': 3.0, 'size': 8.6, 'logo': 0.66, 'gap': 14, 'sign': (15, 30)},
    {'pad': 2.3, 'size': 8.0, 'logo': 0.55, 'gap': 9, 'sign': (13, 24)},
    {'pad': 1.7, 'size': 7.4, 'logo': 0.45, 'gap': 6, 'sign': (12, 20)},
    {'pad': 1.2, 'size': 6.8, 'logo': 0.38, 'gap': 4, 'sign': (11, 16)},
]


def _num(value, blank_zero=True):
    value = Decimal(value or 0).quantize(Decimal('0.01'))
    if blank_zero and value == 0:
        return ''
    return f'{value:f}'.rstrip('0').rstrip('.')


def generate_dtr_pdf(employee, records, period_start, generated_by=None, allocations=None, breakdown=None):
    """`allocations`: {date: {'source', 'rows': [{'project', 'regular', 'overtime'}]}}; `breakdown`: month_breakdown() rows."""
    result = None
    for level in LEVELS:
        result, pages = _build(employee, records, period_start, generated_by, allocations or {}, breakdown or [], level)
        if pages == 1:
            break
    return result


def _build(employee, records, period_start, generated_by, allocations, breakdown, level):
    margin = 0.34 * inch
    page = A4
    page_width = page[0] - 2 * margin
    buffer = BytesIO()
    title = f'سجل الدوام اليومي - شهر {month_label(period_start)}'
    doc = SimpleDocTemplate(buffer, pagesize=page, topMargin=margin, bottomMargin=0.5 * inch, leftMargin=margin, rightMargin=margin,
                            title=f'DTR {employee.full_name} {period_start:%m-%Y}')
    base = getSampleStyleSheet()['Normal']
    size = level['size']
    cell = ParagraphStyle('DCell', parent=base, fontName=FONT, fontSize=size, leading=size + 1.7, alignment=TA_CENTER)
    cell_r = ParagraphStyle('DCellR', parent=cell, alignment=TA_RIGHT)
    small_r = ParagraphStyle('DSmallR', parent=cell_r, fontSize=size - 0.6, leading=size + 0.9)
    head = ParagraphStyle('DHead', parent=cell, fontName=BOLD, fontSize=size - 0.2, leading=size + 1.1, textColor=colors.white)
    bold = ParagraphStyle('DBold', parent=cell, fontName=BOLD)
    bold_r = ParagraphStyle('DBoldR', parent=bold, alignment=TA_RIGHT)
    company = ParagraphStyle('DCompany', parent=cell, fontName=BOLD, fontSize=16, leading=19, textColor=NAVY_C)
    company_en = ParagraphStyle('DCompanyEn', parent=cell, fontSize=9.5, leading=12, textColor=colors.HexColor('#595959'))
    title_style = ParagraphStyle('DTitle', parent=cell, fontName=BOLD, fontSize=13, leading=17)
    label = ParagraphStyle('DLabel', parent=cell, fontName=BOLD, fontSize=9, leading=11, textColor=NAVY_C)
    bar = ParagraphStyle('DBar', parent=cell, fontName=BOLD, fontSize=9.5, leading=12, textColor=colors.white)

    widths = [page_width * w / sum(WEIGHTS) for w in WEIGHTS]
    n = len(widths)

    def rtl(values):
        return list(reversed(values))

    def text(value, style, width):
        if value in (None, ''):
            return ''
        value = str(value)
        return rtl_paragraph(value, style, width - 5) if _ARABIC_RE.search(value) else Paragraph(value, style)

    # ---- banner: text in the middle, logo on the left
    logo_path = finders.find('images/one_stop_logo.png')
    banner_rows = [[Paragraph(_t(COMPANY_AR), company)], [Paragraph(COMPANY_EN, company_en)], [Paragraph(_t(title), title_style)]]
    side = page_width * 0.22
    banner_text = Table(banner_rows, colWidths=[page_width - 2 * side])
    banner_text.setStyle(TableStyle([('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    logo = ''
    if logo_path:
        from PIL import Image as PILImage
        with PILImage.open(logo_path) as logo_file:
            ratio = logo_file.width / logo_file.height
        logo = Image(logo_path, width=level['logo'] * inch * ratio, height=level['logo'] * inch)
    banner = Table([[logo, banner_text, '']], colWidths=[side, page_width - 2 * side, side])
    banner.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'LEFT'), ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                                ('LINEBELOW', (0, 0), (-1, 0), 1.2, NAVY_C), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                                ('LEFTPADDING', (0, 0), (0, 0), 0)]))

    # ---- who: name, position, department, id
    def kv(key, value, width):
        return [text(value, cell_r, width) if value else '', Paragraph(_t(key), label)]
    third = page_width / 3
    who = Table([
        [text(employee.full_name, bold_r, third * 2 / 2), Paragraph(_t('الموظف'), label),
         text(employee.position.title if employee.position_id else '', cell_r, third), Paragraph(_t('الوظيفة'), label)],
        [text(employee.department.name if employee.department_id else '', cell_r, third), Paragraph(_t('القسم'), label),
         text(f'{period_start:%m/%Y}', cell_r, third), Paragraph(_t('الشهر'), label)],
    ], colWidths=[page_width * 0.34, page_width * 0.11, page_width * 0.43, page_width * 0.12])
    who.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
                             ('BOX', (0, 0), (-1, -1), 0.5, GRID_C), ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#' + TOTAL_FILL)),
                             ('BACKGROUND', (3, 0), (3, -1), colors.HexColor('#' + TOTAL_FILL))]))
    who = Table([[who]], colWidths=[page_width])
    who.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 4)]))

    # ---- the month, one line per day
    rows = [rtl([Paragraph('<br/>'.join(_t(line) for line in lines), head) for lines in HEADER_LINES])]
    counts, total_hours, total_ot, total_late, total_under = {}, Decimal('0'), Decimal('0'), 0, 0
    fills = []
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1
        hours = r.total_hours
        total_hours += hours or Decimal('0')
        total_ot += r.overtime_hours or Decimal('0')
        total_late += r.late_minutes
        total_under += r.undertime_minutes
        info = allocations.get(r.date)
        if info:
            lines = []
            for row in info['rows']:
                name = row['project'].name
                part = f"{name if len(name) <= 30 else name[:29] + '…'}: {_num(row['regular'], False)}"
                if row['overtime']:
                    part += f" + {_num(row['overtime'], False)} إضافي"
                lines.append(part)
            project_cell = text('\n'.join(lines), small_r, widths[10])
        else:
            project_cell = ''
        worked = hours is not None
        values = [
            f'{r.date:%d/%m}', Paragraph(_t(DAYS_AR[r.date.weekday()]), cell), Paragraph(_t(STATUS_AR.get(r.status, r.status)), cell),
            f'{r.clock_in:%H:%M}' if r.clock_in else '', f'{r.clock_out:%H:%M}' if r.clock_out else '',
            _num(r.break_hours, False) if worked else '', _num(hours, False) if worked else '', _num(r.overtime_hours),
            str(r.late_minutes) if r.late_minutes else '', str(r.undertime_minutes) if r.undertime_minutes else '',
            project_cell, text(r.notes, small_r, widths[11]),
        ]
        rows.append(rtl(values))
        fills.append(r.status)
    totals = [''] * n
    totals[2] = Paragraph(_t(f'المجموع ({len(records)} يوم)'), bold)   # the label sits in the left cell of the 3-column span
    totals[6] = Paragraph(_num(total_hours, False) or '0', bold)
    totals[7] = Paragraph(_num(total_ot, False) or '0', bold)
    totals[8] = Paragraph(str(total_late), bold)
    totals[9] = Paragraph(str(total_under), bold)
    rows.append(rtl(totals))
    last = len(rows) - 1
    table = Table(rows, colWidths=rtl(widths), repeatRows=1)
    style = [
        ('FONTNAME', (0, 0), (-1, -1), FONT), ('FONTSIZE', (0, 0), (-1, -1), size), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
        ('TOPPADDING', (0, 0), (-1, -1), level['pad']), ('BOTTOMPADDING', (0, 0), (-1, -1), level['pad']),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY_C), ('SPAN', (n - 3, last), (n - 1, last)),
        ('BACKGROUND', (0, last), (-1, last), colors.HexColor('#' + TOTAL_FILL)), ('LINEABOVE', (0, last), (-1, last), 1.2, NAVY_C),
        ('LINEBELOW', (0, last), (-1, last), 1.6, NAVY_C), ('FONTNAME', (0, last), (-1, last), BOLD),
    ]
    for index, status in enumerate(fills, start=1):
        colour = STATUS_FILL.get(status) or (('#' + BAND) if index % 2 == 0 else '#FFFFFF')
        style.append(('BACKGROUND', (0, index), (-1, index), colors.HexColor(colour)))
    table.setStyle(TableStyle(style))

    # ---- summary: days by status, and the hours per project
    summary_labels = [('present', 'حاضر'), ('absent', 'غائب'), ('on_leave', 'إجازة مدفوعة'), ('unpaid_leave', 'إجازة غير مدفوعة'),
                      ('rest_day', 'عطلة أسبوعية'), ('holiday', 'عطلة رسمية')]
    summary = Table([
        rtl([Paragraph(_t(name), head) for _, name in summary_labels] + [Paragraph(_t('مجموع الساعات'), head), Paragraph(_t('الإضافي'), head)]),
        rtl([Paragraph(str(counts.get(key, 0)), bold) for key, _ in summary_labels] + [Paragraph(_num(total_hours, False) or '0', bold),
                                                                                    Paragraph(_num(total_ot, False) or '0', bold)]),
    ], colWidths=[page_width / 8] * 8)
    summary.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), NAVY_C), ('GRID', (0, 0), (-1, -1), 0.4, GRID_C), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                 ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), level['pad']),
                                 ('BOTTOMPADDING', (0, 0), (-1, -1), level['pad'])]))
    closing = [summary]
    if breakdown:
        project_rows = [rtl([Paragraph(_t(h), head) for h in ['المشروع', 'عدد الأيام', 'الساعات', 'الساعات الإضافية']])]
        for item in breakdown:
            project_rows.append(rtl([text(item['project'].name, cell_r, page_width * 0.5), str(item['days']),
                                     _num(item['regular_hours'], False), _num(item['overtime_hours'], False)]))
        pw = [page_width * 0.5, page_width * 0.16, page_width * 0.17, page_width * 0.17]
        project_table = Table(project_rows, colWidths=rtl(pw), repeatRows=1)
        project_table.setStyle(TableStyle([('FONTNAME', (0, 0), (-1, -1), FONT), ('FONTSIZE', (0, 0), (-1, -1), size), ('BACKGROUND', (0, 0), (-1, 0), NAVY_C),
                                           ('GRID', (0, 0), (-1, -1), 0.4, GRID_C), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), level['pad']),
                                           ('BOTTOMPADDING', (0, 0), (-1, -1), level['pad'])]))
        bar_row = Table([[Paragraph(_t('ساعات الشهر حسب المشروع'), bar)]], colWidths=[page_width])
        bar_row.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), NAVY_C), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        closing += [Spacer(1, level['gap'] * 0.7), bar_row, project_table]

    sign_w = page_width / 3
    sign = Table(
        [[Paragraph(_t('اعتماد المدير'), label), Paragraph(_t('المسؤول المباشر'), label), Paragraph(_t('الموظف'), label)],
         [' ', ' ', ' ']], colWidths=[sign_w] * 3, rowHeights=list(level['sign']))
    sign.setStyle(TableStyle([('LINEBELOW', (0, 1), (-1, 1), 0.7, colors.HexColor('#7F7F7F')), ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                              ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 14)]))
    closing += [Spacer(1, level['gap']), sign]

    story = [banner, who, Spacer(1, 6), table, Spacer(1, level['gap']), KeepTogether(closing)]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor('#595959'))
        canvas.drawCentredString(page[0] / 2, 0.28 * inch, f'{document.page}')
        canvas.drawString(margin, 0.28 * inch, f'{date.today():%d/%m/%Y}' + (f'  -  {generated_by}' if generated_by and not _ARABIC_RE.search(str(generated_by)) else ''))
        canvas.drawRightString(page[0] - margin, 0.28 * inch, 'One Stop ERP')
        canvas.setStrokeColor(GRID_C)
        canvas.line(margin, 0.42 * inch, page[0] - margin, 0.42 * inch)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer.getvalue(), doc.page
