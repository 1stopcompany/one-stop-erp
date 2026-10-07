"""
PDF of the employee payroll in the layout of the company's salary sheet (08.2026.xlsx): A4 landscape, a title row with the logo, the
16 columns right to left, a totals line, the prepared / reviewed line and the notes. Same numbers as payroll_sheet_excel.
"""
from decimal import Decimal
from io import BytesIO

from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME as BOLD, MR_FONT_NAME as FONT, _ARABIC_RE, _t, rtl_paragraph

from .payroll_sheet_excel import WIDTHS, prepared_by, reviewed_by
from .services import payroll_sheet as sheet_data

HEADER_FILL = colors.HexColor('#DDEBF7')


def _num(value, blank_zero=True):
    """Like the sheet's General format: 8000, 219.9, 75 -- no thousands separator, no trailing zeros."""
    if value in (None, ''):
        return ''
    value = Decimal(value).quantize(Decimal('0.01'))
    if blank_zero and value == 0:
        return ''
    text = f'{value:f}'.rstrip('0').rstrip('.') if '.' in f'{value:f}' else f'{value:f}'
    return text or '0'


def generate_payroll_sheet_pdf(payslips, period_start, notes):
    rows = sheet_data.sheet_rows(payslips)
    total = sheet_data.totals(rows)
    margin = 0.3 * inch
    page = landscape(A4)
    page_width = page[0] - 2 * margin
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page, topMargin=margin, bottomMargin=margin, leftMargin=margin, rightMargin=margin,
                            title=sheet_data.title(period_start))
    base = getSampleStyleSheet()['Normal']
    cell = ParagraphStyle('PSCell', parent=base, fontName=FONT, fontSize=8, leading=10, alignment=TA_CENTER)
    cell_r = ParagraphStyle('PSCellR', parent=cell, alignment=TA_RIGHT)
    head = ParagraphStyle('PSHead', parent=cell, fontName=BOLD, fontSize=7.5, leading=9.5)
    bold = ParagraphStyle('PSBold', parent=cell, fontName=BOLD, fontSize=8.5, leading=11, alignment=TA_RIGHT)
    title_style = ParagraphStyle('PSTitle', parent=cell, fontName=BOLD, fontSize=11, leading=14)

    widths = [page_width * w / sum(WIDTHS) for w in WIDTHS]
    n = len(widths)

    def rtl(values):
        return list(reversed(values))

    def text(value, style, width):
        if value in (None, ''):
            return ''
        value = str(value)
        return rtl_paragraph(value, style, width - 6) if _ARABIC_RE.search(value) else Paragraph(value, style)

    # the title row: logo beside the title, both centred
    logo_path = finders.find('images/one_stop_logo.png')
    title_cells = []
    if logo_path:
        from PIL import Image as PILImage
        with PILImage.open(logo_path) as logo_file:
            ratio = logo_file.width / logo_file.height
        title_cells.append(Image(logo_path, width=0.62 * inch * ratio, height=0.62 * inch))
    title_cells.append(Paragraph(_t(sheet_data.title(period_start)), title_style))
    title_table = Table([title_cells], colWidths=([title_cells[0].drawWidth + 0.2 * inch] if len(title_cells) > 1 else []) + [3.2 * inch])
    title_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))

    table_rows = [[title_table] + [''] * (n - 1), rtl([text(h, head, w) for h, w in zip(sheet_data.HEADERS, widths)])]
    for r in rows:
        values = [
            str(r['n']), text(r['name'], cell_r, widths[1]), text(r['position'], cell_r, widths[2]), str(r['national_id']),
            str(r['bank_account']), str(r['days'] or '-'), _num(r['base'], False), _num(r['ot_hours']), _num(r['ot_rate']),
            _num(r['ot_value']), _num(r['allowances']), _num(r['deductions']), _num(r['tax']), _num(r['total'], False),
            _num(r['advances']), _num(r['net'], False),
        ]
        table_rows.append(rtl(values))
    totals_values = [''] * n
    for index, key in ((6, 'base'), (11, 'deductions'), (12, 'tax'), (13, 'total'), (14, 'advances'), (15, 'net')):
        totals_values[index] = Paragraph(_num(total[key], False), ParagraphStyle('PST', parent=cell, fontName=BOLD))
    table_rows.append(rtl(totals_values))
    totals_row = len(table_rows) - 1

    # prepared by / reviewed by, then the notes -- full-width rows (spans are in physical column order, i.e. mirrored)
    table_rows.append([Paragraph(_t(f'إعداد : شؤون الموظفين : {prepared_by()}          تدقيق: {reviewed_by()}'), bold)] + [''] * (n - 1))
    prepared_row = len(table_rows) - 1
    note_rows = []
    for line in ['ملاحظات:'] + list(notes):
        table_rows.append([rtl_paragraph(line, bold, page_width - 12)] + [''] * (n - 1))
        note_rows.append(len(table_rows) - 1)

    table = Table(table_rows, colWidths=rtl(widths), repeatRows=2)
    style = [
        ('GRID', (0, 0), (-1, -1), 0.7, colors.black), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), FONT), ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 1), (-1, 1), HEADER_FILL),
        ('BACKGROUND', (0, totals_row), (-1, totals_row), HEADER_FILL), ('SPAN', (0, prepared_row), (-1, prepared_row)),
    ]
    for r in note_rows:
        style.append(('SPAN', (0, r), (-1, r)))
    table.setStyle(TableStyle(style))
    doc.build([table])
    buffer.seek(0)
    return buffer.getvalue()
