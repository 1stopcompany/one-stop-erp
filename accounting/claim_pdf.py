"""
The printed payment claim, laid out like the company's own form (the Excel sheet of 1.11 Payments): the logo, the title, the vendor / project block, the claim
details, the deductions and the final amount, how it was paid (cash / cheque), the 12 requirements ticks, and the signature row (project manager,
finance, executive director, general manager) with the name and date of whoever signed. Arabic form: every row is drawn from right to left, so the cells
are listed in the order they are SEEN (left to right) and the label sits at the right edge.
"""
from io import BytesIO

from reportlab.graphics.shapes import Drawing, Line, Rect
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME, MR_FONT_NAME, _owner_report_logo_path, _t, rtl_paragraph

from .models import REQUIREMENTS, PaymentClaim

LABEL_BG = colors.HexColor('#dbe8f5')
BAND_BG = colors.HexColor('#ededed')
HEAD_BG = colors.HexColor('#fde9c4')
TOTAL_BG = colors.HexColor('#fdf0c4')
LINE = colors.HexColor('#333333')

# the nine physical columns, left to right (the sheet's J, I, H, G, F, E, D, C, B)
COLUMN_UNITS = [22.4, 4.1, 12.1, 14.4, 4.4, 9.1, 13.4, 18.4, 4.0]
COLS = len(COLUMN_UNITS)


def _money(value):
    if value is None:
        return ''
    text = f'{value:,.2f}'
    return text[:-3] if text.endswith('.00') else text


def _checkbox(checked):
    """A small square, crossed when ticked (drawn, because the form's font has no ballot-box glyph)."""
    drawing = Drawing(11, 11)
    drawing.add(Rect(0.5, 0.5, 10, 10, strokeColor=LINE, fillColor=None, strokeWidth=0.8))
    if checked:
        drawing.add(Line(2.5, 2.5, 8.5, 8.5, strokeColor=LINE, strokeWidth=1.2))
        drawing.add(Line(2.5, 8.5, 8.5, 2.5, strokeColor=LINE, strokeWidth=1.2))
    return drawing


def _date(value):
    return value.strftime('%d/%m/%Y') if value else ''


def _name(user):
    return (user.get_full_name() or user.username) if user else ''


class _Grid:
    """Rows of segments (text, columns spanned, kind) given in the order they are seen; builds the table and its spans / colours."""

    def __init__(self, page_width):
        total = sum(COLUMN_UNITS)
        self.widths = [page_width * u / total for u in COLUMN_UNITS]
        self.rows, self.styles = [], []
        self.base = ParagraphStyle('cell', fontName=MR_FONT_NAME, fontSize=8.5, leading=11, alignment=TA_CENTER)
        self.bold = ParagraphStyle('cellb', parent=self.base, fontName=MR_FONT_BOLD_NAME)

    def cell(self, text, width, bold=False):
        if isinstance(text, tuple) and text[0] == 'BOX':
            return _checkbox(text[1])
        return rtl_paragraph(str(text or ''), self.bold if bold else self.base, max(width - 6, 10)) if text else ''

    def add(self, segments, height=None, row_span=None):
        """segments: list of (text, ncols, kind) with kind in value | label | head | band | total | plain."""
        r = len(self.rows)
        row, col = [''] * COLS, 0
        for text, n, kind in segments:
            width = sum(self.widths[col:col + n])
            row[col] = self.cell(text, width, bold=kind in ('label', 'head', 'band', 'total'))
            if n > 1:
                self.styles.append(('SPAN', (col, r), (col + n - 1, r)))
            bg = {'label': LABEL_BG, 'head': HEAD_BG, 'band': BAND_BG, 'total': TOTAL_BG}.get(kind)
            if bg is not None:
                self.styles.append(('BACKGROUND', (col, r), (col + n - 1, r), bg))
            col += n
        assert col == COLS, (col, segments)
        self.rows.append(row)
        return r

    def build(self):
        table = Table(self.rows, colWidths=self.widths, repeatRows=0)
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.6, LINE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ] + self.styles))
        return table


def generate_payment_claim_pdf(claim):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.45 * inch, rightMargin=0.45 * inch, topMargin=0.4 * inch, bottomMargin=0.4 * inch,
                            title=f'Payment claim {claim.number}')
    page_width = A4[0] - 0.9 * inch
    elements = []

    # ---- logo band
    logo_path = _owner_report_logo_path()
    company = Paragraph(_t('شركة ون ستوب للمقاولات'), ParagraphStyle('co', fontName=MR_FONT_BOLD_NAME, fontSize=15, alignment=TA_CENTER, leading=20))
    logo = Image(logo_path, width=1.9 * inch, height=1.15 * inch, kind='proportional') if logo_path else Paragraph('ONE STOP', ParagraphStyle('o', fontName=MR_FONT_BOLD_NAME, fontSize=14))
    head = Table([[logo, company]], colWidths=[page_width * 0.38, page_width * 0.62])
    head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOX', (0, 0), (-1, -1), 0.6, LINE),
                              ('LINEBELOW', (0, 0), (-1, -1), 0, colors.white)]))
    elements.append(head)

    g = _Grid(page_width)
    kind_text = 'مرحلية' if claim.claim_type == PaymentClaim.INTERIM else 'نهائية'
    g.add([(f'مطالبة مالية (المستفيد - {kind_text})', COLS, 'band')])
    g.add([(_date(claim.claim_date), 1, 'value'), ('التاريخ', 2, 'label'), (claim.beneficiary_name, 4, 'value'), ('اسم المورد/المستفيد', 2, 'label')])
    project = f'{claim.project.name}' if claim.project_id else 'الإدارة العامة'
    g.add([(claim.number, 1, 'value'), ('رقم المطالبة', 2, 'label'), (project, 4, 'value'), ('اسم المشروع', 2, 'label')])
    g.add([(claim.nature_of_work, 7, 'value'), ('طبيعة العمل', 2, 'label')])
    g.add([(_money(claim.current_contract_value), 1, 'value'), ('قيمة العقد الحالية', 2, 'label'), (_money(claim.original_contract_value), 4, 'value'), ('قيمة العقد الابتدائية', 2, 'label')])
    g.add([(_money(claim.previous_payments), 7, 'value'), ('الدفعات السابقة', 2, 'label')])
    g.add([(f'مطالبة {kind_text} - تفاصيل المطالبة', COLS, 'band')])
    g.add([('المبلغ/ شيكل', 1, 'head'), ('التفاصيل', 6, 'head'), ('البيان', 2, 'head')])
    lines = list(claim.lines.all()) or []
    for line in lines:
        g.add([(_money(line.amount), 1, 'value'), (line.details, 6, 'value'), (line.statement or 'تفاصيل المطالبة', 2, 'label')])
    for _blank in range(max(0, 2 - len(lines))):
        g.add([('', 1, 'value'), ('', 6, 'value'), ('', 2, 'label')])
    g.add([(claim.notes, 7, 'value'), ('ملاحظات', 2, 'label')])
    g.add([('', 7, 'value'), ('خصومات', 2, 'label')])
    g.add([(_money(claim.deduction_agreed) if claim.deduction_agreed else '', 7, 'value'), ('خصم متفق عليه', 2, 'label')])
    g.add([(_money(claim.deduction_source_retention) if claim.deduction_source_retention else '', 7, 'value'), ('حجز بدل خصم مصدر', 2, 'label')])
    g.add([(_money(claim.deduction_other) if claim.deduction_other else '', 7, 'value'), ('حجوزات / خصومات أخرى', 2, 'label')])
    g.add([(_money(claim.net_due), 7, 'value'), ('المبلغ النهائي المستحق للدفع', 2, 'label')])
    g.add([(_money(claim.total_amount), 1, 'total'), ('المجموع الكلي:', 2, 'total'), ('', 6, 'total')])
    g.add([('', COLS, 'band')])

    # ---- payment
    g.add([(_date(claim.cash_date), 1, 'value'), ('التاريخ:', 2, 'label'), (_money(claim.cash_amount), 3, 'value'), ('المبلغ', 1, 'label'), ('طريقة الدفع/ نقدي', 2, 'label')])
    g.add([(claim.cheque_no, 3, 'value'), ('رقم الشيك', 1, 'label'), (_money(claim.cheque_amount), 2, 'value'), ('المبلغ', 1, 'label'), ('طريقة الدفع / شيكات', 2, 'label')])
    g.add([(_date(claim.cheque_due_date), 3, 'value'), ('تاريخ الاستحقاق', 1, 'label'), (claim.payment_note, 3, 'value'), ('', 2, 'label')])
    g.add([('', COLS, 'band')])

    # ---- requirements
    g.add([('متطلبات تقديم المطالبة للصرف', COLS, 'head')])
    ticked = set(claim.requirements or [])
    columns = [REQUIREMENTS[0:4], REQUIREMENTS[4:8], REQUIREMENTS[8:12]]   # right, middle, left
    for row_index in range(4):
        right, middle, left = (columns[0][row_index], columns[1][row_index], columns[2][row_index])
        box = lambda key: ('BOX', key in ticked)
        g.add([(left[1], 1, 'value'), (box(left[0]), 1, 'value'), (middle[1], 2, 'value'), (box(middle[0]), 1, 'value'), (right[1], 3, 'value'), (box(right[0]), 1, 'value')])
    g.add([('', COLS, 'band')])

    # ---- signatures (project manager, finance, executive director, general manager)
    g.add([('المدير العام', 1, 'head'), ('المدير التنفيذي', 2, 'head'), ('المالية', 2, 'head'), ('مدير المشروع', 2, 'head'), ('الشخص المفوض', 2, 'label')])
    people = [(claim.general_by, claim.general_at), (claim.executive_by, claim.executive_at), (claim.finance_by, claim.finance_at), (claim.submitted_by, claim.submitted_at)]
    g.add([(_name(people[0][0]), 1, 'value'), (_name(people[1][0]), 2, 'value'), (_name(people[2][0]), 2, 'value'), (_name(people[3][0]), 2, 'value'), ('التوقيع', 2, 'label')])
    g.add([(_date(people[0][1]), 1, 'value'), (_date(people[1][1]), 2, 'value'), (_date(people[2][1]), 2, 'value'), (_date(people[3][1]), 2, 'value'), ('التاريخ', 2, 'label')])

    elements.append(g.build())
    if claim.status == PaymentClaim.PAID:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(_t(f'تم الدفع بتاريخ {_date(claim.paid_at)}'), ParagraphStyle('paid', fontName=MR_FONT_BOLD_NAME, fontSize=9, alignment=TA_CENTER)))
    doc.build(elements)
    return buffer.getvalue()
