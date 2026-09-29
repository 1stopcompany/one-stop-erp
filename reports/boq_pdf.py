"""
The project's bill of quantities as a print-out for management: sections, main items and
sub-items with unit, quantity, budget (cost) and contract (sell) prices, subtotals per section
and per main item, the grand totals and the planned margin -- laid out like the tender's own
schedule of quantities.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .print_helpers import BLUE, PHASE, SECTION, footer, letterhead, money, qty, rtl, signature_block, styles
from .progress_models import ProjectPhase
from .utils import _t

# visual left -> right (Arabic reads from the right, so the item number is last)
WIDTHS = [0.06, 0.10, 0.08, 0.10, 0.08, 0.06, 0.06, 0.36, 0.10]
HEADERS = ['الوزن %', 'إجمالي العقد', 'سعر العقد', 'إجمالي التكلفة', 'سعر التكلفة', 'الكمية', 'الوحدة', 'بيان الأعمال', 'البند']


def boq_rows(project):
    """[(section name, [(phase, [sub-items shown])])] with the totals the print-out needs."""
    phases = list(
        ProjectPhase.objects.filter(project=project).prefetch_related('sub_items').order_by('order', 'code')
    )
    sections = []
    for phase in phases:
        name = phase.section or ''
        if not sections or sections[-1][0] != name:
            sections.append((name, []))
        subs = list(phase.sub_items.all())
        shown = [] if all(s.is_whole for s in subs) else subs  # a whole item is the phase's own line
        sections[-1][1].append((phase, shown))
    return sections


def generate_boq_pdf(project):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), topMargin=0.5 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch, title=f'BOQ - {project.name}',
    )
    width = landscape(A4)[0] - 1.0 * inch
    col = [w * width for w in WIDTHS]
    S = styles()
    el = []
    letterhead(el, S, 'جدول الكميات والأسعار', 'Bill of Quantities and Prices', project, width)

    sections = boq_rows(project)
    grand_budget = grand_contract = 0
    rows = [[Paragraph(_t(h), S['head']) for h in HEADERS]]
    styles_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#9aa5bd')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]

    def add_row(cells, background=None):
        rows.append(cells)
        if background:
            styles_cmds.append(('BACKGROUND', (0, len(rows) - 1), (-1, len(rows) - 1), colors.HexColor(background)))

    def description(name_ar, name_en, bold=False):
        ar = rtl(name_ar, S['cell_b' if bold else 'cell_r'], col[7])
        if not name_en or name_en == name_ar:
            return ar
        return [ar, Paragraph(name_en, S['note'])]

    for section_name, phase_entries in sections:
        section_budget = section_contract = 0
        if section_name:
            row_idx = len(rows)
            add_row([''] * 7 + [Paragraph(_t(section_name), S['cell_b']), ''], SECTION)
            styles_cmds.append(('SPAN', (7, row_idx), (8, row_idx)))
        for phase, subs in phase_entries:
            budget, contract = phase.budget_total(), phase.contract_total()
            section_budget += budget
            section_contract += contract
            whole = not subs
            whole_item = phase.sub_items.filter(is_whole=True).first() if whole else None
            add_row([
                Paragraph(f'{phase.weight_percentage}', S['cell']) if phase.weight_percentage else '',
                Paragraph(money(contract) if contract else '', S['cell_bc']),
                Paragraph(money(phase.contract_unit_price) if whole and phase.contract_unit_price else '', S['cell']),
                Paragraph(money(budget) if budget else '', S['cell_bc']),
                Paragraph(money(phase.budget_unit_price) if whole and phase.budget_unit_price else '', S['cell']),
                Paragraph(qty(phase.quantity) if whole else '', S['cell']),
                Paragraph(_t(phase.unit) if whole else '', S['cell']),
                description(phase.name_ar, phase.name_en, bold=True),
                Paragraph(_t(phase.code), S['cell_bc']),
            ], PHASE)
            for sub in subs:
                add_row([
                    Paragraph(f'{sub.weight_percentage}', S['cell']) if sub.weight_percentage else '',
                    Paragraph(money(sub.contract_total) if sub.contract_total else '', S['cell']),
                    Paragraph(money(sub.contract_unit_price) if sub.contract_unit_price else '', S['cell']),
                    Paragraph(money(sub.budget_total) if sub.budget_total else '', S['cell']),
                    Paragraph(money(sub.budget_unit_price) if sub.budget_unit_price else '', S['cell']),
                    Paragraph(qty(sub.quantity), S['cell']),
                    Paragraph(_t(sub.unit), S['cell']),
                    description(sub.name_ar, sub.name_en),
                    Paragraph(_t(sub.code), S['cell']),
                ])
        if section_name:
            add_row([
                '', Paragraph(money(section_contract), S['cell_bc']), '', Paragraph(money(section_budget), S['cell_bc']), '', '', '',
                Paragraph(_t(f'مجموع {section_name}'), S['cell_b']), '',
            ], SECTION)
        grand_budget += section_budget
        grand_contract += section_contract

    if len(rows) == 1:
        el.append(Paragraph(_t('لا توجد بنود في جدول كميات هذا المشروع بعد.'), S['cell_r']))
    else:
        add_row(['', Paragraph(money(grand_contract), S['cell_bc']), '', Paragraph(money(grand_budget), S['cell_bc']), '', '', '',
                 Paragraph(_t('المجموع الكلي'), S['cell_b']), ''], '#c9d5ec')
        table = Table(rows, colWidths=col, repeatRows=1)
        table.setStyle(TableStyle(styles_cmds))
        el.append(table)

        margin = grand_contract - grand_budget
        summary = Table([[
            Paragraph(money(margin), S['kpi_value']), Paragraph(money(grand_budget), S['kpi_value']), Paragraph(money(grand_contract), S['kpi_value']),
        ], [
            Paragraph(_t('الهامش المخطط'), S['kpi_label']), Paragraph(_t('إجمالي التكلفة (الميزانية)'), S['kpi_label']),
            Paragraph(_t('إجمالي العقد'), S['kpi_label']),
        ]], colWidths=[width * 0.2] * 3, hAlign='RIGHT')
        summary.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#c5cde0')),
                                     ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#c5cde0'))]))
        el += [Spacer(1, 10), summary]
        el.append(Spacer(1, 4))
        el.append(Paragraph(_t('المبالغ بعملة المشروع. الوزن % هو نسبة البند من قيمة العقد.'), S['note']))
        signature_block(el, S, width)

    doc.build(el, onFirstPage=footer(f'BOQ - {project.project_symbol}'), onLaterPages=footer(f'BOQ - {project.project_symbol}'))
    return buffer.getvalue()
