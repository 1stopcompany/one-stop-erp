"""
Barcode rendering for ItemMaster.barcode_value (see procurement.models
for how the value itself is constructed -- the item's own
Family/Group/Classification/Brand/attribute codes, each letter-prefixed,
e.g. "F03G04C01B01T000", so the barcode's own printed text is
self-describing on sight; confirmed with the client as preferable to a
plain numeric code with a check digit).

Uses python-barcode (Code128, PNG via Pillow) for on-screen/inline
display, and reportlab for a small printable label PDF -- both
dependencies are already used elsewhere in this project.
"""

from io import BytesIO

import barcode as barcode_lib
from barcode.writer import ImageWriter

from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from reports.utils import shape_text, _ARABIC_RE, MR_FONT_NAME, MR_FONT_BOLD_NAME, FONT_NAME as AR_FONT_NAME

LABEL_SIZE = (80 * mm, 40 * mm)


def render_barcode_png(value):
    """
    Returns PNG bytes for a Code128 barcode of `value`, with `value`
    itself printed underneath -- the encoded value (see
    ItemMaster.barcode_value) is already the readable, letter-prefixed
    classification breakdown, so there's no separate "human text" to
    show instead of it.

    Must pass the printed text via `.write()`'s own `text=` keyword, not
    inside the `options` dict: python-barcode's `render()` (see
    barcode.base.Barcode.render) always overwrites options["text"] with
    `self.get_fullcode()` whenever write_text is truthy and its own
    `text=` keyword wasn't given -- anything put in `options["text"]`
    directly is silently clobbered and never reaches the image.
    """
    code = barcode_lib.get("code128", value, writer=ImageWriter())
    buf = BytesIO()
    code.write(buf, options={
        "module_height": 12.0,
        "font_size": 8,
        "quiet_zone": 2.0,
    }, text=value)
    return buf.getvalue()


def generate_item_label_pdf(item):
    """A single 80x40mm printable label: barcode + item code + description."""
    buffer = BytesIO()
    width, height = LABEL_SIZE
    c = canvas.Canvas(buffer, pagesize=(width, height))

    png_bytes = render_barcode_png(item.barcode_value)
    from reportlab.lib.utils import ImageReader
    img = ImageReader(BytesIO(png_bytes))
    img_w, img_h = img.getSize()

    # Fit the barcode (which already has its own code number baked in
    # underneath the bars) into BOTH the available width and the available
    # height -- scaling to width alone (the previous approach) ignored the
    # image's own aspect ratio: for a barcode this wide relative to its
    # height, filling the full label width blew the image up so tall that
    # it overflowed the 40mm label and got clipped by the page edge,
    # taking the number printed under the bars down with it.
    top_margin = 3 * mm
    description_zone_height = 9 * mm  # reserved for the description line below the barcode
    max_w = width - 6 * mm
    max_h = height - top_margin - description_zone_height
    scale = min(max_w / img_w, max_h / img_h)
    draw_w = img_w * scale
    draw_h = img_h * scale
    barcode_y = height - top_margin - draw_h
    c.drawImage(img, (width - draw_w) / 2, barcode_y, width=draw_w, height=draw_h, mask="auto")

    desc = item.description or ""
    font = MR_FONT_NAME
    if _ARABIC_RE.search(desc):
        font = AR_FONT_NAME
        desc = shape_text(desc)
    c.setFont(font, 7)
    text_y = barcode_y - 5 * mm
    c.drawCentredString(width / 2, text_y, desc[:60])

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
