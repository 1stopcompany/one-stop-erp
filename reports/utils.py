from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing, Circle, Rect, Line
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from PIL import Image as PILImage
import os
import re

import arabic_reshaper
from bidi.algorithm import get_display

# reportlab's built-in fonts (Helvetica, etc.) have no Arabic glyphs at
# all -- every Arabic character silently renders as a blank/missing-glyph
# box. Register a real Arabic-capable font under the names the rest of
# this module uses instead of 'Helvetica'/'Helvetica-Bold', for every
# style and every table cell (not just headers) since any free-text field
# here can contain Arabic.
#
# The font is IBM Plex Sans Arabic (SIL Open Font License -- free for
# commercial use, static/fonts/IBMPlexSansArabic-OFL.txt), a clean
# geometric Arabic sans-serif chosen as a freely-licensable stand-in for
# "Madani Arabic" (the font used in the real source reports this module's
# layout is based on): Madani Arabic's own free download is
# personal-use-only, and embedding it in this company's official
# client-facing reports would need a paid commercial license the company
# would have to obtain directly from the type foundry -- ask before
# swapping to it.
#
# Almarai (also OFL, also a reasonable visual match) was tried first and
# rejected: arabic_reshaper emits legacy Arabic Presentation Forms
# codepoints, and Almarai's cmap is missing the isolated/final forms of
# several very common letters (alef, reh, waw, ...) -- those render as
# blank tofu boxes. IBM Plex Sans Arabic's cmap covers the full set this
# module's shape_text()/rtl_paragraph() can produce.
FONT_NAME = 'Helvetica'
FONT_BOLD_NAME = 'Helvetica-Bold'
_WINDOWS_FONTS_DIR = r'C:\Windows\Fonts'
try:
    from django.conf import settings as _django_settings
    _fonts_dir = os.path.join(_django_settings.BASE_DIR, 'static', 'fonts')
    pdfmetrics.registerFont(TTFont('IBMPlexSansArabic', os.path.join(_fonts_dir, 'IBMPlexSansArabic-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('IBMPlexSansArabic-Bold', os.path.join(_fonts_dir, 'IBMPlexSansArabic-Bold.ttf')))
    FONT_NAME = 'IBMPlexSansArabic'
    FONT_BOLD_NAME = 'IBMPlexSansArabic-Bold'
except Exception:
    try:
        # Fall back to Windows' bundled Tahoma if the bundled font isn't present.
        pdfmetrics.registerFont(TTFont('Tahoma', os.path.join(_WINDOWS_FONTS_DIR, 'tahoma.ttf')))
        pdfmetrics.registerFont(TTFont('Tahoma-Bold', os.path.join(_WINDOWS_FONTS_DIR, 'tahomabd.ttf')))
        FONT_NAME = 'Tahoma'
        FONT_BOLD_NAME = 'Tahoma-Bold'
    except Exception:
        # Neither font file is present on this machine (e.g. a Linux
        # server with neither bundled font copied over) -- fall back to
        # Helvetica. Arabic text will still be blank there, but
        # English/numeric content keeps working rather than crashing.
        pass

# Times New Roman -- originally added only for generate_report_pdf() (the English-only EDGE-format Monthly
# Report), to match the real source .docx, which uses Times New Roman throughout (its styles.xml
# docDefaults). Kept separate from FONT_NAME/FONT_BOLD_NAME above rather than replacing them: on some builds
# of the font (older Windows releases, some language packs) Times New Roman has no Arabic glyphs, so it must
# never become the shared default those other (Arabic-capable) report PDFs rely on unconditionally. The
# times.ttf actually bundled with this Windows box DOES cover the Arabic presentation forms this module's
# shape_text() produces (checked against every glyph in a real Arabic project name/report heading -- see the
# session notes), so generate_daily_report_pdf() also uses MR_FONT_NAME/MR_FONT_BOLD_NAME by request; if this
# ever runs on a machine whose times.ttf lacks Arabic coverage, the except-fallback below still keeps
# MR_FONT_NAME on the Arabic-capable font rather than silently blanking Arabic text.
MR_FONT_NAME = FONT_NAME
MR_FONT_BOLD_NAME = FONT_BOLD_NAME
MR_FONT_ITALIC_NAME = FONT_NAME
MR_FONT_BOLD_ITALIC_NAME = FONT_BOLD_NAME
# Times New Roman is looked for in static/fonts first (copy times.ttf, timesbd.ttf, timesi.ttf, timesbi.ttf there on a server that
# has no Windows fonts), then in the Windows fonts folder.
_times_dir = _WINDOWS_FONTS_DIR
try:
    _bundled_times = os.path.join(_django_settings.BASE_DIR, 'static', 'fonts')
    if os.path.exists(os.path.join(_bundled_times, 'times.ttf')):
        _times_dir = _bundled_times
except Exception:
    pass
try:
    pdfmetrics.registerFont(TTFont('TimesNewRoman', os.path.join(_times_dir, 'times.ttf')))
    pdfmetrics.registerFont(TTFont('TimesNewRoman-Bold', os.path.join(_times_dir, 'timesbd.ttf')))
    pdfmetrics.registerFont(TTFont('TimesNewRoman-Italic', os.path.join(_times_dir, 'timesi.ttf')))
    pdfmetrics.registerFont(TTFont('TimesNewRoman-BoldItalic', os.path.join(_times_dir, 'timesbi.ttf')))
    MR_FONT_NAME = 'TimesNewRoman'
    MR_FONT_BOLD_NAME = 'TimesNewRoman-Bold'
    MR_FONT_ITALIC_NAME = 'TimesNewRoman-Italic'
    MR_FONT_BOLD_ITALIC_NAME = 'TimesNewRoman-BoldItalic'
except Exception:
    # Times New Roman isn't bundled on this machine -- keep whatever
    # Arabic-capable font was resolved above rather than crashing.
    pass

_ARABIC_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F]')


class _TocDocTemplate(SimpleDocTemplate):
    """
    A SimpleDocTemplate that auto-collects a real, clickable Table of
    Contents from every Paragraph whose style name is 'MRHeading' (the
    Monthly Report's numbered-section headings, e.g. "2. Executive
    Summary"), matching the real EDGE report's own Word-generated TOC.
    Must be built with multiBuild() (not build()): reportlab needs a
    first pass to learn each heading's final page number before it can
    render the TOC page itself, since the TOC appears earlier in the
    document than the sections it lists.

    Each heading gets a same-named PDF bookmark (canvas.bookmarkPage) the
    instant it's drawn; passing that bookmark's key as the 4th element of
    the 'TOCEntry' notification is what reportlab's own TableOfContents
    flowable needs to render that row as a clickable link to it (see
    reportlab/platypus/tableofcontents.py's own docstring/wrap()) --
    without the key, a TOC shows correct page numbers as plain text but
    nothing is actually clickable. addOutlineEntry additionally lists
    every section in the PDF reader's own bookmarks/outline panel, a
    second, independent way to jump to any section besides the in-page
    TOC. id(flowable) is stable and unique across multiBuild's repeated
    passes (they reuse the very same flowable objects each time), so it's
    a safe, collision-free per-heading key.
    """

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable.style, 'name', None) == 'MRHeading':
            text = flowable.getPlainText()
            key = f'toc-anchor-{id(flowable)}'
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0, closed=0)
            self.notify('TOCEntry', (0, text, self.page, key))


def shape_text(text):
    """
    Reshape + bidi-reorder Arabic text for reportlab, which (unlike a
    browser) does not do Arabic letter joining or right-to-left
    reordering on its own. Text with no Arabic characters passes through
    unchanged; mixed Arabic/Latin text (e.g. "Report No. 123 - مبنى") is
    still handled correctly by python-bidi's algorithm. Safe to call on
    any value (None, numbers, etc.) -- always returns a string.
    """
    if text is None:
        return ''
    text = str(text)
    if not _ARABIC_RE.search(text):
        return text
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def _t(value, default=''):
    """shape_text with a default for empty/None values."""
    if value in (None, ''):
        return default
    return shape_text(value)


def _qty(value, default='—'):
    """A Decimal/number as a plain (non-exponential) string with trailing zeros trimmed, e.g. Decimal('65.35') -> '65.35', Decimal('15.00') -> '15'."""
    if value in (None, ''):
        return default
    text = format(Decimal(value), 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


ARABIC_WEEKDAYS = ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']  # date.weekday(): Monday=0


def _kpi_icon(kind, color_hex, size=0.34 * inch):
    """A small flat glyph on a filled color circle, for a PDF summary-strip KPI card (workers / hours /
    activities / equipment / issues). Drawn from plain vector shapes rather than an emoji or an external
    icon font, so it renders identically on any machine reportlab runs on -- no font/glyph-coverage risk."""
    d = Drawing(size, size)
    cx = cy = size / 2
    d.add(Circle(cx, cy, size / 2, fillColor=colors.HexColor(color_hex), strokeColor=None))
    white = colors.white
    if kind == 'workers':
        d.add(Circle(cx, cy + size * 0.13, size * 0.12, fillColor=white, strokeColor=None))
        d.add(Rect(cx - size * 0.17, cy - size * 0.22, size * 0.34, size * 0.28,
                    rx=size * 0.14, ry=size * 0.14, fillColor=white, strokeColor=None))
    elif kind == 'hours':
        d.add(Circle(cx, cy, size * 0.22, fillColor=None, strokeColor=white, strokeWidth=1.6))
        d.add(Line(cx, cy, cx, cy + size * 0.14, strokeColor=white, strokeWidth=1.6, strokeLineCap=1))
        d.add(Line(cx, cy, cx + size * 0.11, cy - size * 0.02, strokeColor=white, strokeWidth=1.6, strokeLineCap=1))
    elif kind == 'activities':
        d.add(Line(cx - size * 0.15, cy - size * 0.01, cx - size * 0.03, cy - size * 0.14,
                    strokeColor=white, strokeWidth=2.4, strokeLineCap=1))
        d.add(Line(cx - size * 0.03, cy - size * 0.14, cx + size * 0.19, cy + size * 0.13,
                    strokeColor=white, strokeWidth=2.4, strokeLineCap=1))
    elif kind == 'equipment':
        d.add(Rect(cx - size * 0.22, cy - size * 0.06, size * 0.30, size * 0.16, fillColor=white, strokeColor=None))
        d.add(Rect(cx + size * 0.02, cy - size * 0.13, size * 0.18, size * 0.23,
                    rx=size * 0.03, ry=size * 0.03, fillColor=white, strokeColor=None))
        for wx in (-0.12, 0.12):
            d.add(Circle(cx + size * wx, cy - size * 0.15, size * 0.065, fillColor=colors.HexColor(color_hex), strokeColor=white, strokeWidth=1.3))
    elif kind == 'issues':
        d.add(Rect(cx - size * 0.16, cy - size * 0.2, size * 0.32, size * 0.4,
                    rx=size * 0.03, ry=size * 0.03, fillColor=white, strokeColor=None))
        d.add(Rect(cx - size * 0.07, cy + size * 0.16, size * 0.14, size * 0.06, fillColor=colors.HexColor(color_hex), strokeColor=None))
        for dy in (0.06, -0.03, -0.12):
            d.add(Line(cx - size * 0.09, cy + size * dy, cx + size * 0.09, cy + size * dy,
                        strokeColor=colors.HexColor(color_hex), strokeWidth=1.2))
    return d


def _rtl_wrap_lines(text, font_name, font_size, max_width, justify=False):
    """
    Word-wrap `text` to fit `max_width` (points) at `font_name`/`font_size`,
    then bidi-reorder EACH resulting line separately.

    get_display() assumes the string it reorders renders as a single line;
    calling shape_text() on a whole long paragraph and letting reportlab's
    Paragraph wrap the (already-reordered) result breaks the visual order
    at reportlab's own wrap points, since reportlab wraps naively on the
    pre-shaped string with no idea it's RTL. Wrapping must happen first
    (on the original, un-reordered text), one line at a time.

    If `justify=True`, every line except the last is stretched to exactly
    `max_width` by distributing extra space characters between its words
    (in logical order, before reshaping) -- reportlab's own JUSTIFY
    alignment can't do this for us since each line here is a hard-broken
    unit (see rtl_paragraph), not something reportlab re-wraps itself.
    """
    words = text.split(' ')
    lines = []
    current_words = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if not current or pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            current_words.append(word)
        else:
            lines.append(current_words)
            current_words = [word]
            current = word
    if current_words:
        lines.append(current_words)

    shaped = []
    for i, line_words in enumerate(lines):
        is_last = (i == len(lines) - 1)
        line_text = ' '.join(line_words)
        if justify and not is_last and len(line_words) > 1:
            deficit = max_width - pdfmetrics.stringWidth(line_text, font_name, font_size)
            space_width = pdfmetrics.stringWidth(' ', font_name, font_size)
            extra_spaces = int(deficit / space_width) if space_width else 0
            if extra_spaces > 0:
                gaps = len(line_words) - 1
                base, remainder = divmod(extra_spaces, gaps)
                parts = [line_words[0]]
                for gi in range(1, len(line_words)):
                    n_extra = base + (1 if gi <= remainder else 0)
                    parts.append(' ' * (1 + n_extra) + line_words[gi])
                line_text = ''.join(parts)
        shaped.append(shape_text(line_text))
    return shaped


def rtl_paragraph(text, style, max_width, justify=False):
    """
    Build a Paragraph for a long RTL text block that may wrap across
    several lines (see _rtl_wrap_lines for why this needs to differ from
    plain Paragraph(_t(text), style)). `\n` in `text` starts a new
    paragraph block (rendered as a line break). `justify=True` stretches
    every non-final line to the full `max_width` (see _rtl_wrap_lines).
    """
    if not text:
        return Paragraph('', style)
    para_blocks = []
    for block in str(text).split('\n'):
        block = block.strip()
        if not block:
            continue
        lines = _rtl_wrap_lines(block, style.fontName, style.fontSize, max_width, justify=justify)
        para_blocks.append('<br/>'.join(lines))
    return Paragraph('<br/>'.join(para_blocks), style)


def generate_report_pdf(report):
    """
    Generate the "Monthly Site Progress Report" PDF for a MonthlyReport,
    matching the real English-language format submitted to the EDGE
    (green-building) consultant/certifier: cover page, executive summary,
    progress summary, key activities, materials status, HSE, QC, issues/
    risks/delays, plan for next month, full BOQ progress breakdown,
    photographic record, sign-off and appendix.

    Unlike generate_owner_financial_report_pdf, this report's own text is
    English, so it uses plain left-aligned Paragraphs (reportlab's normal
    wrapping/justify) instead of rtl_paragraph()/_rtl_wrap_lines() -- those
    are only needed for text reportlab must re-order for RTL display.
    _t() is still applied defensively to every field since a free-text
    field (e.g. a site engineer's Arabic name) could contain Arabic.
    """
    from .progress_models import calculate_project_progress
    from .models import ReportAttachment, MaterialSupply

    # This report's own text is English, so its font must match the real
    # source .docx (Times New Roman throughout -- see MR_FONT_NAME above),
    # not the Arabic-capable font the other report PDFs share. Capture
    # that Arabic-capable font under its own name FIRST, then shadow
    # FONT_NAME/FONT_BOLD_NAME for the rest of this function: every style
    # and TableStyle below reads the plain (module-level) names, and a
    # local assignment makes Python treat them as local for the whole
    # function body, so this is the only place that needs to change.
    # globals() lookup (not a bare `FONT_NAME` read) is required here: the
    # assignments below make Python treat FONT_NAME/FONT_BOLD_NAME as
    # local names for this whole function, so a plain reference to them
    # on this line would raise UnboundLocalError rather than reading the
    # module-level value.
    AR_FONT_NAME = globals()['FONT_NAME']
    AR_FONT_BOLD_NAME = globals()['FONT_BOLD_NAME']
    FONT_NAME = MR_FONT_NAME
    FONT_BOLD_NAME = MR_FONT_BOLD_NAME

    def smart_para(text, style, default='—'):
        """
        A Paragraph in `style` (Times New Roman) -- unless `text` actually
        contains Arabic (project/client names are stored in Arabic in
        this system even though the EDGE report format itself is
        English), in which case it falls back to the Arabic-capable font
        so that value doesn't render as blank tofu.
        """
        if not text:
            return default
        text = str(text)
        if _ARABIC_RE.search(text):
            ar_font = AR_FONT_BOLD_NAME if style.fontName == FONT_BOLD_NAME else AR_FONT_NAME
            ar_style = ParagraphStyle(f'{style.name}Ar', parent=style, fontName=ar_font)
            return Paragraph(shape_text(text), ar_style)
        return Paragraph(_t(text), style)

    buffer = BytesIO()
    page_size = A4
    # Margins match the real source .docx's own page setup (word/document.xml
    # w:pgMar): 0.75" top/left/right, ~0.56" bottom.
    doc = _TocDocTemplate(
        buffer, pagesize=page_size,
        topMargin=0.75 * inch, bottomMargin=0.5625 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    page_width = page_size[0] - 1.5 * inch

    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'MRTitle', parent=styles['Heading1'], fontSize=15,
        textColor=colors.HexColor('#1f4788'), alignment=TA_CENTER,
        fontName=FONT_BOLD_NAME, spaceAfter=4,
    )
    # 13pt bold -- matches the real .docx's own section headings ("2.
    # Executive Summary", "3. Progress Summary", ...: w:sz=26 half-points,
    # w:b, no named Heading style) exactly, down to the point size.
    heading_style = ParagraphStyle(
        'MRHeading', parent=styles['Heading2'], fontSize=13,
        textColor=colors.white, backColor=colors.HexColor('#1f4788'),
        fontName=FONT_BOLD_NAME, spaceBefore=10, spaceAfter=6,
        alignment=TA_LEFT, borderPadding=(4, 6, 4, 6),
    )
    normal_style = ParagraphStyle(
        'MRNormal', parent=styles['Normal'], fontSize=10,
        alignment=TA_LEFT, fontName=FONT_NAME, leading=14,
    )

    def _ml(text, default=''):
        """
        Join a multi-line free-text field's lines with <br/> for Paragraph
        rendering -- a plain '\\n' in the source text (e.g. one "Activity
        N: ..." per line in next_month_plan) is otherwise collapsed to a
        single space by reportlab's Paragraph, unlike a browser.
        """
        if not text:
            return default
        lines = [shape_text(line.strip()) for line in str(text).split('\n') if line.strip()]
        return '<br/>'.join(lines) or default
    small_style = ParagraphStyle(
        'MRSmall', parent=styles['Normal'], fontSize=8,
        alignment=TA_LEFT, fontName=FONT_NAME, leading=11,
    )
    cell_style = ParagraphStyle(
        'MRCell', parent=styles['Normal'], fontSize=8,
        alignment=TA_LEFT, fontName=FONT_NAME, leading=10,
    )
    schedule_cell_style = ParagraphStyle(
        'MRScheduleCell', parent=styles['Normal'], fontSize=6.5,
        alignment=TA_LEFT, fontName=FONT_NAME, leading=8,
    )
    caption_style = ParagraphStyle(
        'MRCaption', parent=styles['Normal'], fontSize=9,
        alignment=TA_CENTER, fontName=FONT_NAME, leading=12,
    )

    def hdr_table(rows, col_widths, font_size=9, repeat_rows=1):
        t = Table(rows, colWidths=col_widths, repeatRows=repeat_rows)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD_NAME),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), font_size),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6fb')]),
        ]))
        return t

    project = report.project
    period_label = report.reporting_period_to.strftime('%b %Y')

    # ---------------- COVER PAGE ----------------
    logo_path = _owner_report_logo_path()
    elements.append(Spacer(1, 0.7 * inch))
    if logo_path:
        cover_logo = Image(logo_path, width=4.2 * inch, height=1.0 * inch, kind='proportional')
        cover_logo.hAlign = 'CENTER'
        elements.append(cover_logo)
    rule = Table([['']], colWidths=[page_width], rowHeights=[3])
    rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f2c811'))]))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(rule)
    elements.append(Spacer(1, 0.7 * inch))

    # 16pt bold (not italic) -- matches the real .docx's own title run
    # (w:sz=32 half-points, w:b, no w:i) for "MONTHLY SITE PROGRESS REPORT".
    cover_title_style = ParagraphStyle(
        'MRCoverTitle', parent=styles['Heading1'], fontSize=16,
        textColor=colors.HexColor('#1f4788'), alignment=TA_CENTER,
        fontName=FONT_BOLD_NAME, spaceAfter=10,
    )
    # 12pt bold italic -- matches the real .docx's subtitle run (the
    # "R02.07.2026 - Jul 2026 (...)" line: w:sz=24 half-points, w:b, w:i).
    cover_sub_style = ParagraphStyle(
        'MRCoverSub', parent=styles['Normal'], fontSize=12,
        textColor=colors.HexColor('#333333'), alignment=TA_CENTER,
        fontName=MR_FONT_BOLD_ITALIC_NAME, spaceAfter=4,
    )
    elements.append(Paragraph('MONTHLY SITE PROGRESS REPORT', cover_title_style))
    rev_suffix = f' — Rev{report.revision_number:02d}' if report.revision_number > 1 else ''
    elements.append(Paragraph(_t(f'{report.report_number} — {period_label}{rev_suffix}'), cover_sub_style))
    elements.append(Spacer(1, 0.6 * inch))

    engineer_name = ''
    if report.site_engineer:
        engineer_name = report.site_engineer.get_full_name() or report.site_engineer.username

    duration_label = '—'
    if project.start_date and project.end_date:
        delta = relativedelta(project.end_date, project.start_date)
        months = delta.years * 12 + delta.months
        duration_label = f'{months} months'

    # Cover-table cell style, 9pt -- matches the real .docx's own info
    # table (w:sz=18 half-points). Project/client/engineer names are
    # stored in Arabic in this system, so their values go through
    # smart_para() to fall back to the Arabic-capable font as needed.
    cover_cell_style = ParagraphStyle('MRCoverCell', parent=normal_style, fontSize=9, leading=12)
    cover_rows = [
        ['Project Name', smart_para(project.name, cover_cell_style)],
        ['Report No.', _t(report.report_number)],
        ['Client', smart_para(project.client_name, cover_cell_style)],
        ['Reporting Period', f"{report.reporting_period_from.strftime('%d/%m/%Y')} – {report.reporting_period_to.strftime('%d/%m/%Y')}"],
        ['Contractor', 'One Stop Contracting'],
        ['Contract No.', _t(project.contract_number, '—')],
        ['Location', smart_para(project.location, cover_cell_style)],
        ['Prepared By', smart_para(engineer_name, cover_cell_style, default='One Stop Team')],
        ['Contract Start Date', project.start_date.strftime('%d/%m/%Y') if project.start_date else '—'],
        ['Contract Duration', duration_label],
        ['Planned Completion Date', project.end_date.strftime('%d/%m/%Y') if project.end_date else '—'],
    ]
    cover_table = Table(cover_rows, colWidths=[page_width * 0.38, page_width * 0.62])
    cover_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#deeaf6')),
        ('FONTNAME', (0, 0), (0, -1), FONT_BOLD_NAME),
        ('FONTNAME', (1, 0), (1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(cover_table)
    elements.append(PageBreak())

    # ---------------- Table of Contents ----------------
    # Real page numbers, resolved by _TocDocTemplate.afterFlowable() +
    # doc.multiBuild() below -- every "N. Section Name" heading Paragraph
    # further down registers itself as a TOC entry when it's drawn.
    elements.append(Paragraph('Table of Contents', heading_style))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            'MRTocEntry', parent=normal_style, fontSize=10.5, leading=16,
            leftIndent=0, firstLineIndent=0,
        ),
    ]
    elements.append(toc)
    elements.append(PageBreak())

    # ---------------- 2. Executive Summary ----------------
    elements.append(Paragraph('2. Executive Summary', heading_style))
    elements.append(Paragraph(_ml(report.executive_summary, 'No executive summary provided.'), normal_style))
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 3. Progress Summary ----------------
    progress = calculate_project_progress(project, as_of_date=report.reporting_period_to)
    previous_progress = calculate_project_progress(project, as_of_date=report.reporting_period_from - relativedelta(days=1))
    overall_pct = progress['overall_percentage']
    this_month_pct = overall_pct - previous_progress['overall_percentage']

    elements.append(Paragraph('3. Progress Summary', heading_style))
    progress_rows = [['Item', 'Planned %', 'Actual %']]
    progress_rows.append(['Overall Project Progress (Cumulative)', '—', f'{overall_pct:.3f}%'])
    progress_rows.append([
        'Progress This Month', '—',
        Paragraph(
            f"{this_month_pct:.3f}% ({previous_progress['overall_percentage']:.3f}% as of {report.reporting_period_from.strftime('%d/%m')} → {overall_pct:.3f}% as of {report.reporting_period_to.strftime('%d/%m')})",
            cell_style,
        ),
    ])
    for item in report.progress_category_items.all():
        progress_rows.append([
            Paragraph(_t(item.item_name), cell_style), _t(item.planned_value, '—'),
            Paragraph(_t(item.actual_value, '—'), cell_style),
        ])
    progress_rows.append(['Schedule Variance (+/- days)', '—', Paragraph(_t(report.schedule_variance_note, '—'), cell_style)])
    progress_table = Table(progress_rows, colWidths=[page_width * 0.35, page_width * 0.15, page_width * 0.50], repeatRows=1)
    progress_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD_NAME),
        ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, 1), (-1, 2), colors.HexColor('#deeaf6')),
        ('FONTNAME', (0, 1), (-1, 2), FONT_BOLD_NAME),
    ]))
    elements.append(progress_table)
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 4. Key Activities Carried Out This Month ----------------
    key_activities = list(report.key_activities.all())
    if key_activities:
        elements.append(Paragraph('4. Key Activities Carried Out This Month', heading_style))
        rows = [['No.', 'Activity / Work Item', 'Status', 'Remarks']]
        for i, a in enumerate(key_activities, start=1):
            rows.append([
                str(i),
                Paragraph(_t(a.activity), cell_style),
                _t(a.get_status_display()),
                Paragraph(_t(a.remarks, '—'), cell_style),
            ])
        activity_table = hdr_table(rows, [page_width * 0.06, page_width * 0.34, page_width * 0.15, page_width * 0.45])
        elements.append(activity_table)
        elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 5. Materials Status ----------------
    materials = list(report.material_supplies.all())
    if materials:
        elements.append(Paragraph('5. Materials Status', heading_style))
        material_type_labels = dict(MaterialSupply.MATERIAL_TYPE_CHOICES)
        rows = [['Type', 'Material', 'Qty (cumulative)', 'Delivered', 'Used', 'Remaining / Notes']]
        for m in materials:
            delivered = f'{m.delivered_quantity:g} {m.unit}' if m.delivered_quantity is not None else '—'
            used = f'{m.used_quantity:g} {m.unit}' if m.used_quantity is not None else '—'
            rows.append([
                _t(material_type_labels.get(m.material_type, '—')),
                Paragraph(_t(m.material_description), cell_style),
                f'{m.quantity:g} {m.unit}',
                delivered, used,
                Paragraph(_t(m.remaining_notes, '—'), cell_style),
            ])
        material_table = hdr_table(rows, [page_width * 0.14, page_width * 0.24, page_width * 0.16, page_width * 0.14, page_width * 0.12, page_width * 0.20])
        elements.append(material_table)
        elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 6. Health, Safety & Environment (HSE) ----------------
    elements.append(Paragraph('6. Health, Safety &amp; Environment (HSE)', heading_style))
    hse_rows = [
        ['Lost Time Incidents (LTI)', Paragraph(_t(report.hse_lti_note, '—'), cell_style)],
        ['Near Misses Reported (NM)', Paragraph(_t(report.hse_near_misses_note, '—'), cell_style)],
        ['Toolbox Talks Conducted (TBT)', Paragraph(_t(report.hse_toolbox_talks_note, '—'), cell_style)],
        ['Site Inspections Conducted', Paragraph(_t(report.hse_site_inspections_note, '—'), cell_style)],
        ['Corrective Actions Open / Closed', Paragraph(_t(report.hse_corrective_actions_note, '—'), cell_style)],
    ]
    hse_table = Table(hse_rows, colWidths=[page_width * 0.40, page_width * 0.60])
    hse_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#deeaf6')),
        ('FONTNAME', (0, 0), (0, -1), FONT_BOLD_NAME),
        ('FONTNAME', (1, 0), (1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(hse_table)
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 7. Quality Control / Inspections ----------------
    elements.append(Paragraph('7. Quality Control / Inspections', heading_style))
    elements.append(Paragraph(f'<b>Inspections / tests conducted this month:</b> {_t(report.qc_inspections_note, "—")}', normal_style))
    elements.append(Spacer(1, 0.05 * inch))
    elements.append(Paragraph(f'<b>Non-conformances raised and status:</b> {_t(report.qc_nonconformances_note, "—")}', normal_style))
    elements.append(Spacer(1, 0.05 * inch))
    elements.append(Paragraph(f'<b>Approvals / material submittals pending:</b> {_t(report.qc_pending_submittals_note, "—")}', normal_style))
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 8. Issues, Risks & Delays ----------------
    issues = list(report.issues_risks_delays.all())
    elements.append(Paragraph('8. Issues, Risks &amp; Delays', heading_style))
    if issues:
        rows = [['No.', 'Issue / Risk / Delay', 'Impact', 'Mitigation / Action']]
        for i, iss in enumerate(issues, start=1):
            rows.append([
                str(i),
                Paragraph(_t(iss.description), cell_style),
                Paragraph(_t(iss.impact, '—'), cell_style),
                Paragraph(_t(iss.mitigation, '—'), cell_style),
            ])
        issue_table = hdr_table(rows, [page_width * 0.06, page_width * 0.35, page_width * 0.25, page_width * 0.34])
        elements.append(issue_table)
    else:
        elements.append(Paragraph(
            'No significant issues, risks, or delays were encountered during the reporting period.', normal_style
        ))
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 9. Plan for Next Month ----------------
    elements.append(Paragraph('9. Plan for Next Month', heading_style))
    elements.append(Paragraph(_ml(report.next_month_plan, 'No plan provided.'), normal_style))
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 10. BOQ Progress Breakdown by Item ----------------
    elements.append(PageBreak())
    elements.append(Paragraph('10. BOQ Progress Breakdown by Item', heading_style))
    col_widths = [page_width * w for w in (0.045, 0.215, 0.075, 0.215, 0.075, 0.11, 0.13, 0.135)]
    schedule_header_style = ParagraphStyle(
        'MRScheduleHeader', parent=schedule_cell_style, textColor=colors.whitesmoke, fontName=FONT_BOLD_NAME,
    )
    # Header cells (other than the narrow "No." column) are wrapped in
    # Paragraphs (not plain strings) so a label too wide for its column
    # wraps onto a second line instead of overflowing into the next cell --
    # plain table-cell strings don't wrap.
    schedule_rows = [[
        'No.',
        *[Paragraph(h, schedule_header_style) for h in (
            'Main Item', '% of Total', 'Sub-item', 'Sub %', 'Start Date', 'Planned Completion', 'Execution %',
        )],
    ]]
    span_cmds = []
    row_idx = 1
    for phase_row in progress['phases']:
        phase = phase_row['phase']
        sub_items = list(phase.sub_items.all())
        start_row = row_idx
        if sub_items:
            for i, sub_item in enumerate(sub_items):
                sub_result = next((s for s in phase_row['sub_items'] if s['sub_item'].id == sub_item.id), None)
                exec_pct = sub_result['execution_percentage'] if sub_result else Decimal('0')
                schedule_rows.append([
                    _t(phase.code) if i == 0 else '',
                    smart_para(phase.name_en or phase.name_ar, schedule_cell_style) if i == 0 else '',
                    f'{phase.weight_percentage}%' if i == 0 else '',
                    smart_para(sub_item.name_en or sub_item.name_ar, schedule_cell_style),
                    f'{sub_item.weight_percentage}%',
                    sub_item.planned_start_date.strftime('%d/%m/%y') if sub_item.planned_start_date else '—',
                    sub_item.planned_completion_date.strftime('%d/%m/%y') if sub_item.planned_completion_date else '—',
                    f'{exec_pct:.1f}%',
                ])
                row_idx += 1
        else:
            schedule_rows.append([
                _t(phase.code), smart_para(phase.name_en or phase.name_ar, schedule_cell_style), f'{phase.weight_percentage}%',
                '—', '—', '—', '—', f"{phase_row['execution_percentage']:.1f}%",
            ])
            row_idx += 1
        end_row = row_idx - 1
        if end_row > start_row:
            span_cmds += [
                ('SPAN', (0, start_row), (0, end_row)),
                ('SPAN', (1, start_row), (1, end_row)),
                ('SPAN', (2, start_row), (2, end_row)),
            ]

    schedule_rows.append(['', 'TOTAL', '100%', '', '', '', '', f'{overall_pct:.3f}%'])
    total_row_idx = row_idx
    span_cmds.append(('SPAN', (0, total_row_idx), (1, total_row_idx)))

    schedule_table = Table(schedule_rows, colWidths=col_widths, repeatRows=1)
    schedule_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD_NAME),
        ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
        ('FONTNAME', (0, total_row_idx), (-1, total_row_idx), FONT_BOLD_NAME),
        ('BACKGROUND', (0, total_row_idx), (-1, total_row_idx), colors.HexColor('#deeaf6')),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('ROWBACKGROUNDS', (0, 1), (-1, total_row_idx - 1), [colors.white, colors.HexColor('#f4f6fb')]),
    ] + span_cmds))
    elements.append(schedule_table)
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 11. Photographic Record ----------------
    # Fixed-size boxes per orientation, same layout as the Owner Financial
    # report's photo gallery -- see _photo_orientation there for rationale.
    LANDSCAPE_BOX = (page_width, 3.5 * inch)
    PORTRAIT_BOX = (page_width / 2 - 0.1 * inch, 3.5 * inch)

    def _photo_orientation(path):
        try:
            with PILImage.open(path) as im:
                w, h = im.size
            return 'landscape' if w >= h else 'portrait'
        except Exception:
            return 'landscape'

    photos = list(report.phase_photos.select_related('phase').order_by('phase__order', 'order', '-taken_date'))
    if photos or report.photos_external_link:
        elements.append(PageBreak())
        elements.append(Paragraph('11. Photographic Record', heading_style))
        if report.photos_external_link:
            link_style = ParagraphStyle(
                'MRPhotoLink', parent=normal_style, fontName=FONT_NAME, textColor=colors.HexColor('#1155cc'),
            )
            # Escape '&' for reportlab's mini-XML parser (a Dropbox/Drive
            # URL commonly carries '&'-separated query params, e.g. '&dl=0').
            safe_url = report.photos_external_link.replace('&', '&amp;')
            elements.append(Paragraph(f'Full album: <a href="{safe_url}">{safe_url}</a>', link_style))
            elements.append(Spacer(1, 0.1 * inch))
        photos_by_phase = {}
        for p in photos:
            photos_by_phase.setdefault(p.phase, []).append(p)

        for phase, phase_photos in photos_by_phase.items():
            phase_name = phase.name_en or phase.name_ar
            phase_label = f"{phase.code}. {phase_name}" if phase.code else phase_name
            # smart_para (not a plain Paragraph) since phase_label falls back
            # to name_ar (Arabic) when a phase has no English name set.
            elements.append(smart_para(f'Phase {phase_label}', ParagraphStyle(
                'MRPhotoPhaseHeading', parent=normal_style, fontName=FONT_BOLD_NAME, fontSize=10.5,
                textColor=colors.HexColor('#1f4788'), spaceBefore=8, spaceAfter=4,
            )))

            items = []
            for photo in phase_photos:
                try:
                    path = photo.photo.path
                    orientation = _photo_orientation(path)
                    box_w, box_h = LANDSCAPE_BOX if orientation == 'landscape' else PORTRAIT_BOX
                    img = Image(path, width=box_w, height=box_h, kind='proportional')
                except Exception:
                    continue
                cap = Paragraph(_t(photo.caption, ' '), caption_style)
                items.append((orientation, [img, Spacer(1, 0.05 * inch), cap]))

            i = 0
            while i < len(items):
                orientation = items[i][0]
                cols = 1 if orientation == 'landscape' else 2
                run = []
                while i < len(items) and items[i][0] == orientation:
                    run.append(items[i][1])
                    i += 1
                for j in range(0, len(run), cols):
                    row_cells = run[j:j + cols]
                    row_cols = len(row_cells)
                    col_w = page_width if row_cols == 1 else page_width / row_cols
                    photo_table = Table([row_cells], colWidths=[col_w] * row_cols)
                    photo_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ]))
                    elements.append(photo_table)
            elements.append(Spacer(1, 0.1 * inch))

    # ---------------- Response to Comments (supervision / external consultant review) ----------------
    review_comments = list(report.review_comments.all())
    if review_comments:
        elements.append(Paragraph('Response to Comments', heading_style))
        rows = [['Reference', 'Comment', 'Response', 'Status']]
        for c in review_comments:
            rows.append([
                Paragraph(_t(c.reference, '—'), cell_style),
                Paragraph(_t(c.comment_text), cell_style),
                Paragraph(_t(c.response_text, '—'), cell_style),
                _t(c.get_status_display()),
            ])
        review_table = hdr_table(rows, [page_width * 0.15, page_width * 0.32, page_width * 0.38, page_width * 0.15])
        elements.append(review_table)
        elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 12. Sign-Off ----------------
    elements.append(PageBreak())
    elements.append(Paragraph('12. Sign-Off', heading_style))
    sig_name_style = ParagraphStyle('MRSigName', parent=normal_style, alignment=TA_CENTER)
    sig_data = [
        ['Prepared By', 'Reviewed By', 'Approved By'],
        [
            smart_para(engineer_name, sig_name_style),
            smart_para(report.reviewed_by.get_full_name(), sig_name_style, 'Pending') if report.reviewed_by else 'Pending',
            smart_para(report.approved_by.get_full_name(), sig_name_style, 'Pending') if report.approved_by else 'Pending',
        ],
        [
            report.created_at.strftime('%d/%m/%Y'),
            report.review_date.strftime('%d/%m/%Y') if report.review_date else '—',
            report.approval_date.strftime('%d/%m/%Y') if report.approval_date else '—',
        ],
    ]
    sig_table = Table(sig_data, colWidths=[page_width / 3] * 3)
    sig_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD_NAME),
        ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 0.2 * inch))

    # ---------------- 13. Appendix ----------------
    attachments = list(
        ReportAttachment.objects.filter(report_type='monthly', report_id=report.id).order_by('order', 'created_at')
    )
    if attachments:
        elements.append(Paragraph('13. Appendix — Supporting Documents', heading_style))
        rows = [['No.', 'Description', 'Type', 'Location / Reference']]
        for i, a in enumerate(attachments, start=1):
            rows.append([
                str(i), Paragraph(_t(a.description, '—'), cell_style),
                _t(a.get_attachment_type_display()), Paragraph(_t(a.location, '—'), cell_style),
            ])
        appendix_table = hdr_table(rows, [page_width * 0.08, page_width * 0.42, page_width * 0.20, page_width * 0.30])
        elements.append(appendix_table)

    # Footer
    footer_text = f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Status: {report.get_status_display()}"
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(footer_text, small_style))

    # multiBuild (not build): the Table of Contents needs a first pass to
    # learn each heading's final page number before its own page can be
    # rendered, since it appears earlier in the document than the
    # sections it lists -- see _TocDocTemplate.afterFlowable().
    doc.multiBuild(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_daily_report_pdf(report):
    """
    Generate the Daily Site Report PDF, matching the real company template (OS-FRM-SITE-DR-02): bilingual
    (Arabic/English) A4 landscape, numbered sections in the same order as the real form -- 1. Daily Works/
    Progress (today's activity progress against the BOQ), 2. Manpower & Man-Hours (named workers grouped by
    trade, with a subtotal per trade and a daily total), 3A/3B materials & plant, 4. QA/QC & HSE, 5. Site
    events, 6. Next-day plan (tomorrow's work) -- plus visitors, remarks and the sign-off block.
    """
    buffer = BytesIO()
    page_size = A4
    margin = 0.35 * inch
    page_width = page_size[0] - 2 * margin
    doc = SimpleDocTemplate(buffer, pagesize=page_size, topMargin=margin, bottomMargin=margin, leftMargin=margin, rightMargin=margin)
    elements = []

    # Section accent colors -- each numbered section gets its own band color (construction-report convention:
    # blue for progress/schedule, teal for labor, amber for materials/plant, red for safety, purple for events,
    # green for forward planning) instead of one flat color, plus status/priority/readiness colored per cell
    # further down (RAG: red/amber/green) so the printed report reads at a glance like the real site form.
    SECTION_COLORS = {
        'progress': '#1f4788', 'manpower': '#0e7c7b', 'materials': '#b45309', 'equipment': '#9a3412',
        'qaqc': '#b91c1c', 'events': '#6d28d9', 'plan': '#15803d', 'visits': '#334155', 'summary': '#1f4788',
    }
    PROGRESS_STATUS_COLORS = {'completed': '#c6f6d5', 'in_progress': '#bee3f8', 'delayed': '#fed7d7', 'on_hold': '#feebc8', 'not_started': '#e2e8f0'}
    EVENT_STATUS_COLORS = {'closed': '#c6f6d5', 'in_progress': '#feebc8', 'open': '#fed7d7'}
    LEVEL_COLORS = {'high': '#fed7d7', 'medium': '#feebc8', 'low': '#c6f6d5', 'ready': '#c6f6d5', 'pending': '#feebc8', 'not_ready': '#fed7d7',
                     'passed': '#c6f6d5', 'failed': '#fed7d7', 'not_applicable': '#e2e8f0'}

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DCRTitle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#1f4788'),
                                  alignment=TA_CENTER, fontName=MR_FONT_BOLD_NAME, spaceAfter=4)
    company_style = ParagraphStyle('DCRCompany', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#1f4788'),
                                    alignment=TA_CENTER, fontName=MR_FONT_BOLD_NAME)
    normal_style = ParagraphStyle('DCRNormal', parent=styles['Normal'], fontSize=9.5, alignment=TA_LEFT, fontName=MR_FONT_NAME, leading=13)
    small_style = ParagraphStyle('DCRSmall', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, fontName=MR_FONT_NAME)
    cell_style = ParagraphStyle('DCRCell', parent=styles['Normal'], fontSize=7.3, alignment=TA_CENTER, fontName=MR_FONT_NAME, leading=9.5)
    cell_left_style = ParagraphStyle('DCRCellLeft', parent=cell_style, alignment=TA_LEFT)
    header_cell_style = ParagraphStyle('DCRHeaderCell', parent=styles['Normal'], fontSize=7.3, alignment=TA_CENTER,
                                        fontName=MR_FONT_BOLD_NAME, textColor=colors.whitesmoke, leading=9)

    def header_row(labels, col_widths):
        """A table header row of RAW (un-shaped) bilingual labels, each wrapped to its own column width so a
        long "Arabic / English" label breaks onto two lines instead of overflowing into the next column."""
        return [rtl_paragraph(text, header_cell_style, w - 6) for text, w in zip(labels, col_widths)]

    def section_heading(text, section_key='summary'):
        style = ParagraphStyle(f'DCRHeading{section_key}', parent=styles['Heading2'], fontSize=10.5, textColor=colors.white,
                                backColor=colors.HexColor(SECTION_COLORS[section_key]), fontName=MR_FONT_BOLD_NAME, spaceBefore=10,
                                spaceAfter=6, alignment=TA_LEFT, borderPadding=(4, 6, 4, 6))
        return Paragraph(_t(text), style)

    def hdr_table(rows, col_widths, font_size=7.3, span_cmds=None, extra_cmds=None, zebra=True, pad=3):
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
        if span_cmds:
            cmds += span_cmds
        if extra_cmds:
            cmds += extra_cmds
        t.setStyle(TableStyle(cmds))
        return t

    label_cell_style = ParagraphStyle('DCRLabelCell', parent=normal_style, fontName=MR_FONT_BOLD_NAME, fontSize=9, leading=12)
    value_cell_style = ParagraphStyle('DCRValueCell', parent=normal_style, fontSize=9, leading=12)

    def label_value_table(rows, col_widths, extra_cmds=None):
        """rows: iterable of (label, value, label, value, ...) RAW (un-shaped) text -- shaping/wrapping happens here."""
        n_cols = len(rows[0])
        wrapped = []
        for row in rows:
            wrapped_row = []
            for i, text in enumerate(row):
                style = label_cell_style if i % 2 == 0 else value_cell_style
                wrapped_row.append(rtl_paragraph(text, style, col_widths[i] - 10) if text else Paragraph('', style))
            wrapped.append(wrapped_row)
        t = Table(wrapped, colWidths=col_widths)
        cmds = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]
        for c in range(0, n_cols, 2):
            cmds.append(('BACKGROUND', (c, 0), (c, -1), colors.HexColor('#e8f0f8')))
        if extra_cmds:
            cmds += extra_cmds
        t.setStyle(TableStyle(cmds))
        return t

    project = report.project

    # ---------------- Header ----------------
    logo_path = _owner_report_logo_path()
    if logo_path:
        logo = Image(logo_path, width=2.6 * inch, height=0.6 * inch, kind='proportional')
        logo.hAlign = 'CENTER'
        elements.append(logo)
    else:
        elements.append(Paragraph(_t('شركة ون ستوب للمقاولات | ONE STOP CONTRACTING & SERVICES'), company_style))
    elements.append(Paragraph(_t('التقرير اليومي للموقع | DAILY SITE REPORT'), title_style))
    elements.append(Spacer(1, 0.1 * inch))

    day_name = ARABIC_WEEKDAYS[report.report_date.weekday()]
    info_pairs = [
        ('رقم التقرير / Report No.', report.report_number),
        ('التاريخ / Date', f"{report.report_date.strftime('%Y-%m-%d')} — {day_name}"),
        ('الحالة / Status', report.get_status_display()),
        ('المشروع / Project', project.name),
        ('كود المشروع / Project Code', project.project_symbol or 'N/A'),
        ('العميل / Client', getattr(project, 'client_name', '') or 'N/A'),
        ('مهندس الموقع / Site Engineer', report.site_engineer.get_full_name() if report.site_engineer else 'N/A'),
        ('الطقس / Weather', report.get_weather_conditions_display() if report.weather_conditions else '—'),
    ]
    info_rows = [list(info_pairs[i]) + list(info_pairs[i + 1]) for i in range(0, len(info_pairs), 2)]
    elements.append(label_value_table(info_rows, [page_width * w for w in (0.14, 0.36, 0.14, 0.36)]))
    elements.append(Spacer(1, 0.12 * inch))

    # ---------------- Summary strip (KPI cards: icon badge + number + bilingual label) ----------------
    hours_attendance = list(report.worker_attendance.select_related('labor_classification__category').all())
    total_hours = sum((a.total_hours or Decimal('0')) for a in hours_attendance)
    staff_hours = sum((a.total_hours or Decimal('0')) for a in hours_attendance
                       if a.labor_classification and a.labor_classification.category and a.labor_classification.category.is_staff_category)
    worker_hours = total_hours - staff_hours
    open_issues = report.site_events.exclude(status='closed').count()
    kpi_number_style = ParagraphStyle('DCRKpiNumber', parent=styles['Normal'], fontSize=16,
                                       alignment=TA_CENTER, fontName=MR_FONT_BOLD_NAME, textColor=colors.HexColor('#1a202c'))
    kpi_split_number_style = ParagraphStyle('DCRKpiSplitNumber', parent=kpi_number_style, fontSize=13)
    kpi_label_style = ParagraphStyle('DCRKpiLabel', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER,
                                      fontName=MR_FONT_NAME, textColor=colors.HexColor('#6b7280'), leading=8.5)

    def kpi_label_html(label_ar, label_en):
        # Shape the Arabic half on its own, then join with an explicit <br/> -- shaping/bidi-reordering the
        # Arabic and Latin halves together as one string (as a bare "\n" would require) scrambles the break.
        return f"{_t(label_ar)}<br/>{label_en}"

    def kpi_card(icon_kind, color_hex, number_text, label_ar, label_en, width):
        icon = _kpi_icon(icon_kind, color_hex)
        icon.hAlign = 'CENTER'
        inner = Table([[icon], [Paragraph(number_text, kpi_number_style)],
                       [Paragraph(kpi_label_html(label_ar, label_en), kpi_label_style)]], colWidths=[width])
        inner.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (0, 0), 6), ('BOTTOMPADDING', (0, 0), (0, 0), 4),
            ('TOPPADDING', (0, 1), (0, 1), 0), ('BOTTOMPADDING', (0, 1), (0, 1), 3),
            ('TOPPADDING', (0, 2), (0, 2), 2), ('BOTTOMPADDING', (0, 2), (0, 2), 6),
        ]))
        return inner

    def kpi_split_card(icon_kind, color_hex, parts, width):
        """Same card shape as kpi_card, but the number row splits into 2+ side-by-side values (e.g. man-hours
        as staff vs. workers) instead of one combined total."""
        icon = _kpi_icon(icon_kind, color_hex)
        icon.hAlign = 'CENTER'
        half = width / len(parts)
        number_row = [Paragraph(value_text, kpi_split_number_style) for value_text, _ar, _en in parts]
        label_row = [Paragraph(kpi_label_html(ar, en), kpi_label_style) for _v, ar, en in parts]
        split_table = Table([number_row, label_row], colWidths=[half] * len(parts))
        split_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, 0), 3),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 0),
            ('LINEAFTER', (0, 0), (-2, -1), 0.5, colors.HexColor('#e2e8f0')),
        ]))
        inner = Table([[icon], [split_table]], colWidths=[width])
        inner.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (0, 0), 6), ('BOTTOMPADDING', (0, 0), (0, 0), 4),
            ('TOPPADDING', (0, 1), (0, 1), 0), ('BOTTOMPADDING', (0, 1), (0, 1), 6),
        ]))
        return inner

    card_width = page_width / 5
    cards = [
        kpi_card('workers', SECTION_COLORS['progress'], str(report.worker_attendance.count()), 'العمال', 'Workers', card_width - 6),
        kpi_split_card('hours', SECTION_COLORS['manpower'], [
            (_qty(staff_hours, '0'), 'موظفين', 'Staff'), (_qty(worker_hours, '0'), 'عمال', 'Workers'),
        ], card_width - 6),
        kpi_card('activities', SECTION_COLORS['plan'], str(report.activity_progress_entries.count()), 'الأنشطة', 'Activities', card_width - 6),
        kpi_card('equipment', SECTION_COLORS['equipment'], str(report.equipment.count()), 'المعدات', 'Equipment', card_width - 6),
        kpi_card('issues', '#b91c1c' if open_issues else SECTION_COLORS['visits'], str(open_issues), 'قضايا مفتوحة', 'Open Issues', card_width - 6),
    ]
    summary_table = Table([cards], colWidths=[card_width] * 5)
    summary_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#e2e8f0')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fafbfc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.1 * inch))

    # ---------------- 1. Daily Works / Progress ----------------
    elements.append(section_heading('1. الأعمال المنفذة خلال اليوم | DAILY WORKS / PROGRESS', 'progress'))
    entries = list(report.activity_progress_entries.select_related('sub_item').prefetch_related('crews').all())
    if entries:
        status_labels = {
            'not_started': 'لم يبدأ / Not Started', 'in_progress': 'جارٍ التنفيذ / In Progress',
            'completed': 'مكتمل / Completed', 'delayed': 'متأخر / Delayed', 'on_hold': 'معلق / On Hold',
        }
        col_widths = [page_width * w for w in (0.0426, 0.1489, 0.1064, 0.0851, 0.0851, 0.0532, 0.0638, 0.0638, 0.0745, 0.0638, 0.1064, 0.1064)]
        rows = [header_row(['#', 'النشاط / Activity', 'بند BOQ / BOQ Item', 'الطاقم / Crew', 'الموقع / Location',
                             'الوحدة / Unit', 'الكمية الكلية / Total', 'كمية اليوم / Today', 'التراكمي / Cumulative',
                             'الإنجاز / %', 'الحالة / Status', 'ملاحظات / Remarks'], col_widths)]
        status_cmds = []
        for i, e in enumerate(entries, start=1):
            crew_names = ', '.join(c.name for c in e.crews.all()) or '—'
            rows.append([
                str(i), rtl_paragraph(e.activity_description, cell_left_style, col_widths[1] - 8),
                rtl_paragraph(str(e.sub_item) if e.sub_item_id else '—', cell_style, col_widths[2] - 6),
                rtl_paragraph(crew_names, cell_style, col_widths[3] - 6),
                rtl_paragraph(e.location, cell_style, col_widths[4] - 8), _t(e.unit, '—'),
                _qty(e.total_quantity), _qty(e.quantity_today, '0'), _qty(e.quantity_cumulative, '0'),
                f'{e.completion_percentage:.1f}%',
                rtl_paragraph(status_labels.get(e.status, e.get_status_display()), cell_style, col_widths[10] - 6),
                rtl_paragraph(e.reference_notes, cell_style, col_widths[11] - 8),
            ])
            if e.status in PROGRESS_STATUS_COLORS:
                status_cmds.append(('BACKGROUND', (10, i), (10, i), colors.HexColor(PROGRESS_STATUS_COLORS[e.status])))
        elements.append(hdr_table(rows, col_widths, extra_cmds=status_cmds))
    else:
        elements.append(Paragraph(_t('لا يوجد أعمال مسجلة اليوم / No activity progress recorded'), normal_style))
    elements.append(Spacer(1, 0.12 * inch))

    # ---------------- 2. Manpower & Man-Hours (grouped by trade, with subtotals) ----------------
    elements.append(section_heading('2. العمالة وساعات العمل | MANPOWER & MAN-HOURS', 'manpower'))
    attendance = list(report.worker_attendance.select_related('labor_classification', 'crew').all())
    if attendance:
        groups = {}
        for a in attendance:
            key = a.labor_classification.name if a.labor_classification else None
            groups.setdefault(key, []).append(a)

        col_widths = [page_width * w for w in (0.0303, 0.1818, 0.1212, 0.1212, 0.1818, 0.0758, 0.0758, 0.0606, 0.0606, 0.0909)]
        rows = [header_row(['#', 'اسم العامل / Name', 'الطاقم / Crew', 'الجهة / Contractor', 'النشاط / الموقع / Activity-Location',
                             'دخول / In', 'خروج / Out', 'استراحة / Break', 'إضافي / OT', 'إجمالي الساعات / Total Hrs'], col_widths)]
        span_cmds, band_cmds = [], []
        row_idx = 1
        grand_workers, grand_hours = 0, Decimal('0')
        for key, members in groups.items():
            label = _t(key) if key else _t('غير مصنف / Unclassified')
            rows.append([f'{label} ({len(members)})', '', '', '', '', '', '', '', '', ''])
            span_cmds.append(('SPAN', (0, row_idx), (9, row_idx)))
            band_cmds += [('BACKGROUND', (0, row_idx), (9, row_idx), colors.HexColor('#ffe9a8')),
                          ('FONTNAME', (0, row_idx), (9, row_idx), MR_FONT_BOLD_NAME), ('ALIGN', (0, row_idx), (9, row_idx), 'LEFT')]
            row_idx += 1
            group_hours = Decimal('0')
            for i, a in enumerate(members, start=1):
                hrs = a.total_hours or Decimal('0')
                group_hours += hrs
                rows.append([
                    str(i), rtl_paragraph(a.worker_name, cell_left_style, col_widths[1] - 8),
                    _t(a.crew.name, '—') if a.crew_id else '—',
                    _t(a.contractor_name, '—'), rtl_paragraph(a.activity_location, cell_style, col_widths[4] - 8),
                    a.time_in.strftime('%H:%M') if a.time_in else '—', a.time_out.strftime('%H:%M') if a.time_out else '—',
                    _qty(a.break_hours, '0'), _qty(a.overtime_hours, '0'), _qty(hrs, '0'),
                ])
                row_idx += 1
            rows.append([f"{_t('إجمالي المجموعة / Subtotal')} — {len(members)} {_t('عامل / workers')}",
                         '', '', '', '', '', '', '', '', _qty(group_hours, '0')])
            span_cmds.append(('SPAN', (0, row_idx), (8, row_idx)))
            band_cmds += [('BACKGROUND', (0, row_idx), (9, row_idx), colors.HexColor('#eef1f8')),
                          ('FONTNAME', (0, row_idx), (9, row_idx), MR_FONT_BOLD_NAME)]
            row_idx += 1
            grand_workers += len(members)
            grand_hours += group_hours

        rows.append([f"{_t('إجمالي العمالة اليومية / DAILY TOTAL')} — {grand_workers} {_t('عامل / workers')}",
                     '', '', '', '', '', '', '', '', _qty(grand_hours, '0')])
        span_cmds.append(('SPAN', (0, row_idx), (8, row_idx)))
        band_cmds += [('BACKGROUND', (0, row_idx), (9, row_idx), colors.HexColor('#d4edda')),
                      ('FONTNAME', (0, row_idx), (9, row_idx), MR_FONT_BOLD_NAME)]

        elements.append(hdr_table(rows, col_widths, span_cmds=span_cmds, extra_cmds=band_cmds, zebra=False))
    else:
        elements.append(Paragraph(_t('لا يوجد حضور عمالة مسجل / No worker attendance recorded'), normal_style))

    # ---------------- Today's Labor Cost vs. Productivity (same estimate/grouping as the web page --
    # see reports/services/daily_labor_summary.py) ----------------
    from .services.daily_labor_summary import daily_labor_productivity_summary
    productivity_rows = daily_labor_productivity_summary(report)
    if productivity_rows:
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph(_t('تكلفة العمالة مقابل الإنتاجية اليوم / TODAY\'S LABOR COST VS. PRODUCTIVITY'),
                                   ParagraphStyle('DCRProdHeading', parent=normal_style, fontName=MR_FONT_BOLD_NAME, fontSize=9)))
        col_widths = [page_width * w for w in (0.14, 0.28, 0.13, 0.15, 0.15, 0.15)]
        rows = [header_row(['الطاقم / Crew', 'النشاط / Activity', 'الساعات / Man-Hours', 'التكلفة التقديرية / Est. Cost',
                             'كمية اليوم / Today\'s Qty', 'تكلفة الوحدة / Cost / Unit'], col_widths)]
        for row in productivity_rows:
            crew_label = row['crew'].name if row['crew'] else _t('بدون طاقم / No Crew')
            activity_label = row['activity'].activity_description if row['activity'] else '—'
            qty_label = f"{_qty(row['quantity_today'], '')} {row['unit']}".strip() if row['quantity_today'] else '—'
            cost_per_unit_label = f"${row['cost_per_unit']:.2f} / {row['unit']}" if row['cost_per_unit'] else '—'
            rows.append([
                rtl_paragraph(crew_label, cell_left_style, col_widths[0] - 6),
                rtl_paragraph(activity_label, cell_left_style, col_widths[1] - 8),
                _qty(row['hours'], '0'), f"${row['cost']:.2f}", qty_label, cost_per_unit_label,
            ])
        elements.append(hdr_table(rows, col_widths, font_size=7.5))
        elements.append(Paragraph(
            _t('تقدير تكلفة يومي (ليس رقم رواتب رسمي) / Same-day estimate, not a payroll figure.'),
            ParagraphStyle('DCRProdNote', parent=small_style, alignment=TA_LEFT, fontSize=6.5)))

    if report.work_hours_note:
        elements.append(Spacer(1, 0.06 * inch))
        note_style = ParagraphStyle('DCRWorkHoursNote', parent=normal_style, backColor=colors.HexColor('#fff8e1'),
                                     borderColor=colors.HexColor('#e0a800'), borderWidth=0.75, borderPadding=6)
        elements.append(rtl_paragraph(
            f"ملاحظة ساعات العمل (موظفين / عمال) — Work Hours Note (Staff / Workers): {report.work_hours_note}",
            note_style, page_width))
    elements.append(Spacer(1, 0.12 * inch))
    elements.append(PageBreak())

    # ---------------- 3A/3B. Materials & Plant ----------------
    if report.daily_materials.exists():
        elements.append(section_heading('3A. المواد الموردة | MATERIAL DELIVERIES', 'materials'))
        col_widths = [page_width * w for w in (0.06, 0.54, 0.20, 0.20)]
        rows = [header_row(['#', 'المادة / Material', 'الكمية / Quantity', 'الوحدة / Unit'], col_widths)]
        for i, m in enumerate(report.daily_materials.all(), start=1):
            rows.append([str(i), rtl_paragraph(m.material_description, cell_left_style, col_widths[1] - 8), _qty(m.quantity, '0'), _t(m.unit)])
        elements.append(hdr_table(rows, col_widths, font_size=8))
        elements.append(Spacer(1, 0.12 * inch))

    if report.equipment.exists():
        elements.append(section_heading('3B. المعدات والآليات | PLANT & EQUIPMENT', 'equipment'))
        col_widths = [page_width * w for w in (0.0435, 0.3478, 0.3478, 0.1304, 0.1304)]
        rows = [header_row(['#', 'المعدة / Equipment', 'استُخدمت في / Used For (Activity)',
                             'ساعات التشغيل / Hours Worked', 'عدد عاطل / Idle Qty.'], col_widths)]
        for i, eq in enumerate(report.equipment.select_related('activity').all(), start=1):
            rows.append([
                str(i), rtl_paragraph(eq.equipment_name, cell_left_style, col_widths[1] - 8),
                rtl_paragraph(eq.activity.activity_description if eq.activity_id else '—', cell_left_style, col_widths[2] - 8),
                str(eq.hours_worked), str(eq.quantity_idle),
            ])
        elements.append(hdr_table(rows, col_widths, font_size=8))
        elements.append(Spacer(1, 0.12 * inch))

    # ---------------- 4. QA/QC & HSE ----------------
    if hasattr(report, 'qaqc'):
        q = report.qaqc
        elements.append(section_heading('4. الجودة والسلامة | QA/QC & HSE CONTROL', 'qaqc'))
        yn = lambda v: 'نعم / Yes' if v else 'لا / No'
        rows = [
            ('حالة الفحص / Inspection', q.get_inspection_status_display(), 'Toolbox Talk / PTW', yn(q.toolbox_talk_conducted)),
            ('مرجع IR / MIR / Test', q.ir_mir_test_reference or '—', 'حادث / Incident', yn(q.incident_occurred)),
            ('PPE / نظافة الموقع', q.ppe_site_cleanliness_status or '—', 'شبه حادث / Near Miss', yn(q.near_miss_occurred)),
            ('مرجع NCR / HSE', q.ncr_hse_reference or '—', '', ''),
        ]
        qaqc_cmds = []
        if q.inspection_status in LEVEL_COLORS:
            qaqc_cmds.append(('BACKGROUND', (1, 0), (1, 0), colors.HexColor(LEVEL_COLORS[q.inspection_status])))
        if q.incident_occurred:
            qaqc_cmds.append(('BACKGROUND', (3, 1), (3, 1), colors.HexColor('#fed7d7')))
        if q.near_miss_occurred:
            qaqc_cmds.append(('BACKGROUND', (3, 2), (3, 2), colors.HexColor('#fed7d7')))
        elements.append(label_value_table(rows, [page_width * w for w in (0.14, 0.36, 0.14, 0.36)], extra_cmds=qaqc_cmds))
        if q.toolbox_talk_conducted and q.toolbox_talk_topic:
            elements.append(Paragraph(_t(f'Toolbox Talk: {q.toolbox_talk_topic}'), normal_style))
        if q.notes:
            elements.append(rtl_paragraph(q.notes, normal_style, page_width))
        elements.append(Spacer(1, 0.12 * inch))

    # ---------------- 5. Site Events / Instructions / Delays ----------------
    events = list(report.site_events.all())
    if events:
        elements.append(section_heading('5. الأحداث والتعليمات والتأخيرات | SITE EVENTS / INSTRUCTIONS / DELAYS', 'events'))
        col_widths = [page_width * w for w in (0.03, 0.10, 0.09, 0.24, 0.20, 0.12, 0.08, 0.08, 0.06)]
        rows = [header_row(['#', 'النوع / Type', 'المرجع / Ref.', 'الوصف / Description', 'الإجراء / Required Action',
                             'المسؤول / Responsible', 'تاريخ الإغلاق / Target', 'الحالة / Status', 'الأثر / Impact (h)'], col_widths)]
        status_cmds = []
        for i, ev in enumerate(events, start=1):
            rows.append([
                str(i), rtl_paragraph(ev.get_event_type_display(), cell_style, col_widths[1] - 6), _t(ev.reference, '—'),
                rtl_paragraph(ev.description, cell_left_style, col_widths[3] - 8),
                rtl_paragraph(ev.required_action, cell_style, col_widths[4] - 8),
                rtl_paragraph(ev.responsible_party or (ev.responsible_user.get_full_name() if ev.responsible_user else '') or '—', cell_style, col_widths[5] - 6),
                ev.target_date.strftime('%Y-%m-%d') if ev.target_date else '—', _t(ev.get_status_display()),
                _qty(ev.time_impact_hours, '—'),
            ])
            if ev.status in EVENT_STATUS_COLORS:
                status_cmds.append(('BACKGROUND', (7, i), (7, i), colors.HexColor(EVENT_STATUS_COLORS[ev.status])))
        elements.append(hdr_table(rows, col_widths, extra_cmds=status_cmds))
        elements.append(Spacer(1, 0.12 * inch))

    # ---------------- 6. Next Day Plan / Readiness ----------------
    plan = list(report.next_day_plan.all())
    if plan:
        elements.append(section_heading('6. خطة اليوم التالي | NEXT DAY PLAN / READINESS', 'plan'))
        col_widths = [page_width * w for w in (0.03, 0.20, 0.10, 0.10, 0.16, 0.11, 0.10, 0.10, 0.10)]
        rows = [header_row(['#', 'النشاط المخطط / Planned Activity', 'الموقع / Location', 'القوى العاملة / Manpower',
                             'الموارد المطلوبة / Resources', 'المسؤول / Responsible', 'الأولوية / Priority',
                             'الجاهزية / Readiness', 'ملاحظات / Remarks'], col_widths)]
        level_cmds = []
        for i, p in enumerate(plan, start=1):
            rows.append([
                str(i), rtl_paragraph(p.planned_activity, cell_left_style, col_widths[1] - 8),
                rtl_paragraph(p.location, cell_style, col_widths[2] - 8), str(p.manpower_required) if p.manpower_required else '—',
                rtl_paragraph(p.resources_required, cell_style, col_widths[4] - 8),
                rtl_paragraph(p.responsible_party or '—', cell_style, col_widths[5] - 6),
                _t(p.get_priority_display(), '—'), _t(p.get_readiness_display(), '—'),
                rtl_paragraph(p.remarks, cell_style, col_widths[8] - 8),
            ])
            if p.priority in LEVEL_COLORS:
                level_cmds.append(('BACKGROUND', (6, i), (6, i), colors.HexColor(LEVEL_COLORS[p.priority])))
            if p.readiness in LEVEL_COLORS:
                level_cmds.append(('BACKGROUND', (7, i), (7, i), colors.HexColor(LEVEL_COLORS[p.readiness])))
        elements.append(hdr_table(rows, col_widths, extra_cmds=level_cmds))
    else:
        elements.append(section_heading('6. خطة اليوم التالي | NEXT DAY PLAN / READINESS', 'plan'))
        elements.append(Paragraph(_t('لا يوجد خطة لليوم التالي / No next-day plan recorded'), normal_style))
    elements.append(Spacer(1, 0.12 * inch))

    # ---------------- Visitors ----------------
    if report.visitors.exists():
        elements.append(section_heading('زيارات الموقع | SITE VISITS', 'visits'))
        col_widths = [page_width * w for w in (0.12, 0.34, 0.54)]
        rows = [header_row(['الوقت / Time', 'الاسم / Name', 'الجهة / Representing'], col_widths)]
        for v in report.visitors.all():
            rows.append([v.visit_time.strftime('%H:%M'), _t(v.visitor_name), _t(v.representing, '—')])
        elements.append(hdr_table(rows, col_widths, font_size=8.5))
        elements.append(Spacer(1, 0.12 * inch))

    # ---------------- 7. Daily Summary & Sign-off ----------------
    elements.append(section_heading('7. ملخص اليوم واعتماد التقرير | DAILY SUMMARY & SIGN-OFF', 'summary'))
    if report.remarks:
        elements.append(rtl_paragraph(report.remarks, normal_style, page_width))
    else:
        elements.append(Paragraph(_t('—'), normal_style))
    if report.status == 'rejected' and report.rejection_reason:
        elements.append(Spacer(1, 0.08 * inch))
        rejection_style = ParagraphStyle('DCRRejection', parent=normal_style, textColor=colors.HexColor('#b02a37'))
        elements.append(rtl_paragraph(f"{_t('سبب الرفض / Rejection reason')}: {report.rejection_reason}", rejection_style, page_width))
    elements.append(Spacer(1, 0.2 * inch))

    sign_col_widths = [page_width / 3] * 3
    sign_rows = [
        header_row(['أعدّه / Prepared by — Site Engineer', 'راجعه / Reviewed by — Engineering Manager',
                    'اعتماد / Approved by — General Manager'], sign_col_widths),
        [
            _t(report.site_engineer.get_full_name(), '—') if report.site_engineer else '—',
            _t(report.reviewed_by.get_full_name(), '—') if report.reviewed_by else '—',
            _t(report.approved_by.get_full_name(), '—') if report.approved_by else '—',
        ], [
            report.created_at.strftime('%Y-%m-%d'),
            report.review_date.strftime('%Y-%m-%d') if report.review_date else '—',
            report.approval_date.strftime('%Y-%m-%d') if report.approval_date else '—',
        ],
    ]
    sign_table = Table(sign_rows, colWidths=sign_col_widths, rowHeights=[28, 30, 20])
    sign_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
        ('FONTNAME', (0, 1), (-1, -1), MR_FONT_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(sign_table)

    footer_text = f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Form: OS-FRM-SITE-DR-02"
    elements.append(Spacer(1, 0.12 * inch))
    elements.append(Paragraph(footer_text, small_style))

    # ---------------- Annex -- Site Photo Log (matching the real form's separate "SITE PHOTO LOG" sheet: a
    # numbered photo grid with each shot captioned by description / location, at the very end of the report) ----------------
    from .models import ReportAttachment
    all_attachments = list(ReportAttachment.objects.filter(report_type='daily', report_id=report.id).order_by('order', 'created_at'))
    # Documents (Word/PDF/etc. -- not a displayable image) get their own annex below the photo log
    # instead of a gray placeholder box inside the photo grid standing in for a picture that isn't
    # one; photos/videos/other (no dedicated annex of their own) keep the previous placeholder-box
    # behavior in the photo grid so they still print somewhere rather than being dropped.
    photo_attachments = [a for a in all_attachments if a.attachment_type != 'document']
    document_attachments = [a for a in all_attachments if a.attachment_type == 'document']
    if photo_attachments:
        elements.append(PageBreak())
        elements.append(section_heading('ملحق — سجل صور الموقع | ANNEX — SITE PHOTO LOG', 'summary'))
        caption_style = ParagraphStyle('DCRPhotoCaption', parent=cell_style, fontSize=8, leading=10)
        box_w = page_width / 2 - 0.08 * inch
        box_h = 2.5 * inch
        items = []
        for n, att in enumerate(photo_attachments, start=1):
            label = f"PHOTO {n:02d}"
            try:
                if att.attachment_type != 'photo' or not att.file or not os.path.exists(att.file.path):
                    raise ValueError('not a displayable image')
                cell = Image(att.file.path, width=box_w, height=box_h, kind='proportional')
            except Exception:
                cell = Table([['']], colWidths=[box_w], rowHeights=[box_h])
                cell.setStyle(TableStyle([
                    ('BOX', (0, 0), (-1, -1), 0.75, colors.grey), ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f4f6fb')),
                ]))
            caption_bits = [label]
            if att.description:
                caption_bits.append(att.description)
            if att.location:
                caption_bits.append(f"({att.location})")
            if att.attachment_type != 'photo':
                caption_bits.append(f"[{att.get_attachment_type_display()}]")
            items.append([cell, Spacer(1, 0.04 * inch), rtl_paragraph(' — '.join(caption_bits), caption_style, box_w)])
        for j in range(0, len(items), 2):
            row = items[j:j + 2]
            col_w = page_width if len(row) == 1 else page_width / 2
            photo_table = Table([row], colWidths=[col_w] * len(row))
            photo_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ]))
            elements.append(photo_table)

    # ---------------- Annex -- Supporting Documents (non-photo attachments: Word/PDF/etc., listed by
    # name/description/location rather than embedded as images) -- printed after the photo log ----------------
    if document_attachments:
        elements.append(PageBreak())
        elements.append(section_heading('ملحق — المستندات المرفقة | ANNEX — SUPPORTING DOCUMENTS', 'summary'))
        doc_col_widths = [page_width * 0.08, page_width * 0.42, page_width * 0.25, page_width * 0.25]
        doc_rows = [header_row(['#', 'Document / الوصف', 'Location / الموقع', 'Date / التاريخ'], doc_col_widths)]
        for n, att in enumerate(document_attachments, start=1):
            description = att.description or (os.path.basename(att.file.name) if att.file else '—')
            doc_rows.append([
                Paragraph(str(n), cell_style),
                rtl_paragraph(description, cell_left_style, doc_col_widths[1] - 6),
                rtl_paragraph(att.location or '—', cell_style, doc_col_widths[2] - 6),
                Paragraph(_t(att.created_at.strftime('%Y-%m-%d')), cell_style),
            ])
        elements.append(hdr_table(doc_rows, doc_col_widths))

    doc.build(elements)
    buffer.seek(0)
    pdf_bytes = buffer.getvalue()

    # The Supporting Documents annex above only lists each document (description/location/date) --
    # an uploaded PDF's own pages are appended in full straight after it, so the printed report
    # actually carries the document, not just a reference to it. A divider page (reusing this same
    # report's fonts/RTL shaping) names which document follows, since several may be attached.
    # Non-PDF uploads (Word, images, ...) can't be merged in as pages this way and stay listed
    # only in the table above; a PDF that fails to open (corrupted upload) is skipped the same way.
    pdf_documents = [
        a for a in document_attachments
        if a.file and a.file.name.lower().endswith('.pdf')
    ]
    if pdf_documents:
        import fitz

        def _divider_page_pdf(label_text):
            div_buffer = BytesIO()
            div_doc = SimpleDocTemplate(
                div_buffer, pagesize=A4,
                topMargin=1 * inch, bottomMargin=1 * inch, leftMargin=1 * inch, rightMargin=1 * inch,
            )
            div_style = ParagraphStyle(
                'DCRDocDivider', parent=styles['Heading2'], fontSize=14, alignment=TA_CENTER,
                fontName=MR_FONT_BOLD_NAME, textColor=colors.HexColor('#1f4788'),
            )
            div_doc.build([Spacer(1, 3.2 * inch), rtl_paragraph(label_text, div_style, page_width)])
            div_buffer.seek(0)
            return div_buffer.getvalue()

        try:
            merged = fitz.open(stream=pdf_bytes, filetype='pdf')
            for att in pdf_documents:
                if not os.path.exists(att.file.path):
                    continue
                try:
                    label = att.description or os.path.basename(att.file.name)
                    divider_bytes = _divider_page_pdf(f'المستند المرفق | Attached Document: {label}')
                    with fitz.open(stream=divider_bytes, filetype='pdf') as divider:
                        merged.insert_pdf(divider)
                    with fitz.open(att.file.path) as extra:
                        merged.insert_pdf(extra)
                except Exception:
                    continue
            pdf_bytes = merged.tobytes()
            merged.close()
        except Exception:
            pass  # fall back to the report without merged pages rather than fail the whole export

    return pdf_bytes


def _owner_report_logo_path():
    """Path to the One Stop company logo used in the owner financial PDF header."""
    from django.conf import settings
    path = os.path.join(settings.BASE_DIR, 'static', 'images', 'one_stop_logo.png')
    return path if os.path.exists(path) else None


def generate_owner_financial_report_pdf(report):
    """
    Generate the "التقرير الفني والمالي الشهري" PDF for an OwnerFinancialReport,
    matching the real template used with project owners: company letterhead,
    executive indicators, next-month outlook, phase-by-phase progress
    narrative, the full BOQ schedule-of-values table (the "الجدول الزمني
    المنجز"), the payment-due calculation, material/equipment price
    comparison, a closing note, and a phase-organized photo gallery with
    captions.
    """
    buffer = BytesIO()
    page_size = A4
    doc = SimpleDocTemplate(
        buffer, pagesize=page_size,
        topMargin=0.8 * inch, bottomMargin=0.85 * inch,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch,
        title='التقرير الفني والمالي الشهري',
    )
    page_width = page_size[0] - 1.6 * inch
    GRID_C = colors.HexColor('#BFBFBF')
    BAND_C = colors.HexColor('#F3F6FB')
    TOTAL_C = colors.HexColor('#D9E2F3')
    NAVY_C = colors.HexColor('#1F3864')

    def _footer(canvas, document):
        canvas.saveState()
        canvas.setFont(MR_FONT_NAME, 8)
        canvas.setFillColor(colors.HexColor('#595959'))
        canvas.drawCentredString(page_size[0] / 2, 0.42 * inch, str(document.page))
        canvas.drawString(0.8 * inch, 0.42 * inch, report.reporting_period_to.strftime('%d/%m/%Y'))
        canvas.drawRightString(page_size[0] - 0.8 * inch, 0.42 * inch, 'One Stop ERP')
        canvas.setStrokeColor(GRID_C)
        canvas.line(0.8 * inch, 0.58 * inch, page_size[0] - 0.8 * inch, 0.58 * inch)
        canvas.restoreState()

    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'OFRTitle', parent=styles['Heading1'], fontSize=15,
        textColor=colors.HexColor('#1F3864'), alignment=TA_CENTER,
        fontName=MR_FONT_BOLD_NAME, spaceAfter=4,
    )
    company_style = ParagraphStyle(
        'OFRCompany', parent=styles['Normal'], fontSize=12,
        textColor=colors.HexColor('#1F3864'), alignment=TA_RIGHT,
        fontName=MR_FONT_BOLD_NAME,
    )
    heading_style = ParagraphStyle(
        'OFRHeading', parent=styles['Heading2'], fontSize=13,
        textColor=colors.white, backColor=colors.HexColor('#1F3864'),
        fontName=MR_FONT_BOLD_NAME, spaceBefore=12, spaceAfter=8,
        alignment=TA_RIGHT, borderPadding=(5, 8, 5, 8), leading=16,
    )
    normal_style = ParagraphStyle(
        'OFRNormal', parent=styles['Normal'], fontSize=10.5,
        alignment=TA_RIGHT, fontName=MR_FONT_NAME, leading=15.5,
    )
    small_style = ParagraphStyle(
        'OFRSmall', parent=styles['Normal'], fontSize=9,
        alignment=TA_RIGHT, fontName=MR_FONT_NAME, leading=12,
    )
    cell_style = ParagraphStyle(
        'OFRCell', parent=styles['Normal'], fontSize=9,
        alignment=TA_CENTER, fontName=MR_FONT_NAME, leading=11.5,
    )
    cell_text_style = ParagraphStyle(
        'OFRCellText', parent=cell_style, alignment=TA_RIGHT, fontSize=9.5, leading=11.8,
    )
    schedule_cell_style = ParagraphStyle(
        'OFRScheduleCell', parent=styles['Normal'], fontSize=7.8,
        alignment=TA_CENTER, fontName=MR_FONT_NAME, leading=9.6,
    )
    caption_style = ParagraphStyle(
        'OFRCaption', parent=styles['Normal'], fontSize=9,
        alignment=TA_CENTER, fontName=MR_FONT_NAME, leading=12,
    )

    def hdr_table(rows, col_widths, header_bg='#1F3864', font_size=10):
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_bg)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), MR_FONT_BOLD_NAME),
            ('FONTNAME', (0, 1), (-1, -1), MR_FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), font_size),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BAND_C]),
        ]))
        return t

    # ---------------- COVER PAGE ----------------
    project = report.project
    period_label = report.reporting_period_to.strftime('%m/%Y')
    project_desc = project.description or project.name
    project_line = project_desc + (f' — {project.location}' if project.location else '')

    logo_path = _owner_report_logo_path()
    elements.append(Spacer(1, 0.7 * inch))
    if logo_path:
        cover_logo = Image(logo_path, width=4.2 * inch, height=1.0 * inch, kind='proportional')
        cover_logo.hAlign = 'CENTER'
        elements.append(cover_logo)
    else:
        elements.append(Paragraph(_t('شركة ون ستوب للمقاولات'), company_style))
    elements.append(Spacer(1, 0.15 * inch))
    # yellow accent rule, echoing the logo's colours
    rule = Table([['']], colWidths=[page_width], rowHeights=[3])
    rule.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f2c811'))]))
    elements.append(rule)
    elements.append(Spacer(1, 0.7 * inch))

    cover_title_style = ParagraphStyle(
        'OFRCoverTitle', parent=styles['Heading1'], fontSize=20,
        textColor=colors.HexColor('#1F3864'), alignment=TA_CENTER,
        fontName=MR_FONT_BOLD_NAME, spaceAfter=10,
    )
    cover_sub_style = ParagraphStyle(
        'OFRCoverSub', parent=styles['Normal'], fontSize=13,
        textColor=colors.HexColor('#333333'), alignment=TA_CENTER,
        fontName=MR_FONT_NAME, spaceAfter=4,
    )
    elements.append(Paragraph(_t('التقرير الفني والمالي الشهري'), cover_title_style))
    elements.append(Paragraph(_t(f'شهر {period_label}'), cover_sub_style))
    elements.append(Spacer(1, 0.6 * inch))

    manager_name = ''
    if report.site_engineer:
        manager_name = report.site_engineer.get_full_name() or report.site_engineer.username

    cover_rows = [
        [_t(project.name), _t('اسم المشروع')],
        [_t(project_line), _t('وصف المشروع')],
        [_t(project.project_symbol), _t('رمز المشروع')],
        [_t(project.contract_number), _t('رقم العقد')],
        [_t(project.client_name), _t('المالك / الجهة المستفيدة')],
        [_t(f'{report.contract_value_snapshot:,.0f} شيكل'), _t('قيمة العقد')],
        [_t(f"{report.reporting_period_from.strftime('%d/%m/%Y')} — {report.reporting_period_to.strftime('%d/%m/%Y')}"), _t('فترة التقرير')],
        [_t(manager_name, '—'), _t('مدير المشروع')],
        [_t(report.report_number), _t('رقم التقرير')],
        [report.reporting_period_to.strftime('%d/%m/%Y'), _t('تاريخ التقرير')],
    ]
    cover_table = Table(cover_rows, colWidths=[page_width * 0.62, page_width * 0.38])
    cover_table.setStyle(TableStyle([
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#D9E2F3')),
        ('FONTNAME', (0, 0), (0, -1), MR_FONT_NAME),
        ('FONTNAME', (1, 0), (1, -1), MR_FONT_BOLD_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(cover_table)
    elements.append(PageBreak())

    # ---------------- Executive Indicators ----------------
    progress = report._progress_result()
    overall_pct = progress['overall_percentage']

    duration_label = '—'
    if project.start_date and project.end_date:
        delta = relativedelta(project.end_date, project.start_date)
        months = delta.years * 12 + delta.months
        duration_label = _t(f'{months} شهرا')

    indicators = [
        [_t('القيمة'), _t('المؤشر')],
        [_t(f"{report.contract_value_snapshot:,.0f} شيكل"), _t('قيمة العقد الإبتدائية')],
        [_t(f"{report.amount_due():,.2f} شيكل"), _t('المبلغ المستحق للدفع حاليا')],
        [_t(f"{report.advance_payment_value_snapshot:,.0f} شيكل"), _t('قيمة الدفعة المقدمة')],
        [_t(f"{report.previous_payments_total:,.0f} شيكل"), _t('دفعات سابقة')],
        [f"{report.next_month_expected_completion_pct}%" if report.next_month_expected_completion_pct is not None else '—',
         _t('نسبة الإنجاز المتوقعة للشهر القادم')],
        [f"{overall_pct:.3f}%", _t('نسبة الإنجاز الحالية')],
        [project.start_date.strftime('%m.%Y') if project.start_date else '—', _t('تاريخ بدأ المشروع')],
        [duration_label, _t('مدة المشروع')],
    ]
    elements.append(Paragraph(_t('المؤشرات التنفيذية :-'), heading_style))
    ind_table = Table(indicators, colWidths=[page_width * 0.35, page_width * 0.65])
    ind_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY_C),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), MR_FONT_BOLD_NAME),
        ('FONTNAME', (0, 1), (-1, -1), MR_FONT_NAME),
        ('FONTNAME', (1, 1), (1, -1), MR_FONT_BOLD_NAME),
        ('BACKGROUND', (1, 1), (1, -1), BAND_C),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('TEXTCOLOR', (0, 2), (0, 2), colors.HexColor('#c00000')),
        ('TEXTCOLOR', (0, 4), (0, 5), colors.HexColor('#c00000')),
    ]))
    elements.append(ind_table)
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- Next Month Expected Works ----------------
    if report.next_month_expected_works:
        next_month_date = (report.reporting_period_to + relativedelta(months=1)).strftime('%d/%m/%Y')
        elements.append(Paragraph(_t('الأعمال المتوقعة للشهر القادم:-'), heading_style))
        elements.append(Paragraph(
            _t(f'(متوقع) — أبرز الأعمال المتوقعة حتى {next_month_date}'), small_style
        ))
        elements.append(rtl_paragraph(report.next_month_expected_works, normal_style, page_width, justify=True))
        elements.append(Spacer(1, 0.15 * inch))

    # ---------------- Progress Summary (phase narrative) ----------------
    elements.append(Paragraph(_t('ملخص سير المشروع :-'), heading_style))
    if report.progress_summary:
        elements.append(rtl_paragraph(report.progress_summary, normal_style, page_width, justify=True))
        elements.append(Spacer(1, 0.08 * inch))

    phase_updates = list(report.phase_updates.select_related('phase').all())
    if phase_updates:
        status_colors = {
            'done': colors.HexColor('#d9ead3'),
            'in_progress': colors.HexColor('#fff2cc'),
            'pending': colors.HexColor('#F3F6FB'),
        }
        rows = [[_t('الأعمال المنفذة'), _t('الحالة'), _t('المرحلة')]]
        status_cmds = []
        for i, u in enumerate(phase_updates, start=1):
            phase_label = f"{u.phase.code}. {u.phase.name_ar}" if u.phase.code else u.phase.name_ar
            rows.append([
                rtl_paragraph(u.work_performed, cell_text_style, page_width * 0.55 - 14, justify=True),
                _t(u.get_status_display()),
                rtl_paragraph(phase_label, cell_text_style, page_width * 0.30 - 14),
            ])
            status_cmds.append(('BACKGROUND', (1, i), (1, i), status_colors.get(u.status, colors.white)))
        summary_table = Table(rows, colWidths=[page_width * 0.55, page_width * 0.15, page_width * 0.30], repeatRows=1)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3864')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), MR_FONT_BOLD_NAME),
            ('FONTNAME', (0, 1), (-1, -1), MR_FONT_NAME),
            ('FONTNAME', (1, 1), (1, -1), MR_FONT_BOLD_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (0, -1), [colors.white, BAND_C]),
        ] + status_cmds))
        elements.append(summary_table)
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- Full BOQ Schedule Table ("الجدول الزمني المنجز") ----------------
    elements.append(PageBreak())
    elements.append(Paragraph(_t('نسبة الإنجاز الحالية :'), heading_style))
    elements.append(rtl_paragraph(
        f"يشير الجدول التالي إلى نسب الإنجاز حتى تاريخ {report.reporting_period_to.strftime('%d/%m/%Y')} استنادا إلى النسب الواردة في العقد:",
        normal_style, page_width, justify=True,
    ))
    elements.append(Spacer(1, 0.08 * inch))

    col_widths = [page_width * w for w in (0.04, 0.17, 0.07, 0.17, 0.07, 0.10, 0.10, 0.08, 0.20)]
    schedule_rows = [[
        _t('البند'), _t('البند الرئيسي'), _t('%القيمة'), _t('تجزئة البند'), _t('%تجزئة'),
        _t('من'), _t('إلى'), _t('%التنفيذ'), _t('القيمة'),
    ]]
    span_cmds = []
    row_idx = 1
    total_earned_value = Decimal('0')
    for phase_row in progress['phases']:
        phase = phase_row['phase']
        sub_items = phase.sub_items.all()
        n = len(sub_items) or 1
        start_row = row_idx
        if phase_row['earned_value'] is not None:
            total_earned_value += phase_row['earned_value']
        if sub_items:
            for i, sub_item in enumerate(sub_items):
                sub_result = next((s for s in phase_row['sub_items'] if s['sub_item'].id == sub_item.id), None)
                exec_pct = sub_result['execution_percentage'] if sub_result else Decimal('0')
                sub_value = (sub_item.weight_percentage / Decimal('100')) * (exec_pct / Decimal('100')) * report.contract_value_snapshot
                schedule_rows.append([
                    _t(phase.code) if i == 0 else '',
                    rtl_paragraph(phase.name_ar, schedule_cell_style, col_widths[1] - 8) if i == 0 else '',
                    f'{phase.weight_percentage}%' if i == 0 else '',
                    rtl_paragraph(sub_item.name_ar, schedule_cell_style, col_widths[3] - 8),
                    f'{sub_item.weight_percentage}%',
                    sub_item.planned_start_date.strftime('%d/%m/%y') if sub_item.planned_start_date else '—',
                    sub_item.planned_completion_date.strftime('%d/%m/%y') if sub_item.planned_completion_date else '—',
                    f'{exec_pct:.1f}%',
                    f'{sub_value:,.0f}' if sub_value else '',
                ])
                row_idx += 1
        else:
            schedule_rows.append([
                _t(phase.code), rtl_paragraph(phase.name_ar, schedule_cell_style, col_widths[1] - 8), f'{phase.weight_percentage}%',
                '—', '—', '—', '—', f"{phase_row['execution_percentage']:.1f}%",
                f"{phase_row['earned_value']:,.0f}" if phase_row['earned_value'] else '',
            ])
            row_idx += 1
        end_row = row_idx - 1
        if end_row > start_row:
            span_cmds += [
                ('SPAN', (0, start_row), (0, end_row)),
                ('SPAN', (1, start_row), (1, end_row)),
                ('SPAN', (2, start_row), (2, end_row)),
            ]

    # Totals row
    schedule_rows.append([
        '', _t('المجموع الكلي'), '100%', '', '', '', '', f'{overall_pct:.2f}%', f'{total_earned_value:,.0f}',
    ])
    total_row_idx = row_idx
    span_cmds.append(('SPAN', (0, total_row_idx), (1, total_row_idx)))

    schedule_table = Table(schedule_rows, colWidths=col_widths, repeatRows=1)
    schedule_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3864')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), MR_FONT_BOLD_NAME),
        ('FONTNAME', (0, 1), (-1, -1), MR_FONT_NAME),
        ('FONTNAME', (0, total_row_idx), (-1, total_row_idx), MR_FONT_BOLD_NAME),
        ('BACKGROUND', (0, total_row_idx), (-1, total_row_idx), colors.HexColor('#D9E2F3')),
        ('FONTSIZE', (0, 0), (-1, -1), 7.8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.6),
        ('TOPPADDING', (0, 0), (-1, -1), 2.6),
        ('LINEABOVE', (0, total_row_idx), (-1, total_row_idx), 1.2, NAVY_C),
        ('LINEBELOW', (0, total_row_idx), (-1, total_row_idx), 1.6, NAVY_C),
        ('ROWBACKGROUNDS', (0, 1), (-1, total_row_idx - 1), [colors.white, BAND_C]),
    ] + span_cmds))
    elements.append(schedule_table)
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- Payment Calculation Summary ----------------
    payment_rows = [
        [_t('قيمة الأعمال المنجزة في الموقع حسب نسب الإنجاز'), f'{report.earned_value_to_date():,.2f}'],
        [_t('قيمة العقد'), f'{report.contract_value_snapshot:,.2f}'],
        [_t('قيمة الدفعة المقدمة'), f'{report.advance_payment_value_snapshot:,.2f}'],
        [_t('دفعات سابقة'), f'{report.previous_payments_total:,.2f}'],
        [_t(f'استقطاع قيمة الدفعة المقدمة ({report.advance_retention_rate()}%)'), f'{report.advance_retention_amount():,.2f}'],
        [_t(f'استقطاع حسن التنفيذ ({report.performance_retention_rate_snapshot}%)'), f'{report.performance_retention_amount():,.2f}'],
    ]
    payment_table = Table(payment_rows, colWidths=[page_width * 0.75, page_width * 0.25])
    payment_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), MR_FONT_NAME),
        ('FONTNAME', (1, 0), (1, -1), MR_FONT_BOLD_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, BAND_C]),
        ('RIGHTPADDING', (0, 0), (0, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(payment_table)
    elements.append(Spacer(1, 0.08 * inch))

    formula_style = ParagraphStyle(
        'OFRFormula', parent=styles['Normal'], fontSize=11,
        alignment=TA_RIGHT, fontName=MR_FONT_BOLD_NAME, leading=14,
    )
    formula_row = Table([
        [rtl_paragraph('قيمة الدفعة المطلوبة = (قيمة الأعمال المنجزة − نسبة الدفعة المقدمة − حسن التنفيذ − الدفعات السابقة)', formula_style, page_width * 0.75 - 12),
         _t(f'{report.amount_due():,.2f} شيكل')],
    ], colWidths=[page_width * 0.75, page_width * 0.25])
    formula_row.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), MR_FONT_BOLD_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFF6DD')),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, NAVY_C),
        ('LINEBELOW', (0, 0), (-1, 0), 1.6, NAVY_C),
        ('GRID', (0, 0), (-1, -1), 0.4, GRID_C),
        ('RIGHTPADDING', (0, 0), (0, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(formula_row)
    elements.append(Spacer(1, 0.2 * inch))

    # ---------------- Material / Equipment Price Comparison ----------------
    price_items = list(report.price_comparison_items.all())
    if price_items or report.material_price_note:
        elements.append(PageBreak())
        elements.append(Paragraph(_t('الوضع الراهن لأسعار المواد'), heading_style))
        if report.material_price_note:
            elements.append(rtl_paragraph(report.material_price_note, normal_style, page_width, justify=True))
            elements.append(Spacer(1, 0.1 * inch))

        if price_items:
            price_rows = [[_t('فرق السعر'), _t('السعر الجديد'), _t('السعر القديم'), _t('الكمية'), _t('الوحدة'), _t('الصنف'), _t('النوع')]]
            total_diff = Decimal('0')
            # Arabic labels for the PDF, independent of the (English) admin/UI choice labels.
            type_labels = {'concrete_grade': 'باطون', 'equipment': 'معدات', 'material': 'مواد'}
            for item in price_items:
                total_diff += item.price_difference
                price_rows.append([
                    f'{item.price_difference:,.2f}', f'{item.new_unit_price:,.2f}', f'{item.old_unit_price:,.2f}',
                    f'{item.quantity:g}', _t(item.unit), _t(item.item_name), _t(type_labels.get(item.item_type, item.item_type)),
                ])
            price_rows.append(['', '', '', '', '', '', _t('المجموع')])
            price_rows[-1][0] = f'{total_diff:,.2f}'
            price_table = hdr_table(price_rows, [page_width * w for w in (0.13, 0.13, 0.13, 0.10, 0.12, 0.24, 0.15)])
            price_table.setStyle(TableStyle([
                ('BACKGROUND', (0, len(price_rows) - 1), (-1, len(price_rows) - 1), TOTAL_C),
                ('FONTNAME', (0, len(price_rows) - 1), (-1, len(price_rows) - 1), MR_FONT_BOLD_NAME),
                ('LINEABOVE', (0, len(price_rows) - 1), (-1, len(price_rows) - 1), 1.2, NAVY_C),
                ('LINEBELOW', (0, len(price_rows) - 1), (-1, len(price_rows) - 1), 1.6, NAVY_C),
            ]))
            elements.append(price_table)
            elements.append(Spacer(1, 0.1 * inch))

            within = report.price_comparison_items.model.is_within_contract_threshold(
                project, report.reporting_period_from, report.reporting_period_to, report.contract_value_snapshot,
            )
            threshold_note = (
                'هذا الفرق لن ينعكس على مبلغ المطالبة المالية حسب العقد لأنه لم يتجاوز نسبة 1.5% من القيمة الإجمالية للعقد.'
                if within else
                'تنبيه: هذا الفرق تجاوز نسبة 1.5% من القيمة الإجمالية للعقد، ويستوجب مطالبة مالية منفصلة حسب العقد.'
            )
            elements.append(rtl_paragraph(threshold_note, small_style, page_width, justify=True))
        elements.append(Spacer(1, 0.15 * inch))

    # ---------------- Closing Note ----------------
    if report.closing_note:
        elements.append(Paragraph(_t('ملاحظة تنظيمية متعلقة بالتدفق المالي للمشروع'), heading_style))
        for para in report.closing_note.split('\n'):
            if para.strip():
                elements.append(rtl_paragraph(para.strip(), normal_style, page_width, justify=True))
                elements.append(Spacer(1, 0.05 * inch))

    # ---------------- Photo Gallery (grouped by phase, with captions) ----------------
    # Fixed-size boxes per orientation: landscape photos get one full-width
    # slot per row (2 fit on a portrait A4 page), portrait photos get a
    # 2-column grid (4 fit on a page). Every photo is fit into its box with
    # kind='proportional' (never stretched), so the box itself -- not the
    # source image -- is what stays a consistent, fixed size on the page.
    LANDSCAPE_BOX = (page_width, 3.5 * inch)
    PORTRAIT_BOX = (page_width / 2 - 0.1 * inch, 3.5 * inch)

    def _photo_orientation(path):
        try:
            with PILImage.open(path) as im:
                w, h = im.size
            return 'landscape' if w >= h else 'portrait'
        except Exception:
            return 'landscape'

    photos = list(report.phase_photos.select_related('phase').order_by('phase__order', 'order', '-taken_date'))
    if photos:
        elements.append(PageBreak())
        photos_by_phase = {}
        for p in photos:
            photos_by_phase.setdefault(p.phase, []).append(p)

        for phase, phase_photos in photos_by_phase.items():
            phase_label = f"{phase.code}. {phase.name_ar}" if phase.code else phase.name_ar
            elements.append(rtl_paragraph(f'صور المشروع – المرحلة {phase_label}', heading_style, page_width - 12))

            # Resolve each photo's fixed box by its own orientation.
            items = []
            for photo in phase_photos:
                try:
                    path = photo.photo.path
                    orientation = _photo_orientation(path)
                    box_w, box_h = LANDSCAPE_BOX if orientation == 'landscape' else PORTRAIT_BOX
                    img = Image(path, width=box_w, height=box_h, kind='proportional')
                except Exception:
                    continue
                cap = Paragraph(_t(photo.caption, ' '), caption_style)
                items.append((orientation, [img, Spacer(1, 0.05 * inch), cap]))

            # Lay out consecutive same-orientation photos together: 1 column
            # (full width) for landscape, 2 columns for portrait -- this is
            # what naturally caps a page at 2 landscape / 4 portrait photos
            # given the box heights above.
            i = 0
            while i < len(items):
                orientation = items[i][0]
                cols = 1 if orientation == 'landscape' else 2
                run = []
                while i < len(items) and items[i][0] == orientation:
                    run.append(items[i][1])
                    i += 1
                for j in range(0, len(run), cols):
                    row_cells = run[j:j + cols]
                    # A short trailing row (fewer photos than the grid's
                    # column count) is rendered as its own single centered
                    # column instead of padded with a blank cell, so a lone
                    # leftover photo sits in the middle of the page rather
                    # than stuck to one side.
                    row_cols = len(row_cells)
                    col_w = page_width if row_cols == 1 else page_width / row_cols
                    photo_table = Table([row_cells], colWidths=[col_w] * row_cols)
                    photo_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ]))
                    elements.append(photo_table)
            elements.append(Spacer(1, 0.1 * inch))

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    buffer.seek(0)
    return buffer.getvalue()


def generate_monthly_dashboard_pdf(report):
    """
    Generate a management-facing "Executive Dashboard" PDF for a
    MonthlyReport: the same KPIs/charts-as-tables shown on the on-screen
    dashboard (services.monthly_report_generator.compute_dashboard_data),
    laid out as a professional administrative document rather than the
    full EDGE-consultant report format generate_report_pdf() produces.

    Every section is always printed, even when its underlying data is
    empty -- an explicit "no data for this period" line takes the place
    of the table/paragraph instead of the section being silently omitted,
    so a reader can tell "nothing happened here" apart from "this PDF is
    missing a section".
    """
    from .services.monthly_report_generator import compute_dashboard_data

    data = compute_dashboard_data(report)
    project = report.project

    buffer = BytesIO()
    page_size = A4
    doc = SimpleDocTemplate(
        buffer, pagesize=page_size,
        topMargin=0.9 * inch, bottomMargin=0.8 * inch,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    )
    page_width = page_size[0] - 1.8 * inch

    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'MDTitle', parent=styles['Heading1'], fontSize=18,
        textColor=colors.HexColor('#1f4788'), alignment=TA_CENTER,
        fontName=FONT_BOLD_NAME, spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        'MDSub', parent=styles['Normal'], fontSize=11,
        textColor=colors.HexColor('#555555'), alignment=TA_CENTER,
        fontName=FONT_NAME, spaceAfter=2,
    )
    heading_style = ParagraphStyle(
        'MDHeading', parent=styles['Heading2'], fontSize=12,
        textColor=colors.white, backColor=colors.HexColor('#1f4788'),
        fontName=FONT_BOLD_NAME, spaceBefore=14, spaceAfter=6,
        alignment=TA_RIGHT, borderPadding=(4, 6, 4, 6),
    )
    normal_style = ParagraphStyle(
        'MDNormal', parent=styles['Normal'], fontSize=10,
        alignment=TA_RIGHT, fontName=FONT_NAME, leading=15,
    )
    cell_style = ParagraphStyle(
        'MDCell', parent=styles['Normal'], fontSize=9,
        alignment=TA_CENTER, fontName=FONT_NAME, leading=12,
    )
    no_data_style = ParagraphStyle(
        'MDNoData', parent=styles['Normal'], fontSize=10,
        alignment=TA_CENTER, fontName=FONT_NAME, leading=14,
        textColor=colors.HexColor('#888888'),
    )

    def hdr_table(rows, col_widths, font_size=9):
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD_NAME),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), font_size),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6fb')]),
        ]))
        return t

    def no_data_row(text):
        elements.append(Paragraph(_t(text), no_data_style))
        elements.append(Spacer(1, 0.1 * inch))

    # ---------------- Cover / header ----------------
    logo_path = _owner_report_logo_path()
    if logo_path:
        cover_logo = Image(logo_path, width=3.2 * inch, height=0.75 * inch, kind='proportional')
        cover_logo.hAlign = 'CENTER'
        elements.append(cover_logo)
        elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(_t('لوحة المؤشرات التنفيذية الشهرية'), title_style))
    elements.append(Paragraph('Executive Monthly Dashboard', sub_style))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(
        _t(f"{project.name} — {report.reporting_period_from.strftime('%d/%m/%Y')} إلى {report.reporting_period_to.strftime('%d/%m/%Y')}"),
        sub_style,
    ))
    elements.append(Paragraph(_t(f"{data['report_count']} تقرير يومي لهذه الفترة — {report.get_status_display()}"), sub_style))
    elements.append(Spacer(1, 0.2 * inch))

    # ---------------- Key indicators ----------------
    elements.append(Paragraph(_t('المؤشرات الرئيسية :-'), heading_style))
    qc_rate = f'{round(data["qc_passed"] / data["qc_total"] * 100)}%' if data['qc_total'] else '—'
    indicators = [
        [_t('القيمة'), _t('المؤشر')],
        [f"{data['overall_pct']:.1f}%", _t('نسبة الإنجاز التراكمية')],
        [f"{data['pct_delta']:+.1f}%" if data['pct_delta'] else '0.0%', _t('التقدم خلال هذه الفترة')],
        [f"{data['total_man_hours']:.1f}", _t('إجمالي ساعات العمل')],
        [str(data['distinct_workers']), _t('عدد العمال المسجلين بالاسم')],
        [str(data['equipment_hours']), _t('ساعات تشغيل المعدات')],
        [qc_rate, _t('نسبة نجاح فحوصات الجودة')],
        [str(data['hse']['hse_incidents']), _t('حوادث السلامة (HSE)')],
        [str(data['hse']['near_misses']), _t('حالات شبه الحادث')],
        [f"{data['hse']['corrective_actions_open']} / {data['hse']['corrective_actions_closed']}", _t('إجراءات تصحيحية (مفتوحة / مغلقة)')],
    ]
    elements.append(hdr_table(indicators, [page_width * 0.35, page_width * 0.65], font_size=10))
    elements.append(Spacer(1, 0.1 * inch))

    # ---------------- Daily man-hours ----------------
    elements.append(Paragraph(_t('ساعات العمل اليومية :-'), heading_style))
    if data['manhours_series']:
        rows = [[_t('ساعات العمل'), _t('التاريخ')]]
        for point in data['manhours_series']:
            rows.append([f"{point['hours']:.1f}", point['date']])
        col_w = page_width / 2
        elements.append(hdr_table(rows, [col_w, col_w]))
    else:
        no_data_row('لا توجد بيانات ساعات عمل مسجلة لهذه الفترة.')

    # ---------------- Key activities by status ----------------
    elements.append(Paragraph(_t('الأنشطة الرئيسية حسب الحالة :-'), heading_style))
    status_labels_ar = {
        'completed': 'مكتمل', 'in_progress': 'قيد التنفيذ',
        'delayed': 'متأخر', 'not_started': 'لم يبدأ',
    }
    if data['key_activities']:
        rows = [[_t('ملاحظات'), _t('الحالة'), _t('النشاط')]]
        for a in data['key_activities']:
            rows.append([
                Paragraph(_t(a.remarks, '—'), cell_style),
                _t(status_labels_ar.get(a.status, a.status)),
                Paragraph(_t(a.activity), cell_style),
            ])
        elements.append(hdr_table(rows, [page_width * 0.30, page_width * 0.18, page_width * 0.52], font_size=8.5))
    else:
        no_data_row('لم يتم تسجيل أي نشاط رئيسي لهذه الفترة.')

    elements.append(PageBreak())

    # ---------------- Progress by phase ----------------
    elements.append(Paragraph(_t('نسبة الإنجاز حسب المرحلة (تراكمي) :-'), heading_style))
    if data['phase_progress']:
        rows = [[_t('نسبة الإنجاز'), _t('المرحلة')]]
        for p in data['phase_progress']:
            rows.append([f"{p['pct']:.1f}%", Paragraph(_t(p['name']), cell_style)])
        elements.append(hdr_table(rows, [page_width * 0.25, page_width * 0.75]))
    else:
        no_data_row('لا توجد مراحل معرّفة لهذا المشروع (جدول الكميات BOQ فارغ).')
    elements.append(Spacer(1, 0.1 * inch))

    # ---------------- Materials delivered ----------------
    elements.append(Paragraph(_t('المواد الموردة خلال هذه الفترة :-'), heading_style))
    if data['materials']:
        rows = [[_t('الوحدة'), _t('الكمية'), _t('المادة')]]
        for m in data['materials']:
            rows.append([_t(m.unit), f'{m.quantity:.2f}', Paragraph(_t(m.material_description), cell_style)])
        elements.append(hdr_table(rows, [page_width * 0.2, page_width * 0.2, page_width * 0.6]))
    else:
        no_data_row('لم يتم توريد أي مواد خلال هذه الفترة.')
    elements.append(Spacer(1, 0.1 * inch))

    # ---------------- Preliminary cost estimate ----------------
    from .services.cost_estimator import compute_cost_estimate
    cost = compute_cost_estimate(report)

    elements.append(Paragraph(_t('التكلفة التقديرية المبدئية :-'), heading_style))
    elements.append(Paragraph(
        _t(
            'تقدير مبدئي تقريبي فقط: العمالة محسوبة على معدل يومي ثابت (وليس الأجر الفعلي)، '
            'وأي مادة عليها علامة "تقديري" سعرها عشوائي وليس عرض سعر حقيقي.'
        ),
        ParagraphStyle('MDCostWarning', parent=styles['Normal'], fontSize=8.5, alignment=TA_RIGHT,
                       fontName=FONT_NAME, textColor=colors.HexColor('#a15c00'), leading=12),
    ))
    elements.append(Spacer(1, 0.06 * inch))

    labor = cost['labor']
    cost_summary_rows = [
        [_t('التكلفة'), _t('التفاصيل'), _t('البند')],
        [f"₪{labor['unskilled_cost']:,.0f}",
         _t(f"{labor['unskilled_days']} يوم × ₪{labor['unskilled_wage']:.0f}"),
         _t('عمالة عادية')],
        [f"₪{labor['skilled_cost']:,.0f}",
         _t(f"{labor['skilled_days']} يوم × ₪{labor['skilled_wage']:.0f}"),
         _t('عمالة فنية')],
        [f"₪{cost['materials']['total_materials_cost']:,.0f}",
         _t(f"{len(cost['materials']['items'])} مادة (تقديرية)"),
         _t('مواد')],
        [f"₪{cost['grand_total']:,.0f}", '', _t('الإجمالي التقديري')],
    ]
    elements.append(hdr_table(cost_summary_rows, [page_width * 0.25, page_width * 0.35, page_width * 0.4], font_size=10))
    elements.append(Spacer(1, 0.1 * inch))

    if cost['materials']['items']:
        rows = [[_t('تقديري؟'), _t('الإجمالي'), _t('سعر الوحدة'), _t('الوحدة'), _t('الكمية'), _t('المادة')]]
        for item in cost['materials']['items']:
            m = item['material']
            rows.append([
                _t('نعم') if m.unit_price_is_estimated else _t('لا'),
                f'₪{item["total_cost"]:,.2f}',
                f'₪{m.unit_price:,.2f}',
                _t(m.unit),
                f'{m.quantity:.2f}',
                Paragraph(_t(m.material_description), cell_style),
            ])
        elements.append(hdr_table(
            rows, [page_width * 0.1, page_width * 0.14, page_width * 0.14, page_width * 0.12, page_width * 0.12, page_width * 0.38],
            font_size=8,
        ))
    else:
        no_data_row('لا توجد مواد للتسعير خلال هذه الفترة.')
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- Issues, risks & delays ----------------
    elements.append(Paragraph(_t('المشاكل والمخاطر والتأخيرات :-'), heading_style))
    if data['issues']:
        rows = [[_t('الإجراء المتخذ'), _t('الأثر'), _t('الوصف')]]
        for i in data['issues']:
            rows.append([
                Paragraph(_t(i.mitigation, '—'), cell_style),
                Paragraph(_t(i.impact, '—'), cell_style),
                Paragraph(_t(i.description), cell_style),
            ])
        elements.append(hdr_table(rows, [page_width * 0.3, page_width * 0.3, page_width * 0.4], font_size=8.5))
    else:
        no_data_row('لم يتم تسجيل أي مشاكل أو مخاطر أو تأخيرات خلال هذه الفترة.')

    elements.append(PageBreak())

    # ---------------- Executive summary ----------------
    elements.append(Paragraph(_t('الملخص التنفيذي :-'), heading_style))
    if report.executive_summary:
        elements.append(rtl_paragraph(report.executive_summary, normal_style, page_width, justify=True))
    else:
        no_data_row('لم يتم كتابة ملخص تنفيذي لهذه الفترة.')
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- Next period plan ----------------
    elements.append(Paragraph(_t('خطة الفترة القادمة :-'), heading_style))
    if report.next_month_plan:
        elements.append(rtl_paragraph(report.next_month_plan, normal_style, page_width))
    else:
        no_data_row('لا توجد خطة مسجلة للفترة القادمة.')
    elements.append(Spacer(1, 0.2 * inch))

    # ---------------- Sign-off ----------------
    elements.append(Paragraph(_t('الاعتماد :-'), heading_style))

    def _name_or_dash(user):
        if not user:
            return '—'
        return user.get_full_name() or user.username

    signoff_rows = [
        [_t('التاريخ'), _t('الاسم'), _t('الدور')],
        [report.report_date.strftime('%d/%m/%Y') if report.report_date else '—', _t(_name_or_dash(report.site_engineer)), _t('أعدّه')],
        [report.review_date.strftime('%d/%m/%Y') if report.review_date else '—', _t(_name_or_dash(report.reviewed_by)), _t('راجعه')],
        [report.approval_date.strftime('%d/%m/%Y') if report.approval_date else '—', _t(_name_or_dash(report.approved_by)), _t('اعتمده')],
    ]
    elements.append(hdr_table(signoff_rows, [page_width * 0.3, page_width * 0.4, page_width * 0.3], font_size=10))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        _t(f'تم إصدار هذا التقرير آليًا بتاريخ {datetime.now().strftime("%d/%m/%Y")}'),
        ParagraphStyle('MDFooterNote', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER,
                       fontName=FONT_NAME, textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def generate_internal_monthly_report_pdf(report):
    """
    Generate the company's own internal monthly progress report -- the
    third report type alongside the EDGE-consultant report
    (generate_report_pdf) and the owner financial report
    (generate_owner_financial_report_pdf). Adapted from a generic EPC
    "Monthly Progress Report" template (RAG executive summary, earned-
    value-style progress, key issues, HSE statistics, cost estimate,
    sign-off) down to what actually applies to a residential/commercial
    building contractor and to data this system actually tracks -- no
    oil & gas / EPC-specific sections (NOC certificates, IFR/IFA document
    codes, pipeline/DCS scope, subcontract KVD approvals, ...).

    Like generate_report_pdf (the EDGE report), this report's own text is
    English, so it uses Times New Roman (MR_FONT_NAME/MR_FONT_BOLD_NAME)
    and plain left-aligned Paragraphs, with the same page margins as the
    real source .docx reports in this app, rather than the Arabic-capable
    font/RTL layout the other internal-report sections used previously.
    User-entered free text (activity/issue descriptions, plans, names)
    is still frequently Arabic in real use, so every such field goes
    through smart_para()/smart_cell(), which falls back to the Arabic-
    capable font for that one value instead of rendering blank tofu.
    """
    from .services.cost_estimator import compute_cost_estimate
    from .services.internal_report_data import compute_internal_report_data, RAG_GREEN, RAG_AMBER, RAG_RED, RAG_GREY
    from .site_event_models import SiteEvent
    from .daily_detail_models import DailyReportQAQC

    cost = compute_cost_estimate(report)
    ir_data = compute_internal_report_data(report)
    project = report.project

    # See generate_report_pdf for why FONT_NAME/FONT_BOLD_NAME are shadowed
    # to the Latin (Times New Roman) font for the duration of this function
    # rather than using the Arabic-capable font the other report PDFs share.
    AR_FONT_NAME = globals()['FONT_NAME']
    AR_FONT_BOLD_NAME = globals()['FONT_BOLD_NAME']
    FONT_NAME = MR_FONT_NAME
    FONT_BOLD_NAME = MR_FONT_BOLD_NAME

    RAG_HEX = {RAG_GREEN: '#c6efce', RAG_AMBER: '#ffeb9c', RAG_RED: '#ffc7ce', RAG_GREY: '#e0e0e0'}

    buffer = BytesIO()
    page_size = A4
    doc = SimpleDocTemplate(
        buffer, pagesize=page_size,
        topMargin=0.75 * inch, bottomMargin=0.5625 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    page_width = page_size[0] - 1.5 * inch

    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'IRTitle', parent=styles['Heading1'], fontSize=16,
        textColor=colors.HexColor('#1f4788'), alignment=TA_CENTER,
        fontName=FONT_BOLD_NAME, spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        'IRSub', parent=styles['Normal'], fontSize=10.5,
        textColor=colors.HexColor('#555555'), alignment=TA_CENTER,
        fontName=FONT_NAME, spaceAfter=2,
    )
    heading_style = ParagraphStyle(
        'IRHeading', parent=styles['Heading2'], fontSize=13,
        textColor=colors.white, backColor=colors.HexColor('#1f4788'),
        fontName=FONT_BOLD_NAME, spaceBefore=12, spaceAfter=6,
        alignment=TA_LEFT, borderPadding=(4, 6, 4, 6),
    )
    sub_heading_style = ParagraphStyle(
        'IRSubHeading', parent=styles['Heading3'], fontSize=10.5,
        textColor=colors.HexColor('#1f4788'), fontName=FONT_BOLD_NAME,
        alignment=TA_LEFT, spaceBefore=8, spaceAfter=4,
    )
    normal_style = ParagraphStyle(
        'IRNormal', parent=styles['Normal'], fontSize=10,
        alignment=TA_LEFT, fontName=FONT_NAME, leading=14,
    )
    cell_style = ParagraphStyle(
        'IRCell', parent=styles['Normal'], fontSize=8.5,
        alignment=TA_LEFT, fontName=FONT_NAME, leading=11,
    )
    no_data_style = ParagraphStyle(
        'IRNoData', parent=styles['Normal'], fontSize=9.5,
        alignment=TA_LEFT, fontName=FONT_NAME, leading=13,
        textColor=colors.HexColor('#888888'),
    )
    note_style = ParagraphStyle(
        'IRNote', parent=styles['Normal'], fontSize=8, alignment=TA_LEFT,
        fontName=FONT_NAME, textColor=colors.HexColor('#999999'), leading=11,
    )
    warning_style = ParagraphStyle(
        'IRWarning', parent=styles['Normal'], fontSize=8.5, alignment=TA_LEFT,
        fontName=FONT_NAME, textColor=colors.HexColor('#a15c00'), leading=12,
    )

    def smart_text(value):
        """
        Plain string for a table cell -- Arabic-reshaped if `value`
        contains Arabic (so it isn't reordered/joined wrong), passed
        through unchanged otherwise. Safe for any value.
        """
        if value in (None, ''):
            return '—'
        text = str(value)
        return shape_text(text) if _ARABIC_RE.search(text) else text

    def smart_para(value, style=cell_style, default='—'):
        """A Paragraph in `style` (Times New Roman), or the Arabic-capable
        font if `value` actually contains Arabic (frequent for user-entered
        free text like activity/issue descriptions and names)."""
        if not value:
            return default
        text = str(value)
        if _ARABIC_RE.search(text):
            ar_font = AR_FONT_BOLD_NAME if style.fontName == FONT_BOLD_NAME else AR_FONT_NAME
            ar_style = ParagraphStyle(f'{style.name}ArIR{id(style)}', parent=style, fontName=ar_font)
            return Paragraph(shape_text(text), ar_style)
        return Paragraph(text, style)

    def multiline_para(value, style=normal_style, default='—'):
        if not value:
            return default
        lines = [smart_text(line.strip()) for line in str(value).split('\n') if line.strip()]
        # smart_text() may have bidi-reordered individual Arabic lines --
        # wrap each in its own Paragraph run via <br/> like _ml() in
        # generate_report_pdf, since reportlab collapses '\n' otherwise.
        return Paragraph('<br/>'.join(lines) or default, style)

    def hdr_table(rows, col_widths, font_size=9, cell_colors=None):
        t = Table(rows, colWidths=col_widths, repeatRows=1)
        style_cmds = [
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
        ]
        if cell_colors:
            for (row_idx, col_idx), hexcolor in cell_colors.items():
                style_cmds.append(('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), colors.HexColor(hexcolor)))
        t.setStyle(TableStyle(style_cmds))
        return t

    def no_data_row(text):
        elements.append(Paragraph(text, no_data_style))
        elements.append(Spacer(1, 0.1 * inch))

    def pct_str(value):
        return f"{value:.1f}%" if value is not None else '—'

    def signed_pct_str(value):
        return f"{value:+.1f}%" if value is not None else '—'

    def money_str(value):
        return f"₪{value:,.0f}" if value is not None else '—'

    def date_str(value):
        return value.strftime('%d/%m/%Y') if value else '—'

    # ---------------- Cover / header ----------------
    logo_path = _owner_report_logo_path()
    if logo_path:
        cover_logo = Image(logo_path, width=3.2 * inch, height=0.75 * inch, kind='proportional')
        cover_logo.hAlign = 'CENTER'
        elements.append(cover_logo)
        elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph('Internal Monthly Progress Report', title_style))
    elements.append(Spacer(1, 0.05 * inch))
    elements.append(smart_para(
        f"{project.name} — {report.reporting_period_from.strftime('%d/%m/%Y')} to {report.reporting_period_to.strftime('%d/%m/%Y')}",
        sub_style,
    ))
    elements.append(Paragraph(f"{report.report_number} — {report.get_status_display()}", sub_style))
    elements.append(Spacer(1, 0.2 * inch))

    # ---------------- 1. Executive Summary (RAG status + progress overview) ----------------
    elements.append(Paragraph('1. Executive Summary', heading_style))

    # -- 1.a Status indicators, checkbox-style (Item | Controlled | Caution | Critical | Remarks) --
    elements.append(Paragraph('General Status Indicators', sub_heading_style))

    rag = ir_data['rag']
    rag_labels = [
        ('deliverables', 'Activities & Deliverables'),
        ('hse', 'HSE / Safety'),
        ('schedule', 'Schedule'),
        ('cost', 'Cost'),
        ('risks', 'Risks / Issues'),
        ('overall', 'Overall Project Status'),
    ]
    rag_cell_colors = {}
    rag_rows = [['Item', 'Controlled', 'Caution', 'Critical', 'Remarks']]
    for row_idx, (key, label) in enumerate(rag_labels, start=1):
        color = rag[key]['color']
        controlled = '✓' if color == RAG_GREEN else ''
        caution = '✓' if color == RAG_AMBER else ''
        critical = '✓' if color == RAG_RED else ''
        if color == RAG_GREEN:
            rag_cell_colors[(row_idx, 1)] = RAG_HEX[RAG_GREEN]
        elif color == RAG_AMBER:
            rag_cell_colors[(row_idx, 2)] = RAG_HEX[RAG_AMBER]
        elif color == RAG_RED:
            rag_cell_colors[(row_idx, 3)] = RAG_HEX[RAG_RED]
        rag_rows.append([label, controlled, caution, critical, smart_text(rag[key]['remark'])])
    elements.append(hdr_table(
        rag_rows,
        [page_width * 0.24, page_width * 0.13, page_width * 0.13, page_width * 0.13, page_width * 0.37],
        font_size=9, cell_colors=rag_cell_colors,
    ))
    elements.append(Spacer(1, 0.15 * inch))

    # -- 1.b Current progress overview (Baseline vs. Actual vs. Variance per phase) --
    elements.append(Paragraph('Current Progress Overview (Cumulative)', sub_heading_style))
    po = ir_data['progress_overview']
    if po['rows']:
        progress_overview_rows = [['Item', 'Baseline Plan', 'Actual', 'Variance', 'Remarks / Reasons for Delay']]
        for r in po['rows']:
            progress_overview_rows.append([
                smart_text(r['phase_name']), pct_str(r['baseline_pct']), pct_str(r['actual_pct']),
                signed_pct_str(r['variance_pct']), r['remark'],
            ])
        overall = po['overall']
        progress_overview_rows.append([
            'Overall Progress', pct_str(overall['baseline_pct']), pct_str(overall['actual_pct']),
            signed_pct_str(overall['variance_pct']),
            '' if overall['complete'] else 'Overall baseline requires planned dates for every phase',
        ])
        elements.append(hdr_table(
            progress_overview_rows,
            [page_width * 0.30, page_width * 0.13, page_width * 0.12, page_width * 0.12, page_width * 0.33],
            font_size=8.5,
        ))
    else:
        no_data_row('No phases defined for this project (BOQ is empty).')
    elements.append(Spacer(1, 0.12 * inch))

    # -- 1.c Project key milestones --
    elements.append(Paragraph('Project Key Milestones', sub_heading_style))
    ms = ir_data['milestones']
    if ms['summary'] or ms['list']:
        summary_rows = [['Phase', 'Total', 'Scheduled\nThis Period', 'Completed\nThis Period', 'Scheduled\nTo Date', 'Completed\nTo Date', 'Variance']]
        for s in ms['summary']:
            summary_rows.append([
                smart_text(s['phase_name']), str(s['total']), str(s['scheduled_period']), str(s['completed_period']),
                str(s['scheduled_to_date']), str(s['completed_to_date']), f"{s['variance']:+d}",
            ])
        elements.append(hdr_table(
            summary_rows,
            [page_width * 0.30, page_width * 0.10, page_width * 0.12, page_width * 0.12,
             page_width * 0.12, page_width * 0.12, page_width * 0.12],
            font_size=8,
        ))
        elements.append(Spacer(1, 0.1 * inch))

        status_labels_milestone = {
            'achieved_on_time': 'Achieved', 'achieved_late': 'Achieved (Late)',
            'overdue': 'Overdue', 'upcoming': 'Upcoming',
        }
        list_rows = [['Milestone', 'Phase', 'Baseline', 'Forecast', 'Actual', 'Status']]
        for m in ms['list']:
            list_rows.append([
                smart_para(m['name'], cell_style), smart_para(m['phase_name'], cell_style),
                date_str(m['baseline_date']), date_str(m['forecast_date']), date_str(m['actual_date']),
                status_labels_milestone.get(m['status'], m['status']),
            ])
        elements.append(hdr_table(
            list_rows,
            [page_width * 0.27, page_width * 0.20, page_width * 0.13, page_width * 0.13,
             page_width * 0.13, page_width * 0.14],
            font_size=8,
        ))
    else:
        no_data_row('No key milestones recorded for this project yet.')
    elements.append(Spacer(1, 0.1 * inch))

    # -- 1.d Earned value analysis (BAC / PV / EV in real currency) --
    elements.append(Paragraph('Earned Value Analysis', sub_heading_style))
    eva = ir_data['eva']
    if eva['contract_value'] is None:
        no_data_row('No contract value recorded for this project to compute the financial analysis.')
    else:
        eva_rows = [['Item', 'Budget (BAC)', 'Planned Value (PV)', 'Earned Value (EV)', 'Schedule Variance (SV)', 'Remarks']]
        for r in eva['rows']:
            eva_rows.append([
                smart_text(r['phase_name']), money_str(r['bac']), money_str(r['pv']), money_str(r['ev']),
                money_str(r['sv']), r['remark'],
            ])
        overall = eva['overall']
        eva_rows.append([
            'Total', money_str(overall['bac']), money_str(overall['pv']), money_str(overall['ev']),
            money_str(overall['sv']),
            '' if overall['complete'] else 'Total PV requires planned dates for all phases',
        ])
        elements.append(hdr_table(
            eva_rows,
            [page_width * 0.24, page_width * 0.13, page_width * 0.14, page_width * 0.14,
             page_width * 0.14, page_width * 0.21],
            font_size=8,
        ))
        elements.append(Spacer(1, 0.06 * inch))
        elements.append(Paragraph(
            'Actual Cost (AC) and CPI/CV/EAC are not available yet since there is no documented actual-cost link '
            '(pending Cost Control integration); the BAC/PV/EV figures above are fully real, derived from the '
            'contract value and the actual/planned completion percentages.',
            note_style,
        ))
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 2. Key Activities This Period ----------------
    elements.append(Paragraph('2. Key Activities This Period', heading_style))
    status_labels_ar = {
        'completed': 'Completed', 'in_progress': 'In Progress',
        'delayed': 'Delayed', 'not_started': 'Not Started',
    }
    data = ir_data['dashboard']
    key_activities = data['key_activities'] if data else []
    if key_activities:
        rows = [['Activity', 'Status', 'Remarks']]
        for a in key_activities:
            rows.append([
                smart_para(a.activity, cell_style), status_labels_ar.get(a.status, a.status),
                smart_para(a.remarks, cell_style),
            ])
        elements.append(hdr_table(rows, [page_width * 0.52, page_width * 0.18, page_width * 0.30], font_size=8.5))
    else:
        no_data_row('No key activity recorded for this period.')

    elements.append(PageBreak())

    # ---------------- 3. Key Issues & Risks ----------------
    elements.append(Paragraph('3. Key Issues & Risks', heading_style))
    issues = data['issues'] if data else []
    if issues:
        rows = [['Description', 'Impact', 'Action Required']]
        for i in issues:
            rows.append([
                smart_para(i.description, cell_style), smart_para(i.impact, cell_style, default='—'),
                smart_para(i.mitigation, cell_style, default='—'),
            ])
        elements.append(hdr_table(rows, [page_width * 0.4, page_width * 0.3, page_width * 0.3], font_size=8.5))
    else:
        no_data_row('No issues or risks recorded for this period.')
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 4. HSE Statistics (this period + project-to-date) ----------------
    elements.append(Paragraph('4. HSE Statistics', heading_style))
    lifetime_start = project.start_date or report.reporting_period_from
    hse_lifetime = SiteEvent.hse_summary_for_period(project, lifetime_start, report.reporting_period_to)
    toolbox_talks_lifetime = DailyReportQAQC.toolbox_talks_conducted_for_period(project, lifetime_start, report.reporting_period_to)
    toolbox_talks_period = DailyReportQAQC.toolbox_talks_conducted_for_period(
        project, report.reporting_period_from, report.reporting_period_to,
    )
    hse_stat_rows = [
        ['Indicator', 'This Period', 'Cumulative (Since Project Start)'],
        ['Safety Incidents', str(data['hse']['hse_incidents']), str(hse_lifetime['hse_incidents'])],
        ['Near-Miss Cases', str(data['hse']['near_misses']), str(hse_lifetime['near_misses'])],
        ['Toolbox Talk Sessions', str(toolbox_talks_period), str(toolbox_talks_lifetime)],
        ['Corrective Actions (Open / Closed)',
         f"{data['hse']['corrective_actions_open']} / {data['hse']['corrective_actions_closed']}",
         f"{hse_lifetime['corrective_actions_open']} / {hse_lifetime['corrective_actions_closed']}"],
    ]
    elements.append(hdr_table(hse_stat_rows, [page_width * 0.4, page_width * 0.3, page_width * 0.3], font_size=9.5))
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 5. Labor & Cost Estimate ----------------
    elements.append(Paragraph('5. Labor & Preliminary Cost Estimate', heading_style))
    elements.append(Paragraph(
        'Preliminary estimate: labor is costed at a flat daily rate, and materials marked "estimated" use '
        'randomly assigned placeholder prices, not real supplier quotes.',
        warning_style,
    ))
    elements.append(Spacer(1, 0.06 * inch))
    labor = cost['labor']
    cost_summary_rows = [
        ['Item', 'Details', 'Cost'],
        ['Unskilled Labor', f"{labor['unskilled_days']} day(s) x ₪{labor['unskilled_wage']:.0f}", money_str(labor['unskilled_cost'])],
        ['Skilled Labor', f"{labor['skilled_days']} day(s) x ₪{labor['skilled_wage']:.0f}", money_str(labor['skilled_cost'])],
        ['Materials', f"{len(cost['materials']['items'])} item(s), estimated", money_str(cost['materials']['total_materials_cost'])],
        ['Estimated Total', '', money_str(cost['grand_total'])],
    ]
    elements.append(hdr_table(cost_summary_rows, [page_width * 0.35, page_width * 0.4, page_width * 0.25], font_size=10))
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- 6. Plan for Next Period ----------------
    elements.append(Paragraph('6. Plan for Next Period', heading_style))
    if report.next_month_plan:
        elements.append(multiline_para(report.next_month_plan, normal_style))
    else:
        no_data_row('No plan recorded for the next period.')
    elements.append(Spacer(1, 0.2 * inch))

    # ---------------- 7. Critical Path (imported from MS Project / Primavera) ----------------
    elements.append(Paragraph('7. Critical Path (Schedule)', heading_style))
    cp = ir_data['critical_path']
    if cp['tasks'] or cp['schedule_start']:
        info_bits = []
        if cp['schedule_start']:
            info_bits.append(f"Approved schedule start: {date_str(cp['schedule_start'])}")
        if cp['schedule_finish']:
            info_bits.append(f"Project expected finish: {date_str(cp['schedule_finish'])}")
            info_bits.append(f"Days remaining to completion: {cp['remaining_days']}")
        elements.append(Paragraph(
            ' | '.join(info_bits),
            ParagraphStyle('IRScheduleInfo', parent=styles['Normal'], fontSize=9, alignment=TA_LEFT,
                           fontName=FONT_NAME, textColor=colors.HexColor('#555555'), leading=13),
        ))
        elements.append(Paragraph(
            f"Source: {cp['source_file_name']} (imported from Microsoft Project)",
            note_style,
        ))
        elements.append(Spacer(1, 0.08 * inch))

        if cp['tasks']:
            crit_rows = [['Activity', 'Start', 'Finish', 'Duration', 'Float']]
            for t in cp['tasks']:
                crit_rows.append([
                    smart_para(t['name'], cell_style), date_str(t['start']), date_str(t['finish']),
                    t['duration_text'] or '—',
                    f"{t['total_slack_days']:.0f} day(s)" if t['total_slack_days'] is not None else '—',
                ])
            elements.append(hdr_table(
                crit_rows,
                [page_width * 0.45, page_width * 0.15, page_width * 0.15, page_width * 0.13, page_width * 0.12],
                font_size=8.5,
            ))
        else:
            no_data_row('No critical-path activities identified in the imported schedule.')
    else:
        no_data_row('No schedule (MS Project / Primavera) has been imported for this project yet.')
    elements.append(Spacer(1, 0.15 * inch))

    # ---------------- Sign-off ----------------
    elements.append(Paragraph('Sign-off', heading_style))

    def _name_or_dash(user):
        if not user:
            return '—'
        return user.get_full_name() or user.username

    signoff_rows = [
        ['Role', 'Name', 'Date'],
        ['Prepared by', smart_text(_name_or_dash(report.site_engineer)), date_str(report.report_date)],
        ['Reviewed by', smart_text(_name_or_dash(report.reviewed_by)), date_str(report.review_date)],
        ['Approved by', smart_text(_name_or_dash(report.approved_by)), date_str(report.approval_date)],
    ]
    elements.append(hdr_table(signoff_rows, [page_width * 0.3, page_width * 0.4, page_width * 0.3], font_size=10))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        f'This report was generated automatically on {datetime.now().strftime("%d/%m/%Y")} — For Internal Use Only',
        ParagraphStyle('IRFooterNote', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER,
                       fontName=FONT_NAME, textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
