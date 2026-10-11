"""Printable catalogue of the tools register: one row per tool with its photo, QR + code, name, maker, condition and location."""
import io
from datetime import date

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME, MR_FONT_NAME, rtl_paragraph, _t

COLS = [26 * mm, 30 * mm, 52 * mm, 26 * mm, 24 * mm, 28 * mm]   # photo, QR+code, name, maker, condition, location
PHOTO_BOX = 22 * mm
QR_SIZE = 20 * mm
STATUS_COLORS = {'new': '#1b7f3b', 'working': '#1b7f3b', 'needs_maintenance': '#b26a00', 'in_maintenance': '#b26a00',
                 'broken': '#b3261e', 'scrapped': '#555555'}


class _Placeholder(Flowable):
    """Grey box with 'No photo' where a tool has no picture yet."""
    def __init__(self, size):
        super().__init__()
        self.width = self.height = size

    def draw(self):
        self.canv.setStrokeColor(colors.HexColor('#bbbbbb'))
        self.canv.setFillColor(colors.HexColor('#f4f4f4'))
        self.canv.rect(0, 0, self.width, self.height, fill=1)
        self.canv.setFillColor(colors.HexColor('#999999'))
        self.canv.setFont(MR_FONT_NAME, 7)
        self.canv.drawCentredString(self.width / 2, self.height / 2 - 2, 'No photo')


class _QR(Flowable):
    def __init__(self, url, size):
        super().__init__()
        self.url, self.width, self.height = url, size, size

    def draw(self):
        code = qr.QrCodeWidget(self.url, barLevel='M')
        x0, y0, x1, y1 = code.getBounds()
        drawing = Drawing(self.width, self.height, transform=[self.width / (x1 - x0), 0, 0, self.height / (y1 - y0), 0, 0])
        drawing.add(code)
        renderPDF.draw(drawing, self.canv, 0, 0)


def _photo(tool):
    if not tool.photo:
        return _Placeholder(PHOTO_BOX)
    try:
        with tool.photo.open('rb') as handle:
            data = handle.read()
        from PIL import Image as PILImage
        width, height = PILImage.open(io.BytesIO(data)).size
        scale = min(PHOTO_BOX / width, PHOTO_BOX / height)
        return Image(io.BytesIO(data), width=width * scale, height=height * scale)
    except Exception:   # a missing / unreadable file must not stop the whole catalogue
        return _Placeholder(PHOTO_BOX)


def build_catalog_pdf(tools, url_for_tool, title='Tools register', subtitle=''):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=title)
    head = ParagraphStyle('head', fontName=MR_FONT_BOLD_NAME, fontSize=15, leading=18)
    sub = ParagraphStyle('sub', fontName=MR_FONT_NAME, fontSize=9, leading=11, textColor=colors.HexColor('#555555'))
    th = ParagraphStyle('th', fontName=MR_FONT_BOLD_NAME, fontSize=8.5, leading=10, textColor=colors.white)
    cell = ParagraphStyle('cell', fontName=MR_FONT_NAME, fontSize=9, leading=11)
    cell_bold = ParagraphStyle('cellb', parent=cell, fontName=MR_FONT_BOLD_NAME)
    code_style = ParagraphStyle('code', fontName=MR_FONT_BOLD_NAME, fontSize=10, leading=12, alignment=1)
    small = ParagraphStyle('small', fontName=MR_FONT_NAME, fontSize=7.5, leading=9, textColor=colors.HexColor('#555555'))

    tools = list(tools)
    story = [Paragraph(_t(title), head), Paragraph(f'{subtitle}{" - " if subtitle else ""}{len(tools)} tools - printed {date.today():%d/%m/%Y}', sub), Spacer(1, 4 * mm)]
    rows = [[Paragraph(label, th) for label in ('Photo', 'Code', 'Tool', 'Maker', 'Condition', 'Location')]]
    for tool in tools:
        name = rtl_paragraph(tool.name, cell_bold, COLS[2] - 4 * mm)
        extra = ' - '.join(filter(None, [tool.category, tool.model_no, tool.serial_no]))
        name_cell = [name] + ([rtl_paragraph(extra, small, COLS[2] - 4 * mm)] if extra else [])
        status_color = STATUS_COLORS.get(tool.status, '#333333')
        status = Paragraph(f'<font color="{status_color}"><b>{tool.get_status_display()}</b></font>', cell)
        location = rtl_paragraph(tool.location_label, cell, COLS[5] - 4 * mm)
        rows.append([
            _photo(tool),
            [_QR(url_for_tool(tool), QR_SIZE), Spacer(1, 1 * mm), Paragraph(tool.code, code_style)],
            name_cell, Paragraph(tool.manufacturer or '-', cell), status, location,
        ])
    table = Table(rows, colWidths=COLS, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2f4f6f')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 1), (1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#bbbbbb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f9fb')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(MR_FONT_NAME, 8)
        canvas.setFillColor(colors.HexColor('#777777'))
        canvas.drawString(12 * mm, 8 * mm, 'One Stop Contracting - tools register')
        canvas.drawRightString(A4[0] - 12 * mm, 8 * mm, f'Page {document.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
