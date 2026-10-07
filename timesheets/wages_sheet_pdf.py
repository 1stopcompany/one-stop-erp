"""
PDF of the day-labor wages sheet ("كشف اجور عمال"): the company's columns on the same formal page as the employee payroll sheet --
Times New Roman, A4 landscape, right to left, the banner with the title in the middle and the logo on the left, one titled table per
project (with its sub-groups, متفرقات), banded lines, totals, worker-level adjustments, the grand total, signature boxes and a footer
with page numbers. `sheet` comes from daily_worker_payroll_service.wages_sheet().
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import CondPageBreak, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME as BOLD, MR_FONT_NAME as FONT, _ARABIC_RE, _t, rtl_paragraph

from .payroll_sheet_excel import BAND, COMPANY_AR, COMPANY_EN, NAVY, NET_FILL, TOTAL_FILL, month_label
from .pdf import WAGES_SHEET_COLUMNS

NAVY_C = colors.HexColor('#' + NAVY)
GRID_C = colors.HexColor('#BFBFBF')
SUB_C = colors.HexColor('#DCE6F2')

# the headers with the line breaks chosen by hand (narrow columns), in the sheet's order
HEADER_LINES = [
    ['#'], ['الاســـم'], ['طبيعة العمل'], ['ايام', 'العمل'], ['ايام', 'الجمع'], ['مجموع الايام', 'شامل جمع'], ['الاجر', 'اليومي'],
    ['الاجر', 'المدفوع'], ['المجموع'], ['عدد الساعات', 'الاضافية'], ['سعر', 'الساعة'], ['قيمة', 'الساعات'], ['الاجر', 'المستحق'],
    ['سلف'], ['الصافي', 'للدفع'], ['رقم الهوية'], ['التوقيع'],
]


def _money(value, blank_zero=False):
    value = Decimal(value).quantize(Decimal('0.01'))
    if blank_zero and value == 0:
        return ''
    return f'{value:,.2f}'


def _plain(value):
    text = f'{Decimal(value):.2f}'.rstrip('0').rstrip('.')
    return text or '0'


def generate_wages_sheet_pdf(sheet, generated_by=None):
    margin = 0.32 * inch
    page = landscape(A4)
    page_width = page[0] - 2 * margin
    buffer = BytesIO()
    period_start, period_end = sheet['period_start'], sheet['period_end']
    doc = SimpleDocTemplate(buffer, pagesize=page, topMargin=margin, bottomMargin=0.5 * inch, leftMargin=margin, rightMargin=margin,
                            title=f'كشف اجور عمال {period_start:%m-%Y}')
    base = getSampleStyleSheet()['Normal']
    cell = ParagraphStyle('WCell', parent=base, fontName=FONT, fontSize=8.2, leading=10, alignment=TA_CENTER)
    cell_r = ParagraphStyle('WCellR', parent=cell, alignment=TA_RIGHT)
    head = ParagraphStyle('WHead', parent=cell, fontName=BOLD, fontSize=7.8, leading=9.4, textColor=NAVY_C)
    company = ParagraphStyle('WCompany', parent=cell, fontName=BOLD, fontSize=16, leading=19, textColor=NAVY_C)
    company_en = ParagraphStyle('WCompanyEn', parent=cell, fontSize=9.5, leading=12, textColor=colors.HexColor('#595959'))
    title_style = ParagraphStyle('WTitle', parent=cell, fontName=BOLD, fontSize=13, leading=17)
    period_style = ParagraphStyle('WPeriod', parent=cell, fontSize=9, leading=12, textColor=colors.HexColor('#595959'))
    memo = ParagraphStyle('WMemo', parent=cell_r, fontSize=9.5, leading=13)
    bar = ParagraphStyle('WBar', parent=cell, fontName=BOLD, fontSize=10.5, leading=14, textColor=colors.white)
    bold_cell = ParagraphStyle('WBold', parent=cell, fontName=BOLD)
    label = ParagraphStyle('WLabel', parent=cell, fontName=BOLD, fontSize=9.5, leading=12, textColor=NAVY_C)

    weights = [w for _, w in WAGES_SHEET_COLUMNS]
    widths = [page_width * w / sum(weights) for w in weights]
    ncols = len(widths)

    def rtl(values):
        return list(reversed(values))

    def text(value, style, width):
        if not value:
            return ''
        value = str(value)
        return rtl_paragraph(value, style, width - 6) if _ARABIC_RE.search(value) else Paragraph(value, style)

    # ---- banner: the text exactly in the middle, the logo on the left edge
    logo_path = finders.find('images/one_stop_logo.png')
    side = page_width * 0.25
    banner_text = Table([[Paragraph(_t(COMPANY_AR), company)], [Paragraph(COMPANY_EN, company_en)],
                         [Paragraph(_t(f'كشف اجور عمال - شهر {month_label(period_start)}'), title_style)],
                         [Paragraph(_t(f'{period_start:%d/%m/%Y}  -  {period_end:%d/%m/%Y}'), period_style)]], colWidths=[page_width - 2 * side])
    banner_text.setStyle(TableStyle([('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    logo = ''
    if logo_path:
        from PIL import Image as PILImage
        with PILImage.open(logo_path) as logo_file:
            ratio = logo_file.width / logo_file.height
        logo = Image(logo_path, width=0.62 * inch * ratio, height=0.62 * inch)
    banner = Table([[logo, banner_text, '']], colWidths=[side, page_width - 2 * side, side])
    banner.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (0, 0), 'LEFT'), ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                                ('LINEBELOW', (0, 0), (-1, 0), 1.2, NAVY_C), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('LEFTPADDING', (0, 0), (0, 0), 0)]))
    story = [banner, Spacer(1, 6),
             Paragraph(_t('إلى : الادارة العامة.   الموضوع: استحقاق صرف الرواتب والأجور.'), memo),
             Paragraph(_t(f'بالإشارة إلى الموضوع أعلاه ، نعلمكم باستحقاق صرف الرواتب والأجور التالية عن شهر {period_start:%m.%Y}'), memo),
             Spacer(1, 8)]

    if not sheet['sections']:
        story.append(Paragraph(_t('لا يوجد حضور أو إدخالات لهذا الشهر.'), memo))

    idx = {key: ncols - 1 - i for i, key in enumerate(['n', 'name', 'trade', 'days', 'friday', 'tdays', 'dwage', 'rate', 'total', 'oth', 'hrate',
                                                       'otv', 'due', 'adv', 'net', 'nid', 'sign'])}

    for section in sheet['sections']:
        name = section['project'].name if section['project'] else '—'
        rows = [[Paragraph(_t(f'كشف اجور عمال ({name})'), bar)] + [''] * (ncols - 1),
                rtl([Paragraph('<br/>'.join(_t(line) for line in lines), head) for lines in HEADER_LINES])]
        sub_title_rows, sub_total_rows = [], []

        def total_line(label_text, due, net):
            line = [''] * ncols
            line[idx['name']] = Paragraph(_t(label_text), ParagraphStyle('WTL', parent=bold_cell, alignment=TA_RIGHT))
            line[idx['due']] = Paragraph(_money(due), bold_cell)
            line[idx['net']] = Paragraph(_money(net), bold_cell)
            return line

        banded = []
        for group in section['groups']:
            if section['has_subs']:
                sub_title_rows.append(len(rows))
                rows.append([Paragraph(_t(group['name'] or 'بدون متفرقة'), ParagraphStyle('WSub', parent=cell_r, fontName=BOLD, textColor=NAVY_C))] + [''] * (ncols - 1))
            for k, r in enumerate(group['rows']):
                if k % 2:
                    banded.append(len(rows))
                rows.append(rtl([
                    str(r['n']), text(r['worker'].full_name, cell_r, widths[1]), text(r['trade'], cell_r, widths[2]),
                    _plain(r['days']), _plain(r['friday_days']), _plain(r['total_days']), _money(r['daily_wage']), _money(r['paid_rate']),
                    _money(r['total']), _plain(r['overtime_hours']) if r['overtime_hours'] else '', _money(r['hour_rate']),
                    _money(r['overtime_value'], True), _money(r['due']), _money(r['advances'], True), _money(r['net']),
                    str(r['national_id']), '',
                ]))
            if section['has_subs']:
                sub_total_rows.append(len(rows))
                rows.append(total_line(f"مجموع {group['name'] or 'بدون متفرقة'}", group['total_due'], group['total_net']))
        rows.append(total_line('المجموع النهائي للمتفرقات' if section['has_subs'] else 'المجموع', section['total_due'], section['total_net']))
        last = len(rows) - 1
        net_col = idx['net']
        style = [
            ('FONTNAME', (0, 0), (-1, -1), FONT), ('FONTSIZE', (0, 0), (-1, -1), 8.2), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
            ('TOPPADDING', (0, 0), (-1, -1), 2.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6),
            ('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 0), (-1, 0), NAVY_C),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#' + TOTAL_FILL)),
            ('BACKGROUND', (net_col, 2), (net_col, last - 1), colors.HexColor('#' + NET_FILL)),
            ('BACKGROUND', (0, last), (-1, last), colors.HexColor('#' + TOTAL_FILL)),
            ('LINEABOVE', (0, last), (-1, last), 1.2, NAVY_C), ('LINEBELOW', (0, last), (-1, last), 1.6, NAVY_C),
        ]
        for r in banded:
            style.append(('BACKGROUND', (0, r), (net_col - 1, r), colors.HexColor('#' + BAND)))
            style.append(('BACKGROUND', (net_col + 1, r), (-1, r), colors.HexColor('#' + BAND)))
        for r in sub_title_rows:
            style += [('SPAN', (0, r), (-1, r)), ('BACKGROUND', (0, r), (-1, r), SUB_C)]
        for r in sub_total_rows:
            style += [('BACKGROUND', (0, r), (-1, r), SUB_C)]
        table = Table(rows, colWidths=rtl(widths), repeatRows=2)
        table.setStyle(TableStyle(style))
        # the table fills the page and carries on to the next one (title and headings repeat); only a start with no room for
        # a few lines is moved to the next page
        story += [CondPageBreak(1.2 * inch), table, Spacer(1, 10)]

    if sheet['adjustments']:
        adj_title = Table([[Paragraph(_t('تسويات على مستوى العامل (بدلات / خصومات / سلف)'), bar)]], colWidths=[page_width])
        adj_title.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), NAVY_C), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        adj_widths = [page_width * w for w in (0.35, 0.15, 0.15, 0.15, 0.2)]
        adj_rows = [rtl([Paragraph(_t(h), head) for h in ('الاســـم', 'بدلات', 'خصومات', 'سلف', 'الأثر على الصافي')])]
        for a in sheet['adjustments']:
            adj_rows.append(rtl([text(a['worker'].full_name, cell_r, adj_widths[0]), _money(a['allowances']), _money(a['deductions']),
                                 _money(a['advances']), _money(a['effect'])]))
        adj = Table(adj_rows, colWidths=rtl(adj_widths))
        adj.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.4, GRID_C), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#' + TOTAL_FILL)),
                                 ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('FONTNAME', (0, 1), (-1, -1), FONT),
                                 ('FONTSIZE', (0, 0), (-1, -1), 8.2), ('TOPPADDING', (0, 0), (-1, -1), 2.6), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6)]))
        story += [KeepTogether([adj_title, adj]), Spacer(1, 10)]

    grand = Table([[Paragraph(_money(sheet['grand_total']), ParagraphStyle('WGrand', parent=bold_cell, fontSize=12.5)),
                    Paragraph(_t('المجموع الكلي'), ParagraphStyle('WGrandL', parent=bold_cell, fontSize=12.5, textColor=NAVY_C))]],
                  colWidths=[page_width * 0.22, page_width * 0.14], hAlign='RIGHT')
    grand.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 1.2, NAVY_C), ('LINEAFTER', (0, 0), (0, 0), 0.6, NAVY_C),
                               ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#' + NET_FILL)), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                               ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    sign_w = page_width / 3
    names = [getattr(settings, 'WAGES_APPROVED_BY', ''), getattr(settings, 'WAGES_REVIEWED_BY', ''), getattr(settings, 'WAGES_PREPARED_BY', '')]
    sign = Table([[Paragraph(_t('اعتماد'), label), Paragraph(_t('تدقيق'), label), Paragraph(_t('إعداد'), label)],
                  [text(n, cell, sign_w) or ' ' for n in names]], colWidths=[sign_w] * 3, rowHeights=[16, 32])
    sign.setStyle(TableStyle([('LINEBELOW', (0, 1), (-1, 1), 0.7, colors.HexColor('#7F7F7F')), ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                              ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 14)]))
    closing = [grand, Spacer(1, 14), sign]
    if generated_by:
        closing.append(Paragraph(f'Generated {date.today():%d/%m/%Y} by {generated_by}',
                                 ParagraphStyle('WGen', parent=base, fontName=FONT, fontSize=7, textColor=colors.grey)))
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
    return buffer.getvalue()
