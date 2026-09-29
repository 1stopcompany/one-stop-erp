"""
"How to price a project and follow its cost" user guide -- PDF, Arabic-narrated with the real
English on-screen labels quoted verbatim, in the same style as the Procurement and HR guides
(drawn mock-ups of the real screens, not literal screenshots).

Every number in the worked example is produced by the SAME functions the Cost Control pages use
(cost_control.services), fed stand-in objects, so the guide can never disagree with the system
about how a figure is calculated.
"""
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from procurement.manual_pdf import BLUE, GREEN, LIGHT, RED, _button, _styles
from reports.utils import FONT_BOLD_NAME, FONT_NAME, _owner_report_logo_path, _t, rtl_paragraph

from .services import _line_row, _rollup

D = Decimal


def _example(code, name, unit, qty, budget_price, contract_price, progress, committed, actual):
    """One BOQ item (sub-item), calculated by the real service code."""
    sub = SimpleNamespace(
        code=code, name_ar=name, name_en=name, unit=unit, quantity=D(qty),
        budget_unit_price=D(budget_price), contract_unit_price=D(contract_price),
        budget_total=D(qty) * D(budget_price), contract_total=D(qty) * D(contract_price),
        latest_execution_percentage=lambda as_of=None: D(progress),
    )
    return _line_row(sub, None, D(committed), D(actual), None)


def _money(value):
    return f"{D(value):,.2f}"


def generate_pricing_manual_pdf():
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=0.8 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch,
        title="Pricing & Cost Control - User Guide",
    )
    page_width = A4[0] - 1.6 * inch
    S = _styles()
    el = []

    # ------------------------------------------------------------------ helpers
    def para(text, style='body', width=None):
        """Long Arabic text, wrapped line by line so the right-to-left order stays correct."""
        return rtl_paragraph(text, S[style], width or page_width)

    def cell(text, width, bold=False, color=None):
        style = ParagraphStyle('c', parent=S['cell'], fontName=FONT_BOLD_NAME if bold else FONT_NAME,
                               textColor=colors.HexColor(color) if color else colors.black)
        return rtl_paragraph(text, style, width - 10)

    def bullets(items, width=None):
        return [para(f'•  {t}', 'body', width) for t in items]

    def screen_mock(title, body, buttons=None):
        inner = [[Paragraph(_t(title), S['screen_title'])]] + [[b] for b in body]
        if buttons:
            inner.append([Table([buttons], hAlign='RIGHT')])
        t = Table(inner, colWidths=[page_width])
        t.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor('#d0d5dd')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, 0), 0), ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
            ('TOPPADDING', (0, 1), (-1, -1), 8), ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 1), (-1, -1), 10), ('RIGHTPADDING', (0, 1), (-1, -1), 10),
        ]))
        return t

    def table(headers, rows, widths, font_size=8.5, highlight=None, total_row=False, scale=1.0, bold_rows=()):
        size = min(9, font_size)
        head = [Paragraph(_t(h), ParagraphStyle('h', parent=S['cell'], fontName=FONT_BOLD_NAME, textColor=colors.white,
                                                 fontSize=size, leading=size + 2)) for h in headers]
        t = Table([head] + rows, colWidths=[w * page_width * scale for w in widths], repeatRows=1)
        cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.grey), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), font_size), ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT)]),
        ]
        for r in bold_rows:
            cmds += [('BACKGROUND', (0, r), (-1, r), colors.HexColor('#e2e8f5')), ('FONTNAME', (0, r), (-1, r), FONT_BOLD_NAME)]
        if total_row:
            cmds += [('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e2e8f5')), ('FONTNAME', (0, -1), (-1, -1), FONT_BOLD_NAME)]
        for (r, c), color in (highlight or {}).items():
            cmds.append(('BACKGROUND', (c, r), (c, r), colors.HexColor(color)))
        t.setStyle(TableStyle(cmds))
        return t

    def callout(text, color='#fff8e1', border='#ffc107'):
        t = Table([[rtl_paragraph(text, S['body'], page_width - 24)]], colWidths=[page_width])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(color)), ('BOX', (0, 0), (-1, -1), 1, colors.HexColor(border)),
            ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        return t

    def flow(steps):
        for i, step in enumerate(steps):
            box = Table([[Paragraph(_t(f'{i + 1}. {step}'), S['flow_box'])]], colWidths=[page_width * 0.8])
            box.hAlign = 'CENTER'
            box.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(BLUE)),
                ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('ROUNDEDCORNERS', [6, 6, 6, 6]),
            ]))
            el.append(box)
            if i < len(steps) - 1:
                el.append(Paragraph('↓', S['flow_arrow']))

    def heading(text):
        el.append(Paragraph(_t(text), S['step_title']))

    def gap(h=0.12):
        el.append(Spacer(1, h * inch))

    def status_cell(row, width):
        color = {'overrun': RED, 'over_committed': RED, 'no_progress': '#a15c00', 'on_track': GREEN}.get(row['status'])
        return cell(row['status_label'], width, True, color)

    # ------------------------------------------------------------------ the worked example (real maths)
    concrete = _example('1.2', 'Concrete works', 'm3', 120, 420, 560, 100, 49000, 49000)
    columns = _example('2.1', 'Columns and slabs', 'm3', 250, 480, 640, 55, 75000, 75000)
    columns_early = _example('2.1', 'Columns and slabs', 'm3', 250, 480, 640, 55, 45000, 45000)
    tiling = _example('3.1', 'Tiling', 'm2', 600, 75, 105, 10, 30000, 0)
    painting = _example('3.2', 'Painting', 'm2', 1200, 14, 22, 0, 0, 0)
    foundations = _rollup('phase', [concrete], code='1', name='Foundations')
    structure = _rollup('phase', [columns], code='2', name='Structure')
    finishes = _rollup('phase', [tiling, painting], code='3', name='Finishes')
    project_total = _rollup('project', [foundations, structure, finishes])
    contract_total, eac_total = project_total['contract'], project_total['eac']

    # ================================================================== cover
    logo = _owner_report_logo_path()
    if logo:
        img = Image(logo, width=3.2 * inch, height=0.75 * inch, kind='proportional')
        img.hAlign = 'CENTER'
        el += [img, Spacer(1, 0.2 * inch)]
    el.append(Paragraph(_t('دليل التسعير ومتابعة التكلفة'), S['title']))
    el.append(Paragraph('Pricing & Cost Control — User Guide', S['sub']))
    gap(0.1)
    el.append(Paragraph(_t('من وثيقة العطاء وجدول كميات المشروع (BOQ) حتى مقارنة الميزانية بالفعلي والمنجز'), S['sub']))
    gap(0.15)
    el.append(para('تنويه: الشاشات في هذا الدليل محاكاة مرسومة لنفس شكل النظام الفعلي، والأرقام مثال محسوب '
                   'بنفس معادلات النظام وليست بيانات مشروع حقيقي. كل المبالغ بعملة المشروع.', 'note'))
    el.append(PageBreak())

    # ================================================================== 1. big picture
    heading('الفكرة العامة')
    el.append(para('التسعير بالنظام على جدول كميات المشروع نفسه (BOQ): المراحل الرئيسية Phases وتحتها البنود الفرعية Sub-items، '
                   'زي جدول الكميات بوثيقة العطاء تماماً. بتدخل الوحدة والكمية وسعر التكلفة وسعر العقد مرة وحدة، على المرحلة كاملة '
                   'أو على بنودها الفرعية، وكل باقي الأرقام (الملتزم، الفعلي، المنجز، التوقع) بتنحسب لحالها من المشتريات '
                   'والاستلام وتقارير الإنجاز. التسعير مش على أصناف المستودع.'))
    gap()
    flow(['اختياري: قراءة وثيقة العطاء وتجهيز مسودة BOQ بالمساعد الذكي (AI Assistant)',
          'مراحل المشروع وبنوده بالوحدة والكمية والسعرين (Manage BOQ)', 'شراء المواد: كل بند بأمر الشراء يُنسب لبند BOQ',
          'أوامر الشراء الصادرة تصير "ملتزم به" Committed', 'الاستلام بالموقع يصير "فعلي" Actual',
          'تقارير الإنجاز تحدد نسبة كل بند، ومنها "المنجز" Earned', 'صفحة Budget vs Actual: المقارنة والتوقع'])
    gap(0.2)
    el.append(para('لكل بند أربع أرقام، وكل واحد إله معنى مختلف:'))
    gap(0.06)
    w = [0.24, 0.44, 0.32]
    el.append(table(['من وين بتجي', 'شو يعني', 'الرقم'], [
        [cell('أسعار BOQ', page_width * w[0]), cell('كمية × سعر التكلفة. الخطة.', page_width * w[1]), cell('Budget (الميزانية)', page_width * w[2], True)],
        [cell('أوامر الشراء الصادرة', page_width * w[0]), cell('قيمة ما طلبته من الموردين، حتى لو ما وصلت البضاعة.', page_width * w[1]), cell('Committed (الملتزم)', page_width * w[2], True)],
        [cell('الاستلام بالموقع', page_width * w[0]), cell('قيمة ما وصل فعلاً، بأسعار أوامر الشراء.', page_width * w[1]), cell('Actual (الفعلي)', page_width * w[2], True)],
        [cell('تقارير الإنجاز', page_width * w[0]), cell('الميزانية × نسبة إنجاز البند. كم تساوي الشغلة المنجزة.', page_width * w[1]), cell('Earned (المنجز)', page_width * w[2], True)],
    ], w))
    gap(0.15)
    el.append(callout('لماذا المنجز مهم؟ لو صرفت 84% من ميزانية بند لكن الشغل المنجز فيه 40% فقط، فأنت متجاوز التكلفة '
                      'حتى لو لسا ما وصلت للميزانية الكاملة. مقارنة "الفعلي مقابل الميزانية الكاملة" بتبين كل مشروع '
                      'ناجح بأول نصفه، لهيك النظام بيقارن الفعلي بالمنجز.'))
    el.append(PageBreak())

    # ================================================================== 2. roles
    heading('الأدوار والصلاحيات')
    w = [0.55, 0.45]
    el.append(table(['الصلاحية', 'الدور'], [
        [cell('يعدّل جدول الكميات والأسعار لكل المشاريع', page_width * w[0]), cell('الأدمن (Admin)', page_width * w[1], True)],
        [cell('يعدّل جدول الكميات والأسعار لكل المشاريع', page_width * w[0]), cell('مدير الهندسة (Engineering Manager)', page_width * w[1], True)],
        [cell('يعدّل جدول كميات وأسعار مشروعه هو فقط', page_width * w[0]), cell('مدير المشروع (Project Manager)', page_width * w[1], True)],
        [cell('يشوف صفحات التكلفة لمشروعه، ويحدد بند BOQ بطلب المواد', page_width * w[0]), cell('موظف الموقع (Site Engineer)', page_width * w[1], True)],
        [cell('يحدد بند BOQ بأوامر الشراء ويتابع الاستلام', page_width * w[0]), cell('موظف المشتريات (Procurement Officer)', page_width * w[1], True)],
        [cell('المساعد الذكي: يقرأ الوثائق ويستورد مسودة BOQ ويراجع المشروع (مدير المشروع لمشروعه فقط)', page_width * w[0]),
         cell('الأدمن، مدير الهندسة، مدير المشروع', page_width * w[1], True)],
        [cell('المساعد الذكي: يشوف النتائج ويشغّل مراجعة المشروع ويسأل بالفقاعة، بدون قراءة وثائق ولا استيراد', page_width * w[0]),
         cell('المدير العام (General Manager)', page_width * w[1], True)],
    ], w, font_size=9.5))
    gap(0.15)
    el.append(para('قبل ما تبدأ:'))
    el += bullets([
        'التسعير بيصير وقت العطاء، والمشروع لسا Planning. ما لازم يكون بدأ العمل.',
        'مراحل المشروع وبنوده بتنحفظ مرة وحدة، ونفسها بتخدم تقارير الإنجاز والتقارير المالية للمالك.',
        'أي عمل على المشروع (تقارير الموقع، تسجيل الإنجاز، المشتريات والاستلام، صرف المستودع، حضور الموقع) مقفول لحد ما يكون عليه تأمين ساري بوثيقته، '
        'وBOQ مسعّر بالكامل (لكل بند كمية وسعر تكلفة وسعر عقد). التأمين وBOQ والتسعير نفسها ما بتنقفل، لأنها اللي بتفتح المشروع.',
    ])
    el.append(PageBreak())

    # ================================================================== 2b. AI: read a tender document into a draft BOQ
    heading('الخطوة 1 (اختيارية): تجهيز جدول الكميات من وثيقة العطاء بالمساعد الذكي')
    el.append(para('بدل ما تكتب بنود جدول كميات العطاء بإيدك، المساعد الذكي (AI Assistant) بيقرأ الوثيقة أو المخطط وبيجهّز مسودة BOQ: '
                   'الأقسام، البنود الرئيسية، البنود الفرعية، وبكل بند رقمه ووحدته وكميته. المسودة مجرد مسودة: ما بيتغيّر شي بالمشروع '
                   'إلا لما تراجعها وتضغط "Import ticked items".'))
    gap(0.08)
    el += bullets([
        'من صفحة المشروع أو صفحة Manage BOQ اضغط "AI Assistant".',
        'بقسم "Read a document into a draft BOQ" اختر وثيقة موجودة بالمشروع (وثائق العطاء أو المخططات)، أو ارفع ملف: PDF أو صورة أو Excel أو CSV أو نص، '
        'حتى 32 ميغابايت. ملفات DWG وDXF لازم تصدّرها PDF من برنامج الرسم أولاً.',
        'اكتب ملاحظة للقارئ إذا بدك واضغط "Read document". الوثيقة الكبيرة بتاخد دقيقة أو أكثر، وبتلاقي النتيجة بـ "Recent runs".',
        'راجع المسودة وقارنها بالوثيقة، حدّد البنود اللي بدك ياها، واضغط "Import ticked items".',
    ])
    gap(0.06)
    d_w = [0.16, 0.10, 0.10, 0.44, 0.10]
    el.append(screen_mock('AI Assistant — Draft BOQ (read from the tender document)', [table(
        ['Note', 'Quantity', 'Unit', 'Description', 'No.'],
        [[cell('', page_width * 0.16 * 0.93), '100', 'm2', cell('Internal wall plastering', page_width * 0.44 * 0.93), '1.04'],
         [cell('Check', page_width * 0.16 * 0.93, True, '#a15c00'), '250', 'm3', cell('Columns and slabs', page_width * 0.44 * 0.93), '2.1'],
         [cell('Unsure', page_width * 0.16 * 0.93, True, RED), '—', 'm2', cell('Floor tiling', page_width * 0.44 * 0.93), '3.1'],
         [cell('Already in BOQ', page_width * 0.16 * 0.93, True, '#6c757d'), '1', 'lump sum', cell('Demolition works', page_width * 0.44 * 0.93), '1.01']],
        d_w, font_size=7.5, scale=0.93)],
        buttons=[_button('Import ticked items', GREEN)]))
    gap(0.1)
    w = [0.62, 0.38]
    el.append(table(['معناها', 'العلامة'], [
        [cell('رقم البند موجود أصلاً بالـ BOQ. ما بينستورد ولا بينكتب فوق الموجود.', page_width * w[0]), cell('Already in BOQ', page_width * w[1], True, '#6c757d')],
        [cell('البند بدون رقم بالوثيقة. ما بينستورد، أضفه يدوياً بعد ما تحدد رقمه.', page_width * w[0]), cell('No number', page_width * w[1], True, '#a15c00')],
        [cell('القارئ اضطر يفسّر شي بالوثيقة. راجعه.', page_width * w[0]), cell('Check', page_width * w[1], True, '#a15c00')],
        [cell('القارئ مش متأكد. البند بيبدأ غير محدّد بالمربع، وما تستورده قبل ما تتأكد من الوثيقة.', page_width * w[0]), cell('Unsure', page_width * w[1], True, RED)],
    ], w, font_size=9))
    gap(0.1)
    el.append(callout('المساعد بينقل اللي مكتوب بالوثيقة ولا يقدّر: الكمية أو الوحدة اللي مش مكتوبة بتضل فاضية، ومن المخططات بيقرأ جداولها '
                      'وملاحظاتها ولا بيقيس من الرسم. راجع كل كمية ووحدة بالوثيقة الأصلية، خصوصاً بالجداول المعقدة أو الممسوحة ضوئياً، لأن القراءة ممكن تغلط.'))
    gap(0.1)
    el += bullets([
        'على يمين المسودة: "Things the reader noticed" و"Compared with the current BOQ" (بنود ناقصة أو زايدة وكميات مختلفة عن BOQ الحالي).',
        'الأسعار المطبوعة بالوثيقة ما بتنستورد إلا إذا حددت "Use prices printed in the document"، وبعد الاستيراد سعّر من Manage BOQ (الخطوة 2) '
        'ثم اضغط "Weights from prices". البنود المستوردة عليها علامة [AI:run] بملاحظاتها.',
    ])
    el.append(PageBreak())

    # ================================================================== 3. Manage BOQ
    heading('الخطوة 2: جدول كميات المشروع (Manage BOQ)')
    el.append(para('من صفحة المشروع اضغط "Manage BOQ". بتبني الجدول من ثلاث مستويات: القسم Section (مثلاً Civil Works)، '
                   'المرحلة Phase، والبند الفرعي Sub-item. لكل مرحلة وبند حقول: رقم البند (No.)، الوحدة (Unit)، الكمية (Quantity)، '
                   'سعر التكلفة (Budget unit price)، وسعر العقد (Contract unit price).'))
    gap(0.08)
    el.append(para('في طريقتين للتسعير، وبتستخدم اللي بتناسب كل بند:'))
    gap(0.05)
    w = [0.6, 0.4]
    el.append(table(['متى', 'الطريقة'], [
        [cell('بند واحد بمقطوع أو بكمية وحدة، مثل "أعمال هدم" (مقطوع) أو "قصارة داخلية" (100 م²). اضغط Edit على المرحلة واملأ الوحدة والكمية والسعرين.', page_width * w[0]),
         cell('تسعير المرحلة كاملة', page_width * w[1], True)],
        [cell('المرحلة فيها بنود متعددة بكميات وأسعار مختلفة، مثل "نظام القوى" (إبريز مفرد ومزدوج ومفتاح...). اضغط Add Sub-item لكل بند.', page_width * w[0]),
         cell('تسعير البنود الفرعية', page_width * w[1], True)],
    ], w, font_size=9))
    gap(0.1)
    b = _example('1.04', 'Plastering', 'm2', 100, 30, 45, 0, 0, 0)
    mock_w = [0.13, 0.13, 0.13, 0.13, 0.09, 0.09, 0.30]
    el.append(screen_mock('BOQ Editor — Civil Works', [table(
        ['Contract total', 'Contract price', 'Budget price', 'Qty', 'Unit', 'No.', 'Item'],
        [[_money(b['contract']), '45.00', '30.00', '100', cell('m2', page_width * 0.09), '1.04', cell('Internal wall plastering', page_width * 0.28)]],
        mock_w, font_size=7.5, scale=0.93)],
        buttons=[_button('Add Phase'), _button('Weights from prices', GREEN)]))
    gap(0.1)
    el.append(para(f'النظام بيحسب: سعر التكلفة الكلي = {_money(b["budget"])} وسعر العقد الكلي = {_money(b["contract"])}، '
                   f'والهامش المخطط = {_money(b["contract"] - b["budget"])}. مجموع المرحلة هو دايماً مجموع بنودها الفرعية، '
                   'وفوق الصفحة بيظهر مجموع الميزانية والعقد والهامش للمشروع كله.'))
    gap(0.08)
    el.append(callout('المرحلة المسعّرة كاملة بيعملها النظام تلقائياً بند فرعي واحد اسمه "whole item"، حتى تقدر تسجل عليه نسبة الإنجاز. '
                      'لو أضفت بعدين بنود فرعية حقيقية، بتاخد مكانه. لا تحذفه ولا تعدله بإيدك، عدّل المرحلة نفسها.',
                      '#e8f1ff', '#0d6efd'))
    el.append(PageBreak())

    # ================================================================== 4. weights + section
    heading('الخطوة 3: الأقسام والأوزان')
    el += bullets([
        'القسم (Section): اكتب اسمه على المرحلة (مثلاً "Civil Works" أو "الأعمال الكهربائية"). النظام بيجمع مراحل القسم الواحد ويعطيك مجموع القسم، مثل "خلاصة جداول الكميات" بوثيقة العطاء.',
        'الوزن (Weight %): هو نسبة كل بند من قيمة العقد، وهو اللي بتعتمد عليه نسبة إنجاز المشروع وتقرير المالك. بدل ما تكتبه بإيدك، بعد ما تسعّر اضغط "Weights from prices" ويتوزع لحاله حسب سعر العقد.',
        'لازم تكون الأوزان بمجموع 100%. الصفحة بتبين المجموع بالأخضر إذا صح وبالأحمر إذا لا.',
        'نسبة الإنجاز (Update %): بتسجل لكل بند نسبة إنجازه التراكمية، أو بتيجي من تقارير الموقع Daily/Monthly.',
    ])
    gap(0.15)
    el.append(callout('وثيقة العطاء (مثلاً جدول كميات مشروع فاتن) غالباً بتجي بأعمدة السعر فاضية. بتحمّل الوحدات والكميات، وبعدين '
                      'بتسعّر بندًا بندًا. إذا في بنود كميتها فاضية بالوثيقة، خليها فاضية بالنظام لحد ما تنحسب.'))
    el.append(PageBreak())

    # ================================================================== 5. purchases
    heading('الخطوة 4: الشراء ونسب المواد لبند BOQ')
    el.append(para('كل سطر بطلب الشراء (PR) أو أمر الشراء المباشر (PO) فيه حقل "BOQ item". اختار البند اللي هالمادة رايحة له '
                   '(القائمة بتعرض بنود مشروع الطلب فقط). لو أنشأت أمر الشراء من عروض الأسعار RFQ، النظام بينقل البند من سطر الطلب لحاله.'))
    gap(0.08)
    w = [0.44, 0.26, 0.30]
    el.append(table(['شو بيصير بالأرقام', 'هل بينحسب "ملتزم"؟', 'حالة أمر الشراء'], [
        [cell('ما بينحسب. لسا مسودة.', page_width * w[0]), cell('لا', page_width * w[1], True), cell('Draft', page_width * w[2], True)],
        [cell('بينحسب ملتزم فوراً.', page_width * w[0]), cell('نعم', page_width * w[1], True), cell('Sent / Confirmed', page_width * w[2], True)],
        [cell('ملتزم، والمستلم منه بينحسب فعلي.', page_width * w[0]), cell('نعم', page_width * w[1], True), cell('Partially Received', page_width * w[2], True)],
        [cell('ملتزم وفعلي بالكامل.', page_width * w[0]), cell('نعم', page_width * w[1], True), cell('Fully Received', page_width * w[2], True)],
        [cell('ما بينحسب.', page_width * w[0]), cell('لا', page_width * w[1], True), cell('Cancelled', page_width * w[2], True)],
    ], w, font_size=9))
    gap(0.12)
    el += bullets([
        'الفعلي = الكمية المستلمة × سعر الوحدة بأمر الشراء. الاستلام بالموقع (Site Receiving) هو اللي بيحرّكه.',
        'المشتريات اللي ما إلها بند BOQ بتظهر بتحذير أصفر "Not assigned to a BOQ item"، وما بتنحسب بمقارنة أي ميزانية. اختار لها بنداً.',
        'كمية المادة (أكياس، أطنان) مش نفس كمية البند (م²، م³)، فالنظام بيقارن التكلفة الكلية، مش كمية المادة.',
    ])
    el.append(PageBreak())

    # ================================================================== 6. reading the page
    heading('الخطوة 5: قراءة صفحة Budget vs Actual')
    el.append(para('من قائمة Cost Control اختر "Budget vs Actual" ثم المشروع. فوق أربع بطاقات، وتحتها الجدول: القسم، ثم المرحلة، ثم بنودها.'))
    gap(0.08)
    card_style = ParagraphStyle('card', parent=S['cell'], fontSize=8)

    def card(title, value, sub, color):
        t = Table([[Paragraph(_t(title), card_style)], [Paragraph(_t(value), ParagraphStyle('v', parent=card_style, fontSize=11, fontName=FONT_BOLD_NAME))],
                   [Paragraph(_t(sub), card_style)]], colWidths=[page_width * 0.205])
        t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor(color)), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        return t

    cards = Table([[
        card('Forecast at completion', _money(eac_total), f'{_money(project_total["budget"] - eac_total)} vs budget', RED),
        card('Actual vs Earned', f'{_money(project_total["actual"])} / {_money(project_total["earned"])}', f'CPI {project_total["cpi"]}', GREEN),
        card('Committed (ordered)', _money(project_total['committed']), f'Free: {_money(project_total["uncommitted"])}', '#dddddd'),
        card('Budget (cost)', _money(project_total['budget']), f'Contract {_money(contract_total)}', '#dddddd'),
    ]], colWidths=[page_width * 0.215] * 4)

    sw = page_width * 0.93 * 0.13
    rows, bold = [], []

    def add(row, indent=False):
        name = cell(('   ' if indent else '') + row['name'], page_width * 0.93 * 0.2, not indent)
        rows.append([status_cell(row, sw), _money(row['eac']), str(row['cpi'] or '—'), _money(row['cost_variance']), _money(row['earned']),
                     _money(row['actual']), _money(row['committed']), _money(row['budget']), f"{row['progress_pct']}%", name])
        if not indent:
            bold.append(len(rows))

    for phase_row, lines in ((foundations, [concrete]), (structure, [columns]), (finishes, [tiling, painting])):
        add(phase_row)
        for line in lines:
            add(line, True)
    rows.append(['', _money(eac_total), str(project_total['cpi']), _money(project_total['cost_variance']), _money(project_total['earned']),
                 _money(project_total['actual']), _money(project_total['committed']), _money(project_total['budget']), '', cell('Project total', page_width * 0.93 * 0.2, True)])
    el.append(screen_mock('Budget vs Actual — Tower A', [cards, Spacer(1, 6), table(
        ['Status', 'Forecast', 'CPI', 'Cost var.', 'Earned', 'Actual', 'Committed', 'Budget', 'Progress', 'Item'],
        rows, [0.13, 0.10, 0.06, 0.09, 0.09, 0.09, 0.11, 0.09, 0.09, 0.15], font_size=6.6, total_row=True, scale=0.93, bold_rows=bold)]))
    gap(0.12)
    w = [0.6, 0.4]
    el.append(table(['معناها', 'الحالة (Status)'], [
        [cell('ما في طلب ولا استلام بعد.', page_width * w[0]), cell('Not started', page_width * w[1], True)],
        [cell('في أمر شراء، لكن لسا ما وصل شي.', page_width * w[0]), cell('Ordered, not received', page_width * w[1], True)],
        [cell('التكلفة ضمن ±5% من قيمة الشغل المنجز (CPI بين 0.95 و1.05).', page_width * w[0]), cell('On track', page_width * w[1], True, GREEN)],
        [cell('صرفت أكثر من قيمة الشغل المنجز (CPI أقل من 0.95).', page_width * w[0]), cell('Over cost', page_width * w[1], True, RED)],
        [cell('صرفت أقل من قيمة الشغل المنجز (CPI أكثر من 1.05).', page_width * w[0]), cell('Under cost', page_width * w[1], True)],
        [cell('صرفت فلوس لكن ما في نسبة إنجاز مسجلة. غالباً تقرير الإنجاز ناقص.', page_width * w[0]), cell('Spent, no progress recorded', page_width * w[1], True, '#a15c00')],
        [cell('طلبت من الموردين أكثر من ميزانية البند كلها.', page_width * w[0]), cell('Ordered more than budget', page_width * w[1], True, RED)],
    ], w, font_size=8.5))
    el.append(PageBreak())

    # ================================================================== 7. worked example
    heading('مثال محسوب خطوة بخطوة')
    c, e = columns, columns_early
    el.append(para(f'البند 2.1 "{c["name"]}": الكمية {c["quantity"]:,.0f} م³، سعر التكلفة {c["budget_price"]:,.0f}، سعر العقد {c["contract_price"]:,.0f}. '
                   'الإنجاز المسجل 55%.'))
    gap(0.08)
    w = [0.42, 0.33, 0.25]
    el.append(para('أولاً، بعد استلام مواد بقيمة 45,000:'))
    gap(0.05)
    el.append(table(['القيمة', 'كيف بتنحسب', 'الرقم'], [
        [_money(e['budget']), cell('250 × 480', page_width * w[1]), cell('Budget', page_width * w[2], True)],
        [_money(e['earned']), cell('120,000 × 55%', page_width * w[1]), cell('Earned', page_width * w[2], True)],
        [_money(e['actual']), cell('المواد المستلمة', page_width * w[1]), cell('Actual', page_width * w[2], True)],
        [_money(e['cost_variance']), cell('Earned − Actual', page_width * w[1]), cell('Cost variance', page_width * w[2], True)],
        [str(e['cpi']), cell('Earned ÷ Actual', page_width * w[1]), cell('CPI', page_width * w[2], True)],
    ], w, font_size=9.5))
    el.append(para(f'النتيجة: {e["status_label"]}.'))
    gap(0.15)
    el.append(para('ثانياً، بعد استلام مواد بقيمة 75,000 (نفس الـ 55% إنجاز):'))
    gap(0.05)
    el.append(table(['القيمة', 'كيف بتنحسب', 'الرقم'], [
        [_money(c['actual']), cell('المواد المستلمة', page_width * w[1]), cell('Actual', page_width * w[2], True)],
        [_money(c['cost_variance']), cell('66,000 − 75,000', page_width * w[1]), cell('Cost variance', page_width * w[2], True)],
        [str(c['cpi']), cell('66,000 ÷ 75,000', page_width * w[1]), cell('CPI', page_width * w[2], True)],
        [_money(c['eac']), cell('Budget × Actual ÷ Earned = 120,000 × 75,000 ÷ 66,000', page_width * w[1]), cell('Forecast (EAC)', page_width * w[2], True)],
        [_money(c['vac']), cell('120,000 − Forecast', page_width * w[1]), cell('Variance at completion', page_width * w[2], True)],
    ], w, font_size=9.5, highlight={(3, 0): '#f8d7da'}))
    el.append(para(f'النتيجة: {c["status_label"]}. لاحظ أنك صرفت 62% من الميزانية الكاملة ({_money(c["actual"])} من {_money(c["budget"])}) '
                   'والشغل المنجز 55% فقط.'))
    gap(0.15)
    el.append(para('كمية العمل وتكلفة الوحدة (الكمية المنفذة = الكمية المخططة × نسبة الإنجاز):'))
    gap(0.05)
    el.append(table(['القيمة', 'كيف بتنحسب', 'الرقم'], [
        [f'{c["executed_qty"]:,.1f}', cell('250 × 55%', page_width * w[1]), cell('Executed qty', page_width * w[2], True)],
        [_money(c['actual_unit_cost']), cell('75,000 ÷ 137.5', page_width * w[1]), cell('Actual unit cost', page_width * w[2], True)],
        [_money(c['budget_price']), cell('سعر الميزانية للوحدة', page_width * w[1]), cell('Budget unit price', page_width * w[2], True)],
        [_money(c['unit_cost_variance']), cell('كل م³ منفذ عم يكلف أكثر بهالمبلغ', page_width * w[1]), cell('Difference', page_width * w[2], True)],
    ], w, font_size=9.5, total_row=True))
    el.append(PageBreak())

    # ================================================================== 8. acting on it
    heading('ماذا أفعل عند ظهور انحراف؟')
    w = [0.55, 0.45]
    el.append(table(['التصرف', 'اللي بتشوفه'], [
        [cell('راجع الأسعار بأوامر الشراء المنسوبة للبند. غيّر المورد أو فاوض، أو حدّث سعر الميزانية إذا السوق تغير فعلاً.', page_width * w[0]), cell('Actual unit cost أعلى من Budget unit price', page_width * w[1], True)],
        [cell('راجع الكميات المستلمة والهدر. تأكد إن نسبة الإنجاز محدّثة وصحيحة قبل ما تتهم أحد.', page_width * w[0]), cell('Over cost والأسعار مطابقة', page_width * w[1], True)],
        [cell('اطلب من موظف الموقع تحديث الإنجاز. الإنجاز الناقص بيظهر البند متجاوز وهو مش كذلك.', page_width * w[0]), cell('Spent, no progress recorded', page_width * w[1], True)],
        [cell('راجع أوامر الشراء المفتوحة قبل ما توافق على طلبات جديدة لنفس البند. ممكن تلغي أو تخفض.', page_width * w[0]), cell('Ordered more than budget', page_width * w[1], True)],
        [cell('اختار لها بند BOQ من سطر الطلب أو أمر الشراء عشان تدخل المقارنة.', page_width * w[0]), cell('تحذير Not assigned to a BOQ item', page_width * w[1], True)],
        [cell('الهامش المتوقع (Forecast margin) أقل من المخطط. ارفع الأمر للإدارة.', page_width * w[0]), cell('Forecast أعلى من الميزانية', page_width * w[1], True)],
    ], w, font_size=9))
    gap(0.2)
    el.append(para('الداشبورد (Cost Control Dashboard): اختر المشروع فبتشوف نفس البطاقات الأربع، مع رسم بياني لكل مرحلة '
                   '(Budgeted / Committed / Earned / Actual) وعدد البنود حسب حالة التكلفة، وآخر التنبيهات.'))
    el.append(PageBreak())

    # ================================================================== 8b. AI assistant while working
    heading('المساعد الذكي أثناء العمل: الفقاعة ومراجعة المشروع')
    el.append(para('بعد ما يصير المشروع مسعّراً وعليه مشتريات، المساعد بيفيدك بثلاث طرق. كلها للقراءة فقط: ما بيغيّر أي رقم ولا بيعتمد ولا بيطلب شي.'))
    gap(0.08)
    el.append(para('1) فقاعة المحادثة. بأسفل يمين كل صفحة (للأدمن ومدير الهندسة والمدير العام ومدير المشروع) بتلاقي أيقونة المساعد، '
                   'وأول ما تفتح صفحة بتطلع رسالة ترحيب صغيرة. اضغطها فبتفتح المحادثة على المشروع اللي أنت فيه (وبتقدر تغيّر المشروع من القائمة اللي بأعلاها). '
                   'اسأله بالعربي أو الإنجليزي، أو اضغط على أحد الأسئلة الجاهزة.'))
    gap(0.08)
    bubble_w = page_width * 0.78
    user_bubble = Table([[rtl_paragraph('وين وصلنا بالميزانية؟ في بنود تجاوزت؟', S['cell'], bubble_w - 16)]], colWidths=[bubble_w])
    user_bubble.hAlign = 'RIGHT'
    user_bubble.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#dbe7ff')), ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor(BLUE)),
                                     ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    bot_bubble = Table([[rtl_paragraph('بند 2.1 (Columns and slabs) صرفت عليه 75,000 من ميزانية 120,000 والإنجاز المسجل 55%، فهو متجاوز للتكلفة (CPI 0.88). '
                                       'أنصحك تراجع أسعار أوامر الشراء المنسوبة له.', S['cell'], bubble_w - 16)]], colWidths=[bubble_w])
    bot_bubble.hAlign = 'LEFT'
    bot_bubble.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.white), ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#d0d5dd')),
                                    ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    el.append(screen_mock('AI Assistant — FTN (chat bubble)', [user_bubble, bot_bubble]))
    gap(0.1)
    el += bullets([
        'إجاباته من بيانات المشروع الحية (BOQ، Budget vs Actual، المشتريات، الإنجاز، التأمين). لو الجواب مش موجود بالبيانات بيقلك شو الناقص.',
        'المحادثة بتنحفظ بالمتصفح فقط وبتنمسح لما تسكّر التبويب. زر ↺ بيبدأ محادثة جديدة. الحد 40 سؤال بالساعة لكل مستخدم.',
    ])
    gap(0.12)
    el.append(para('2) مراجعة المشروع. من صفحة AI Assistant اضغط "Review project" (وتقدر تكتب تركيز، مثل "ركّز على الأعمال الكهربائية"). '
                   'بيقرأ كل شي بالمشروع ويرجّعلك ملخص وقائمة ملاحظات مرتبة (Error ثم Warning ثم Info)، لكل ملاحظة الأرقام اللي استند عليها والإجراء المقترح. '
                   'بياخد دقائق.'))
    gap(0.1)
    el.append(para('3) فحوصات صحة المشروع (Project health checks). بنفس الصفحة، وبتشتغل دايماً بدون ذكاء اصطناعي وبدون تكلفة. أمثلة:'))
    gap(0.05)
    w = [0.5, 0.5]
    el.append(table(['الفحص', 'المجال'], [
        [cell('مجموع الأوزان مش 100%، بنود بكمية بدون سعر، بنود مسعّرة بأقل من تكلفتها، مراحل فاضية', page_width * w[0]), cell('BOQ', page_width * w[1], True)],
        [cell('بوليصة تأمين منتهية أو قريبة الانتهاء، أو مشروع Active بدون تأمين', page_width * w[0]), cell('Insurance', page_width * w[1], True)],
        [cell('بنود متجاوزة أو مطلوب منها أكثر من الميزانية، مشتريات بدون بند BOQ، CPI أقل من 0.95', page_width * w[0]), cell('Cost', page_width * w[1], True)],
        [cell('آخر تسجيل إنجاز أقدم من 45 يوماً، أو ما في إنجاز مسجل أبداً', page_width * w[0]), cell('Progress', page_width * w[1], True)],
        [cell('طلبات شراء معلّقة للموافقة أكثر من أسبوع، وأوامر شراء تأخر موعد توريدها', page_width * w[0]), cell('Procurement', page_width * w[1], True)],
    ], w, font_size=9))
    gap(0.12)
    el.append(callout('المساعد ممكن يغلط، وكل ما كانت الوثيقة أعقد أو الجهاز أضعف زادت الأخطاء. اعتبر كلامه تنبيه يوجّهك للمكان الصح، '
                      'وتأكد من أي رقم مهم من Budget vs Actual أو الوثيقة الأصلية قبل ما تبني عليه قرار.'))
    gap(0.1)
    el.append(para('للمسؤول (إعداد المساعد): بملف .env إما تحط ANTHROPIC_API_KEY (Claude: الوثائق والأسئلة بتنرسل لخدمة Anthropic)، '
                   'أو AI_PROVIDER=ollama لتشغيل موديل مفتوح على جهاز الشركة (ما بيطلع شي برا الشركة وبدون رسوم استخدام، لكن دقته أقل خصوصاً على الجداول، '
                   'وبدو جهاز قوي). فحوصات الصحة بتشتغل بدون أي إعداد.', 'note'))
    el.append(PageBreak())

    # ================================================================== 8c. drawings: materials, quantities, EDGE
    heading('تحليل المخططات: المواد والكميات وبيانات المباني الخضراء (EDGE)')
    el.append(para('لما ترفع مخطط بصفحة Drawings، المساعد الذكي بيقراه (تلقائياً إذا كان المساعد مفعّل) ويطلعلك المواد والكميات المكتوبة عليه، '
                   'وبيربطها بالـ BOQ المسعّر، وبيجمع معلومات المباني الخضراء. تقدر تشغّله كمان بزر "Analyze" (أو "Re-analyze") جنب كل نسخة مخطط، '
                   'أو من صفحة AI Assistant باختيار "Materials, quantities & green-building (EDGE) data" لمخطط أو لملف مواصفات.'))
    gap(0.08)
    w = [0.62, 0.38]
    el.append(table(['شو بتلاقي', 'التبويب'], [
        [cell('قائمة المواد والعناصر حسب الفئة (مواد، تشطيبات، أبواب وشبابيك، إنشائي، ميكانيك وكهرباء...)، مع المواصفة والمكان والكمية والصفحة. '
              'المادة اللي كميتها مش مكتوبة بتنذكر برضو وكميتها "not stated".', page_width * w[0]), cell('Materials & quantities', page_width * w[1], True)],
        [cell('كل بند من المخطط مربوط ببند BOQ بنفس الرقم: الكميات بتنجمع لكل بند وبتقارن بكمية الـ BOQ (الفرق الموجب معناه المخطط بيطلب أكثر من الـ BOQ)، '
              'وتكلفة كمية المخطط = الكمية × سعر التكلفة بالـ BOQ. الجمع والمقارنة والتسعير بالكود، مش بالذكاء الاصطناعي.', page_width * w[0]),
         cell('Compared with the BOQ', page_width * w[1], True)],
        [cell('نقاط بيانات EDGE اللي ذكرها المستند: القشرة الخارجية والزجاج والعزل، أنظمة التبريد والإضاءة والطاقة المتجددة، تدفق الأدوات الصحية والري '
              'وحصاد المياه، ومواد الأرضيات والجدران والسقف. اللي مش مذكور بيظهر "Not stated".', page_width * w[0]), cell('Green building (EDGE)', page_width * w[1], True)],
    ], w, font_size=9))
    gap(0.1)
    el.append(para('صفحة "Green-building summary" (زر بصفحة AI Assistant) بتجمع نقاط EDGE من كل المخططات والمواصفات المحللة بالمشروع بمكان واحد، '
                   'وبتبين شو لسا ناقص عشان تطلبه من المصمم، وبتنزّل كملف Excel. EDGE نظام تصنيف من IFC للمباني اللي بتوفر 20% على الأقل من الطاقة والمياه والطاقة '
                   'الكامنة بالمواد مقارنة بمبنى مرجعي محلي.'))
    gap(0.08)
    el.append(callout('مهم: النظام ما بيحسب وفورات EDGE ولا بيعطي شهادة ولا نتيجة. الحساب بيتم بتطبيق EDGE الرسمي مع خط الأساس المحلي، وهاي الصفحة بتجهّز '
                      'المدخلات وبتبين الناقص. القراءة من المخطط بتنقل اللي مكتوب فقط: ما بتقيس بالمسطرة ولا بتعدّ الرموز ولا بتجمع أرقام من عندها. ملفات DWG لازم تتصدّر PDF، '
                      'والوحدة لو اختلفت عن وحدة الـ BOQ ما بتنسّعر. راجع الأرقام المهمة بالمخطط الأصلي.'))
    gap(0.1)
    el += bullets([
        'الخطوات لبلوغ مرحلة EDGE: ارفع كل المخططات (معماري، إنشائي، كهرباء، ميكانيك، تشطيبات) والمواصفات، دعها تنحلل، افتح Green-building summary، واطلب الناقص من المصمم.',
        'كل ما زاد عدد الوثائق المحللة قلّ الناقص. النقاط اللي بتظهر Unsure أو Check راجعها بالمخطط قبل ما تدخلها بتطبيق EDGE.',
        'الإعداد (للمسؤول): AI_AUTO_ANALYZE_DRAWINGS=0 بملف .env بيطفي التحليل التلقائي عند الرفع. مع Claude الملف بينرسل لـ Anthropic، ومع Ollama المحلي لا.',
    ])
    el.append(PageBreak())

    # ================================================================== 9. FAQ
    heading('أسئلة شائعة')
    faq = [
        ('البند ما بيظهر بصفحة Budget vs Actual', 'لازم يكون مسعّر (كمية وسعر) أو عليه مشتريات. بند بدون أسعار وبدون شراء ما بيظهر.'),
        ('كل الأرقام أصفار', 'ما في استلام بعد أو أوامر شراء صادرة لبنود هالمشروع. الأصفار طبيعية بأول المشروع.'),
        ('المشتريات ما ظهرت عند أي بند', 'ما اخترت "BOQ item" على السطر. راجع التحذير الأصفر واختار البند من الطلب أو أمر الشراء.'),
        ('ظهر بند اسمه whole item', 'هاد البند التلقائي للمرحلة المسعّرة كاملة. سجّل عليه الإنجاز، وعدّل الأسعار من المرحلة نفسها.'),
        ('الأوزان لا تساوي 100%', 'اضغط "Weights from prices" بعد ما تسعّر، أو عدّلها يدوياً.'),
        ('ما قدرت أنشئ طلب مواد أو تقرير لمشروع، أو ظهرت رسالة "Work is blocked"', 'المشروع مقفول للعمل: لسا Planning، أو ما عليه تأمين ساري بوثيقته، أو الـ BOQ مش مسعّر بالكامل. شريط أحمر بأعلى صفحة المشروع والـ Workflow بيبين السبب بالضبط. عالجه (ارفع التأمين، أو كمّل الكميات والأسعار بـ Manage BOQ) وبينفتح المشروع فوراً.'),
        ('الصرف من المستودع لمشروع ما ظهر بالفعلي', 'الفعلي حالياً من الاستلام على أوامر الشراء فقط. الصرف من المستودع لسا ما بيدخل بحساب التكلفة.'),
        ('كيف أطبع التقرير أو جدول الكميات للمدير العام؟', 'من صفحة Budget vs Actual (أو صفحة المشروع) اختر المشروع ثم Print report للتقرير أو Print BOQ لجدول الكميات. بيفتح PDF جاهز للطباعة بترويسة الشركة ومكان توقيع المدير العام ومدير الهندسة ومدير المشروع. متاح للأدمن والمدير العام ومدير الهندسة ومدير المشروع نفسه.'),
        ('المساعد الذكي مش شغّال (رسالة "AI assistant isn’t switched on yet")', 'المساعد لسا ما تم إعداده. اطلب من المسؤول يضبطه بملف .env (مفتاح Claude أو Ollama المحلي). فحوصات الصحة بتشتغل بدونه.'),
        ('الاستيراد تخطّى بنود', 'البنود اللي رقمها موجود أصلاً بالـ BOQ، أو اللي بدون رقم، بتنتخطى، والرسالة بتبين عددها. أضف الناقص يدوياً من Manage BOQ.'),
        ('المسودة فيها بنود ناقصة أو كميات غلط', 'راجع "Things the reader noticed". الوثيقة الكبيرة قسّمها لأجزاء، والمخططات صدّرها PDF واضح. الملف الممسوح ضوئياً أصعب على القارئ. قارن دايماً بالأصل قبل الاستيراد.'),
        ('هل وثائقي بتطلع برا الشركة؟', 'مع Claude نعم: الوثيقة والأسئلة بتنرسل لخدمة Anthropic. مع Ollama المحلي لا، كل شي بيتعالج على جهاز الشركة. الإعداد بيحدده المسؤول.'),
        ('فقاعة المحادثة ما ظهرت عندي', 'بتظهر للأدمن ومدير الهندسة والمدير العام ومدير المشروع (لمشاريعه فقط). موظف الموقع والمشتريات ما بيشوفوها.'),
        ('بدي أحتفظ بالميزانية الأصلية قبل التعديل', 'لسا ما في تجميد للخط الأساسي ولا أوامر تغيير. أي تعديل بيكتب فوق القديم، فسجّل الأصل خارج النظام.'),
    ]
    el.append(table(['الجواب', 'السؤال'], [[cell(a, page_width * 0.55), cell(q, page_width * 0.45, True)] for q, a in faq], [0.55, 0.45], font_size=9))
    gap(0.2)
    heading('ملخص المعادلات')
    el.append(table(['المعادلة', 'الرقم'], [
        [cell('الكمية × سعر التكلفة (للبند)، ومجموع البنود للمرحلة', page_width * 0.6), cell('Budget', page_width * 0.4, True)],
        [cell('الكمية × سعر العقد', page_width * 0.6), cell('Contract', page_width * 0.4, True)],
        [cell('قيمة أوامر الشراء الصادرة المنسوبة للبند', page_width * 0.6), cell('Committed', page_width * 0.4, True)],
        [cell('الكمية المستلمة × سعر أمر الشراء', page_width * 0.6), cell('Actual', page_width * 0.4, True)],
        [cell('Budget × نسبة الإنجاز', page_width * 0.6), cell('Earned', page_width * 0.4, True)],
        [cell('Earned − Actual (سالب = تجاوز)', page_width * 0.6), cell('Cost variance', page_width * 0.4, True)],
        [cell('Earned ÷ Actual (أقل من 0.95 = تجاوز)', page_width * 0.6), cell('CPI', page_width * 0.4, True)],
        [cell('Budget × Actual ÷ Earned، وما بينزل عن الملتزم', page_width * 0.6), cell('Forecast (EAC)', page_width * 0.4, True)],
        [cell('Actual ÷ الكمية المنفذة', page_width * 0.6), cell('Actual unit cost', page_width * 0.4, True)],
    ], [0.6, 0.4], font_size=9))

    doc.build(el)
    return buffer.getvalue()
