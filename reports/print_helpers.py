"""
Shared building blocks for the management print-outs (BOQ, cost report): Arabic-aware styles,
the company letterhead, a page footer with page numbers, and the sign-off block.
"""
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from .utils import FONT_BOLD_NAME, FONT_NAME, _owner_report_logo_path, _t, rtl_paragraph

BLUE = '#1f4788'
LIGHT = '#f4f6fb'
SECTION = '#dfe6f3'
PHASE = '#eef2f9'
GREY = '#6c757d'


def styles():
    base = dict(fontName=FONT_NAME, fontSize=8.5, leading=11)
    return {
        'title': ParagraphStyle('PTitle', fontName=FONT_BOLD_NAME, fontSize=17, textColor=colors.HexColor(BLUE), alignment=TA_CENTER, leading=22),
        'sub': ParagraphStyle('PSub', fontName=FONT_NAME, fontSize=10.5, textColor=colors.HexColor('#555555'), alignment=TA_CENTER, leading=14),
        'meta': ParagraphStyle('PMeta', alignment=TA_RIGHT, **{**base, 'fontSize': 9.5, 'leading': 13}),
        'cell': ParagraphStyle('PCell', alignment=TA_CENTER, **base),
        'cell_r': ParagraphStyle('PCellR', alignment=TA_RIGHT, **base),
        'cell_b': ParagraphStyle('PCellB', alignment=TA_RIGHT, **{**base, 'fontName': FONT_BOLD_NAME}),
        'cell_bc': ParagraphStyle('PCellBC', alignment=TA_CENTER, **{**base, 'fontName': FONT_BOLD_NAME}),
        'head': ParagraphStyle('PHead', alignment=TA_CENTER, textColor=colors.white, **{**base, 'fontName': FONT_BOLD_NAME}),
        'note': ParagraphStyle('PNote', alignment=TA_RIGHT, textColor=colors.HexColor(GREY), **{**base, 'fontSize': 8, 'leading': 11}),
        'kpi_label': ParagraphStyle('PKL', alignment=TA_CENTER, textColor=colors.HexColor(GREY), **{**base, 'fontSize': 8}),
        'kpi_value': ParagraphStyle('PKV', alignment=TA_CENTER, **{**base, 'fontName': FONT_BOLD_NAME, 'fontSize': 12, 'leading': 15}),
    }


def money(value, places=2):
    return f"{Decimal(value or 0):,.{places}f}"


def qty(value):
    """12.000 -> 12, 7.500 -> 7.5, None -> ''."""
    if value is None:
        return ''
    text = f"{Decimal(value):,.3f}".rstrip('0').rstrip('.')
    return text or '0'


def rtl(text, style, width):
    """Arabic text that may wrap, kept in the right visual order inside a table cell."""
    return rtl_paragraph(text or '', style, max(width - 8, 20))


def letterhead(elements, S, title_ar, title_en, project, width):
    logo = _owner_report_logo_path()
    if logo:
        img = Image(logo, width=2.6 * inch, height=0.6 * inch, kind='proportional')
        img.hAlign = 'CENTER'
        elements += [img, Spacer(1, 4)]
    elements.append(Paragraph(_t(title_ar), S['title']))
    elements.append(Paragraph(title_en, S['sub']))
    elements.append(Spacer(1, 6))

    info = Table([[
        Paragraph(_t(f'التاريخ: {date.today():%Y-%m-%d}'), S['meta']),
        Paragraph(_t(f'العقد: {project.contract_number or "—"}'), S['meta']),
        Paragraph(_t(f'صاحب العمل: {project.client_name or "—"}'), S['meta']),
        Paragraph(_t(f'المشروع: {project.name} ({project.project_symbol})'), S['meta']),
    ]], colWidths=[width * 0.16, width * 0.19, width * 0.30, width * 0.35])
    info.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#c5cde0')), ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(LIGHT)),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements += [info, Spacer(1, 8)]


def signature_block(elements, S, width, roles=(('المدير العام', 'General Manager'), ('مدير الهندسة', 'Engineering Manager'), ('مدير المشروع', 'Project Manager'))):
    cells = []
    for ar, en in roles:
        cells.append([Paragraph(_t(ar), S['cell_bc']), Paragraph(en, S['cell']), Spacer(1, 22), Paragraph('.' * 40, S['cell']),
                      Paragraph(_t('التوقيع / التاريخ'), S['note'])])
    box = Table([[Table([[c] for c in cell], colWidths=[width / len(roles) - 12]) for cell in cells]], colWidths=[width / len(roles)] * len(roles))
    box.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements += [Spacer(1, 14), box]


def footer(label):
    """A canvas callback: project label on the left, 'Page x' on the right, and a confidentiality line."""
    def draw(canvas, doc):
        canvas.saveState()
        width, _ = doc.pagesize
        canvas.setStrokeColor(colors.HexColor('#c5cde0'))
        canvas.line(doc.leftMargin, 0.55 * inch, width - doc.rightMargin, 0.55 * inch)
        canvas.setFont(FONT_NAME, 8)
        canvas.setFillColor(colors.HexColor(GREY))
        canvas.drawString(doc.leftMargin, 0.38 * inch, f'{label}  |  {date.today():%Y-%m-%d}')
        canvas.drawRightString(width - doc.rightMargin, 0.38 * inch, f'Page {doc.page}')
        canvas.drawCentredString(width / 2, 0.38 * inch, _t('وثيقة داخلية - سرّي'))
        canvas.restoreState()
    return draw
