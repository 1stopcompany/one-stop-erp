"""
The employees' hours spread over projects, laid out for the payroll files: an extra Excel sheet and an extra PDF page after the
company's salary sheet ("توزيع ساعات الموظفين على المشاريع"). For every employee who has hours on projects (typed in the Daily Time
Record or taken from the daily reports -- see services/project_hours.py): one line per project with days, hours, the cost of those
hours, overtime hours, the cost of the overtime (hourly rate x the structure's multiplier) and the total; a subtotal per employee
and, at the end, what each project is charged in all. The monthly salary itself is unchanged -- this is its distribution.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.staticfiles import finders
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import CondPageBreak, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME as BOLD, MR_FONT_NAME as FONT, _ARABIC_RE, _t, rtl_paragraph

from .payroll_sheet_excel import BAND, COMPANY_AR, COMPANY_EN, FONT as XL_FONT, GRID, HAIR, MONEY, NAVY, TOTAL_FILL, month_label
from .services.project_hours import month_breakdown

TITLE = 'توزيع ساعات الموظفين على المشاريع'
HEADERS = ['#', 'الاسم', 'المشروع', 'عدد الأيام', 'الساعات', 'جمع وعطل ونقص (س)', 'تكلفة الساعات', 'ساعات إضافية', 'تكلفة الإضافي', 'الإجمالي']
WIDTHS = [4.5, 24, 30, 8, 9, 13, 13, 10, 12, 13]
ZERO = Decimal('0')


def _num(value):
    value = Decimal(value).quantize(Decimal('0.01'))
    return f'{value:f}'.rstrip('0').rstrip('.') if value else '0'


def detail_text(totals):
    """One line under an employee: where the hours nobody recorded came from, and what happens with a shortfall."""
    parts = [f"الجمع (مدفوعة، تُحسب حضوراً): {totals['fridays']} × 8 = {_num(totals['friday_hours'])} س"]
    if totals['leave_hours']:
        parts.append(f"عطل وإجازات مدفوعة: {_num(totals['leave_hours'])} س")
    if totals['shortfall_hours']:
        parts.append(f"نقص الدوام: {_num(totals['shortfall_hours'])} س (لا يؤثر على الراتب، ويُرحَّل على الإجازة السنوية: كل 8 ساعات = يوم)")
    return '  |  '.join(parts)


def split_data(payslips, period_start, period_end):
    """({'employee', 'rows', 'totals'} for every employee with hours, {project: totals}) for the payslips' employees."""
    people, projects = [], {}
    for payslip in payslips:
        rows, totals = month_breakdown(payslip.employee, period_start, period_end)
        if not rows:
            continue
        people.append({'employee': payslip.employee, 'rows': rows, 'totals': totals})
        for row in rows:
            item = projects.setdefault(row['project'].pk, {
                'project': row['project'], 'regular_hours': ZERO, 'overtime_hours': ZERO, 'regular_cost': ZERO,
                'overtime_cost': ZERO, 'cost': ZERO,
            })
            for key in ('regular_hours', 'overtime_hours', 'regular_cost', 'overtime_cost', 'cost'):
                item[key] += row[key]
    return people, sorted(projects.values(), key=lambda i: i['project'].name)


# ------------------------------------------------------------------------------------------------ Excel
def add_split_sheet(wb, people, projects, period_start, period_end):
    """Append the sheet to the payroll workbook; nothing is added when nobody has hours on projects."""
    if not people:
        return
    ws = wb.create_sheet(f'{period_start:%m.%Y} مشاريع')
    ws.sheet_view.rightToLeft = True
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.center.text = 'صفحة &P من &N'
    ws.oddFooter.right.text = 'One Stop ERP'
    for i, width in enumerate(WIDTHS, start=1):
        ws.column_dimensions[L(i)].width = width
    last_col = len(WIDTHS)

    def font(size=11, bold=False, color='000000'):
        return Font(name=XL_FONT, size=size, bold=bold, color=color)

    centre = Alignment(horizontal='center', vertical='center', wrap_text=True)
    right = Alignment(horizontal='right', vertical='center', wrap_text=True)

    def merge(r, value, fnt, height):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        cell = ws.cell(r, 1, value)
        cell.font, cell.alignment = fnt, centre
        ws.row_dimensions[r].height = height

    merge(1, COMPANY_AR, font(17, True, NAVY), 28)
    merge(2, COMPANY_EN, font(11, False, '595959'), 17)
    merge(3, f'{TITLE} - شهر {month_label(period_start)}', font(15, True), 26)
    merge(4, f'{period_start:%d/%m/%Y}  -  {period_end:%d/%m/%Y}', font(10.5, False, '595959'), 17)
    for c in range(1, last_col + 1):
        ws.cell(4, c).border = Border(bottom=Side(style='medium', color=NAVY))
    ws.row_dimensions[5].height = 6

    def header(r, labels):
        for c, text in enumerate(labels, start=1):
            cell = ws.cell(r, c, text)
            cell.font, cell.alignment = font(10.5, True, 'FFFFFF'), centre
            cell.fill = PatternFill('solid', fgColor=NAVY)
        ws.row_dimensions[r].height = 30

    header(6, HEADERS)
    ws.freeze_panes = 'A7'
    r = 7
    sub_fill = PatternFill('solid', fgColor='DCE6F2')
    for number, person in enumerate(people, start=1):
        first = r
        for index, row in enumerate(person['rows']):
            values = {
                1: number if index == 0 else None, 2: person['employee'].full_name if index == 0 else None, 3: row['project'].name,
                4: row['days'], 5: float(row['regular_hours']), 6: float(row['extra_hours']), 7: float(row['regular_cost']),
                8: float(row['overtime_hours']), 9: float(row['overtime_cost']), 10: f'=G{r}+I{r}',
            }
            for c in range(1, last_col + 1):
                cell = ws.cell(r, c, values.get(c))
                cell.font, cell.border = font(11, c == 10), GRID
                cell.alignment = right if c in (2, 3) else centre
                if c in (7, 9, 10):
                    cell.number_format = MONEY
            r += 1
        last = r - 1
        ws.cell(r, 2, f"مجموع {person['employee'].full_name}")
        for c in (5, 6, 7, 8, 9, 10):
            ws.cell(r, c, f'=SUM({L(c)}{first}:{L(c)}{last})')
        for c in range(1, last_col + 1):
            cell = ws.cell(r, c)
            cell.font, cell.fill, cell.border = font(11, True, NAVY), sub_fill, GRID
            cell.alignment = right if c == 2 else centre
            if c in (7, 9, 10):
                cell.number_format = MONEY
        r += 1
        # what the hours nobody recorded are: Fridays, paid holidays, and the shortfall that is settled through the leave balance
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=last_col)
        note = ws.cell(r, 2, detail_text(person['totals']))
        note.font, note.alignment = Font(name=XL_FONT, size=9.5, italic=True, color='595959'), right
        ws.row_dimensions[r].height = 18
        r += 1


# ------------------------------------------------------------------------------------------------ PDF
NAVY_C = colors.HexColor('#' + NAVY)
GRID_C = colors.HexColor('#BFBFBF')


def _money(value):
    return f'{Decimal(value).quantize(Decimal("0.01")):,.2f}'


def _plain(value):
    value = Decimal(value).quantize(Decimal('0.01'))
    return f'{value:f}'.rstrip('0').rstrip('.') if value else '0'


def generate_split_pdf(people, projects, period_start, period_end):
    """The distribution as its own landscape PDF (merged after the salary sheet by the export view); b'' when there is nothing to show."""
    if not people:
        return b''
    margin = 0.32 * inch
    page = landscape(A4)
    page_width = page[0] - 2 * margin
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=page, topMargin=margin, bottomMargin=0.48 * inch, leftMargin=margin, rightMargin=margin,
                            title=TITLE)
    base = getSampleStyleSheet()['Normal']
    size = 8.6
    cell = ParagraphStyle('SPCell', parent=base, fontName=FONT, fontSize=size, leading=size + 2, alignment=TA_CENTER)
    cell_r = ParagraphStyle('SPCellR', parent=cell, alignment=TA_RIGHT)
    bold = ParagraphStyle('SPBold', parent=cell, fontName=BOLD)
    bold_r = ParagraphStyle('SPBoldR', parent=bold, alignment=TA_RIGHT)
    head = ParagraphStyle('SPHead', parent=cell, fontName=BOLD, textColor=colors.white)
    company = ParagraphStyle('SPCompany', parent=cell, fontName=BOLD, fontSize=16, leading=19, textColor=NAVY_C)
    company_en = ParagraphStyle('SPCompanyEn', parent=cell, fontSize=9.5, leading=12, textColor=colors.HexColor('#595959'))
    title_style = ParagraphStyle('SPTitle', parent=cell, fontName=BOLD, fontSize=13, leading=17)
    period_style = ParagraphStyle('SPPeriod', parent=cell, fontSize=9, leading=12, textColor=colors.HexColor('#595959'))
    bar = ParagraphStyle('SPBar', parent=cell, fontName=BOLD, fontSize=10.5, leading=14, textColor=colors.white)
    small_r = ParagraphStyle('SPSmallR', parent=cell_r, fontSize=7.8, leading=10, textColor=colors.HexColor('#444444'))

    widths = [page_width * w / sum(WIDTHS) for w in WIDTHS]

    def rtl(values):
        return list(reversed(values))

    def text(value, style, width):
        if value in (None, ''):
            return ''
        value = str(value)
        return rtl_paragraph(value, style, width - 6) if _ARABIC_RE.search(value) else Paragraph(value, style)

    # banner (text centred, logo on the left), like the salary sheet
    banner_rows = [[Paragraph(_t(COMPANY_AR), company)], [Paragraph(COMPANY_EN, company_en)],
                   [Paragraph(_t(f'{TITLE} - شهر {month_label(period_start)}'), title_style)],
                   [Paragraph(_t(f'{period_start:%d/%m/%Y}  -  {period_end:%d/%m/%Y}'), period_style)]]
    side = page_width * 0.25
    banner_text = Table(banner_rows, colWidths=[page_width - 2 * side])
    banner_text.setStyle(TableStyle([('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    logo = ''
    logo_path = finders.find('images/one_stop_logo.png')
    if logo_path:
        from PIL import Image as PILImage
        with PILImage.open(logo_path) as logo_file:
            ratio = logo_file.width / logo_file.height
        logo = Image(logo_path, width=0.6 * inch * ratio, height=0.6 * inch)
    banner = Table([[logo, banner_text, '']], colWidths=[side, page_width - 2 * side, side])
    banner.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'LEFT'), ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                                ('LINEBELOW', (0, 0), (-1, 0), 1.2, NAVY_C), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                                ('LEFTPADDING', (0, 0), (0, 0), 0)]))

    header_row = rtl([Paragraph(_t(h), head) for h in HEADERS])
    rows = [header_row]
    sub_rows, note_rows = [], []
    for number, person in enumerate(people, start=1):
        for index, row in enumerate(person['rows']):
            rows.append(rtl([
                str(number) if index == 0 else '', text(person['employee'].full_name, cell_r, widths[1]) if index == 0 else '',
                text(row['project'].name, cell_r, widths[2]), str(row['days']), _plain(row['regular_hours']), _plain(row['extra_hours']),
                _money(row['regular_cost']), _plain(row['overtime_hours']), _money(row['overtime_cost']), _money(row['cost']),
            ]))
        totals = person['totals']
        sub_rows.append(len(rows))
        rows.append(rtl([
            '', text(f"مجموع {person['employee'].full_name}", bold_r, widths[1] + widths[2]), '', '', Paragraph(_plain(totals['regular_hours']), bold),
            Paragraph(_plain(totals['extra_hours']), bold), Paragraph(_money(totals['regular_cost']), bold),
            Paragraph(_plain(totals['overtime_hours']), bold), Paragraph(_money(totals['overtime_cost']), bold), Paragraph(_money(totals['cost']), bold),
        ]))
        note_rows.append(len(rows))
        rows.append([text(detail_text(totals), small_r, page_width - 6)] + [''] * (len(WIDTHS) - 1))
    table = Table(rows, colWidths=rtl(widths), repeatRows=1)
    style = [
        ('FONTNAME', (0, 0), (-1, -1), FONT), ('FONTSIZE', (0, 0), (-1, -1), size), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
        ('TOPPADDING', (0, 0), (-1, -1), 2.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY_C),
    ]
    for r in sub_rows:
        style += [('BACKGROUND', (0, r), (-1, r), colors.HexColor('#DCE6F2')), ('FONTNAME', (0, r), (-1, r), BOLD)]
    for r in note_rows:
        style += [('SPAN', (0, r), (-1, r)), ('BACKGROUND', (0, r), (-1, r), colors.HexColor('#F7F9FC'))]
    table.setStyle(TableStyle(style))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor('#595959'))
        canvas.drawString(margin, 0.28 * inch, f'{date.today():%d/%m/%Y}')
        canvas.drawRightString(page[0] - margin, 0.28 * inch, 'One Stop ERP')
        canvas.setStrokeColor(GRID_C)
        canvas.line(margin, 0.42 * inch, page[0] - margin, 0.42 * inch)
        canvas.restoreState()

    doc.build([banner, Spacer(1, 6), table], onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def merge_pdfs(first, second):
    """`second` appended after `first` (both bytes); `first` alone when there is no second."""
    if not second:
        return first
    import pymupdf
    document = pymupdf.open(stream=first, filetype='pdf')
    document.insert_pdf(pymupdf.open(stream=second, filetype='pdf'))
    return document.tobytes()
