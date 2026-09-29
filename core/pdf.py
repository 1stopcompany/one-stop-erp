"""A standalone PDF for a single SpecificationSection, so someone can download just "01010 - Summary of
Work" instead of the whole (900-page) volume. English-only content, so no Arabic shaping is needed here --
see reports/utils.py for that machinery."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def generate_specification_section_pdf(section) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                             leftMargin=0.8 * inch, rightMargin=0.8 * inch)
    styles = getSampleStyleSheet()
    company_style = ParagraphStyle('SpecCompany', parent=styles['Normal'], fontSize=9,
                                    textColor=colors.HexColor('#6c757d'), alignment=TA_LEFT)
    title_style = ParagraphStyle('SpecTitle', parent=styles['Heading1'], fontSize=15,
                                  textColor=colors.HexColor('#1f4788'), spaceAfter=4)
    meta_style = ParagraphStyle('SpecMeta', parent=styles['Normal'], fontSize=9.5,
                                 textColor=colors.HexColor('#6c757d'), spaceAfter=14)
    body_style = ParagraphStyle('SpecBody', parent=styles['Normal'], fontSize=10.5, leading=15,
                                 alignment=TA_LEFT, spaceAfter=10)

    elements = [
        Paragraph(escape('One Stop Construction and Services -- Standards and Specifications'), company_style),
        Spacer(1, 0.05 * inch),
        Paragraph(escape(f"{section.code} – {section.title}"), title_style),
        Paragraph(escape(f"{section.volume.label}" + (f" ({section.volume.title})" if section.volume.title else "")
                          + (f" · {section.volume.revision}" if section.volume.revision else "")), meta_style),
    ]
    for block in section.content.split("\n\n"):
        block = block.strip()
        if block:
            elements.append(Paragraph(escape(block).replace("\n", "<br/>"), body_style))
    if not section.content.strip():
        elements.append(Paragraph(escape("No text captured for this section."), body_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
