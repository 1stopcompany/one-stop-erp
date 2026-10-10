"""Printable QR labels for tools: an A4 sheet, 3 columns x 8 rows (70 x 36 mm), each label = QR + code + name + company."""
import io

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from reports.utils import MR_FONT_BOLD_NAME, MR_FONT_NAME, _t

COLS, ROWS = 3, 8
LABEL_W, LABEL_H = 70 * mm, 36 * mm
COMPANY = 'One Stop Contracting'


def _fit(c, text, font, size, max_width):
    while size > 5 and c.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def build_labels_pdf(tools, url_for_tool):
    """tools: iterable of Tool; url_for_tool(tool) -> absolute URL encoded in the QR (opens the tool's page when scanned)."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_w, page_h = A4
    margin_x = (page_w - COLS * LABEL_W) / 2
    margin_y = (page_h - ROWS * LABEL_H) / 2
    per_page = COLS * ROWS
    for index, tool in enumerate(tools):
        slot = index % per_page
        if index and slot == 0:
            c.showPage()
        col, row = slot % COLS, slot // COLS
        x = margin_x + col * LABEL_W
        y = page_h - margin_y - (row + 1) * LABEL_H
        c.setLineWidth(0.4)
        c.setDash(1, 2)
        c.rect(x, y, LABEL_W, LABEL_H)
        c.setDash()

        code = qr.QrCodeWidget(url_for_tool(tool), barLevel='M')
        x0, y0, x1, y1 = code.getBounds()
        size = 28 * mm
        drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
        drawing.add(code)
        renderPDF.draw(drawing, c, x + 3 * mm, y + (LABEL_H - size) / 2)

        text_x = x + 3 * mm + size + 3 * mm
        text_w = LABEL_W - (text_x - x) - 2 * mm
        c.setFont(MR_FONT_BOLD_NAME, _fit(c, tool.code, MR_FONT_BOLD_NAME, 15, text_w))
        c.drawString(text_x, y + LABEL_H - 11 * mm, tool.code)
        name = _t(tool.name)
        c.setFont(MR_FONT_NAME, _fit(c, name, MR_FONT_NAME, 10, text_w))
        c.drawRightString(text_x + text_w, y + LABEL_H - 17 * mm, name)
        maker = ' '.join(filter(None, [tool.manufacturer, tool.serial_no]))
        if maker:
            c.setFont(MR_FONT_NAME, _fit(c, maker, MR_FONT_NAME, 8, text_w))
            c.drawString(text_x, y + LABEL_H - 22 * mm, maker)
        c.setFont(MR_FONT_NAME, 7)
        c.drawString(text_x, y + 4 * mm, COMPANY)
    c.save()
    return buffer.getvalue()
