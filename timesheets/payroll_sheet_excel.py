"""
Excel export of the employee payroll in the layout of the company's salary sheet (08.2026.xlsx): right-to-left, A4 landscape on one
page, a title row with the company logo, the 16 columns, a totals line, the prepared/reviewed line and the notes. The overtime
value, the total and the net are live formulas exactly as in that sheet, so the file can still be adjusted by hand.
"""
import os

from django.conf import settings
from django.contrib.staticfiles import finders
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from .services import payroll_sheet as sheet_data

WIDTHS = [2.9, 25.7, 16.3, 12.3, 12.7, 5.0, 11.4, 6.9, 6.3, 6.1, 5.9, 9.6, 8.9, 11.4, 10.4, 11.4]
THIN = Side(style='thin', color='000000')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill('solid', fgColor='DDEBF7')


def prepared_by():
    return getattr(settings, 'PAYROLL_PREPARED_BY', '')


def reviewed_by():
    return getattr(settings, 'PAYROLL_REVIEWED_BY', '')


def build_payroll_workbook(payslips, period_start, notes):
    """`payslips` in the order of the sheet; `notes` is the list of note texts written for the month."""
    rows = sheet_data.sheet_rows(payslips)
    wb = Workbook()
    ws = wb.active
    ws.title = f'{period_start:%m.%Y}'
    ws.sheet_view.rightToLeft = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.25
    ws.page_margins.top = ws.page_margins.bottom = 0.4
    ws.print_options.horizontalCentered = True
    for i, width in enumerate(WIDTHS, start=1):
        ws.column_dimensions[L(i)].width = width

    last_col = len(WIDTHS)
    bold = Font(name='Calibri', size=11, bold=True)
    plain = Font(name='Calibri', size=11)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # row 1: the title (with the logo beside it)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    cell = ws.cell(1, 1, sheet_data.title(period_start))
    cell.font, cell.alignment = Font(name='Calibri', size=12, bold=True), center
    ws.row_dimensions[1].height = 62
    for c in range(1, last_col + 1):
        ws.cell(1, c).border = BORDER
    logo = finders.find('images/one_stop_logo.png')
    if logo and os.path.exists(logo):
        image = XLImage(logo)
        image.height, image.width = 62, 62 * image.width / image.height if image.height else 62
        ws.add_image(image, 'I1')

    # row 2: the headers
    for c, text in enumerate(sheet_data.HEADERS, start=1):
        cell = ws.cell(2, c, text)
        cell.font, cell.fill, cell.alignment, cell.border = Font(name='Calibri', size=10, bold=True), HEADER_FILL, center, BORDER
    ws.row_dimensions[2].height = 45

    first = 3
    r = first
    for row in rows:
        values = {
            1: row['n'], 2: row['name'], 3: row['position'], 4: int(row['national_id']) if str(row['national_id']).isdigit() else row['national_id'],
            5: int(row['bank_account']) if str(row['bank_account']).isdigit() else row['bank_account'],
            6: row['days'] or '-', 7: float(row['base']), 8: float(row['ot_hours']) if row['ot_hours'] else None,
            9: round(float(row['ot_rate']), 2) if row['ot_rate'] else None,
            11: float(row['allowances']) if row['allowances'] else None,
            12: float(row['deductions']) if row['deductions'] else None,
            13: round(float(row['tax']), 2) if row['tax'] else None, 15: float(row['advances']) if row['advances'] else None,
        }
        formulas = {10: f'=I{r}*H{r}', 14: f'=G{r}+M{r}+J{r}+K{r}-L{r}', 16: f'=N{r}-M{r}-O{r}'}
        for c in range(1, last_col + 1):
            cell = ws.cell(r, c, values.get(c, formulas.get(c)))
            cell.font, cell.border = plain, BORDER
            cell.alignment = Alignment(horizontal='right' if c in (2, 3) else 'center', vertical='center', wrap_text=c in (2, 3))
        r += 1
    last = r - 1

    # the totals line, as in the sheet: base, deductions, tax, total, advances, net
    for c in range(1, last_col + 1):
        cell = ws.cell(r, c)
        cell.font, cell.fill, cell.border, cell.alignment = bold, HEADER_FILL, BORDER, Alignment(horizontal='center', vertical='center')
    for c in (7, 12, 13, 14, 15, 16):
        ws.cell(r, c, f'=SUM({L(c)}{first}:{L(c)}{last})')
    r += 1

    # prepared by / reviewed by
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    ws.cell(r, 1, f'إعداد : شؤون الموظفين : {prepared_by()}          تدقيق:').font = bold
    ws.cell(r, 4, reviewed_by()).font = bold
    ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=last_col)
    for c in range(1, last_col + 1):
        ws.cell(r, c).border = BORDER
        ws.cell(r, c).alignment = Alignment(horizontal='right', vertical='center')
    ws.row_dimensions[r].height = 22
    r += 1

    # notes: a heading row, then one row per note
    for text in ['ملاحظات:'] + list(notes):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        cell = ws.cell(r, 1, text)
        cell.font, cell.alignment = bold, Alignment(horizontal='right', vertical='center', wrap_text=True)
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = BORDER
        ws.row_dimensions[r].height = 20 if len(text) < 140 else 34
        r += 1
    return wb
