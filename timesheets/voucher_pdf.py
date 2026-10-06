"""
The day-labor payment voucher (سند صرف نقداً + قسيمة عامل مياومة): the company's own form that the worker signs when
he receives his wages -- a wage slip table, the receipt / release declaration and the signature boxes, on the company
letterhead. One voucher (two pages) per worker and month; any number of them can be put in one PDF.

The wording comes from timesheets.voucher_text (copied from the Word form); the first clause, which says the contractual
relationship has ended, can be left out for workers who carry on working.
"""
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

from reportlab.pdfbase import pdfmetrics
from reports.utils import MR_FONT_BOLD_NAME as BOLD, MR_FONT_NAME as FONT, _t, rtl_paragraph, shape_text

from . import voucher_text
from .services.daily_worker_payroll_service import compute_daily_worker_statement

LETTERHEAD = 'images/letterhead_a4.jpg'
TOP, BOTTOM, SIDE = 150, 88, 48


def _plain(value):
    value = Decimal(value).quantize(Decimal('0.01'))
    return f'{value:f}'.rstrip('0').rstrip('.') if value else '0'


def _amount(value):
    """The amount as written in the declaration: 45 for a whole number, 3217.50 otherwise."""
    value = Decimal(value).quantize(Decimal('0.01'))
    return str(int(value)) if value == value.to_integral() else f'{value:f}'


def _money(value):
    return f'{Decimal(value):,.2f}'


def _letterhead(canvas, doc):
    path = finders.find(LETTERHEAD)
    if path:
        canvas.saveState()
        canvas.drawImage(path, 0, 0, width=A4[0], height=A4[1])
        canvas.restoreState()


def _justified(text, style, width):
    """
    An Arabic paragraph whose every line but the last fills exactly `width`, so the text lines up with the table edges.
    Lines are broken and measured on the SHAPED text (Arabic letters join, so they are narrower than the raw characters
    reports.utils.rtl_paragraph measures), and the spare room is spread over the gaps between words.
    """
    font, size = style.fontName, style.fontSize
    measure = lambda line: pdfmetrics.stringWidth(shape_text(line), font, size)
    lines, current = [], []
    for word in str(text).split():
        if current and measure(' '.join(current + [word])) > width:
            lines.append(current)
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(current)
    space = pdfmetrics.stringWidth(' ', font, size)
    out = []
    for i, words in enumerate(lines):
        line = ' '.join(words)
        if i < len(lines) - 1 and len(words) > 1:
            extra = int((width - measure(line)) / space)
            if extra > 0:
                base, rest = divmod(extra, len(words) - 1)
                line = words[0] + ''.join(' ' * (1 + base + (1 if g <= rest else 0)) + words[g] for g in range(1, len(words)))
        out.append(shape_text(line))
    return Paragraph('<br/>'.join(out), style)


def _styles():
    base = getSampleStyleSheet()['Normal']
    return {
        'title': ParagraphStyle('VTitle', parent=base, fontName=BOLD, fontSize=12, leading=16, alignment=TA_CENTER),
        'date': ParagraphStyle('VDate', parent=base, fontName=FONT, fontSize=10, leading=14, alignment=TA_RIGHT),
        'cell': ParagraphStyle('VCell', parent=base, fontName=FONT, fontSize=9, leading=11.5, alignment=TA_CENTER),
        'cellb': ParagraphStyle('VCellB', parent=base, fontName=BOLD, fontSize=9.5, leading=12, alignment=TA_CENTER),
        'head': ParagraphStyle('VHead', parent=base, fontName=BOLD, fontSize=11, leading=14, alignment=TA_CENTER),
        'body': ParagraphStyle('VBody', parent=base, fontName=FONT, fontSize=9.2, leading=13, alignment=TA_RIGHT),
        'num': ParagraphStyle('VNum', parent=base, fontName=FONT, fontSize=9.2, leading=13, alignment=TA_RIGHT),
        'sign': ParagraphStyle('VSign', parent=base, fontName=BOLD, fontSize=9.5, leading=13, alignment=TA_RIGHT),
        'signl': ParagraphStyle('VSignL', parent=base, fontName=FONT, fontSize=9.5, leading=26, alignment=TA_RIGHT),
    }


def _voucher_data(slip):
    worker = slip.worker
    statement = compute_daily_worker_statement(worker, slip.period_start, slip.period_end)
    projects = []
    for row in statement['by_project']:
        days = row['days']
        due = row['base_pay'] + row['overtime_pay']
        projects.append({
            'name': row['project'].name if row['project'] else '—', 'days': days, 'friday': days / Decimal(6),
            'paid_rate': (row['base_pay'] / days) if days else worker.daily_rate, 'base_pay': row['base_pay'],
            'overtime_hours': row['overtime_hours'], 'overtime_pay': row['overtime_pay'], 'due': due,
            'advances': row['advances'], 'net': due - row['advances'],
        })
    zero = Decimal('0')
    totals = {key: sum((p[key] for p in projects), zero) for key in
              ('days', 'friday', 'base_pay', 'overtime_hours', 'overtime_pay', 'due', 'advances', 'net')}
    return {
        'worker': worker, 'projects': projects, 'totals': totals,
        'project_names': '، '.join(p['name'] for p in projects) or '—',
        'allowances': slip.other_allowances, 'slip_advances': slip.advances, 'other_deductions': slip.other_deductions,
        'net': slip.net_pay, 'tax': slip.income_tax,
    }


def _story_for(slip, S, width, include_termination):
    data = _voucher_data(slip)
    worker = data['worker']
    start, end = slip.period_start, slip.period_end
    shaped = lambda text, style='cell': Paragraph(_t(text), S[style]) if text else ''
    story = [
        Paragraph(_t('سند صرف نقداً'), S['title']),
        Paragraph('Payment Voucher', ParagraphStyle('VEn', parent=S['title'], fontName=BOLD, fontSize=11)),
        Spacer(1, 4),
        Paragraph(_t(f'التاريخ: {end:%d-%m-%Y}'), S['date']),
        Spacer(1, 3),
    ]

    # ---- who is paid: physical columns left -> right are [extra, extra, value, label] (the page reads right to left)
    w = [width * f for f in (0.27, 0.23, 0.30, 0.20)]
    rows = [
        [shaped('قسيمة عامل مياومة', 'head'), '', '', ''],
        [shaped(f'للفترة من : {start:%d/%m/%Y}        الى: {end:%d/%m/%Y}'), '', '', ''],
        [shaped(f'رقم الهوية: {worker.national_id or "—"}'), '', shaped(worker.full_name, 'cellb'), shaped('اسم العامل', 'cellb')],
        [shaped(worker.trade or '—'), '', shaped('طبيعة العمل', 'cellb'), ''],
    ]
    who = Table(rows, colWidths=w)
    who.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.7, colors.black), ('BOX', (0, 0), (-1, -1), 1.2, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('SPAN', (0, 0), (-1, 0)), ('SPAN', (0, 1), (-1, 1)), ('SPAN', (0, 2), (1, 2)), ('SPAN', (0, 3), (1, 3)),
        ('SPAN', (2, 3), (3, 3)),
    ]))
    story += [who, Spacer(1, 5)]

    # ---- one table for every project the worker was paid for this month, then his totals
    headers = ['المشروع', 'أيام العمل', 'أيام الجمعة', 'مجموع الأيام', 'الأجر المدفوع', 'المجموع', 'ساعات إضافية',
               'قيمة الساعات', 'الأجر المستحق', 'سلف', 'الصافي']
    fractions = [0.21, 0.07, 0.07, 0.07, 0.09, 0.09, 0.07, 0.08, 0.10, 0.06, 0.09]   # logical order, right to left
    widths = [width * f / sum(fractions) for f in fractions]   # always add up to the full width
    small = ParagraphStyle('VSmall', parent=S['cell'], fontSize=8, leading=10)
    smallb = ParagraphStyle('VSmallB', parent=S['cellb'], fontSize=8, leading=10)
    head_style = ParagraphStyle('VHeadS', parent=small, fontName=BOLD, textColor=colors.black)
    table_rows = [[Paragraph(_t(h), head_style) for h in headers]]
    for item in data['projects']:
        table_rows.append([
            rtl_paragraph(item['name'], small, widths[0] - 6), _plain(item['days']), _plain(item['friday']),
            _plain(item['days'] + item['friday']), _money(item['paid_rate']), _money(item['base_pay']),
            _plain(item['overtime_hours']) if item['overtime_hours'] else '',
            _money(item['overtime_pay']) if item['overtime_pay'] else '', _money(item['due']),
            _money(item['advances']) if item['advances'] else '', _money(item['net']),
        ])
    totals = data['totals']
    table_rows.append([
        Paragraph(_t('المجموع'), smallb), _plain(totals['days']), _plain(totals['friday']),
        _plain(totals['days'] + totals['friday']), '', _money(totals['base_pay']),
        _plain(totals['overtime_hours']) if totals['overtime_hours'] else '',
        _money(totals['overtime_pay']) if totals['overtime_pay'] else '', _money(totals['due']),
        _money(totals['advances']) if totals['advances'] else '', _money(totals['net']),
    ])
    table_rows = [list(reversed(r)) for r in table_rows]
    breakdown = Table(table_rows, colWidths=list(reversed(widths)), repeatRows=1)
    last_row = len(table_rows) - 1
    breakdown.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.7, colors.black), ('BOX', (0, 0), (-1, -1), 1.2, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 1), (-1, -1), FONT), ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('BACKGROUND', (0, last_row), (-1, last_row), colors.HexColor('#f1f1f1')), ('FONTNAME', (0, last_row), (-1, last_row), BOLD),
    ]))
    story += [breakdown, Spacer(1, 5)]

    # ---- what is added or taken off the worker as a whole, and the amount he receives
    extra = []
    if data['allowances']:
        extra.append(('بدلات أخرى', _money(data['allowances'])))
    extra.append(('ضريبة الدخل (للعلم - غير مخصومة)', _money(data['tax']) if data['tax'] else ''))
    extra.append(('سلف وقروض (على مستوى العامل)', _money(data['slip_advances']) if data['slip_advances'] else ''))
    if data['other_deductions']:
        extra.append(('خصومات أخرى', _money(data['other_deductions'])))
    extra.append(('الصافي للدفع', _money(data['net'])))
    box_w = [width * 0.22, width * 0.78]   # the same full width as the tables above
    box_rows = [[shaped(v, 'cellb' if label == 'الصافي للدفع' else 'cell'), shaped(label, 'cellb' if label == 'الصافي للدفع' else 'cell')]
                for label, v in extra]
    box = Table(box_rows, colWidths=box_w)
    box.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.7, colors.black), ('BOX', (0, 0), (-1, -1), 1.2, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('BACKGROUND', (0, len(box_rows) - 1), (-1, len(box_rows) - 1), colors.HexColor('#fff9c4')),
    ]))
    story += [box, Spacer(1, 9)]

    # ---- the declaration
    fields = {
        'name': worker.full_name, 'national_id': worker.national_id or '—', 'end_date': f'{end:%d/%m/%Y}',
        'amount': _amount(data['net']), 'projects': data['project_names'], 'month': f'{start:%m/%Y}', 'year': end.year,
    }
    story.append(_justified(voucher_text.INTRO.format(**fields), S['body'], width))
    story.append(Spacer(1, 4))
    clauses = [c for i, c in enumerate(voucher_text.CLAUSES) if include_termination or i != 0]
    num_w = 20
    for n, clause in enumerate(clauses, start=1):
        text = clause.format(**fields) if '{' in clause else clause
        row = Table([[_justified(text, S['body'], width - num_w), Paragraph(f'.{n}', S['num'])]],
                    colWidths=[width - num_w, num_w])
        row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 1),
                                 ('BOTTOMPADDING', (0, 0), (-1, -1), 2), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                 ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        story.append(row)
    story += [Spacer(1, 3), _justified(voucher_text.CLOSING.format(**fields), S['body'], width),
              Spacer(1, 10)]

    # ---- signatures (right to left on the page: accounting, receiver, witness, project manager)
    sig = [
        [shaped('مدير المشروع:', 'sign'), shaped('شاهد:', 'sign'), shaped('المستلم:', 'sign'), shaped('المحاسبة:', 'sign')],
        [shaped('الاسم:', 'signl'), shaped('الاسم:', 'signl'), shaped('الاسم الرباعي:', 'signl'), ''],
        [shaped('التوقيع:', 'signl'), shaped('التوقيع:', 'signl'), shaped('التوقيع:', 'signl'), shaped('التوقيع:', 'signl')],
    ]
    sig_table = Table(sig, colWidths=[width / 4] * 4)
    sig_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 0),
                                   ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    story.append(sig_table)
    return story


def generate_wage_vouchers_pdf(slips, include_termination=True):
    """One voucher (two pages) per DailyWorkerPayslip, in the order given, as a single PDF."""
    buffer = BytesIO()
    width = A4[0] - 2 * SIDE
    doc = BaseDocTemplate(buffer, pagesize=A4, title='Payment vouchers')
    frame = Frame(SIDE, BOTTOM, width, A4[1] - TOP - BOTTOM, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='voucher', frames=[frame], onPage=_letterhead)])
    S = _styles()
    story = []
    for i, slip in enumerate(slips):
        if i:
            story.append(PageBreak())
        story += _story_for(slip, S, width, include_termination)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
