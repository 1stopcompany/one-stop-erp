"""
PDF exports for the HR module: the monthly payroll statement, an
employee's Daily Time Record (DTR), and the "print" replacements for the
employee profile and employee list pages.

These replace the browser's own Ctrl+P print dialog (whose margins,
headers/footers and paper size depend on the user's browser settings,
not the system) with a real, consistently-formatted PDF generated
server-side -- same approach and helpers as procurement/pdf.py.
"""

from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from reports.utils import (
    FONT_NAME as AR_FONT_NAME, FONT_BOLD_NAME as AR_FONT_BOLD_NAME,
    MR_FONT_NAME, MR_FONT_BOLD_NAME, shape_text, _ARABIC_RE, _owner_report_logo_path,
)

FONT_NAME = MR_FONT_NAME
FONT_BOLD_NAME = MR_FONT_BOLD_NAME

BLUE = '#1f4788'
GREEN = '#198754'
RED = '#dc3545'
AMBER = '#ffc107'
LIGHT = '#f4f6fb'


def _styles():
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('PdfTitle', parent=styles['Heading1'], fontSize=16,
                                 textColor=colors.HexColor(BLUE), alignment=TA_CENTER,
                                 fontName=FONT_BOLD_NAME, spaceAfter=6),
        'sub': ParagraphStyle('PdfSub', parent=styles['Normal'], fontSize=10.5,
                               textColor=colors.HexColor('#555555'), alignment=TA_CENTER,
                               fontName=FONT_NAME, spaceAfter=2),
        'heading': ParagraphStyle('PdfHeading', parent=styles['Heading2'], fontSize=12,
                                   textColor=colors.white, backColor=colors.HexColor(BLUE),
                                   fontName=FONT_BOLD_NAME, spaceBefore=12, spaceAfter=6,
                                   alignment=TA_LEFT, borderPadding=(4, 6, 4, 6)),
        'cell': ParagraphStyle('PdfCell', parent=styles['Normal'], fontSize=9,
                                alignment=TA_LEFT, fontName=FONT_NAME, leading=12),
        'footer': ParagraphStyle('PdfFooter', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER,
                                  fontName=FONT_NAME, textColor=colors.HexColor('#999999')),
    }


def _smart(value, style, default='—'):
    """A Paragraph that auto-switches to the Arabic-capable font/reshaping when needed."""
    if value in (None, ''):
        return default
    text = str(value)
    if _ARABIC_RE.search(text):
        ar_font = AR_FONT_BOLD_NAME if style.fontName == FONT_BOLD_NAME else AR_FONT_NAME
        ar_style = ParagraphStyle(f'{style.name}Ar{id(style)}{id(text)}', parent=style, fontName=ar_font)
        return Paragraph(shape_text(text), ar_style)
    return Paragraph(text, style)


def _hdr_table(rows, col_widths, font_size=9, bold_last_row=False):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD_NAME),
        ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), font_size),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT)]),
    ]
    if bold_last_row:
        style_cmds += [
            ('FONTNAME', (0, -1), (-1, -1), FONT_BOLD_NAME),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dde6f5')),
            ('LINEABOVE', (0, -1), (-1, -1), 1.2, colors.HexColor(BLUE)),
        ]
    t.setStyle(TableStyle(style_cmds))
    return t


def _kv_table(pairs, page_width):
    rows = [[Paragraph(f'<b>{k}</b>', ParagraphStyle('kv', fontName=FONT_NAME, fontSize=9.5)), v] for k, v in pairs]
    t = Table(rows, colWidths=[page_width * 0.28, page_width * 0.72])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _name_or_dash(user):
    if not user:
        return '—'
    return user.get_full_name() or user.username


def _cover(elements, title, subtitle, styles):
    logo_path = _owner_report_logo_path()
    if logo_path:
        logo = Image(logo_path, width=3.0 * inch, height=0.7 * inch, kind='proportional')
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(title, styles['title']))
    elements.append(Paragraph(subtitle, styles['sub']))
    elements.append(Spacer(1, 0.15 * inch))


def _footer(elements, styles, generated_by=None):
    text = f'Generated automatically on {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    if generated_by:
        text += f' by {generated_by}'
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(text, styles['footer']))


# ------------------------------------------------------------------ #
# Payroll run (monthly payroll statement -- all employees)
# ------------------------------------------------------------------ #

def generate_payroll_run_pdf(payslips, period_start, is_posted, generated_by=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=0.6 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
    )
    page_width = landscape(A4)[0] - 1.0 * inch
    S = _styles()
    elements = []

    status_word = 'POSTED (مُرحّل)' if is_posted else 'DRAFT (مسودة)'
    _cover(elements, 'Payroll Statement', f'{period_start.strftime("%B %Y")} — {status_word}', S)

    headers = ['#', 'Employee', 'Department', 'Base Pay', 'OT Hrs', 'OT Pay', 'Allowances',
               'Gross', 'Unpaid Leave (d)', 'Unpaid Leave Ded.', 'Other Ded.', 'Advances', 'Net Pay']
    rows = [headers]
    totals = {k: 0 for k in ['base_pay', 'overtime_hours', 'overtime_pay', 'other_allowances', 'gross_pay',
                              'unpaid_leave_days', 'unpaid_leave_deduction', 'other_deductions', 'advances', 'net_pay']}
    for i, p in enumerate(payslips, start=1):
        for k in totals:
            totals[k] += float(getattr(p, k))
        rows.append([
            str(i), _smart(p.employee.full_name, S['cell']),
            _smart(p.employee.department.name if p.employee.department_id else '', S['cell']),
            f'{p.base_pay:,.2f}', f'{p.overtime_hours:g}', f'{p.overtime_pay:,.2f}', f'{p.other_allowances:,.2f}',
            f'{p.gross_pay:,.2f}', f'{p.unpaid_leave_days:g}', f'{p.unpaid_leave_deduction:,.2f}',
            f'{p.other_deductions:,.2f}', f'{p.advances:,.2f}', f'{p.net_pay:,.2f}',
        ])
    rows.append([
        '', 'TOTAL', '', f"{totals['base_pay']:,.2f}", f"{totals['overtime_hours']:g}",
        f"{totals['overtime_pay']:,.2f}", f"{totals['other_allowances']:,.2f}", f"{totals['gross_pay']:,.2f}",
        f"{totals['unpaid_leave_days']:g}", f"{totals['unpaid_leave_deduction']:,.2f}",
        f"{totals['other_deductions']:,.2f}", f"{totals['advances']:,.2f}", f"{totals['net_pay']:,.2f}",
    ])

    col_widths = [page_width * w for w in
                  [0.03, 0.16, 0.11, 0.08, 0.06, 0.07, 0.08, 0.08, 0.08, 0.09, 0.08, 0.08, 0.08]]
    elements.append(_hdr_table(rows, col_widths, font_size=8, bold_last_row=True))
    elements.append(Paragraph(
        'Tax is shown for information only elsewhere in the system and is not subtracted from Net Pay.',
        S['footer'],
    ))
    _footer(elements, S, generated_by)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------ #
# Wages run (كشف الصرف -- monthly disbursement statement, all day-labor
# workers) and a single worker's wage slip, mirroring the salaried
# payroll run / payslip pair above.
# ------------------------------------------------------------------ #

def generate_wages_run_pdf(wage_slips, period_start, is_posted, generated_by=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=0.6 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
    )
    page_width = landscape(A4)[0] - 1.0 * inch
    S = _styles()
    elements = []

    status_word = 'POSTED (مُرحّل)' if is_posted else 'DRAFT (مسودة)'
    _cover(elements, 'Wages Statement (كشف الصرف)', f'{period_start.strftime("%B %Y")} — {status_word}', S)

    headers = ['#', 'Worker', 'Trade', 'Days', 'OT Hrs', 'Base Pay', 'OT Pay',
               'Gross', 'Allowances', 'Deductions', 'Advances', 'Net Pay']
    rows = [headers]
    totals = {k: 0 for k in ['total_days', 'overtime_hours', 'base_pay', 'overtime_pay', 'gross_pay',
                              'other_allowances', 'other_deductions', 'total_advances', 'net_pay']}
    for i, w in enumerate(wage_slips, start=1):
        for k in totals:
            totals[k] += float(getattr(w, k))
        rows.append([
            str(i), _smart(w.worker.full_name, S['cell']), _smart(w.worker.trade, S['cell'], default=''),
            f'{w.total_days:g}', f'{w.overtime_hours:g}', f'{w.base_pay:,.2f}', f'{w.overtime_pay:,.2f}',
            f'{w.gross_pay:,.2f}', f'{w.other_allowances:,.2f}', f'{w.other_deductions:,.2f}',
            f'{w.total_advances:,.2f}', f'{w.net_pay:,.2f}',
        ])
    rows.append([
        '', 'TOTAL', '', f"{totals['total_days']:g}", f"{totals['overtime_hours']:g}",
        f"{totals['base_pay']:,.2f}", f"{totals['overtime_pay']:,.2f}", f"{totals['gross_pay']:,.2f}",
        f"{totals['other_allowances']:,.2f}", f"{totals['other_deductions']:,.2f}",
        f"{totals['total_advances']:,.2f}", f"{totals['net_pay']:,.2f}",
    ])

    col_widths = [page_width * w for w in [0.03, 0.18, 0.11, 0.07, 0.07, 0.1, 0.09, 0.1, 0.1, 0.1, 0.08, 0.09]]
    elements.append(_hdr_table(rows, col_widths, font_size=8, bold_last_row=True))
    _footer(elements, S, generated_by)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------ #
# Day-labor wages sheet in the company's own "كشف اجور عمال" layout
# ------------------------------------------------------------------ #

# (header label, width weight) in logical order; the table is printed right-to-left so the
# first column lands on the page's right edge, like the Excel sheet it replaces.
WAGES_SHEET_COLUMNS = [
    ('#', 0.03), ('الاســـم', 0.165), ('طبيعة العمل', 0.095), ('ايام العمل', 0.05), ('ايام الجمع', 0.05),
    ('مجموع الايام شامل جمع', 0.062), ('الاجر اليومي', 0.058), ('الاجر المدفوع', 0.058), ('المجموع', 0.066),
    ('عدد الساعات الاضافية', 0.055), ('سعر الساعة', 0.05), ('قيمة الساعات', 0.058), ('الاجر المستحق', 0.066),
    ('سلف', 0.045), ('الصافي للدفع', 0.07), ('رقم الهوية', 0.075), ('التوقيع', 0.075),
]


def _plain_num(value):
    """2 decimals, trailing zeros dropped (7.00 -> 7, 2.33 stays)."""
    text = f'{value:.2f}'.rstrip('0').rstrip('.')
    return text or '0'


def generate_wages_sheet_pdf(sheet, generated_by=None):
    """
    The month's day-labor wages in the layout of the company's Excel "كشف اجور عمال": a
    memo header, one titled table per project (every column of that sheet, with a section
    total), any worker-level adjustments, the grand total, and the prepared/reviewed line.
    `sheet` comes from daily_worker_payroll_service.wages_sheet().
    """
    from django.conf import settings
    from reportlab.lib.enums import TA_RIGHT
    from reports.utils import _t, rtl_paragraph

    buffer = BytesIO()
    margin = 0.3 * inch
    page_size = landscape(A4)
    page_width = page_size[0] - 2 * margin
    doc = SimpleDocTemplate(buffer, pagesize=page_size, topMargin=margin, bottomMargin=margin,
                            leftMargin=margin, rightMargin=margin)
    base = getSampleStyleSheet()['Normal']

    memo = ParagraphStyle('WSMemo', parent=base, fontName=FONT_BOLD_NAME, fontSize=10, leading=14, alignment=TA_RIGHT)
    title = ParagraphStyle('WSTitle', parent=base, fontName=FONT_BOLD_NAME, fontSize=10.5, leading=14,
                           alignment=TA_CENTER, textColor=colors.white, backColor=colors.HexColor(BLUE), borderPadding=(3, 4, 3, 4))
    head = ParagraphStyle('WSHead', parent=base, fontName=FONT_BOLD_NAME, fontSize=7, leading=8.5, alignment=TA_CENTER,
                          textColor=colors.white)
    cell = ParagraphStyle('WSCell', parent=base, fontName=FONT_NAME, fontSize=8, leading=10, alignment=TA_CENTER)
    foot = ParagraphStyle('WSFoot', parent=base, fontName=FONT_BOLD_NAME, fontSize=10, leading=14, alignment=TA_RIGHT)

    widths_total = sum(w for _, w in WAGES_SHEET_COLUMNS)
    widths = [page_width * w / widths_total for _, w in WAGES_SHEET_COLUMNS]
    ncols = len(widths)

    def rtl(cells):
        return list(reversed(cells))

    def table(rows, col_widths, extra=None):
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NAME), ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]
        t.setStyle(TableStyle(cmds + (extra or [])))
        return t

    def text_cell(value, style=cell, width=None):
        if not value:
            return ''
        return rtl_paragraph(value, style, (width or 80) - 6) if _ARABIC_RE.search(str(value)) else Paragraph(str(value), style)

    month_label = f'{sheet["period_start"]:%m.%Y}'
    elements = [
        Paragraph(_t('إلى : الادارة العامة.'), memo),
        Paragraph(_t('الموضوع: استحقاق صرف الرواتب والأجور.'), memo),
        Paragraph(_t(f'بالإشارة إلى الموضوع أعلاه ، نعلمكم باستحقاق صرف الرواتب والأجور التالية عن شهر {month_label}'), memo),
        Spacer(1, 0.12 * inch),
    ]

    header = rtl([text_cell(label, head, w) for (label, _), w in zip(WAGES_SHEET_COLUMNS, widths)])
    idx = {label: ncols - 1 - i for i, (label, _) in enumerate(WAGES_SHEET_COLUMNS)}  # column index once reversed
    money = lambda v: f'{v:,.2f}'

    if not sheet['sections']:
        elements.append(Paragraph(_t('لا يوجد حضور أو إدخالات لهذا الشهر.'), memo))

    for section in sheet['sections']:
        name = section['project'].name if section['project'] else '—'
        section_title = [Paragraph(_t(f'كشف اجور عمال ({name})'), title), Spacer(1, 0.04 * inch)]
        rows = [header]
        bold = ParagraphStyle('WSTot', parent=cell, fontName=FONT_BOLD_NAME)
        sub_title = ParagraphStyle('WSSub', parent=cell, fontName=FONT_BOLD_NAME, alignment=TA_RIGHT)
        sub_title_rows, sub_total_rows = [], []

        def total_line(label, due, net):
            line = [''] * ncols
            line[idx['الاجر المستحق']] = money(due)
            line[idx['الصافي للدفع']] = money(net)
            line[idx['الاســـم']] = Paragraph(_t(label), bold)
            return line

        for group in section['groups']:
            if section['has_subs']:      # a project split into subs (متفرقات): each sub gets a title and its own total
                sub_title_rows.append(len(rows))
                rows.append([Paragraph(_t(group['name'] or 'بدون متفرقة'), sub_title)] + [''] * (ncols - 1))
            for r in group['rows']:
                rows.append(rtl([
                    str(r['n']), text_cell(r['worker'].full_name, cell, widths[1]), text_cell(r['trade'], cell, widths[2]),
                    _plain_num(r['days']), _plain_num(r['friday_days']), _plain_num(r['total_days']),
                    money(r['daily_wage']), money(r['paid_rate']), money(r['total']),
                    _plain_num(r['overtime_hours']) if r['overtime_hours'] else '', money(r['hour_rate']),
                    money(r['overtime_value']) if r['overtime_value'] else '',
                    money(r['due']), money(r['advances']) if r['advances'] else '', money(r['net']),
                    str(r['national_id']), '',
                ]))
            if section['has_subs']:
                sub_total_rows.append(len(rows))
                rows.append(total_line(f"مجموع {group['name'] or 'بدون متفرقة'}", group['total_due'], group['total_net']))
        rows.append(total_line('المجموع النهائي للمتفرقات' if section['has_subs'] else 'المجموع',
                               section['total_due'], section['total_net']))
        last = len(rows) - 1
        styles = [
            ('BACKGROUND', (0, last), (-1, last), colors.HexColor('#e8f0f8')),
            ('FONTNAME', (0, last), (-1, last), FONT_BOLD_NAME),
            ('BACKGROUND', (idx['الصافي للدفع'], 1), (idx['الصافي للدفع'], last - 1), colors.HexColor('#fff9c4')),
        ]
        for r in sub_title_rows:
            styles += [('SPAN', (0, r), (-1, r)), ('BACKGROUND', (0, r), (-1, r), colors.HexColor('#d6e4f5'))]
        for r in sub_total_rows:
            styles += [('BACKGROUND', (0, r), (-1, r), colors.HexColor('#f1f5fa')), ('FONTNAME', (0, r), (-1, r), FONT_BOLD_NAME)]
        section_table = table(rows, list(reversed(widths)), styles)
        # a title never sits alone at the foot of a page: keep it with its table (long tables still split)
        elements.append(KeepTogether(section_title + [section_table]) if len(rows) < 30 else section_title[0])
        if len(rows) >= 30:
            elements += [section_title[1], section_table]
        elements.append(Spacer(1, 0.09 * inch))

    if sheet['adjustments']:
        elements.append(Paragraph(_t('تسويات على مستوى العامل (بدلات / خصومات / سلف)'), title))
        elements.append(Spacer(1, 0.04 * inch))
        adj_labels = ['الاســـم', 'بدلات', 'خصومات', 'سلف', 'الأثر على الصافي']
        adj_widths = [page_width * w for w in (0.35, 0.15, 0.15, 0.15, 0.2)]
        rows = [rtl([text_cell(l, head, w) for l, w in zip(adj_labels, adj_widths)])]
        for a in sheet['adjustments']:
            rows.append(rtl([text_cell(a['worker'].full_name, cell, adj_widths[0]), money(a['allowances']),
                             money(a['deductions']), money(a['advances']), money(a['effect'])]))
        elements.append(table(rows, list(reversed(adj_widths))))
        elements.append(Spacer(1, 0.14 * inch))

    grand = Table([[money(sheet['grand_total']), Paragraph(_t('المجموع'), ParagraphStyle('WSGrand', parent=cell, fontName=FONT_BOLD_NAME, fontSize=11))]],
                  colWidths=[page_width * 0.2, page_width * 0.12], hAlign='RIGHT')
    grand.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.8, colors.black), ('FONTNAME', (0, 0), (0, 0), FONT_BOLD_NAME),
                               ('FONTSIZE', (0, 0), (0, 0), 11), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                               ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff9c4')),
                               ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    prepared = getattr(settings, 'WAGES_PREPARED_BY', '') or ' ' * 22
    reviewed = getattr(settings, 'WAGES_REVIEWED_BY', '') or ' ' * 22
    closing = [grand, Spacer(1, 0.1 * inch), Paragraph(_t(f'اعداد : ( {prepared} ) / تدقيق : ( {reviewed} )'), foot)]
    if generated_by:
        closing.append(Paragraph(f'Generated {datetime.now():%d/%m/%Y %H:%M} by {generated_by}',
                                 ParagraphStyle('WSGen', parent=base, fontName=FONT_NAME, fontSize=7, textColor=colors.grey)))
    elements.append(KeepTogether(closing))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_wage_slip_pdf(wage_slip):
    """A single worker's wage slip, same design language as generate_payslip_pdf."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.7 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    page_width = A4[0] - 1.4 * inch
    S = _styles()
    elements = []
    worker = wage_slip.worker

    _cover(elements, 'Wage Slip (كشف صرف)', wage_slip.period_start.strftime('%B %Y'), S)
    status_color = GREEN if wage_slip.status == 'posted' else AMBER
    status_label = 'POSTED — Final' if wage_slip.status == 'posted' else 'DRAFT — Not yet finalized'
    status_table = Table([[status_label]], colWidths=[page_width])
    status_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(status_color)),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white if wage_slip.status == 'posted' else colors.black),
        ('FONTNAME', (0, 0), (-1, -1), FONT_BOLD_NAME),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(status_table)
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(_kv_table([
        ('Worker', _smart(worker.full_name, S['cell'])),
        ('Trade', _smart(worker.trade, S['cell'])),
        ('National ID', worker.national_id or '—'),
        ('Pay Period', f'{wage_slip.period_start.strftime("%d/%m/%Y")} — {wage_slip.period_end.strftime("%d/%m/%Y")}'),
    ], page_width))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph('Earnings', S['heading']))
    elements.append(_hdr_table([
        ['Item', 'Amount'],
        [f'Base Pay ({wage_slip.total_days:g} day(s))', f'{wage_slip.base_pay:,.2f}'],
        [f'Overtime ({wage_slip.overtime_hours:g} h)', f'{wage_slip.overtime_pay:,.2f}'],
        ['Other Allowances', f'{wage_slip.other_allowances:,.2f}'],
        ['Gross Pay', f'{wage_slip.gross_pay:,.2f}'],
    ], [page_width * 0.7, page_width * 0.3], font_size=10, bold_last_row=True))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph('Deductions', S['heading']))
    elements.append(_hdr_table([
        ['Item', 'Amount'],
        ['Other Deductions', f'{wage_slip.other_deductions:,.2f}'],
        ['Advances', f'{wage_slip.total_advances:,.2f}'],
        ['Total Deductions', f'{(wage_slip.other_deductions + wage_slip.total_advances):,.2f}'],
    ], [page_width * 0.7, page_width * 0.3], font_size=10, bold_last_row=True))
    elements.append(Spacer(1, 0.25 * inch))

    net_table = Table([['NET PAY', f'{wage_slip.net_pay:,.2f}']], colWidths=[page_width * 0.7, page_width * 0.3])
    net_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(BLUE)),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), FONT_BOLD_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 13),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(net_table)
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(
        f'Income tax (information only, not deducted from Net Pay): {wage_slip.income_tax:,.2f}', S['footer'],
    ))
    _footer(elements, S)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------ #
# Daily Time Record (one employee, one month)
# ------------------------------------------------------------------ #

STATUS_LABELS = {
    'present': 'Present', 'absent': 'Absent', 'on_leave': 'On Leave',
    'unpaid_leave': 'Unpaid Leave', 'rest_day': 'Rest Day', 'holiday': 'Holiday',
}


def generate_dtr_pdf(employee, records, period_start, generated_by=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.6 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    page_width = A4[0] - 1.2 * inch
    S = _styles()
    elements = []

    _cover(elements, 'Daily Time Record', f'{period_start.strftime("%B %Y")}', S)
    elements.append(_kv_table([
        ('Employee', _smart(employee.full_name, S['cell'])),
        ('Position', _smart(employee.position.title if employee.position_id else '', S['cell'])),
        ('Department', _smart(employee.department.name if employee.department_id else '', S['cell'])),
    ], page_width))
    elements.append(Spacer(1, 0.15 * inch))

    counts = {}
    total_overtime = 0
    total_late = 0
    total_undertime = 0
    headers = ['Date', 'Day', 'Status', 'Clock In', 'Clock Out', 'Late (m)', 'Undertime (m)', 'OT (h)', 'Notes']
    rows = [headers]
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1
        total_overtime += float(r.overtime_hours)
        total_late += r.late_minutes
        total_undertime += r.undertime_minutes
        rows.append([
            r.date.strftime('%Y-%m-%d'), r.date.strftime('%a'),
            STATUS_LABELS.get(r.status, r.status),
            r.clock_in.strftime('%H:%M') if r.clock_in else '—',
            r.clock_out.strftime('%H:%M') if r.clock_out else '—',
            str(r.late_minutes), str(r.undertime_minutes), f'{r.overtime_hours:g}',
            _smart(r.notes, S['cell'], default=''),
        ])
    col_widths = [page_width * w for w in [0.11, 0.07, 0.14, 0.1, 0.1, 0.1, 0.12, 0.08, 0.18]]
    elements.append(_hdr_table(rows, col_widths, font_size=8))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph('Summary', S['heading']))
    summary_rows = [['Present', 'Absent', 'On Leave', 'Unpaid Leave', 'Rest Day', 'Holiday',
                      'Total OT (h)', 'Total Late (m)', 'Total Undertime (m)']]
    summary_rows.append([
        str(counts.get('present', 0)), str(counts.get('absent', 0)), str(counts.get('on_leave', 0)),
        str(counts.get('unpaid_leave', 0)), str(counts.get('rest_day', 0)), str(counts.get('holiday', 0)),
        f'{total_overtime:g}', str(total_late), str(total_undertime),
    ])
    elements.append(_hdr_table(summary_rows, [page_width / 9] * 9, font_size=8.5))

    _footer(elements, S, generated_by)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------ #
# Single payslip (one employee, one month) -- the actual pay stub, used
# by both the web Payroll tab and the mobile app's Payslips screen.
# ------------------------------------------------------------------ #

def generate_payslip_pdf(payslip):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.7 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    page_width = A4[0] - 1.4 * inch
    S = _styles()
    elements = []
    employee = payslip.employee

    _cover(elements, 'Payslip', payslip.period_start.strftime('%B %Y'), S)
    status_color = GREEN if payslip.status == 'posted' else AMBER
    status_label = 'POSTED — Final' if payslip.status == 'posted' else 'DRAFT — Not yet finalized'
    status_table = Table([[status_label]], colWidths=[page_width])
    status_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(status_color)),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white if payslip.status == 'posted' else colors.black),
        ('FONTNAME', (0, 0), (-1, -1), FONT_BOLD_NAME),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(status_table)
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(_kv_table([
        ('Employee', _smart(employee.full_name, S['cell'])),
        ('Employee ID', employee.employee_id),
        ('Department', _smart(employee.department.name if employee.department_id else '—', S['cell'])),
        ('Position', _smart(employee.position.title if employee.position_id else '—', S['cell'])),
        ('Pay Period', f'{payslip.period_start.strftime("%d/%m/%Y")} — {payslip.period_end.strftime("%d/%m/%Y")}'),
    ], page_width))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph('Earnings', S['heading']))
    earnings_rows = [
        ['Base Pay', f'{payslip.base_pay:,.2f}'],
        [f'Overtime ({payslip.overtime_hours:g} h)', f'{payslip.overtime_pay:,.2f}'],
        ['Other Allowances', f'{payslip.other_allowances:,.2f}'],
    ]
    if payslip.pay_basis == 'hourly':
        earnings_rows[1:1] = [
            [f'Regular ({payslip.regular_hours:g} h)', '—'],
            [f'Weekend ({payslip.weekend_hours:g} h)', f'{payslip.weekend_pay:,.2f}'],
            [f'Holiday ({payslip.holiday_hours:g} h)', f'{payslip.holiday_pay:,.2f}'],
        ]
    earnings_rows.append(['Gross Pay', f'{payslip.gross_pay:,.2f}'])
    elements.append(_hdr_table(
        [['Item', 'Amount']] + earnings_rows, [page_width * 0.7, page_width * 0.3],
        font_size=10, bold_last_row=True,
    ))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph('Deductions', S['heading']))
    deduction_rows = [
        [f'Unpaid Leave ({payslip.unpaid_leave_days:g} day(s))', f'{payslip.unpaid_leave_deduction:,.2f}'],
        ['Other Deductions', f'{payslip.other_deductions:,.2f}'],
        ['Advances', f'{payslip.advances:,.2f}'],
        ['Total Deductions', f'{(payslip.unpaid_leave_deduction + payslip.other_deductions + payslip.advances):,.2f}'],
    ]
    elements.append(_hdr_table(
        [['Item', 'Amount']] + deduction_rows, [page_width * 0.7, page_width * 0.3],
        font_size=10, bold_last_row=True,
    ))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(
        f'Tax (information only, not deducted from Net Pay): {payslip.tax:,.2f}', S['footer'],
    ))
    elements.append(Spacer(1, 0.25 * inch))

    net_table = Table([['NET PAY', f'{payslip.net_pay:,.2f}']], colWidths=[page_width * 0.7, page_width * 0.3])
    net_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(BLUE)),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), FONT_BOLD_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 13),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'), ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(net_table)

    _footer(elements, S)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------ #
# Annual leave summary (كشف ملخص الإجازات) -- one employee, one year
# ------------------------------------------------------------------ #

def generate_leave_summary_pdf(summary):
    from datetime import date as _date

    employee = summary['employee']
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.7 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    page_width = A4[0] - 1.4 * inch
    S = _styles()
    elements = []

    _cover(elements, 'Annual Leave Summary', f'{summary["year"]}', S)
    elements.append(_kv_table([
        ('Employee', _smart(employee.full_name, S['cell'])),
        ('Employee ID', employee.employee_id),
        ('Department', _smart(employee.department.name if employee.department_id else '—', S['cell'])),
    ], page_width))
    elements.append(Spacer(1, 0.2 * inch))

    balance_rows = [
        ['Annual Leave Days', 'Carried Over', 'Undertime Ded.', 'Total Allowance', 'Used This Year', 'Remaining'],
        [f'{summary["annual_leave_days"]:g}', f'+{summary["carried_over"]:g}', f'-{summary["undertime_deducted_days"]:g}',
         f'{summary["total_allowance"]:g}', f'{summary["total_used"]:g}', f'{summary["remaining"]:g}'],
    ]
    elements.append(_hdr_table(balance_rows, [page_width / 6] * 6, font_size=9.5, bold_last_row=True))
    elements.append(Spacer(1, 0.25 * inch))

    elements.append(Paragraph('Days Taken Per Month', S['heading']))
    month_headers = [_date(summary['year'], m, 1).strftime('%b') for m in range(1, 13)]
    month_values = [str(summary['by_month'][m]) for m in range(1, 13)]
    elements.append(_hdr_table([month_headers, month_values], [page_width / 12] * 12, font_size=8.5))
    elements.append(Spacer(1, 0.25 * inch))

    if summary['requests']:
        elements.append(Paragraph('Approved Leave Requests This Year', S['heading']))
        rows = [['Type', 'From', 'To', 'Days']]
        for req in summary['requests']:
            rows.append([
                req.get_request_type_display(), req.start_date.strftime('%d/%m/%Y'),
                req.end_date.strftime('%d/%m/%Y'), str(req.days),
            ])
        elements.append(_hdr_table(rows, [page_width * 0.3, page_width * 0.25, page_width * 0.25, page_width * 0.2], font_size=9.5))
    else:
        elements.append(Paragraph('No approved leave requests this year.', S['cell']))

    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        "Friday is excluded from every count, even when it falls inside a request's date range. "
        "Annual allocation is tenure-based (14 days/year under 5 years of service, 21 days/year at 5+). "
        "Unused days carry over for up to 2 years before expiring.",
        S['footer'],
    ))
    _footer(elements, S)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------ #
# Employee profile ("print" replacement)
# ------------------------------------------------------------------ #

def generate_employee_profile_pdf(employee):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.6 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    page_width = A4[0] - 1.2 * inch
    S = _styles()
    elements = []

    _cover(elements, 'Employee Profile', employee.employee_id, S)
    elements.append(Paragraph(shape_text(employee.full_name), ParagraphStyle(
        'name', parent=S['title'], fontSize=14, textColor=colors.HexColor('#333333'),
    )))
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(Paragraph('General Information', S['heading']))
    elements.append(_kv_table([
        ('Email', employee.email or '—'),
        ('Phone', employee.phone_number or '—'),
        ('Address', _smart(
            ', '.join(filter(None, [employee.address_line1, employee.city, employee.state, employee.country])),
            S['cell'],
        )),
        ('Emergency Contact', _smart(
            f'{employee.emergency_contact_name} ({employee.emergency_contact_relationship}) — {employee.emergency_contact_phone}'
            if employee.emergency_contact_name else '—', S['cell'],
        )),
    ], page_width))
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(Paragraph('Job', S['heading']))
    elements.append(_kv_table([
        ('Department', _smart(employee.department.name if employee.department_id else '—', S['cell'])),
        ('Position', _smart(employee.position.title if employee.position_id else '—', S['cell'])),
        ('Employment Type', employee.get_employment_type_display()),
        ('Employment Status', employee.get_employment_status_display()),
        ('Hire Date', employee.hire_date.strftime('%d/%m/%Y') if employee.hire_date else '—'),
        ('Termination Date', employee.termination_date.strftime('%d/%m/%Y') if employee.termination_date else '—'),
        ('Manager', _smart(employee.manager.full_name if employee.manager_id else '—', S['cell'])),
    ], page_width))
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(Paragraph('Leave Balance', S['heading']))
    from django.utils import timezone as _tz
    from timesheets.services.attendance_service import compute_leave_summary
    leave_summary = compute_leave_summary(employee, _tz.localdate().year)
    elements.append(_kv_table([
        ('Annual Leave Days', str(leave_summary['annual_leave_days'])),
        ('Carried Over', f"+{leave_summary['carried_over']}"),
        ('Total Allowance', str(leave_summary['total_allowance'])),
        ('Used This Year', str(leave_summary['total_used'])),
        ('Remaining', str(leave_summary['remaining'])),
    ], page_width))
    elements.append(Spacer(1, 0.15 * inch))

    recent_payslips = employee.payslips.exclude(status='excluded').order_by('-period_start')[:6]
    if recent_payslips:
        elements.append(Paragraph('Recent Payslips', S['heading']))
        rows = [['Period', 'Base Pay', 'Gross', 'Net Pay', 'Status']]
        for p in recent_payslips:
            rows.append([p.period_start.strftime('%B %Y'), f'{p.base_pay:,.2f}',
                         f'{p.gross_pay:,.2f}', f'{p.net_pay:,.2f}', p.get_status_display()])
        elements.append(_hdr_table(rows, [page_width * w for w in [0.3, 0.2, 0.2, 0.2, 0.1]], font_size=9))

    _footer(elements, S)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------------------ #
# Employee list ("print" replacement)
# ------------------------------------------------------------------ #

def generate_employee_list_pdf(employees, filter_summary=''):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.6 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    page_width = A4[0] - 1.2 * inch
    S = _styles()
    elements = []

    _cover(elements, 'Employee List', filter_summary or 'All Employees', S)

    headers = ['#', 'Employee ID', 'Name', 'Department', 'Position', 'Status', 'Hire Date']
    rows = [headers]
    for i, emp in enumerate(employees, start=1):
        rows.append([
            str(i), emp.employee_id, _smart(emp.full_name, S['cell']),
            _smart(emp.department.name if emp.department_id else '', S['cell']),
            _smart(emp.position.title if emp.position_id else '', S['cell']),
            emp.get_employment_status_display(),
            emp.hire_date.strftime('%d/%m/%Y') if emp.hire_date else '—',
        ])
    col_widths = [page_width * w for w in [0.05, 0.13, 0.24, 0.18, 0.18, 0.12, 0.1]]
    elements.append(_hdr_table(rows, col_widths, font_size=8.5))
    elements.append(Paragraph(f'Total: {len(employees)} employee(s)', S['footer']))

    _footer(elements, S)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
