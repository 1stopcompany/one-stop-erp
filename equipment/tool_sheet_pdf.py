"""
Printable record sheet of ONE tool: its details and current photo, then its whole movement history drawn as a PATH -- one step per
handover from the first receipt to today, each with the photo taken at that handover -- and its maintenance history.
"""
import io

from django.utils import timezone
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.utils import MR_FONT_BOLD_NAME, MR_FONT_NAME, _t, rtl_paragraph

PAGE_W = A4[0] - 24 * mm
STEP_PHOTO = 44 * mm
HEADER_PHOTO = 66 * mm   # the tool's current photo at the top of the sheet
KIND_COLORS = {'opening': '#1b7f3b', 'issue': '#1f5fa8', 'return': '#c9740a', 'transfer': '#7b3fa0'}
STATUS_COLORS = {'new': '#1b7f3b', 'working': '#1b7f3b', 'needs_maintenance': '#b26a00', 'in_maintenance': '#b26a00',
                 'broken': '#b3261e', 'scrapped': '#555555'}


def _image(photo):
    """ImageReader for a stored photo, or None when there is none / it cannot be read."""
    if not photo:
        return None
    try:
        with photo.open('rb') as handle:
            return ImageReader(io.BytesIO(handle.read()))
    except Exception:
        return None


def _draw_photo(canvas, reader, x, y, size):
    """Photo fitted inside a size x size box whose bottom-left corner is (x, y); grey 'No photo' box when there is none."""
    canvas.setStrokeColor(colors.HexColor('#bbbbbb'))
    if reader is None:
        canvas.setFillColor(colors.HexColor('#f4f4f4'))
        canvas.rect(x, y, size, size, fill=1)
        canvas.setFillColor(colors.HexColor('#999999'))
        canvas.setFont(MR_FONT_NAME, 8)
        canvas.drawCentredString(x + size / 2, y + size / 2 - 2, 'No photo')
        return
    width, height = reader.getSize()
    scale = min(size / width, size / height)
    w, h = width * scale, height * scale
    canvas.drawImage(reader, x + (size - w) / 2, y + (size - h) / 2, w, h)
    canvas.rect(x, y, size, size, fill=0)


class Step(Flowable):
    """One stop on the path: a dot on the vertical line, the handover's text, and its photo on the right."""

    def __init__(self, number, transfer, first, last, styles):
        super().__init__()
        self.number, self.t, self.first, self.last, self.styles = number, transfer, first, last, styles
        self.reader = _image(transfer.photo)
        self.text_w = PAGE_W - 16 * mm - STEP_PHOTO - 6 * mm

    def _paragraphs(self):
        s, t = self.styles, self.t
        pending = t.status != 'completed'
        when = timezone.localtime(t.completed_at or t.requested_at)
        title = f'{t.get_kind_display()}' + (f' - {t.get_status_display()}' if pending else '')
        parts = [Paragraph(f'<font color="{KIND_COLORS.get(t.kind, "#333333")}"><b>{title}</b></font> &nbsp; <font color="#666666">{when:%d/%m/%Y %H:%M}</font>', s['step'])]
        if t.kind == 'opening':
            parts.append(rtl_paragraph(f'Received into  {t.to_label}', s['place'], self.text_w))
        else:
            parts.append(rtl_paragraph(f'{t.from_label}  ->  {t.to_label}', s['place'], self.text_w))
        who = [f'requested by {_name(t.requested_by)}']
        if t.approved_by_id and t.kind != 'opening':
            who.append(f'approved by {_name(t.approved_by)}')
        if t.completed_by_id:
            who.append(f'handover by {_name(t.completed_by)}')
        parts.append(Paragraph(' &middot; '.join(who) if t.kind != 'opening' else f'recorded by {_name(t.completed_by or t.requested_by)}', s['small']))
        if t.holder:
            parts.append(rtl_paragraph(f'Held on site by: {t.holder}', s['small'], self.text_w))
        if t.return_condition:
            colour = {'ok': '#1b7f3b', 'needs_maintenance': '#b26a00', 'scrap': '#b3261e'}.get(t.return_condition, '#333333')
            parts.append(Paragraph(f'Condition on return: <font color="{colour}"><b>{t.get_return_condition_display()}</b></font>', s['small']))
            if t.return_note:
                parts.append(rtl_paragraph(t.return_note, s['small'], self.text_w))
        if t.note and t.kind != 'opening':
            parts.append(rtl_paragraph(t.note, s['small'], self.text_w))
        return parts

    def wrap(self, avail_w, avail_h):
        self.paras = self._paragraphs()
        text_h = 0
        self.heights = []
        for p in self.paras:
            _, h = p.wrap(self.text_w, 1000)
            self.heights.append(h)
            text_h += h + 1.5
        self.height = max(text_h + 4 * mm, STEP_PHOTO + 6 * mm)
        self.width = avail_w
        return self.width, self.height

    def draw(self):
        c = self.canv
        colour = colors.HexColor(KIND_COLORS.get(self.t.kind, '#333333'))
        line_x, dot_y = 5 * mm, self.height - 7 * mm
        # the path: a vertical line through the dot, joined to the previous and next steps
        c.setStrokeColor(colors.HexColor('#9aa7b4'))
        c.setLineWidth(2)
        c.line(line_x, dot_y if self.first else self.height, line_x, 0 if not self.last else dot_y)
        pending = self.t.status != 'completed'
        c.setFillColor(colors.white if pending else colour)
        c.setStrokeColor(colour)
        c.circle(line_x, dot_y, 3.6 * mm, fill=1)
        c.setFillColor(colour if pending else colors.white)
        c.setFont(MR_FONT_BOLD_NAME, 8)
        c.drawCentredString(line_x, dot_y - 2.7, str(self.number))
        # text
        y = self.height - 2 * mm
        for p, h in zip(self.paras, self.heights):
            y -= h
            p.drawOn(c, 16 * mm, y)
            y -= 1.5
        # photo, on the right
        _draw_photo(c, self.reader, PAGE_W - STEP_PHOTO, self.height - STEP_PHOTO - 2 * mm, STEP_PHOTO)


def _name(user):
    if not user:
        return '-'
    return user.get_full_name() or user.username


def build_tool_sheet_pdf(tool, url):
    from .models import ToolTransfer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f'{tool.code} - tool record')
    styles = {
        'title': ParagraphStyle('title', fontName=MR_FONT_BOLD_NAME, fontSize=17, leading=21),
        'h2': ParagraphStyle('h2', fontName=MR_FONT_BOLD_NAME, fontSize=12, leading=15, textColor=colors.HexColor('#2f4f6f'), spaceBefore=6, spaceAfter=4),
        'step': ParagraphStyle('step', fontName=MR_FONT_NAME, fontSize=10.5, leading=13),
        'place': ParagraphStyle('place', fontName=MR_FONT_BOLD_NAME, fontSize=11, leading=14),
        'small': ParagraphStyle('small', fontName=MR_FONT_NAME, fontSize=8.8, leading=11, textColor=colors.HexColor('#444444')),
        'cell': ParagraphStyle('cell', fontName=MR_FONT_NAME, fontSize=9, leading=11),
        'label': ParagraphStyle('label', fontName=MR_FONT_BOLD_NAME, fontSize=9, leading=11, textColor=colors.HexColor('#555555')),
    }

    class Header(Flowable):
        """Current photo on the left, details in the middle, QR on the right."""
        def __init__(self):
            super().__init__()
            self.reader = _image(tool.photo)

        def wrap(self, avail_w, avail_h):
            self.width, self.height = avail_w, HEADER_PHOTO + 4 * mm
            return self.width, self.height

        def draw(self):
            c = self.canv
            _draw_photo(c, self.reader, 0, 2 * mm, HEADER_PHOTO)
            code = qr.QrCodeWidget(url, barLevel='M')
            x0, y0, x1, y1 = code.getBounds()
            size = 34 * mm
            drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
            drawing.add(code)
            renderPDF.draw(drawing, c, self.width - size, self.height - size)
            c.setFont(MR_FONT_BOLD_NAME, 12)
            c.setFillColor(colors.black)
            c.drawCentredString(self.width - size / 2, self.height - size - 5 * mm, tool.code)
            c.setFillColor(colors.HexColor(STATUS_COLORS.get(tool.status, '#333333')))
            c.setFont(MR_FONT_BOLD_NAME, 10)
            c.drawCentredString(self.width - size / 2, self.height - size - 11 * mm, tool.get_status_display())

    details = [
        ('Category', tool.category), ('Manufacturer', tool.manufacturer), ('Model / serial', ' / '.join(filter(None, [tool.model_no, tool.serial_no]))),
        ('Purchased', ' - '.join(filter(None, [f'{tool.purchase_date:%d/%m/%Y}' if tool.purchase_date else '', f'{tool.purchase_cost}' if tool.purchase_cost else '']))),
        ('Location now', tool.location_label), ('Held by', tool.holder),
        ('Last stock-take', f'{tool.last_inventory_date:%d/%m/%Y}' if tool.last_inventory_date else ''), ('Notes', tool.notes),
    ]
    detail_w = PAGE_W - HEADER_PHOTO - 34 * mm - 8 * mm
    rows = [[Paragraph(label, styles['label']), rtl_paragraph(value or '-', styles['cell'], detail_w - 32 * mm)] for label, value in details]
    details_table = Table(rows, colWidths=[30 * mm, detail_w - 30 * mm])
    details_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
                                       ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#dddddd'))]))

    class HeaderWithDetails(Flowable):
        def __init__(self):
            super().__init__()
            self.header = Header()

        def wrap(self, avail_w, avail_h):
            self.header.wrap(avail_w, avail_h)
            self.details_w, self.details_h = details_table.wrap(detail_w, avail_h)
            self.width, self.height = avail_w, max(self.header.height, self.details_h + 2 * mm)
            return self.width, self.height

        def draw(self):
            self.canv.saveState()
            self.canv.translate(0, self.height - self.header.height)
            self.header.canv = self.canv
            self.header.draw()
            self.canv.restoreState()
            details_table.drawOn(self.canv, HEADER_PHOTO + 6 * mm, self.height - self.details_h)

    story = [Paragraph('Tool record', styles['title']), rtl_paragraph(tool.name, styles['title'], PAGE_W), Spacer(1, 3 * mm), HeaderWithDetails(), Spacer(1, 2 * mm)]

    # ---- the path
    transfers = list(tool.transfers.exclude(status__in=('rejected', 'cancelled')).select_related(
        'from_project', 'from_warehouse', 'to_project', 'to_warehouse', 'requested_by', 'approved_by', 'completed_by'))
    transfers.sort(key=lambda t: (t.completed_at or t.requested_at, t.pk))
    story.append(Paragraph(f'Movement path ({sum(1 for t in transfers if t.status == "completed")} handovers)', styles['h2']))
    if not transfers:
        story.append(Paragraph('No movements recorded.', styles['cell']))
    for index, transfer in enumerate(transfers):
        story.append(Step(index + 1, transfer, first=index == 0, last=index == len(transfers) - 1, styles=styles))

    # ---- maintenance
    jobs = list(tool.maintenance_jobs.all().order_by('opened_at'))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph('Maintenance history', styles['h2']))
    if jobs:
        data = [[Paragraph(h, styles['label']) for h in ('Opened', 'Problem', 'Vendor / parts', 'Cost', 'Status')]]
        for job in jobs:
            data.append([Paragraph(f'{timezone.localtime(job.opened_at):%d/%m/%Y}', styles['cell']),
                         rtl_paragraph(job.problem + (f' -> {job.result_note}' if job.result_note else ''), styles['cell'], 70 * mm),
                         rtl_paragraph(' '.join(filter(None, [job.vendor, job.parts])) or '-', styles['cell'], 42 * mm),
                         Paragraph(f'{job.cost}' if job.cost is not None else '-', styles['cell']),
                         Paragraph(job.get_status_display() + (f' {job.finished_date:%d/%m/%Y}' if job.finished_date else ''), styles['cell'])])
        table = Table(data, colWidths=[22 * mm, 76 * mm, 46 * mm, 16 * mm, PAGE_W - 160 * mm], repeatRows=1)
        table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#bbbbbb')), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2f6')),
                                   ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story.append(table)
    else:
        story.append(Paragraph('No maintenance recorded.', styles['cell']))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(MR_FONT_NAME, 8)
        canvas.setFillColor(colors.HexColor('#777777'))
        canvas.drawString(12 * mm, 8 * mm, f'One Stop Contracting - {tool.code} - printed {timezone.localtime():%d/%m/%Y %H:%M}')
        canvas.drawRightString(A4[0] - 12 * mm, 8 * mm, f'Page {document.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
