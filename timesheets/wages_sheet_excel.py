"""
Excel twin of the day-labor wages sheet PDF (timesheets.pdf.generate_wages_sheet_pdf): the company's own
"كشف اجور عمال" layout -- memo header, one titled table per project, section totals, grand total and the
prepared/reviewed line. The typed columns (days, paid rate, overtime hours, advances) are values; every
other column is a live Excel formula exactly like the original sheet (Friday days = days / 6, total days
= days + Fridays, daily wage = paid rate x 6 / 7, total = paid rate x days, hour rate = paid rate / 8 x 1.5,
...), so the file can still be adjusted by hand after export.
"""
from django.conf import settings
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.pagebreak import Break

HEADERS = [
    '#', 'الاســـم', 'طبيعة العمل', 'ايام العمل', 'ايام الجمع', 'مجموع الايام شامل جمع', 'الاجر اليومي', 'الاجر المدفوع',
    'المجموع', 'عدد الساعات الاضافية', 'سعر الساعة', 'قيمة الساعات', 'الاجر المستحق', 'سلف', 'الصافي للدفع',
    'رقم الهوية', 'التوقيع',
]
WIDTHS = [5, 38, 19, 9, 9, 12, 10, 10, 11, 10, 10, 10, 12, 9, 14, 16, 12]
THIN = Side(style='thin', color='999999')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
BLUE = PatternFill('solid', fgColor='1F4788')
LIGHT = PatternFill('solid', fgColor='E8F0F8')
YELLOW = PatternFill('solid', fgColor='FFFF00')
MONEY = '#,##0.00'
PAGE_POINTS = 720   # usable height of one printed A4-landscape page, in sheet points (the sheet is scaled to fit the width)
LINE_POINTS = 17


def _num(value):
    return float(value)


def build_wages_sheet_workbook(sheet):
    wb = Workbook()
    ws = wb.active
    ws.title = f'{sheet["period_start"]:%m.%Y}'
    ws.sheet_view.rightToLeft = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.25
    ws.page_margins.top = ws.page_margins.bottom = 0.4
    for i, width in enumerate(WIDTHS, start=1):
        ws.column_dimensions[L(i)].width = width

    bold = Font(name='Calibri', size=12, bold=True)
    big = Font(name='Calibri', size=14, bold=True)
    white = Font(name='Calibri', size=11, bold=True, color='FFFFFF')

    month_label = f'{sheet["period_start"]:%m.%Y}'
    ws['B2'] = 'إلى : الادارة العامة.'
    ws['B3'] = 'الموضوع: استحقاق صرف الرواتب والأجور.'
    ws['B4'] = f'بالإشارة إلى الموضوع أعلاه ، نعلمكم باستحقاق صرف الرواتب والأجور التالية عن شهر {month_label}'
    for ref in ('B2', 'B3', 'B4'):
        ws[ref].font = big
    row = 6
    net_cells, due_cells = [], []

    def title_row(r, text):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(HEADERS))
        cell = ws.cell(r, 1, text)
        cell.font, cell.fill, cell.alignment = white, BLUE, CENTER

    def header_row(r):
        for c, text in enumerate(HEADERS, start=1):
            cell = ws.cell(r, c, text)
            cell.font, cell.fill, cell.alignment, cell.border = bold, LIGHT, CENTER, BORDER
        ws.row_dimensions[r].height = 34

    used = 90   # points taken on the first page by the memo header
    for section in sheet['sections']:
        name = section['project'].name if section['project'] else '—'
        # a project's table starts on a fresh page when it would otherwise be cut across pages (a title never sits alone at a page foot)
        lines = sum(len(g['rows']) for g in section['groups']) + (2 * len(section['groups']) if section['has_subs'] else 0) + 1
        needed = 18 + 34 + lines * LINE_POINTS + 16
        if used and used + needed > PAGE_POINTS and needed <= PAGE_POINTS:
            ws.row_breaks.append(Break(id=row - 1))
            used = 0
        used = (used + needed) % PAGE_POINTS if needed > PAGE_POINTS else used + needed
        title_row(row, f'كشف اجور عمال ({name})')
        header_row(row + 1)
        r = row + 2
        subtotal_rows = []
        first_all = r
        for group in section['groups']:
            if section['has_subs']:      # a project split into subs (متفرقات): a title, its lines and its own total per sub
                ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(HEADERS))
                cell = ws.cell(r, 1, group['name'] or 'بدون متفرقة')
                cell.font, cell.fill, cell.alignment = bold, PatternFill('solid', fgColor='D6E4F5'), Alignment(horizontal='right', vertical='center')
                r += 1
            first = r
            for line in group['rows']:
                values = {
                    1: line['n'], 2: line['worker'].full_name, 3: line['trade'] or '', 4: _num(line['days']),
                    8: _num(line['paid_rate']), 10: _num(line['overtime_hours']) if line['overtime_hours'] else None,
                    14: _num(line['advances']) if line['advances'] else None,
                    16: int(line['national_id']) if str(line['national_id']).isdigit() else line['national_id'],
                }
                formulas = {
                    5: f'=D{r}/6', 6: f'=E{r}+D{r}', 7: f'=H{r}*6/7', 9: f'=H{r}*D{r}', 11: f'=H{r}/8*1.5',
                    12: f'=K{r}*J{r}', 13: f'=L{r}+I{r}', 15: f'=M{r}-N{r}',
                }
                for c in range(1, len(HEADERS) + 1):
                    cell = ws.cell(r, c, values.get(c, formulas.get(c)))
                    cell.font, cell.alignment, cell.border = Font(name='Calibri', size=12, bold=True), CENTER, BORDER
                    if c in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15):
                        cell.number_format = MONEY if c not in (4, 10) else 'General'
                ws.cell(r, 15).fill = YELLOW
                r += 1
            last = r - 1
            if section['has_subs']:
                label = f"مجموع {group['name'] or 'بدون متفرقة'}"
                ws.cell(r, 2, label)
                ws.cell(r, 13, f'=SUM(M{first}:M{last})')
                ws.cell(r, 15, f'=SUM(O{first}:O{last})')
                for c in range(1, len(HEADERS) + 1):
                    cell = ws.cell(r, c)
                    cell.font, cell.fill, cell.alignment, cell.border = bold, PatternFill('solid', fgColor='F1F5FA'), CENTER, BORDER
                    if c in (13, 15):
                        cell.number_format = MONEY
                subtotal_rows.append(r)
                r += 1
        if section['has_subs']:
            ws.cell(r, 13, '=' + '+'.join(f'M{x}' for x in subtotal_rows))
            ws.cell(r, 15, '=' + '+'.join(f'O{x}' for x in subtotal_rows))
            ws.cell(r, 2, 'المجموع النهائي للمتفرقات')
        else:
            ws.cell(r, 13, f'=SUM(M{first_all}:M{r - 1})')
            ws.cell(r, 15, f'=SUM(O{first_all}:O{r - 1})')
            ws.cell(r, 2, 'المجموع')
        for c in range(1, len(HEADERS) + 1):
            cell = ws.cell(r, c)
            cell.font, cell.fill, cell.alignment, cell.border = bold, LIGHT, CENTER, BORDER
            if c in (13, 15):
                cell.number_format = MONEY
        due_cells.append(f'M{r}')
        net_cells.append(f'O{r}')
        row = r + 2

    if sheet['adjustments']:
        title_row(row, 'تسويات على مستوى العامل (بدلات / خصومات / سلف)')
        for c, text in enumerate(['#', 'الاســـم', '', 'بدلات', 'خصومات', 'سلف', 'الأثر على الصافي'], start=1):
            cell = ws.cell(row + 1, c, text)
            cell.font, cell.fill, cell.alignment, cell.border = bold, LIGHT, CENTER, BORDER
        r = row + 2
        first = r
        for n, adj in enumerate(sheet['adjustments'], start=1):
            ws.cell(r, 1, n)
            ws.cell(r, 2, adj['worker'].full_name)
            ws.cell(r, 4, _num(adj['allowances']))
            ws.cell(r, 5, _num(adj['deductions']))
            ws.cell(r, 6, _num(adj['advances']))
            ws.cell(r, 7, f'=D{r}-E{r}-F{r}')
            for c in range(1, 8):
                cell = ws.cell(r, c)
                cell.font, cell.alignment, cell.border = Font(name='Calibri', size=12, bold=True), CENTER, BORDER
                if c >= 4:
                    cell.number_format = MONEY
            r += 1
        ws.cell(r, 2, 'المجموع')
        ws.cell(r, 7, f'=SUM(G{first}:G{r - 1})')
        for c in range(1, 8):
            cell = ws.cell(r, c)
            cell.font, cell.fill, cell.alignment, cell.border = bold, LIGHT, CENTER, BORDER
        ws.cell(r, 7).number_format = MONEY
        net_cells.append(f'G{r}')
        row = r + 2

    ws.cell(row, 1, 'المجموع').font = Font(name='Calibri', size=16, bold=True)
    total = ws.cell(row, 15, '=' + '+'.join(net_cells) if net_cells else 0)
    total.font, total.fill, total.number_format, total.alignment, total.border = (
        Font(name='Calibri', size=16, bold=True), YELLOW, MONEY, CENTER, BORDER)
    prepared = getattr(settings, 'WAGES_PREPARED_BY', '') or '                '
    reviewed = getattr(settings, 'WAGES_REVIEWED_BY', '') or '                '
    footer = ws.cell(row + 2, 1, f'اعداد : ( {prepared} )/ تدقيق : ( {reviewed} )')
    footer.font = Font(name='Calibri', size=16, bold=True)
    return wb
