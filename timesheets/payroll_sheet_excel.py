"""
Excel export of the employee payroll: the company's salary-sheet columns (08.2026.xlsx) on a clean, formal page -- Times New Roman,
right-to-left, A4 landscape, the company banner with the logo, a navy header row, banded lines, money with thousands separators,
a totals line, signature boxes (prepared / reviewed / approved), the notes written for the month and a footer with page numbers.
The overtime value, the total and the net are live formulas, so the file can still be adjusted by hand.
"""
import os
from datetime import date

from django.conf import settings
from django.contrib.staticfiles import finders
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.pagebreak import Break

from .services import payroll_sheet as sheet_data

FONT = 'Times New Roman'
NAVY = '1F3864'
BAND = 'F3F6FB'
TOTAL_FILL = 'D9E2F3'
NET_FILL = 'FFF6DD'
WIDTHS = [4.5, 26, 16, 12.5, 13, 6.5, 12, 10, 10.5, 11, 10, 11, 10.5, 13, 10.5, 14]

MONTHS_AR = ['كانون الثاني', 'شباط', 'آذار', 'نيسان', 'أيار', 'حزيران', 'تموز', 'آب', 'أيلول', 'تشرين الأول', 'تشرين الثاني', 'كانون الأول']
COMPANY_AR = 'شركة ون ستوب للمقاولات'
COMPANY_EN = 'One Stop For Contracting Co.'

MONEY = '#,##0.00'
HAIR = Side(style='thin', color='BFBFBF')
GRID = Border(left=HAIR, right=HAIR, top=HAIR, bottom=HAIR)


def prepared_by():
    return getattr(settings, 'PAYROLL_PREPARED_BY', '')


def reviewed_by():
    return getattr(settings, 'PAYROLL_REVIEWED_BY', '')


def approved_by():
    return getattr(settings, 'PAYROLL_APPROVED_BY', '')


def month_label(period_start):
    return f'{MONTHS_AR[period_start.month - 1]} {period_start.year}'


def build_payroll_workbook(payslips, period_start, notes, period_end=None):
    """`payslips` in the order of the sheet; `notes` is the list of note texts written for the month."""
    rows = sheet_data.sheet_rows(payslips)
    wb = Workbook()
    ws = wb.active
    ws.title = f'{period_start:%m.%Y}'
    ws.sheet_view.rightToLeft = True
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.3
    ws.page_margins.top, ws.page_margins.bottom = 0.45, 0.6
    ws.print_options.horizontalCentered = True
    ws.oddFooter.center.text = 'صفحة &P من &N'
    ws.oddFooter.center.font = f'{FONT},Regular'
    ws.oddFooter.right.text = 'One Stop ERP'
    ws.oddFooter.left.text = f'{date.today():%d/%m/%Y}'
    for i, width in enumerate(WIDTHS, start=1):
        ws.column_dimensions[L(i)].width = width
    last_col = len(WIDTHS)

    def font(size=11, bold=False, color='000000'):
        return Font(name=FONT, size=size, bold=bold, color=color)

    def merge(r, c1, c2, value, fnt, alignment, height=None):
        ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        cell = ws.cell(r, c1, value)
        cell.font, cell.alignment = fnt, alignment
        if height:
            ws.row_dimensions[r].height = height
        return cell

    centre = Alignment(horizontal='center', vertical='center', wrap_text=True)
    right = Alignment(horizontal='right', vertical='center', wrap_text=True)

    # banner: logo, company name, title and period
    merge(1, 1, last_col, COMPANY_AR, font(17, True, NAVY), centre, 28)
    merge(2, 1, last_col, COMPANY_EN, font(11, False, '595959'), centre, 17)
    merge(3, 1, last_col, f'جدول رواتب الموظفين - شهر {month_label(period_start)}', font(15, True), centre, 26)
    period_end = period_end or period_start
    merge(4, 1, last_col, f'{period_start:%d/%m/%Y}  -  {period_end:%d/%m/%Y}', font(10.5, False, '595959'), centre, 17)
    for c in range(1, last_col + 1):
        ws.cell(4, c).border = Border(bottom=Side(style='medium', color=NAVY))
    logo = finders.find('images/one_stop_logo.png')
    if logo and os.path.exists(logo):
        image = XLImage(logo)
        image.height, image.width = 62, 62 * image.width / image.height if image.height else 62
        ws.add_image(image, 'N1')   # the sheet is right-to-left, so the last columns are the left edge of the page
    header_row = 6
    ws.row_dimensions[5].height = 6

    # header
    for c, text in enumerate(sheet_data.HEADERS, start=1):
        cell = ws.cell(header_row, c, text)
        cell.font, cell.alignment = font(10.5, True, 'FFFFFF'), centre
        cell.fill = PatternFill('solid', fgColor=NAVY)
        cell.border = Border(left=Side(style='thin', color='FFFFFF'), right=Side(style='thin', color='FFFFFF'))
    ws.row_dimensions[header_row].height = 46
    ws.freeze_panes = ws.cell(header_row + 1, 3)
    ws.print_title_rows = f'{header_row}:{header_row}'

    first = header_row + 1
    r = first
    for index, row in enumerate(rows):
        fill = PatternFill('solid', fgColor=BAND) if index % 2 else None
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
            cell.font = font(11, bold=c in (14, 16))
            cell.border = GRID
            cell.alignment = Alignment(horizontal='right' if c in (2, 3) else 'center', vertical='center', wrap_text=c in (2, 3))
            if c in (7, 9, 10, 11, 12, 13, 14, 15, 16):
                cell.number_format = MONEY
            if c == 16:
                cell.fill = PatternFill('solid', fgColor=NET_FILL)
            elif fill:
                cell.fill = fill
        r += 1
    last = r - 1

    # totals
    for c in range(1, last_col + 1):
        cell = ws.cell(r, c)
        cell.font, cell.fill = font(11.5, True), PatternFill('solid', fgColor=TOTAL_FILL)
        cell.border = Border(top=Side(style='medium', color=NAVY), bottom=Side(style='double', color=NAVY), left=HAIR, right=HAIR)
        cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.cell(r, 2, f'المجموع ({len(rows)})').alignment = Alignment(horizontal='right', vertical='center')
    for c in (7, 10, 11, 12, 13, 14, 15, 16):
        ws.cell(r, c, f'=SUM({L(c)}{first}:{L(c)}{last})').number_format = MONEY
    ws.row_dimensions[r].height = 24
    r += 2

    # signatures (a long table sends the signatures and the notes together to the next page)
    if len(rows) > 15:
        ws.row_breaks.append(Break(id=r - 1))
    block = last_col // 3
    spans = [(1, block, 'إعداد - شؤون الموظفين', prepared_by()), (block + 1, 2 * block, 'تدقيق', reviewed_by()),
             (2 * block + 1, last_col, 'اعتماد', approved_by())]
    for c1, c2, label, name in spans:
        merge(r, c1, c2, label, font(11, True, NAVY), centre, 20)
        merge(r + 1, c1, c2, name or ' ', font(11), centre, 30)
        for c in range(c1, c2 + 1):
            ws.cell(r + 1, c).border = Border(bottom=Side(style='thin', color='7F7F7F'))
    r += 3

    # notes
    merge(r, 1, last_col, 'ملاحظات', font(11.5, True, NAVY), right, 20)
    for c in range(1, last_col + 1):
        ws.cell(r, c).border = Border(bottom=Side(style='thin', color=NAVY))
    r += 1
    for text in notes:
        merge(r, 1, last_col, text, font(11), right, 20 if len(text) < 150 else 34)
        r += 1
    return wb
