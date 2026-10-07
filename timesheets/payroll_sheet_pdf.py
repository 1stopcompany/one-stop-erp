"""
PDF of the employee payroll: the company's salary-sheet columns on a clean, formal page -- Times New Roman, A4 landscape, right to left,
the company banner with the logo, a navy header row, banded lines, a totals line, signature boxes, the notes and a footer with page
numbers. Same numbers as payroll_sheet_excel.

On a machine without Times New Roman (the Linux server) the PDF falls back to the Arabic font bundled with the system; copying
times.ttf / timesbd.ttf into static/fonts makes it use Times New Roman there too (see reports.utils).
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME as BOLD, MR_FONT_NAME as FONT, _ARABIC_RE, _t, rtl_paragraph

from .payroll_sheet_excel import (
    BAND, COMPANY_AR, COMPANY_EN, NAVY, NET_FILL, TOTAL_FILL, WIDTHS, approved_by, month_label, prepared_by, reviewed_by,
)
from .services import payroll_sheet as sheet_data

NAVY_C = colors.HexColor('#' + NAVY)
GRID_C = colors.HexColor('#BFBFBF')


def _money(value, blank_zero=False):
    if value in (None, ''):
        return ''
    value = Decimal(value).quantize(Decimal('0.01'))
    if blank_zero and value == 0:
        return ''
    return f'{value:,.2f}'


def _plain(value):
    if value in (None, ''):
        return ''
    value = Decimal(value).quantize(Decimal('0.01'))
    if value == 0:
        return ''
    return f'{value:f}'.rstrip('0').rstrip('.')


# Spacing levels: the roomy layout first; when the sheet (with its signatures and notes) does not fit one page, tighter ones.
LEVELS = [
    {'pad': 3.2, 'size': 8.3, 'logo': 0.7, 'gap': 16, 'sign': (16, 34)},
    {'pad': 2.3, 'size': 8.0, 'logo': 0.55, 'gap': 9, 'sign': (14, 26)},
    {'pad': 1.6, 'size': 7.6, 'logo': 0.45, 'gap': 5, 'sign': (12, 20)},
]


def generate_payroll_sheet_pdf(payslips, period_start, notes, period_end=None):
    """One page whenever it can be: tries the spacing levels in turn and keeps the first that fits a single page."""
    result = None
    for level in LEVELS:
        result, pages = _build(payslips, period_start, notes, period_end, level)
        if pages == 1:
            break
    return result


def _build(payslips, period_start, notes, period_end, level):
    rows = sheet_data.sheet_rows(payslips)
    total = sheet_data.totals(rows)
    period_end = period_end or period_start
    margin = 0.32 * inch
    page = landscape(A4)
    page_width = page[0] - 2 * margin
    buffer = BytesIO()
    title = f'جدول رواتب الموظفين - شهر {month_label(period_start)}'
    doc = SimpleDocTemplate(buffer, pagesize=page, topMargin=margin, bottomMargin=0.48 * inch, leftMargin=margin, rightMargin=margin,
                            title=sheet_data.title(period_start))
    base = getSampleStyleSheet()['Normal']
    size = level['size']
    cell = ParagraphStyle('PSCell', parent=base, fontName=FONT, fontSize=size, leading=size + 1.8, alignment=TA_CENTER)
    cell_r = ParagraphStyle('PSCellR', parent=cell, alignment=TA_RIGHT)
    head = ParagraphStyle('PSHead', parent=cell, fontName=BOLD, fontSize=size - 0.3, leading=size + 1.3, textColor=colors.white)
    company = ParagraphStyle('PSCompany', parent=cell, fontName=BOLD, fontSize=16, leading=19, textColor=NAVY_C)
    company_en = ParagraphStyle('PSCompanyEn', parent=cell, fontSize=9.5, leading=12, textColor=colors.HexColor('#595959'))
    title_style = ParagraphStyle('PSTitle', parent=cell, fontName=BOLD, fontSize=13, leading=17)
    period_style = ParagraphStyle('PSPeriod', parent=cell, fontSize=9, leading=12, textColor=colors.HexColor('#595959'))
    label = ParagraphStyle('PSLabel', parent=cell, fontName=BOLD, fontSize=9.5, leading=12, textColor=NAVY_C)
    note_head = ParagraphStyle('PSNoteHead', parent=cell_r, fontName=BOLD, fontSize=10, leading=13, textColor=NAVY_C)
    note = ParagraphStyle('PSNote', parent=cell_r, fontSize=9, leading=12)

    widths = [page_width * w / sum(WIDTHS) for w in WIDTHS]
    n = len(widths)

    def rtl(values):
        return list(reversed(values))

    def text(value, style, width):
        if value in (None, ''):
            return ''
        value = str(value)
        return rtl_paragraph(value, style, width - 6) if _ARABIC_RE.search(value) else Paragraph(value, style)

    # ---- banner
    logo_path = finders.find('images/one_stop_logo.png')
    banner_rows = [[Paragraph(_t(COMPANY_AR), company)], [Paragraph(COMPANY_EN, company_en)],
                   [Paragraph(_t(title), title_style)],
                   [Paragraph(_t(f'{period_start:%d/%m/%Y}  -  {period_end:%d/%m/%Y}'), period_style)]]
    banner_text = Table(banner_rows, colWidths=[page_width * 0.6])
    banner_text.setStyle(TableStyle([('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    cells = [banner_text]
    cols = [page_width * 0.62]
    if logo_path:
        from PIL import Image as PILImage
        with PILImage.open(logo_path) as logo_file:
            ratio = logo_file.width / logo_file.height
        logo = Image(logo_path, width=level['logo'] * inch * ratio, height=level['logo'] * inch)
        cells.append(logo)
        cols.append(page_width * 0.38)
    banner = Table([cells], colWidths=cols)
    banner.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                                ('ALIGN', (1, 0), (1, 0), 'LEFT'), ('LINEBELOW', (0, 0), (-1, 0), 1.2, NAVY_C),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))

    # ---- the table
    table_rows = [rtl([Paragraph('<br/>'.join(_t(line) for line in lines), head) for lines in sheet_data.HEADER_LINES])]
    for r in rows:
        values = [
            str(r['n']), text(r['name'], cell_r, widths[1]), text(r['position'], cell_r, widths[2]), str(r['national_id']),
            str(r['bank_account']), str(r['days'] or '-'), _money(r['base']), _plain(r['ot_hours']), _money(r['ot_rate'], True),
            _money(r['ot_value'], True), _money(r['allowances'], True), _money(r['deductions'], True), _money(r['tax'], True),
            _money(r['total']), _money(r['advances'], True), _money(r['net']),
        ]
        table_rows.append(rtl(values))
    totals_values = [''] * n
    bold_cell = ParagraphStyle('PSTotal', parent=cell, fontName=BOLD, fontSize=8.8)
    totals_values[1] = Paragraph(_t(f'المجموع ({len(rows)})'), ParagraphStyle('PSTotalLabel', parent=bold_cell, alignment=TA_RIGHT))
    for index, key in ((6, 'base'), (9, 'ot_value'), (10, 'allowances'), (11, 'deductions'), (12, 'tax'), (13, 'total'),
                       (14, 'advances'), (15, 'net')):
        totals_values[index] = Paragraph(_money(total[key], True) or '0.00', bold_cell)
    table_rows.append(rtl(totals_values))
    last_row = len(table_rows) - 1

    table = Table(table_rows, colWidths=rtl(widths), repeatRows=1)
    net_col = 0   # the net is the last logical column, i.e. the first physical one after mirroring
    style = [
        ('FONTNAME', (0, 0), (-1, -1), FONT), ('FONTSIZE', (0, 0), (-1, -1), size),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, GRID_C), ('TOPPADDING', (0, 0), (-1, -1), level['pad']), ('BOTTOMPADDING', (0, 0), (-1, -1), level['pad']),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY_C), ('LINEBELOW', (0, 0), (-1, 0), 0.8, NAVY_C),
        ('ROWBACKGROUNDS', (0, 1), (-1, last_row - 1), [colors.white, colors.HexColor('#' + BAND)]),
        ('BACKGROUND', (net_col, 1), (net_col, last_row - 1), colors.HexColor('#' + NET_FILL)),
        ('BACKGROUND', (0, last_row), (-1, last_row), colors.HexColor('#' + TOTAL_FILL)),
        ('LINEABOVE', (0, last_row), (-1, last_row), 1.2, NAVY_C), ('LINEBELOW', (0, last_row), (-1, last_row), 1.6, NAVY_C),
        ('FONTNAME', (0, last_row), (-1, last_row), BOLD),
    ]
    table.setStyle(TableStyle(style))

    # ---- signatures and notes
    sign_w = page_width / 3
    sign = Table(
        [[Paragraph(_t('اعتماد'), label), Paragraph(_t('تدقيق'), label), Paragraph(_t('إعداد - شؤون الموظفين'), label)],
         [text(approved_by(), cell, sign_w) or ' ', text(reviewed_by(), cell, sign_w) or ' ', text(prepared_by(), cell, sign_w) or ' ']],
        colWidths=[sign_w] * 3, rowHeights=list(level['sign']))
    sign.setStyle(TableStyle([('LINEBELOW', (0, 1), (-1, 1), 0.7, colors.HexColor('#7F7F7F')), ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                              ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 14)]))
    story = [banner, Spacer(1, 6), table, Spacer(1, level['gap'])]
    closing = [sign]
    if notes:
        closing += [Spacer(1, level['gap'] * 0.7), Paragraph(_t('ملاحظات'), note_head)]
        closing += [rtl_paragraph(line, note, page_width - 12) for line in notes]
    story.append(KeepTogether(closing))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor('#595959'))
        canvas.drawCentredString(page[0] / 2, 0.28 * inch, f'{document.page}')
        canvas.drawString(margin, 0.28 * inch, f'{date.today():%d/%m/%Y}')
        canvas.drawRightString(page[0] - margin, 0.28 * inch, 'One Stop ERP')
        canvas.setStrokeColor(GRID_C)
        canvas.line(margin, 0.42 * inch, page[0] - margin, 0.42 * inch)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer.getvalue(), doc.page
