"""
The monthly payslip (قسيمة الراتب الشهرية), laid out like the company's own Excel form -- employee data, attendance and leave summary,
bank account, statement of the payments of the year, the current payment (allowances / deductions, gross, net, amount in words) and the
signature boxes -- and styled like the workers' payment vouchers: company letterhead, Times New Roman, black-bordered tables, grey headings.

One payslip per page; any number of them can be put in one PDF. The figures come from timesheets.payslip_form.effective(), which lays the
admin's manual entries (Payslip.print_overrides) over the computed ones.
"""
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME as BOLD, MR_FONT_NAME as FONT, _t

from .payslip_form import effective
from .voucher_pdf import BOTTOM, SIDE, TOP, _letterhead

GREY = colors.HexColor('#e8e8e8')
LIGHT = colors.HexColor('#f1f1f1')
NET = colors.HexColor('#fff9c4')
FRACTIONS = [21, 13, 11, 10, 11, 12, 10]   # logical columns right -> left (B..H of the Excel form)


def _plain(value):
    value = Decimal(value).quantize(Decimal('0.01'))
    return f'{value:f}'.rstrip('0').rstrip('.') if value else '0'


def _money(value):
    return f'{Decimal(value):,.2f}'


def _styles():
    base = getSampleStyleSheet()['Normal']
    return {
        'title': ParagraphStyle('PTitle', parent=base, fontName=BOLD, fontSize=12.5, leading=16, alignment=TA_CENTER),
        'period': ParagraphStyle('PPeriod', parent=base, fontName=BOLD, fontSize=10.5, leading=14, alignment=TA_CENTER),
        'sec': ParagraphStyle('PSec', parent=base, fontName=BOLD, fontSize=9.5, leading=12, alignment=TA_RIGHT),
        'lab': ParagraphStyle('PLab', parent=base, fontName=FONT, fontSize=9, leading=11.5, alignment=TA_RIGHT),
        'labb': ParagraphStyle('PLabB', parent=base, fontName=BOLD, fontSize=9, leading=11.5, alignment=TA_RIGHT),
        'val': ParagraphStyle('PVal', parent=base, fontName=FONT, fontSize=9, leading=11.5, alignment=TA_CENTER),
        'valb': ParagraphStyle('PValB', parent=base, fontName=BOLD, fontSize=9.5, leading=12, alignment=TA_CENTER),
        'hdr': ParagraphStyle('PHdr', parent=base, fontName=BOLD, fontSize=9, leading=11.5, alignment=TA_CENTER),
        'sign': ParagraphStyle('PSign', parent=base, fontName=BOLD, fontSize=9.5, leading=13, alignment=TA_CENTER),
    }


class _Grid:
    """
    A table whose columns are given right -> left (as an Arabic form reads) and drawn mirrored. `add(*cells)` takes
    (content, colspan) pairs in reading order; a plain string / Paragraph is a one-column cell.
    """

    def __init__(self, ncols, widths):
        self.n, self.widths, self.rows, self.spans, self.fills = ncols, widths, [], [], []

    def add(self, *cells, fill=None):
        row, col, r = [''] * self.n, 0, len(self.rows)
        for cell in cells:
            content, span = cell if isinstance(cell, tuple) else (cell, 1)
            # the table is mirrored when drawn, and a merged cell keeps its text in its LEFT-most cell: that is the last logical one
            row[col + span - 1] = content
            if span > 1:
                self.spans.append((col, r, col + span - 1, r))
            col += span
        self.rows.append(row)
        if fill is not None:
            self.fills.append((r, fill))

    def table(self, extra=()):
        last = self.n - 1
        mirrored = [list(reversed(r)) for r in self.rows]
        style = [
            ('GRID', (0, 0), (-1, -1), 0.7, colors.black), ('BOX', (0, 0), (-1, -1), 1.2, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2.2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
            ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]
        style += [('SPAN', (last - c1, r0), (last - c0, r1)) for c0, r0, c1, r1 in self.spans]
        style += [('BACKGROUND', (0, r), (-1, r), colour) for r, colour in self.fills]
        style += list(extra)
        table = Table(mirrored, colWidths=list(reversed(self.widths)))
        table.setStyle(TableStyle(style))
        return table


def _story_for(payslip, S, width):
    d = effective(payslip)
    P = lambda text, style='val': Paragraph(_t(text), S[style]) if text not in (None, '') else ''
    num = lambda value: Paragraph(_plain(value), S['val'])
    money = lambda value, style='val': Paragraph(_money(value), S[style])

    # ---- the top block: employee, attendance & leave, bank account
    widths = [width * f / sum(FRACTIONS) for f in FRACTIONS]
    top = _Grid(7, widths)
    top.add((P('قسيمة الراتب الشهرية', 'title'), 7), fill=None)
    period = f'عن شهر {d["month_label"]}' + ('' if d['is_posted'] else ' - مسودة')
    top.add((P(period, 'period'), 7))
    top.add((P('بيانات الموظف', 'sec'), 7), fill=GREY)
    top.add(P('رقم الموظف', 'labb'), (P(d['employee_id'], 'lab'), 3), P('الوصف الوظيفي', 'labb'), (P(d['job_title'], 'lab'), 2))
    top.add(P('اسم الموظف', 'labb'), (P(d['name'], 'lab'), 3), P('القسم / الدائرة', 'labb'), (P(d['department'], 'lab'), 2))
    top.add((P('ملخص الدوام والاجازات', 'sec'), 4), (P('الحساب البنكي', 'sec'), 3), fill=GREY)
    top.add(P('ايام العمل', 'labb'), num(d['working_days']), P('ايام الجمعة', 'labb'), num(d['friday_days']),
            P('اسم البنك', 'labb'), (P(d['bank_name'], 'lab'), 2))
    top.add(P('الاجازات المرصدة', 'labb'), num(d['leave_entitled']), P('العطل الرسمية', 'labb'), num(d['official_holidays']),
            P('رقم الحساب', 'labb'), (P(d['bank_account'], 'lab'), 2))
    top.add(P('الاجازات المستنفذة', 'labb'), num(d['leave_used']), P('الايام المدفوعة', 'labb'), num(d['paid_days']),
            P('الفرع', 'labb'), (P(d['bank_branch'], 'lab'), 2))
    top.add(P('الرصيد الاجازات المتبقي', 'labb'), num(d['leave_balance']), ('', 2), P('العملة', 'labb'), (P(d['currency'], 'lab'), 2))
    story = [top.table(extra=[('BACKGROUND', (0, 5), (-1, 5), GREY)]), Spacer(1, 6)]

    # ---- the payments statement (right side of the page) and the current payment (left side)
    right_w = [widths[0], widths[1], widths[2]]
    left_w = widths[3:]
    months = _Grid(3, right_w)
    months.add(P('كشف حساب للدفعات السابقة', 'hdr'), P('الراتب', 'hdr'), P('بونص', 'hdr'), fill=GREY)
    months.add('', money(d['previous_total']), money(d['previous_bonus']))
    months.add(P(f'كشف حساب للدفعات {d["year"]}', 'hdr'), P('الراتب', 'hdr'), P('بونص', 'hdr'), fill=GREY)
    for index, value in enumerate(d['month_rows'], start=1):
        months.add(P(f'راتب شهر {index}', 'lab'), money(value) if value else '', '')
    months.add(P('المجموع', 'labb'), money(d['month_total'] + d['previous_total']), money(d['previous_bonus']), fill=LIGHT)

    current = _Grid(4, left_w)
    current.add(P('الدفعة الحالية', 'hdr'), (P(f'عن شهر {d["month_label"]}', 'hdr'), 3), fill=GREY)
    current.add(P('الراتب الاجمالي', 'labb'), (money(d['gross']), 3))
    current.add(P('الراتب الاساسي', 'labb'), (money(d['base']), 3))
    current.add((P('العلاوات', 'hdr'), 2), (P('الاقتطاعات', 'hdr'), 2), fill=GREY)
    current.add(P('مواصلات', 'lab'), money(d['transport']) if d['transport'] else '', P('ضريبة الدخل - للعلم', 'lab'), money(d['income_tax']) if d['income_tax'] else '')
    current.add(P('بدل اضافي', 'lab'), money(d['overtime']) if d['overtime'] else '', P('سلف', 'lab'), money(d['advances']) if d['advances'] else '')
    current.add(P('بدلات اخرى', 'lab'), money(d['other_allowances']) if d['other_allowances'] else '', P('خصومات اخرى', 'lab'),
                money(d['other_deductions']) if d['other_deductions'] else '')
    current.add('', '', P('خصم اجازات غير مدفوعة', 'lab'), money(d['unpaid_leave']) if d['unpaid_leave'] else '')
    current.add(P('مجموع العلاوات', 'labb'), money(d['total_allowances']), P('مجموع الاقتطاعات', 'labb'), money(d['total_deductions']), fill=GREY)
    current.add('', '', P('امتيازات اضافية', 'lab'), money(d['extra_benefits']) if d['extra_benefits'] else '')
    current.add('', '', P('بونص', 'lab'), money(d['bonus']) if d['bonus'] else '')
    current.add('', '', '', '')
    current.add(P('الراتب الاجمالي', 'labb'), (money(d['gross']), 3))
    current.add(P('الراتب للدفع', 'labb'), (money(d['net'], 'valb'), 3), fill=NET)
    current.add(P('المبلغ بالكلمات', 'labb'), (P(d['words'], 'valb'), 3))
    current_table = current.table()

    # both halves are as tall as the taller one, so the page reads as one block
    months_table = months.table()
    side_by_side = Table([[current_table, months_table]], colWidths=[sum(left_w), sum(right_w)])
    side_by_side.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story += [side_by_side, Spacer(1, 12)]

    # ---- signatures (right to left on the page: personnel, accounting, receiver)
    box = lambda label: Table([[P(label, 'sign')], [Spacer(1, 26)]], colWidths=[width / 3 - 14])
    boxes = [box('قسم شؤون الموظفين'), box('قسم المحاسبة'), box('توقيع المستلم')]
    for b in boxes:
        b.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 1.0, colors.black), ('LINEBELOW', (0, 0), (-1, 0), 0.7, colors.black),
                               ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    sign = Table([list(reversed(boxes))], colWidths=[width / 3] * 3)
    sign.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(sign)
    if d['note']:
        story += [Spacer(1, 6), Paragraph(_t(f'ملاحظات: {d["note"]}'), S['lab'])]
    return story


def generate_payslip_form_pdf(payslips):
    """One payslip page per Payslip, in the order given, as a single PDF."""
    buffer = BytesIO()
    width = A4[0] - 2 * SIDE
    doc = BaseDocTemplate(buffer, pagesize=A4, title='Payslips')
    frame = Frame(SIDE, BOTTOM, width, A4[1] - TOP - BOTTOM, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='payslip', frames=[frame], onPage=_letterhead)])
    S = _styles()
    story = []
    for i, payslip in enumerate(payslips):
        if i:
            story.append(PageBreak())
        story += _story_for(payslip, S, width)
    if not story:
        story = [Paragraph('No payslips', S['lab'])]
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
