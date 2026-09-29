"""
"How to use the Procurement System" user manual -- PDF, Arabic-narrated
with the real English on-screen button/field labels quoted verbatim, and
illustrated with UI mockups (styled to match the real screens: same
colors, buttons, status badges, table layout) populated with REAL data
pulled live from the database (real project, real item codes, real
vendor names, real quoted prices) rather than placeholder text.

These are drawn mockups, not literal screenshots -- this machine has no
way to render an authenticated browser page to an image file (no
headless-browser tooling, and WeasyPrint's native GTK/Pango libraries
aren't installed here) -- see the chat message that introduced this
module for that limitation and how the user can supply real screenshots
instead if they want them swapped in later.
"""

from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from reports.utils import _t, shape_text, rtl_paragraph, FONT_NAME, FONT_BOLD_NAME, _owner_report_logo_path
from .barcode_utils import render_barcode_png

BLUE = '#1f4788'
GREEN = '#198754'
RED = '#dc3545'
AMBER = '#ffc107'
GREY = '#6c757d'
LIGHT = '#f4f6fb'


def _styles():
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('MTitle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor(BLUE),
                                 alignment=TA_CENTER, fontName=FONT_BOLD_NAME, spaceAfter=8),
        'sub': ParagraphStyle('MSub', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#555555'),
                               alignment=TA_CENTER, fontName=FONT_NAME, spaceAfter=4),
        'step_title': ParagraphStyle('MStepTitle', parent=styles['Heading2'], fontSize=15, textColor=colors.white,
                                      backColor=colors.HexColor(BLUE), fontName=FONT_BOLD_NAME, spaceBefore=4,
                                      spaceAfter=10, alignment=TA_RIGHT, borderPadding=(6, 8, 6, 8)),
        'screen_title': ParagraphStyle('MScreenTitle', parent=styles['Normal'], fontSize=11, textColor=colors.white,
                                        backColor=colors.HexColor('#2c3e50'), fontName=FONT_BOLD_NAME,
                                        alignment=TA_RIGHT, borderPadding=(6, 10, 6, 10)),
        'body': ParagraphStyle('MBody', parent=styles['Normal'], fontSize=10.5, alignment=TA_RIGHT,
                                fontName=FONT_NAME, leading=16),
        'note': ParagraphStyle('MNote', parent=styles['Normal'], fontSize=9, alignment=TA_RIGHT,
                                fontName=FONT_NAME, leading=13, textColor=colors.HexColor('#a15c00')),
        'cell': ParagraphStyle('MCell', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER,
                                fontName=FONT_NAME, leading=12),
        'flow_box': ParagraphStyle('MFlowBox', parent=styles['Normal'], fontSize=10.5, alignment=TA_CENTER,
                                    fontName=FONT_BOLD_NAME, leading=13, textColor=colors.white),
        'flow_arrow': ParagraphStyle('MFlowArrow', parent=styles['Normal'], fontSize=14, alignment=TA_CENTER,
                                      fontName=FONT_BOLD_NAME, textColor=colors.HexColor(BLUE)),
    }


def _button(label, color=BLUE):
    t = Table([[label]], colWidths=[None])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(color)),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), FONT_BOLD_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    return t


def _badge(label, color):
    t = Table([[label]], colWidths=[None])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(color)),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), FONT_BOLD_NAME),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    return t


def generate_procurement_manual_pdf(demo_data):
    """
    demo_data: dict with keys 'project_name', 'draft_pr', 'submitted_pr',
    'full_pr', 'rfq', 'pos' (a list -- an RFQ can be split-sourced across
    several vendors, producing one PO per vendor) -- see
    generate_procurement_manual management command's build_demo_data() for
    how this is assembled from real database records.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=0.8 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch,
    )
    page_width = A4[0] - 1.6 * inch
    S = _styles()
    elements = []

    def screen_mock(title, body_flowables, buttons=None):
        """A card-styled 'screen' box: dark title bar + body + row of mock buttons."""
        inner = [[Paragraph(_t(title), S['screen_title'])]]
        for f in body_flowables:
            inner.append([f])
        if buttons:
            inner.append([Table([buttons], colWidths=None, hAlign='RIGHT')])
        t = Table(inner, colWidths=[page_width])
        t.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor('#d0d5dd')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, 0), 0),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 1), (-1, -1), 10),
            ('RIGHTPADDING', (0, 1), (-1, -1), 10),
        ]))
        return t

    def data_table(headers, rows, col_widths=None, font_size=8.5, cell_colors=None):
        table_rows = [[Paragraph(_t(h), ParagraphStyle('h', parent=S['cell'], fontName=FONT_BOLD_NAME, textColor=colors.white)) for h in headers]]
        for row in rows:
            table_rows.append(row)
        t = Table(table_rows, colWidths=col_widths, repeatRows=1)
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), font_size),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT)]),
        ]
        if cell_colors:
            for (r, c), hexcolor in cell_colors.items():
                style_cmds.append(('BACKGROUND', (c, r), (c, r), colors.HexColor(hexcolor)))
        t.setStyle(TableStyle(style_cmds))
        return t

    def _cell(text):
        """Wrap a plain string in a Paragraph so it wraps instead of overflowing
        into the neighboring cell when the column is narrow (e.g. 'Square Meter')."""
        return Paragraph(_t(str(text)), S['cell'])

    def barcode_cell(barcode_value):
        """A small real barcode image for a table cell -- the real system now shows
        this next to the item code on every screen that lists items (PR/PO/RFQ
        lines, receipts, item catalog), not just the item's own detail page."""
        if not barcode_value:
            return ''
        png = render_barcode_png(barcode_value)
        img = Image(BytesIO(png), width=0.9 * inch, height=0.38 * inch, kind='proportional')
        return img

    # ================= Cover =================
    logo_path = _owner_report_logo_path()
    if logo_path:
        logo = Image(logo_path, width=3.2 * inch, height=0.75 * inch, kind='proportional')
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(_t('دليل استخدام نظام المشتريات'), S['title']))
    elements.append(Paragraph('Procurement System — User Guide', S['sub']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(_t('من طلب الشراء حتى الاستلام في الموقع'), S['sub']))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        _t('تنويه: الشاشات في هذا الدليل هي محاكاة مرسومة لنفس شكل النظام الفعلي (نفس الأزرار والجداول والألوان) '
           'ومعبّأة ببيانات حقيقية من النظام، وليست لقطات شاشة حرفية.'),
        S['note'],
    ))
    elements.append(PageBreak())

    # ================= Roles =================
    elements.append(Paragraph(_t('المقدمة والأدوار'), S['step_title']))
    elements.append(data_table(
        ['المسؤولية', 'الدور'],
        [
            [Paragraph(_t('يقدّم طلب الشراء بالأصناف والكميات المطلوبة لمشروعه'), S['cell']), _t('موظف الموقع (Site Engineer)')],
            [Paragraph(_t('يراجع الطلب ويوافق عليه أو يرفضه'), S['cell']), _t('مدير المشروع (Project Manager)')],
            [Paragraph(_t('يرسل طلبات عروض أسعار، يقارن العروض، يصدر أمر الشراء، يتابع التوريد'), S['cell']), _t('موظف المشتريات (Procurement Officer)')],
            [Paragraph(_t('صلاحية كاملة على كل خطوات النظام'), S['cell']), _t('الأدمن (Admin)')],
        ],
        col_widths=[page_width * 0.65, page_width * 0.35], font_size=9.5,
    ))
    elements.append(Spacer(1, 0.25 * inch))

    elements.append(Paragraph(_t('تسلسل العملية الكامل'), S['step_title']))
    flow_steps = [
        'طلب لوازم (Site Engineer)',
        'مراجعة وموافقة مدير المشروع',
        'طلب عروض أسعار RFQ (موظف المشتريات)',
        'استلام ومقارنة عروض الموردين',
        'اختيار العرض الفائز',
        'إصدار أمر الشراء (PO)',
        'الاستلام في الموقع (Site Receiving)',
    ]
    for i, step in enumerate(flow_steps):
        box = Table([[Paragraph(_t(f'{i + 1}. {step}'), S['flow_box'])]], colWidths=[page_width * 0.8])
        box.hAlign = 'CENTER'
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(BLUE)),
            ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ]))
        elements.append(box)
        if i < len(flow_steps) - 1:
            elements.append(Paragraph('↓', S['flow_arrow']))
    elements.append(PageBreak())

    # ================= Step 1: Create PR =================
    project_name = demo_data['project_name']
    draft_pr = demo_data['draft_pr']
    elements.append(Paragraph(_t('الخطوة 1: تقديم طلب الشراء (Purchase Requisition)'), S['step_title']))
    elements.append(Paragraph(
        _t(f'يدخل موظف الموقع على "New PR" من قائمة "Purchase Requisitions"، يختار المشروع ({project_name})، '
           'تاريخ الاحتياج، ويضيف كل الأصناف المطلوبة بجدول واحد (أكثر من صنف بنفس الطلب) — تمامًا زي نموذج '
           '"طلب لوازم من المستودع" الورقي، بس أونلاين.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.12 * inch))

    line_rows = [[str(l['qty']), _cell(l['unit']), _cell(l['desc']), _cell(l['code']), barcode_cell(l.get('barcode_value'))] for l in draft_pr['lines']]
    lines_table = data_table(['الكمية', 'الوحدة', 'الوصف', 'كود الصنف', 'الباركود'], line_rows,
                              col_widths=[page_width * 0.1, page_width * 0.1, page_width * 0.3, page_width * 0.2, page_width * 0.15])
    elements.append(screen_mock(
        f'New Purchase Requisition — {project_name}',
        [lines_table, Spacer(1, 0.06 * inch), Paragraph(_t('+ Add Item'), ParagraphStyle('add', parent=S['note'], textColor=colors.HexColor(BLUE)))],
        buttons=[_button('Save')],
    ))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        _t('بعد الحفظ، الطلب بيضل "Draft" (مسودة) لغاية ما يضغط موظف الموقع زر "Submit" من صفحة تفاصيل الطلب.'),
        S['body'],
    ))
    elements.append(PageBreak())

    # ================= Step 2: PM Approval =================
    submitted_pr = demo_data['submitted_pr']
    elements.append(Paragraph(_t('الخطوة 2: موافقة مدير المشروع'), S['step_title']))
    elements.append(Paragraph(
        _t(f'بعد الإرسال (Submit)، الطلب رقم {submitted_pr["pr_number"]} بيظهر بقائمة "Purchase Requisitions" '
           'تبع مدير المشروع فقط (نفس مشروعه)، وبيقدر يوافق (Approve) أو يرفض (Reject) مع كتابة السبب.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.12 * inch))

    sub_rows = [[str(l['qty']), _cell(l['unit']), _cell(l['desc']), _cell(l['code']), barcode_cell(l.get('barcode_value'))] for l in submitted_pr['lines']]
    sub_table = data_table(['الكمية', 'الوحدة', 'الوصف', 'كود الصنف', 'الباركود'], sub_rows,
                            col_widths=[page_width * 0.1, page_width * 0.1, page_width * 0.3, page_width * 0.2, page_width * 0.15])
    header_info = Table([
        [Paragraph(_t('Submitted'), ParagraphStyle('st', parent=S['cell'], textColor=colors.white, fontName=FONT_BOLD_NAME)), _t(f'{submitted_pr["pr_number"]}')],
    ], colWidths=[page_width * 0.3, page_width * 0.45])
    header_info.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor(AMBER)),
        ('FONTNAME', (1, 0), (1, 0), FONT_NAME), ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(screen_mock(
        f'{submitted_pr["pr_number"]} — {project_name}',
        [header_info, Spacer(1, 0.08 * inch), sub_table],
        buttons=[_button('Approve', GREEN), _button('Reject', RED)],
    ))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        _t('بعد الموافقة تصير حالة الطلب "Approved"، ويصير متاح لموظف المشتريات يبلّشه (Start Procurement) '
           'أو يفتحله طلب عروض أسعار مباشرة.'),
        S['body'],
    ))
    elements.append(PageBreak())

    # ================= Step 3+4: RFQ + comparison =================
    rfq = demo_data['rfq']
    elements.append(Paragraph(_t('الخطوة 3: طلب عروض الأسعار (RFQ)'), S['step_title']))
    elements.append(Paragraph(
        _t(f'موظف المشتريات بيفتح "New RFQ" من صفحة الطلب المعتمد، ويحدد الموردين المدعوين لتقديم عرض سعر. '
           f'بمثالنا، طلب {rfq["rfq_number"]} انبعت لموردين:'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.06 * inch))
    vendor_rows = [[_t('—'), Paragraph(_t(v), S['cell'])] for v in rfq['vendor_names']]
    elements.append(data_table(['Sent At', 'Vendor'], vendor_rows, col_widths=[page_width * 0.3, page_width * 0.7], font_size=9.5))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph(_t('الخطوة 4: مقارنة عروض الموردين'), S['step_title']))
    elements.append(Paragraph(
        _t('لما توصل عروض الأسعار (تليفونيًا/إيميل/واتساب)، موظف المشتريات بيسجلها بالنظام صنف صنف، '
           'وبيطلع جدول مقارنة تلقائي بين كل الموردين:'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.1 * inch))

    quote_headers = ['الإجمالي', 'مدة التوريد'] + [l['code'] for l in rfq['pr_lines']] + ['المورد']
    quote_rows = []
    cell_colors = {}
    price_col_start = 2
    for i, q in enumerate(rfq['quotes']):
        row = [
            f"₪{q['total']:,.2f}", f"{q['lead_time']} يوم",
        ] + [(f"₪{p:,.2f}" if p is not None else '—') for p in q['prices']] + [Paragraph(_t(q['vendor']), S['cell'])]
        quote_rows.append(row)
        for idx, is_sel in enumerate(q['selected']):
            if is_sel:
                cell_colors[(i + 1, price_col_start + idx)] = '#c6efce'
    n_items = len(rfq['pr_lines'])
    col_w = [page_width * 0.16, page_width * 0.14] + [page_width * 0.14] * n_items + [page_width * (0.7 - 0.14 * n_items)]
    elements.append(data_table(quote_headers, quote_rows, col_widths=col_w, font_size=8, cell_colors=cell_colors))
    elements.append(Spacer(1, 0.08 * inch))
    elements.append(Paragraph(
        _t('الخلايا المظلّلة بالأخضر هي الأسعار المعتمدة — لاحظ إنه ممكن يكون في أكثر من مورد فائز بنفس '
           'طلب عروض الأسعار الواحد، كل واحد فاز ببعض الأصناف (سعره أرخص فيها)، مش بالضرورة مورد واحد '
           'ياخد كل الطلب. موظف المشتريات بيحدد الفائز لكل صنف لحاله من صفحة "Compare Quotes"، وبيصير '
           'متاح فورًا زر "Create Purchase Order(s)" — وممكن ينتج أكثر من أمر شراء واحد، واحد لكل مورد فاز.'),
        S['body'],
    ))
    elements.append(PageBreak())

    # ================= Step 5: PO =================
    pos = demo_data['pos']
    elements.append(Paragraph(_t('الخطوة 5: إصدار أمر الشراء (Purchase Order)'), S['step_title']))
    if len(pos) > 1:
        elements.append(Paragraph(
            _t(f'بضغطة زر واحدة ("Create Purchase Order(s)")، النظام بيحوّل الأسعار المعتمدة تلقائيًا لأوامر '
               f'شراء — أمر واحد لكل مورد فاز بصنف أو أكثر. بمثالنا، ناتج عن نفس طلب عروض الأسعار {rfq["rfq_number"]} '
               f'{len(pos)} أوامر شراء منفصلة (كل مورد ياخد أصنافه يلي فاز فيها بسعره):'),
            S['body'],
        ))
    else:
        elements.append(Paragraph(
            _t(f'بضغطة زر واحدة ("Create Purchase Order(s)")، النظام بيحوّل الأسعار المعتمدة تلقائيًا لأمر شراء '
               f'({pos[0]["po_number"]}) بنفس الأصناف والكميات والأسعار — بدون إعادة إدخال يدوي.'),
            S['body'],
        ))
    elements.append(Spacer(1, 0.1 * inch))
    for po in pos:
        po_rows = [[str(l['ordered']), _cell(l['unit']), f"₪{l['price']:,.2f}", f"₪{l['total']:,.2f}",
                    _cell(f"{l['desc']} ({l['code']})"), barcode_cell(l.get('barcode_value'))]
                   for l in po['lines']]
        po_table = data_table(['الكمية', 'الوحدة', 'سعر الوحدة', 'الإجمالي', 'الصنف', 'الباركود'], po_rows,
                               col_widths=[page_width * 0.09, page_width * 0.09, page_width * 0.15, page_width * 0.15, page_width * 0.32, page_width * 0.15])
        elements.append(screen_mock(
            f'{po["po_number"]} — {po["vendor"]}',
            [po_table],
            buttons=[_button('Send to Vendor')],
        ))
        elements.append(Spacer(1, 0.06 * inch))
        elements.append(Paragraph(_t(f'الإجمالي: ₪{po["total"]:,.2f}'), ParagraphStyle('tot', parent=S['body'], fontName=FONT_BOLD_NAME)))
        elements.append(Spacer(1, 0.12 * inch))
    elements.append(PageBreak())

    # ================= Step 6: Receipt (blind site receiving) =================
    elements.append(Paragraph(_t('الخطوة 6: الاستلام في الموقع (Site Receiving)'), S['step_title']))
    elements.append(Paragraph(
        _t('لما توصل المواد للموقع، مهندس الموقع بيضغط زر "Site Receiving" الأخضر بصفحة أمر الشراء (متاح '
           'إله عن مشروعه بس، وكمان لموظف المشتريات والأدمن). هاي الشاشة **متعمّد** إنها ما تبيّن الكمية '
           'المطلوبة أو المعتمدة أصلاً — لأنه ممكن المشتريات تكون وافقت على كمية مختلفة عن يلي طلبه مهندس '
           'الموقع بالأساس، وما بدنا إياه "يخمّن" الرقم المتوقع، وبس يسجل الكمية الحقيقية يلي قدامه بالموقع.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.12 * inch))

    def empty_input_box():
        box = Table([['']], colWidths=[0.7 * inch], rowHeights=[0.22 * inch])
        box.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#999999')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ]))
        return box

    receiving_po = pos[0]
    recv_lines = receiving_po.get('lines', [])
    blind_rows = []
    for l in recv_lines:
        blind_rows.append([
            empty_input_box(),
            _cell(l['unit']),
            _cell(f"{l['desc']} ({l['code']})"),
            barcode_cell(l.get('barcode_value')),
        ])
    blind_table = data_table(
        ['Quantity received', 'Unit', 'Item', 'Barcode'], blind_rows,
        col_widths=[page_width * 0.75 * 0.22, page_width * 0.75 * 0.13, page_width * 0.75 * 0.4, page_width * 0.75 * 0.25],
        font_size=9,
    )
    elements.append(screen_mock(
        f'Site Receiving — {receiving_po["po_number"]}',
        [blind_table],
        buttons=[_button('Submit Received Quantities')],
    ))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(
        _t('لاحظ: ما في عمود "Ordered" ولا أي رقم مرجعي — بس خانة فاضية لمهندس الموقع يكتب فيها العدد '
           'يلي شافه بعينه. النظام بيتحقق من الباركود (أو الكود المكتوب جنبه) قبل ما يسمحله يسجل، حتى '
           'يتأكد إنه عم يستلم الصنف الصح.'),
        S['note'],
    ))
    elements.append(Spacer(1, 0.15 * inch))

    elements.append(Paragraph(
        _t('بعد الإرسال، النظام بيحسب الفرق تلقائيًا (وهذا الجزء بس موظف المشتريات أو الأدمن بيشوفه، مو مهندس '
           'الموقع): لو الكمية المستلمة أقل من المطلوبة، حالة الأمر بتصير تلقائيًا "Partially Received"، '
           'ولو اكتملت بتصير "Fully Received".'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.1 * inch))
    recv_rows = []
    for l in receiving_po['lines']:
        pct = (l['received'] / l['ordered'] * 100) if l['ordered'] else 0
        status_color = GREEN if pct >= 100 else (AMBER if pct > 0 else GREY)
        status_text = 'مكتمل' if pct >= 100 else ('جزئي' if pct > 0 else 'لم يستلم')
        recv_rows.append([
            _badge(_t(status_text), status_color),
            f"{l['received']:g} / {l['ordered']:g} {l['unit']}",
            Paragraph(_t(l['desc']), S['cell']),
        ])
    elements.append(data_table(['الحالة', 'المستلم / المطلوب (عند المشتريات فقط)', 'الصنف'], recv_rows,
                                col_widths=[page_width * 0.2, page_width * 0.35, page_width * 0.45], font_size=9))
    elements.append(PageBreak())

    # ================= Barcode =================
    barcode = demo_data.get('barcode')
    elements.append(Paragraph(_t('الباركود: طباعة ومسح الأصناف'), S['step_title']))
    elements.append(Paragraph(
        _t('كل صنف بكتالوج الأصناف (Item Master) بيتولّد له باركود خاص فيه تلقائيًا، فور إدخال الصنف — مافي '
           'أي إعداد إضافي مطلوب. رقم الباركود نفسه مبني من كود الصنف ذاته (نفس الترميز الهرمي)، فمش رقم '
           'عشوائي منفصل، وفيه رقم تحقق (check digit) بيتأكد إنو الجهاز مسح الرقم صح. وصورة الباركود هاي '
           'بتظهر جنب كود الصنف بكل شاشة فيها أصناف: طلب الشراء، أمر الشراء، طلب عروض الأسعار، الاستلام '
           'بالموقع، وسجل الاستلامات — مو بس صفحة الصنف لحاله.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.1 * inch))

    if barcode:
        elements.append(Paragraph(_t(f'مثال حقيقي: الصنف {barcode["full_code"]}'), ParagraphStyle('bex', parent=S['body'], fontName=FONT_BOLD_NAME)))
        elements.append(Paragraph(_t(barcode['description']), S['body']))
        elements.append(Spacer(1, 0.08 * inch))
        img = Image(BytesIO(barcode['png_bytes']), width=2.6 * inch, height=1.1 * inch, kind='proportional')
        img.hAlign = 'CENTER'
        elements.append(img)
        elements.append(Spacer(1, 0.15 * inch))

    elements.append(Paragraph(_t('كيف تستخدم الباركود؟'), ParagraphStyle('bhow', parent=S['body'], fontName=FONT_BOLD_NAME, fontSize=11)))
    elements.append(rtl_paragraph(
        '1. لطباعة ملصق صنف: افتح صفحة الصنف (Item Master) → اضغط "Print Label" → يطلع لك ملف PDF بمقاس '
        'ملصق جاهز للطباعة (80×40mm) فيه الباركود ووصف الصنف.\n'
        '2. للبحث عن صنف بالمسح: افتح قائمة "Item Master" → في صندوق مخصص أعلى الصفحة اسمه "Scan a barcode" '
        '→ حط المؤشر جواه وامسح الملصق بجهاز المسح (USB أو بلوتوث) — الجهاز بيكتب الرقم تلقائيًا ويضغط Enter '
        'لحاله، تمامًا متل الكيبورد، وبيوديك لصفحة الصنف مباشرة بدون ما تكتب إشي بإيدك.\n'
        '3. بالبحث العادي: لو لصقت رقم الباركود بمربع البحث العادي (Search) برضه بيلاقي الصنف.\n'
        '4. ما في حاجة لتطبيق موبايل خاص أو كاميرا — أي جهاز مسح باركود تجاري عادي (زي يلي بالصور) بيشتغل، '
        'لأنه بيتصرف متل كيبورد عادي مع أي متصفح.',
        S['body'], page_width,
    ))
    elements.append(PageBreak())

    # ================= Status glossary =================
    elements.append(Paragraph(_t('مرجع الحالات'), S['step_title']))
    elements.append(Paragraph(_t('حالات طلب الشراء (Purchase Requisition)'), ParagraphStyle('sec', parent=S['body'], fontName=FONT_BOLD_NAME, fontSize=11)))
    elements.append(data_table(
        ['المعنى', 'الحالة'],
        [
            [Paragraph(_t('تم إنشاؤه، لسا ما انبعت'), S['cell']), 'Draft'],
            [Paragraph(_t('بانتظار موافقة مدير المشروع'), S['cell']), 'Submitted'],
            [Paragraph(_t('وافق عليه مدير المشروع'), S['cell']), 'Approved'],
            [Paragraph(_t('رفضه مدير المشروع'), S['cell']), 'Rejected'],
            [Paragraph(_t('قيد العمل عند المشتريات (RFQ)'), S['cell']), 'In Procurement'],
            [Paragraph(_t('صدر له أمر شراء'), S['cell']), 'Completed'],
        ],
        col_widths=[page_width * 0.75, page_width * 0.25], font_size=9.5,
    ))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(_t('حالات أمر الشراء (Purchase Order)'), ParagraphStyle('sec2', parent=S['body'], fontName=FONT_BOLD_NAME, fontSize=11)))
    elements.append(data_table(
        ['المعنى', 'الحالة'],
        [
            [Paragraph(_t('تم إنشاؤه، لسا ما انبعت للمورد'), S['cell']), 'Draft'],
            [Paragraph(_t('انبعت للمورد'), S['cell']), 'Sent to Vendor'],
            [Paragraph(_t('أكّد المورد استلام الطلب'), S['cell']), 'Confirmed'],
            [Paragraph(_t('استلمنا جزء من الكمية بالموقع'), S['cell']), 'Partially Received'],
            [Paragraph(_t('استلمنا كل الكمية بالموقع'), S['cell']), 'Fully Received'],
            [Paragraph(_t('أُلغي الطلب'), S['cell']), 'Cancelled'],
        ],
        col_widths=[page_width * 0.75, page_width * 0.25], font_size=9.5,
    ))
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph(
        _t(f'تم إصدار هذا الدليل آليًا بتاريخ {datetime.now().strftime("%d/%m/%Y")}'),
        ParagraphStyle('footer', parent=S['note'], alignment=TA_CENTER, textColor=colors.HexColor('#999999')),
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
