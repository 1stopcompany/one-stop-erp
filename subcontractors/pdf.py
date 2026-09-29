"""
Standalone PDF for one SubcontractorAgreement: header/scope/BOQ lines/payments specific to this
agreement, then -- per the company's own instruction -- the standard General Terms & Conditions
(SubcontractorGeneralTerms) printed at the very end, after everything specific to this agreement,
since they're the same boilerplate on every Musana'a agreement.

Single-language: the agreement's own `language` (chosen once, at creation) decides everything -- no
mixed Arabic/English on the page. For Arabic, this isn't just right-aligned text: table COLUMNS are
laid out right-to-left too (the first logical column prints on the right edge of the page, like a real
Arabic form), matching the same calm section-accent palette, Times New Roman and cell sizing as
generate_daily_report_pdf (reports/utils.py), whose Arabic-capable fonts/shaping (_t/rtl_paragraph)
this reuses rather than registering its own.

SubcontractorGeneralTerms itself stores both languages in one field (Arabic clauses, a blank line,
then their English translation) -- _language_only() picks out just the blocks in the agreement's own
language before printing, rather than showing both.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME, MR_FONT_NAME, _qty, _t, rtl_paragraph

from .models import SubcontractorGeneralTerms

# The exact same section-accent palette as generate_daily_report_pdf (reports/utils.py) -- reused by
# key, not re-picked, so a color tweak there and here never drift apart.
SECTION_COLORS = {
    'main': '#1f4788', 'general': '#1f4788', 'penalty': '#b91c1c', 'conduct': '#6d28d9', 'safety': '#15803d',
}

LABELS = {
    'ar': {
        'company': 'شركة ون ستوب للمقاولات', 'title': 'اتفاقية مصانعة',
        'agreement_no': 'رقم الاتفاقية', 'status': 'الحالة', 'project': 'المشروع', 'vendor': 'المقاول المصانع',
        'start_date': 'تاريخ البدء', 'end_date': 'تاريخ الانتهاء',
        'total_value': 'القيمة الإجمالية', 'paid_to_date': 'المدفوع لتاريخه',
        'scope': 'نطاق العمل', 'boq_lines': 'بنود جدول الكميات', 'payments': 'الدفعات',
        'boq_item': 'البند', 'description': 'الوصف', 'unit': 'الوحدة', 'qty': 'الكمية',
        'unit_price': 'سعر الوحدة', 'total': 'الإجمالي',
        'date': 'التاريخ', 'amount': 'المبلغ', 'notes': 'ملاحظات',
        'no_lines': 'لا يوجد بنود مسجّلة', 'no_payments': 'لا يوجد دفعات مسجّلة',
        'terms_title': 'الشروط والأحكام العامة',
        'terms_intro': 'تنطبق البنود التالية على هذه الاتفاقية وعلى كل اتفاقيات المصانعة لدى الشركة.',
        'general': 'الشروط العامة للعقد', 'penalty': 'الشروط الجزائية',
        'conduct': 'الالتزام الأخلاقي', 'safety': 'الالتزام بالسلامة العامة',
        'not_set': 'لم تُحدد بعد.',
    },
    'en': {
        'company': 'ONE STOP CONTRACTING & SERVICES', 'title': "SUBCONTRACTOR (MUSANA'A) AGREEMENT",
        'agreement_no': 'Agreement No.', 'status': 'Status', 'project': 'Project', 'vendor': 'Vendor',
        'start_date': 'Start Date', 'end_date': 'End Date',
        'total_value': 'Total Value', 'paid_to_date': 'Paid to Date',
        'scope': 'SCOPE OF WORK', 'boq_lines': 'BOQ LINES', 'payments': 'PAYMENTS',
        'boq_item': 'Item', 'description': 'Description', 'unit': 'Unit', 'qty': 'Qty',
        'unit_price': 'Unit Price', 'total': 'Total',
        'date': 'Date', 'amount': 'Amount', 'notes': 'Notes',
        'no_lines': 'No lines recorded', 'no_payments': 'No payments recorded',
        'terms_title': 'STANDARD TERMS & CONDITIONS',
        'terms_intro': "The following clauses apply to this agreement and to every Musana'a agreement the company enters into.",
        'general': 'General Contract Terms', 'penalty': 'Penalty Clauses',
        'conduct': 'Code of Conduct', 'safety': 'Safety Commitment',
        'not_set': 'Not set yet.',
    },
}


def _is_arabic_block(block: str) -> bool:
    """Majority-vote, not "any Arabic char present" -- an Arabic clause often has an English term in
    parentheses (e.g. "(Musana'a)"), which would otherwise misclassify the whole block as English."""
    arabic = sum(1 for ch in block if '؀' <= ch <= 'ۿ')
    latin = sum(1 for ch in block if ch.isalpha() and ch.isascii())
    return arabic >= latin


def _language_only(text, lang) -> str:
    """Pick out just the paragraph blocks in `lang` from a field that stores both languages (blank-line
    separated). Falls back to the whole text if nothing matches, rather than printing nothing."""
    normalized = str(text or '').replace('\r\n', '\n')
    blocks = [b.strip() for b in normalized.split('\n\n') if b.strip()]
    if not blocks:
        return ''
    wanted = [b for b in blocks if _is_arabic_block(b) == (lang == 'ar')]
    return '\n\n'.join(wanted) if wanted else normalized


def generate_subcontractor_agreement_pdf(agreement) -> bytes:
    lang = agreement.language if agreement.language in LABELS else 'ar'
    rtl = lang == 'ar'
    L = LABELS[lang]
    body_align = TA_RIGHT if rtl else TA_LEFT

    buffer = BytesIO()
    page_size = A4
    margin = 0.35 * inch
    page_width = page_size[0] - 2 * margin
    doc = SimpleDocTemplate(buffer, pagesize=page_size, topMargin=margin, bottomMargin=margin, leftMargin=margin, rightMargin=margin)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('SCATitle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#1f4788'),
                                  alignment=TA_CENTER, fontName=MR_FONT_BOLD_NAME, spaceAfter=4)
    company_style = ParagraphStyle('SCACompany', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#1f4788'),
                                    alignment=TA_CENTER, fontName=MR_FONT_BOLD_NAME)
    normal_style = ParagraphStyle('SCANormal', parent=styles['Normal'], fontSize=9.5, alignment=body_align, fontName=MR_FONT_NAME, leading=14)
    cell_style = ParagraphStyle('SCACell', parent=styles['Normal'], fontSize=7.3, alignment=TA_CENTER, fontName=MR_FONT_NAME, leading=9.5)
    cell_body_style = ParagraphStyle('SCACellBody', parent=cell_style, alignment=body_align)
    header_cell_style = ParagraphStyle('SCAHeaderCell', parent=styles['Normal'], fontSize=7.3, alignment=TA_CENTER,
                                        fontName=MR_FONT_BOLD_NAME, textColor=colors.whitesmoke, leading=9)
    label_cell_style = ParagraphStyle('SCALabelCell', parent=normal_style, fontName=MR_FONT_BOLD_NAME, fontSize=9, leading=12)
    value_cell_style = ParagraphStyle('SCAValueCell', parent=normal_style, fontSize=9, leading=12)

    def maybe_rtl(cells, widths):
        """Reverse a row (and its column widths) so the first logical column lands on the page's right
        edge -- real right-to-left table layout, not just right-aligned text in a left-to-right grid."""
        return (list(reversed(cells)), list(reversed(widths))) if rtl else (cells, widths)

    def header_row(labels, col_widths):
        return [rtl_paragraph(text, header_cell_style, w - 6) for text, w in zip(labels, col_widths)]

    def section_heading(text, key='main'):
        style = ParagraphStyle(f'SCAHeading{key}', parent=styles['Heading2'], fontSize=10.5, textColor=colors.white,
                                backColor=colors.HexColor(SECTION_COLORS[key]), fontName=MR_FONT_BOLD_NAME, spaceBefore=10,
                                spaceAfter=6, alignment=TA_RIGHT if rtl else TA_LEFT, borderPadding=(4, 6, 4, 6))
        return Paragraph(_t(text), style)

    def hdr_table(rows, col_widths, font_size=7.3, extra_cmds=None, zebra=True, pad=3):
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), MR_FONT_BOLD_NAME),
            ('FONTNAME', (0, 1), (-1, -1), MR_FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), font_size),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
            ('TOPPADDING', (0, 0), (-1, -1), pad),
        ]
        if zebra:
            cmds.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6fb')]))
        if extra_cmds:
            cmds += extra_cmds
        t.setStyle(TableStyle(cmds))
        return t

    def label_value_table(rows, col_widths):
        wrapped = []
        for row in rows:
            cells, widths = maybe_rtl(row, col_widths)
            wrapped_row = []
            for i, text in enumerate(cells):
                is_label = (len(row) - 1 - i if rtl else i) % 2 == 0
                style = label_cell_style if is_label else value_cell_style
                wrapped_row.append(rtl_paragraph(text, style, widths[i] - 10) if text else Paragraph('', style))
            wrapped.append(wrapped_row)
        t = Table(wrapped, colWidths=widths)
        cmds = [
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT' if rtl else 'LEFT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]
        label_cols = range(1, len(rows[0]), 2) if rtl else range(0, len(rows[0]), 2)
        for c in label_cols:
            cmds.append(('BACKGROUND', (c, 0), (c, -1), colors.HexColor('#e8f0f8')))
        t.setStyle(TableStyle(cmds))
        return t

    elements = [
        Paragraph(_t(L['company']), company_style),
        Paragraph(_t(L['title']), title_style),
        Spacer(1, 0.1 * inch),
    ]

    info_rows = [
        [L['agreement_no'], agreement.agreement_number, L['status'], agreement.get_status_display()],
        [L['project'], agreement.project.name, L['vendor'], agreement.vendor.name],
        [L['start_date'], str(agreement.start_date), L['end_date'], str(agreement.end_date or '—')],
        [L['total_value'], _qty(agreement.total_value), L['paid_to_date'], _qty(agreement.paid_to_date)],
    ]
    elements.append(label_value_table(info_rows, [page_width * w for w in (0.16, 0.34, 0.16, 0.34)]))
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(section_heading(L['scope']))
    elements.append(rtl_paragraph(_language_only(agreement.scope_description, lang) or agreement.scope_description, normal_style, page_width))
    elements.append(Spacer(1, 0.12 * inch))

    lines = list(agreement.lines.select_related('sub_item'))
    elements.append(section_heading(L['boq_lines']))
    if lines:
        col_widths = [page_width * w for w in (0.10, 0.38, 0.08, 0.13, 0.15, 0.16)]
        header_labels = [L['boq_item'], L['description'], L['unit'], L['qty'], L['unit_price'], L['total']]
        header_cells, header_widths = maybe_rtl(header_labels, col_widths)
        rows = [header_row(header_cells, header_widths)]
        for line in lines:
            data_cells, _w = maybe_rtl(
                [_t(line.sub_item.code), rtl_paragraph(line.description, cell_body_style, header_widths[1] - 8),
                 _t(line.unit), _qty(line.quantity), _qty(line.unit_price), _qty(line.total_price)],
                col_widths,
            )
            rows.append(data_cells)
        elements.append(hdr_table(rows, header_widths))
    else:
        elements.append(Paragraph(_t(L['no_lines']), normal_style))
    elements.append(Spacer(1, 0.12 * inch))

    payments = list(agreement.payments.all())
    elements.append(section_heading(L['payments']))
    if payments:
        col_widths = [page_width * w for w in (0.16, 0.16, 0.68)]
        header_cells, header_widths = maybe_rtl([L['date'], L['amount'], L['notes']], col_widths)
        rows = [header_row(header_cells, header_widths)]
        for p in payments:
            data_cells, _w = maybe_rtl(
                [str(p.payment_date), _qty(p.amount), rtl_paragraph(p.notes, cell_body_style, header_widths[2] - 8)],
                col_widths,
            )
            rows.append(data_cells)
        elements.append(hdr_table(rows, header_widths))
    else:
        elements.append(Paragraph(_t(L['no_payments']), normal_style))

    # ---------------- Standard Terms & Conditions -- printed LAST, after everything specific to this
    # agreement, in the agreement's own single language only. ----------------
    terms = SubcontractorGeneralTerms.load()
    elements.append(PageBreak())
    elements.append(section_heading(L['terms_title'], 'main'))
    elements.append(rtl_paragraph(L['terms_intro'], normal_style, page_width))
    elements.append(Spacer(1, 0.1 * inch))

    for key in ('general', 'penalty', 'conduct', 'safety'):
        field = {'general': terms.general_terms, 'penalty': terms.penalty_clauses,
                 'conduct': terms.code_of_conduct, 'safety': terms.safety_commitment}[key]
        elements.append(section_heading(L[key], key))
        elements.append(rtl_paragraph(_language_only(field, lang) or L['not_set'], normal_style, page_width))
        elements.append(Spacer(1, 0.1 * inch))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
