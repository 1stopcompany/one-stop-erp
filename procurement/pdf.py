"""
PDF generation for Purchase Requisitions and Purchase Orders -- the
"طلب شراء" (PR) and "أمر شراء" (PO/PER-02) documents referenced in the
company's ISO 9001:2015 procurement procedure (QMS-PRO-06 / QP-30).

Reuses the Arabic-capable font + reshaping helpers already set up in
reports.utils (item descriptions and user names are frequently Arabic in
real use, same situation as reports.utils.generate_report_pdf's
smart_para()) rather than duplicating font registration in this app.
"""

from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from reports.utils import (
    FONT_NAME as AR_FONT_NAME, FONT_BOLD_NAME as AR_FONT_BOLD_NAME,
    MR_FONT_NAME, MR_FONT_BOLD_NAME, shape_text, _ARABIC_RE, _owner_report_logo_path,
)
from .barcode_utils import render_barcode_png

FONT_NAME = MR_FONT_NAME
FONT_BOLD_NAME = MR_FONT_BOLD_NAME


def _styles():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('PRTitle', parent=styles['Heading1'], fontSize=16,
                                  textColor=colors.HexColor('#1f4788'), alignment=TA_CENTER,
                                  fontName=FONT_BOLD_NAME, spaceAfter=6)
    sub_style = ParagraphStyle('PRSub', parent=styles['Normal'], fontSize=10.5,
                                textColor=colors.HexColor('#555555'), alignment=TA_CENTER,
                                fontName=FONT_NAME, spaceAfter=2)
    heading_style = ParagraphStyle('PRHeading', parent=styles['Heading2'], fontSize=12,
                                    textColor=colors.white, backColor=colors.HexColor('#1f4788'),
                                    fontName=FONT_BOLD_NAME, spaceBefore=12, spaceAfter=6,
                                    alignment=TA_LEFT, borderPadding=(4, 6, 4, 6))
    cell_style = ParagraphStyle('PRCell', parent=styles['Normal'], fontSize=9,
                                 alignment=TA_LEFT, fontName=FONT_NAME, leading=12)
    return styles, title_style, sub_style, heading_style, cell_style


def _smart(value, style, default='—'):
    if not value:
        return default
    text = str(value)
    if _ARABIC_RE.search(text):
        ar_font = AR_FONT_BOLD_NAME if style.fontName == FONT_BOLD_NAME else AR_FONT_NAME
        ar_style = ParagraphStyle(f'{style.name}Ar{id(style)}', parent=style, fontName=ar_font)
        return Paragraph(shape_text(text), ar_style)
    return Paragraph(text, style)


def _hdr_table(rows, col_widths, font_size=9):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD_NAME),
        ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), font_size),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6fb')]),
    ]))
    return t


def _name_or_dash(user):
    if not user:
        return '—'
    return user.get_full_name() or user.username


def _barcode_image(item, width=1.15 * inch, height=0.5 * inch):
    """A real, print-scannable barcode for one item, sized to be usable off a printed page
    (not just a small on-screen thumbnail) -- see procurement.barcode_utils / ItemMaster.barcode_value."""
    if not item.barcode_value:
        return ''
    png = render_barcode_png(item.barcode_value)
    return Image(BytesIO(png), width=width, height=height, kind='proportional')


def _kv_table(pairs, page_width):
    rows = [[Paragraph(f'<b>{k}</b>', ParagraphStyle('kv', fontName=FONT_NAME, fontSize=9.5)), v] for k, v in pairs]
    t = Table(rows, colWidths=[page_width * 0.28, page_width * 0.72])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def generate_pr_pdf(pr):
    """Generate the "Purchase Requisition" PDF for an approved PurchaseRequisitionLine set."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.75 * inch, bottomMargin=0.5625 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    page_width = A4[0] - 1.5 * inch
    styles, title_style, sub_style, heading_style, cell_style = _styles()
    elements = []

    logo_path = _owner_report_logo_path()
    if logo_path:
        logo = Image(logo_path, width=3.2 * inch, height=0.75 * inch, kind='proportional')
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph('Purchase Requisition', title_style))
    elements.append(Paragraph(pr.pr_number, sub_style))
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(_kv_table([
        ('Project', _smart(pr.project.name, cell_style)),
        ('Status', pr.get_status_display()),
        ('Requested By', _smart(_name_or_dash(pr.requested_by), cell_style)),
        ('Required Date', pr.required_date.strftime('%d/%m/%Y') if pr.required_date else '—'),
        ('Approved By', _smart(_name_or_dash(pr.approved_by), cell_style)),
        ('Approved Date', pr.approved_date.strftime('%d/%m/%Y') if pr.approved_date else '—'),
        ('Remarks', _smart(pr.remarks, cell_style)),
    ], page_width))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph('Requested Items', heading_style))
    rows = [['#', 'Barcode', 'Item Code', 'Description', 'Qty', 'Unit', 'Remarks']]
    for i, line in enumerate(pr.lines.select_related('item').all(), start=1):
        rows.append([
            str(i), _barcode_image(line.item), Paragraph(line.item.full_code, cell_style),
            _smart(line.item.description, cell_style),
            f'{line.quantity_requested:g}', line.get_unit_display(), _smart(line.remarks, cell_style, default=''),
        ])
    elements.append(_hdr_table(
        rows, [page_width * 0.04, page_width * 0.19, page_width * 0.15, page_width * 0.27,
               page_width * 0.08, page_width * 0.08, page_width * 0.19],
        font_size=8.5,
    ))
    elements.append(Spacer(1, 0.3 * inch))

    signoff_rows = [
        ['Role', 'Name', 'Date'],
        ['Requested by', _smart(_name_or_dash(pr.requested_by), cell_style), pr.submitted_date.strftime('%d/%m/%Y') if pr.submitted_date else '—'],
        ['Approved by', _smart(_name_or_dash(pr.approved_by), cell_style), pr.approved_date.strftime('%d/%m/%Y') if pr.approved_date else '—'],
    ]
    elements.append(_hdr_table(signoff_rows, [page_width * 0.3, page_width * 0.4, page_width * 0.3], font_size=10))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        f'Generated automatically on {datetime.now().strftime("%d/%m/%Y")}',
        ParagraphStyle('footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER,
                       fontName=FONT_NAME, textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_po_pdf(po):
    """Generate the "Purchase Order" PDF (PER-02) for a PurchaseOrder."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.75 * inch, bottomMargin=0.5625 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    page_width = A4[0] - 1.5 * inch
    styles, title_style, sub_style, heading_style, cell_style = _styles()
    elements = []

    logo_path = _owner_report_logo_path()
    if logo_path:
        logo = Image(logo_path, width=3.2 * inch, height=0.75 * inch, kind='proportional')
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph('Purchase Order', title_style))
    elements.append(Paragraph(po.po_number, sub_style))
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(_kv_table([
        ('Project', _smart(po.project.name, cell_style)),
        ('Vendor', _smart(po.vendor.name, cell_style)),
        ('Related PR', po.pr.pr_number if po.pr else '—'),
        ('Status', po.get_status_display()),
        ('PO Date', po.po_date.strftime('%d/%m/%Y') if po.po_date else '—'),
        ('Delivery Date', po.delivery_date.strftime('%d/%m/%Y') if po.delivery_date else '—'),
        ('Remarks', _smart(po.remarks, cell_style)),
    ], page_width))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph('Order Items', heading_style))
    rows = [['#', 'Barcode', 'Item Code', 'Description', 'Qty', 'Unit', 'Unit Price', 'Total']]
    for i, line in enumerate(po.lines.select_related('item').all(), start=1):
        rows.append([
            str(i), _barcode_image(line.item, width=1.0 * inch, height=0.42 * inch),
            Paragraph(line.item.full_code, cell_style),
            _smart(line.item.description, cell_style),
            f'{line.quantity_ordered:g}', line.get_unit_display(),
            f'₪{line.unit_price:,.2f}', f'₪{line.total_price:,.2f}',
        ])
    elements.append(_hdr_table(
        rows, [page_width * 0.04, page_width * 0.16, page_width * 0.13, page_width * 0.21,
               page_width * 0.08, page_width * 0.07, page_width * 0.15, page_width * 0.15],
        font_size=8,
    ))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(
        f'Grand Total: ₪{po.total_price:,.2f}',
        ParagraphStyle('grandtotal', parent=styles['Normal'], fontSize=11, alignment=TA_LEFT,
                       fontName=FONT_BOLD_NAME, textColor=colors.HexColor('#1f4788')),
    ))
    elements.append(Spacer(1, 0.3 * inch))

    signoff_rows = [
        ['Role', 'Name', 'Date'],
        ['Prepared by', _smart(_name_or_dash(po.created_by), cell_style), po.po_date.strftime('%d/%m/%Y') if po.po_date else '—'],
        ['Approved by', '—', '—'],
    ]
    elements.append(_hdr_table(signoff_rows, [page_width * 0.3, page_width * 0.4, page_width * 0.3], font_size=10))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        f'Generated automatically on {datetime.now().strftime("%d/%m/%Y")}',
        ParagraphStyle('footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER,
                       fontName=FONT_NAME, textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
