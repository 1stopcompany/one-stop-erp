"""
The project cost report as a print-out for management: the headline figures (budget, contract,
committed, actual, earned, CPI, forecast, margin) and the section / main item / sub-item table,
with each line's status -- the same numbers as the Budget vs Actual page, from the same service.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.print_helpers import (
    BLUE, PHASE, SECTION, footer, letterhead, money, qty, rtl, signature_block, styles,
)
from reports.utils import FONT_BOLD_NAME, _t

from .services import project_cost_summary

# visual left -> right
WIDTHS = [0.09, 0.085, 0.04, 0.075, 0.085, 0.085, 0.085, 0.085, 0.085, 0.055, 0.185, 0.045]
HEADERS = ['الحالة', 'التوقع', 'CPI', 'الانحراف', 'المنجز', 'الفعلي', 'الملتزم', 'العقد', 'الميزانية', 'الإنجاز', 'بيان الأعمال', 'البند']
STATUS_AR = {
    'not_started': 'لم يبدأ', 'ordered': 'مطلوب، لم يُستلم', 'on_track': 'ضمن الخطة', 'overrun': 'تجاوز التكلفة',
    'saving': 'أقل من التكلفة', 'no_progress': 'صرف بلا إنجاز مسجل', 'over_committed': 'طلب أكثر من الميزانية',
}
STATUS_COLOR = {'overrun': '#dc3545', 'over_committed': '#dc3545', 'no_progress': '#a15c00', 'on_track': '#198754', 'saving': '#0b7285'}


def generate_cost_report_pdf(project):
    summary = project_cost_summary(project)
    totals = summary['totals']
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), topMargin=0.5 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch, title=f'Cost report - {project.name}',
    )
    width = landscape(A4)[0] - 1.0 * inch
    col = [w * width for w in WIDTHS]
    S = styles()
    el = []
    letterhead(el, S, 'تقرير الميزانية والتكلفة', 'Budget vs Actual - Cost Report', project, width)

    # ---- headline figures
    def kpi(label, value, note='', color=None):
        value_style = S['kpi_value'].clone('kv', textColor=colors.HexColor(color)) if color else S['kpi_value']
        return [Paragraph(_t(label), S['kpi_label']), Paragraph(value, value_style), Paragraph(_t(note), S['kpi_label'])]

    cpi = totals['cpi']
    cpi_color = ('#dc3545' if cpi and cpi < 0.95 else '#198754') if cpi else None
    margin_note = f'هامش مخطط {money(totals["planned_margin"])}' if totals['planned_margin'] is not None else ''
    fmargin = f'هامش متوقع {money(totals["forecast_margin"])}' if totals['forecast_margin'] is not None else ''
    cells = [
        kpi('التوقع عند الإكمال', money(totals['eac']), f'{money(totals["vac"])} مقابل الميزانية', '#dc3545' if totals['vac'] < 0 else '#198754'),
        kpi('مؤشر أداء التكلفة CPI', str(cpi if cpi is not None else '—'), 'المنجز ÷ الفعلي', cpi_color),
        kpi('الفعلي مقابل المنجز', f'{money(totals["actual"])} / {money(totals["earned"])}', f'انحراف {money(totals["cost_variance"])}',
            '#dc3545' if totals['cost_variance'] < 0 else '#198754'),
        kpi('الملتزم (أوامر شراء)', money(totals['committed']), f'المتبقي حراً {money(totals["uncommitted"])}'),
        kpi('عقد المشروع', money(totals['contract']), margin_note),
        kpi('الميزانية (التكلفة)', money(totals['budget']), f'إنجاز موزون {summary["weighted_progress"]}%'),
    ]
    grid = Table([[Table([[p] for p in c], colWidths=[width / 3 - 8]) for c in cells[:3]],
                  [Table([[p] for p in c], colWidths=[width / 3 - 8]) for c in cells[3:]]], colWidths=[width / 3] * 3)
    grid.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#c5cde0')), ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#c5cde0')),
                              ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    el += [grid, Spacer(1, 8)]
    if fmargin:
        el.append(Paragraph(_t(f'{fmargin} (عقد − توقع عند الإكمال)'), S['note']))

    unassigned = summary['unassigned']
    if unassigned['committed'] or unassigned['actual']:
        warn = Table([[Paragraph(_t(
            f'تنبيه: مشتريات غير منسوبة لبند في جدول الكميات: {money(unassigned["committed"])} مطلوب و{money(unassigned["actual"])} مستلم. '
            'هذا صرف حقيقي لا يمكن مقارنته بأي ميزانية إلى أن يُحدَّد له بند.'), S['cell_r'])]], colWidths=[width])
        warn.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff3cd')), ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#ffc107')),
                                  ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        el += [Spacer(1, 4), warn]
    labor = summary.get('staff_labor') or {}
    if labor.get('cost'):
        note = Table([[Paragraph(_t(
            f'تكلفة ساعات الموظفين على هذا المشروع: {money(labor["cost"])} ({labor["regular_hours"].normalize():f} ساعة + '
            f'{labor["overtime_hours"].normalize():f} ساعة إضافية بسعر الراتب) - تظهر بشكل منفصل وليست ضمن أرقام جدول الكميات.'), S['cell_r'])]], colWidths=[width])
        note.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e7f1ff')), ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#9ec5fe')),
                                  ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        el += [Spacer(1, 4), note]
    el.append(Spacer(1, 8))

    # ---- the table
    rows = [[Paragraph(_t(h), S['head']) for h in HEADERS]]
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#9aa5bd')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]

    def numbers(row, style):
        style = style.clone(style.name + '_n', fontSize=7.5)
        return [
            Paragraph(money(row['eac']), style), Paragraph(str(row['cpi'] if row['cpi'] is not None else '—'), style),
            Paragraph(money(row['cost_variance']), style), Paragraph(money(row['earned']), style), Paragraph(money(row['actual']), style),
            Paragraph(money(row['committed']), style), Paragraph(money(row['contract']) if row['contract'] else '', style),
            Paragraph(money(row['budget']), style), Paragraph(f"{row['progress_pct']:.1f}%", style),
        ]

    def status(row):
        color = STATUS_COLOR.get(row['status'], '#495057')
        return rtl(STATUS_AR[row['status']], S['cell_bc'].clone('st_' + row['status'], textColor=colors.HexColor(color)), col[0])

    def add(cells, background=None):
        rows.append(cells)
        if background:
            cmds.append(('BACKGROUND', (0, len(rows) - 1), (-1, len(rows) - 1), colors.HexColor(background)))

    for section in summary['sections']:
        if section['name']:
            idx = len(rows)
            add([''] * 10 + [Paragraph(_t(section['name']), S['cell_b']), ''], SECTION)
            cmds.append(('SPAN', (10, idx), (11, idx)))
        for entry in section['phases']:
            row = entry['row']
            add([status(row)] + numbers(row, S['cell_bc']) + [rtl(row['name'], S['cell_b'], col[10]), Paragraph(_t(row['code']), S['cell_bc'])], PHASE)
            for line in entry['lines']:
                if line['sub_item'].is_whole:
                    continue
                unit = f"{qty(line['quantity'])} {line['unit']}".strip()
                add([status(line)] + numbers(line, S['cell']) + [rtl(f"{line['name']}  ({unit})" if unit else line['name'], S['cell_r'], col[10]),
                                                                    Paragraph(_t(line['code']), S['cell'])])
        if section['name']:
            r = section['row']
            add([''] + numbers(r, S['cell_bc']) + [Paragraph(_t(f'مجموع {section["name"]}'), S['cell_b']), ''], SECTION)

    if len(rows) == 1:
        el.append(Paragraph(_t('لا توجد بنود مسعّرة أو مشتريات لهذا المشروع بعد.'), S['cell_r']))
    else:
        add([''] + numbers(totals, S['cell_bc']) + [Paragraph(_t('إجمالي المشروع'), S['cell_b']), ''], '#c9d5ec')
        table = Table(rows, colWidths=col, repeatRows=1)
        table.setStyle(TableStyle(cmds))
        el.append(table)

    el += [Spacer(1, 6), Paragraph(_t(
        'المنجز = الميزانية × نسبة إنجاز البند. الانحراف = المنجز − الفعلي (سالب = صرف أكثر من قيمة الشغل المنجز). '
        'CPI أقل من 0.95 = تجاوز للتكلفة. التوقع = الميزانية ÷ CPI ولا ينزل عن الملتزم. المبالغ بعملة المشروع.'), S['note'])]
    signature_block(el, S, width)

    doc.build(el, onFirstPage=footer(f'Cost report - {project.project_symbol}'), onLaterPages=footer(f'Cost report - {project.project_symbol}'))
    return buffer.getvalue()
