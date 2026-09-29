"""
"Engineering drawings" user guide -- PDF, Arabic-narrated with the real English on-screen labels quoted verbatim, in the same
style as the Procurement, HR and Pricing guides (drawn mock-ups of the real screens, not literal screenshots).

The lists it quotes (disciplines, statuses, accepted file types, size limit) are read from the same code the pages use, so the
guide cannot drift from the system.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from procurement.manual_pdf import BLUE, GREEN, GREY, LIGHT, RED, _badge, _button, _styles
from projects.validators import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES
from reports.utils import FONT_BOLD_NAME, FONT_NAME, _owner_report_logo_path, _t, rtl_paragraph

from .models import Blueprint, BlueprintRevision

AMBER = '#d99a00'


def generate_blueprints_manual_pdf():
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=0.8 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch, title="Engineering Drawings - User Guide",
    )
    page_width = A4[0] - 1.6 * inch
    S = _styles()
    el = []

    # ------------------------------------------------------------------ helpers
    def para(text, style='body', width=None):
        return rtl_paragraph(text, S[style], width or page_width)

    def cell(text, width, bold=False, color=None):
        style = ParagraphStyle('c', parent=S['cell'], fontName=FONT_BOLD_NAME if bold else FONT_NAME,
                               textColor=colors.HexColor(color) if color else colors.black)
        return rtl_paragraph(text, style, width - 10)

    def bullets(items):
        return [para(f'•  {t}') for t in items]

    def heading(text):
        el.append(Paragraph(_t(text), S['step_title']))

    def gap(h=0.12):
        el.append(Spacer(1, h * inch))

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

    def table(headers, rows, widths, font_size=8.5, scale=1.0):
        size = min(9, font_size)
        head = [Paragraph(_t(h), ParagraphStyle('h', parent=S['cell'], fontName=FONT_BOLD_NAME, textColor=colors.white,
                                                 fontSize=size, leading=size + 2)) for h in headers]
        t = Table([head] + rows, colWidths=[w * page_width * scale for w in widths], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.grey), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), font_size), ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT)]),
        ]))
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

    disciplines = ', '.join(label for _, label in Blueprint.DISCIPLINES)
    extensions = ' '.join(sorted(ALLOWED_EXTENSIONS))
    max_mb = MAX_UPLOAD_BYTES // 1024 // 1024
    status_labels = dict(BlueprintRevision.STATUS)

    # ================================================================== cover
    logo = _owner_report_logo_path()
    if logo:
        img = Image(logo, width=3.2 * inch, height=0.75 * inch, kind='proportional')
        img.hAlign = 'CENTER'
        el += [img, Spacer(1, 0.2 * inch)]
    el.append(Paragraph(_t('دليل المخططات الهندسية'), S['title']))
    el.append(Paragraph('Blueprints & Drawings — User Guide', S['sub']))
    gap(0.1)
    el.append(Paragraph(_t('من رفع المخطط حتى اعتماده للتنفيذ وقراءته بالذكاء الاصطناعي'), S['sub']))
    gap(0.15)
    el.append(para('تنويه: الشاشات في هذا الدليل محاكاة مرسومة لنفس شكل النظام الفعلي، وأسماء المشاريع والمخططات أمثلة وليست بيانات حقيقية.', 'note'))
    el.append(PageBreak())

    # ================================================================== 1. big picture
    heading('الفكرة العامة')
    el.append(para('المخطط الهندسي ما بينبني منه شي بالنظام إلا بعد ما ينعتمد. كل مخطط (ورقة) إله رقم واسم وتخصص، وكل مرة تتغير فيها الورقة بترفع نسخة جديدة '
                   '(Revision) منها. النسخة الوحيدة اللي بينبني عليها هي النسخة المعتمدة "Approved for construction". واعتماد أول مخطط هو اللي بيفتح '
                   'آخر مرحلة من مراحل بدء المشروع.'))
    gap(0.1)
    flow(['التأمين ساري بوثيقته (مرحلة Insurance)', 'وثائق العطاء مرفوعة (مرحلة Tender documents)',
          'رفع المخطط: ورقة جديدة برقمها ونسختها الأولى', 'الاعتماد أو الرفض من المسؤول',
          'جدول الكميات (BOQ) مسعّر بالكامل + مخطط معتمد = إكمال المرحلة الأخيرة', 'المشروع يصير Active ويبدأ العمل'])
    gap(0.15)
    w = [0.62, 0.38]
    el.append(table(['شو معناه', 'المصطلح'], [
        [cell('ورقة المخطط: لها رقم واسم وتخصص، والرقم ما بيتكرر بنفس المشروع.', page_width * w[0]), cell('Drawing / Blueprint', page_width * w[1], True)],
        [cell('نسخة من الورقة (0 أو A أو B...). كل تعديل على الورقة بينرفع كنسخة جديدة، والقديمة بتنحفظ.', page_width * w[0]), cell('Revision', page_width * w[1], True)],
    ], w, font_size=9))
    gap(0.12)
    el.append(para('حالة كل نسخة:'))
    gap(0.05)
    el.append(table(['شو بيصير', 'الحالة'], [
        [cell('انرفعت وبانتظار قرار المسؤول. ما بينبني عليها.', page_width * w[0]), cell(status_labels['pending'], page_width * w[1], True, AMBER)],
        [cell('معتمدة. هي النسخة اللي بينبني عليها.', page_width * w[0]), cell(status_labels['approved'], page_width * w[1], True, GREEN)],
        [cell('انرفضت مع ذكر السبب. بتضل محفوظة للسجل.', page_width * w[0]), cell(status_labels['rejected'], page_width * w[1], True, RED)],
        [cell('كانت معتمدة وحلّت مكانها نسخة أحدث معتمدة.', page_width * w[0]), cell(status_labels['superseded'], page_width * w[1], True, GREY)],
    ], w, font_size=9))
    el.append(PageBreak())

    # ================================================================== 2. roles
    heading('الأدوار والصلاحيات')
    w = [0.55, 0.45]
    el.append(table(['الصلاحية', 'الدور'], [
        [cell('يرفع مخططات ونسخ ويعتمد ويرفض، ويشغّل التحليل الذكي، لكل المشاريع', page_width * w[0]), cell('الأدمن (Admin)', page_width * w[1], True)],
        [cell('نفس صلاحيات الأدمن، لكل المشاريع', page_width * w[0]), cell('مدير الهندسة (Engineering Manager)', page_width * w[1], True)],
        [cell('نفس الصلاحيات لمشروعه هو فقط', page_width * w[0]), cell('مدير المشروع (Project Manager)', page_width * w[1], True)],
        [cell('يرفع مخططات ونسخ لمشروعه فقط، وما بيعتمد ولا بيرفض', page_width * w[0]), cell('موظف الموقع (Site Engineer)', page_width * w[1], True)],
        [cell('يشوف المخططات ونتائج التحليل الذكي بدون رفع أو اعتماد', page_width * w[0]), cell('المدير العام (General Manager)', page_width * w[1], True)],
    ], w, font_size=9.5))
    gap(0.15)
    el.append(para('قبل ما تبدأ:'))
    el += bullets([
        'صفحة المخططات بتنفتح للرفع بعد ما تكتمل مرحلتين: التأمين ووثائق العطاء. قبلها بتشوف رسالة "Drawings open after the insurance and tender-document stages are complete" '
        'ورابط لصفحة Workflow.',
        'المشروع لازم يكون عليه تأمين ساري وBOQ مسعّر بالكامل حتى ينفتح للعمل. اعتماد المخطط لحاله ما بيكفي لإكمال المرحلة الأخيرة.',
    ])
    el.append(PageBreak())

    # ================================================================== 3. opening the page
    heading('الخطوة 1: فتح صفحة المخططات')
    el.append(para('من القائمة الجانبية اختر "Blueprints"، أو من صفحة Workflow. بتشوف قائمة المشاريع وكم مخطط عند كل واحد وكم منها معتمد وكم بانتظار الاعتماد. '
                   'المشروع اللي لسا ما اكتملت مراحله الأولى بيظهر عليه "Locked". اضغط "Open" لفتح مخططات المشروع.'))
    gap(0.08)
    dw = [0.13, 0.17, 0.13, 0.13, 0.44]
    el.append(screen_mock('Blueprints & Drawings', [table(
        ['', 'Awaiting approval', 'Approved', 'Drawings', 'Project'],
        [[_button('Open'), '2', '3', '5', cell('Tower A (TA)', page_width * 0.44 * 0.93)],
         [_badge('Locked', GREY), '0', '0', '0', cell('Villa B (VB)', page_width * 0.44 * 0.93)]],
        dw, font_size=8, scale=0.93)]))
    gap(0.15)
    el.append(para('صفحة مخططات المشروع فيها بطاقة لكل ورقة: رقمها واسمها وتخصصها، وتحتها جدول نسخها بحالة كل نسخة وتاريخ الرفع والمراجعة. '
                   'فوق الصفحة زر "Upload a drawing" (للي إله صلاحية الرفع) وزر "Project workflow".'))
    el.append(PageBreak())

    # ================================================================== 4. upload
    heading('الخطوة 2: رفع مخطط جديد')
    el.append(para('اضغط "Upload a drawing" واملأ البيانات. بترفع الورقة ونسختها الأولى بخطوة وحدة.'))
    gap(0.08)
    rows = [
        [cell('Drawing number', page_width * 0.5, True), cell('S-01', page_width * 0.5)],
        [cell('Title', page_width * 0.5, True), cell('Foundation plan', page_width * 0.5)],
        [cell('Discipline', page_width * 0.5, True), cell('Structural', page_width * 0.5)],
        [cell('Revision', page_width * 0.5, True), cell('0', page_width * 0.5)],
        [cell('File', page_width * 0.5, True), cell('foundation-plan.pdf', page_width * 0.5)],
        [cell('Notes', page_width * 0.5, True), cell('Issued for construction', page_width * 0.5)],
    ]
    form = Table(rows, colWidths=[page_width * 0.45, page_width * 0.45])
    form.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d5dd')), ('BACKGROUND', (0, 0), (0, -1), colors.HexColor(LIGHT)),
                              ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    el.append(screen_mock('Upload a drawing — Tower A', [form], buttons=[_button('Upload', GREEN)]))
    gap(0.1)
    w = [0.68, 0.32]
    el.append(table(['شو تكتب', 'الحقل'], [
        [cell('رقم الورقة كما هو على المخطط. ما بينقبل رقم مكرر بنفس المشروع: افتح الورقة الموجودة وارفع نسخة جديدة منها.', page_width * w[0]), cell('Drawing number', page_width * w[1], True)],
        [cell('اسم المخطط، مثل "Ground floor plan".', page_width * w[0]), cell('Title', page_width * w[1], True)],
        [cell(f'التخصص من القائمة: {disciplines}.', page_width * w[0]), cell('Discipline', page_width * w[1], True)],
        [cell('رقم أو حرف النسخة: 0 أو A أو B أو R1.', page_width * w[0]), cell('Revision', page_width * w[1], True)],
        [cell(f'الملف. الأنواع المقبولة: PDF والصور (jpg وpng وtif) وملفات الرسم (dwg وdxf وrvt وifc) وzip وrar وملفات المكتب، حتى {max_mb} ميغابايت.', page_width * w[0]),
         cell('File', page_width * w[1], True)],
        [cell('ملاحظة اختيارية، مثل سبب التعديل.', page_width * w[0]), cell('Notes', page_width * w[1], True)],
    ], w, font_size=9))
    gap(0.12)
    el.append(callout('ارفع المخطط بصيغة PDF كلما أمكن. المساعد الذكي بيقرا PDF والصور، وملفات DWG وDXF وRVT وIFC لازم تصدّرها PDF من برنامج الرسم حتى تنقرأ. '
                      'وبعد الرفع بيبين النظام رسالة إنه المخطط بانتظار الاعتماد، وإذا كان المساعد الذكي مفعّل بيبدأ قراءته تلقائياً.'))
    el.append(PageBreak())

    # ================================================================== 5. revisions + approval
    heading('الخطوة 3: نسخة جديدة واعتماد المخطط')
    el.append(para('لما يتعدل المخطط، ما بتنشئ ورقة جديدة. من بطاقة الورقة اضغط "New revision" وارفع الملف الجديد مع رقم النسخة. رقم النسخة ما بيتكرر على نفس الورقة.'))
    gap(0.08)
    aw = [0.30, 0.15, 0.15, 0.30, 0.10]
    approve_cell = Table([[_button('Approve', GREEN), _button('Reject', RED)]])
    el.append(screen_mock('Engineering Drawings — Tower A', [
        cell('S-01 — Foundation plan   [Structural]', page_width * 0.9, True),
        table(['', 'Reviewed', 'Uploaded', 'Status', 'Rev.'],
              [[approve_cell, '—', '2026-09-10', _badge(status_labels['pending'], AMBER), 'A'],
               ['', '2026-08-02', '2026-08-01', _badge(status_labels['approved'], GREEN), '0']],
              aw, font_size=8, scale=0.93)],
        buttons=[_button('New revision')]))
    gap(0.12)
    el += bullets([
        'الاعتماد والرفض بس للأدمن ومدير الهندسة ومدير المشروع، وبس على نسخة بحالة "Awaiting approval".',
        'لما تضغط "Approve": النسخة بتصير "Approved for construction"، والنسخة المعتمدة قبلها من نفس الورقة بتصير "Superseded". بأي وقت في نسخة معتمدة وحدة فقط لكل ورقة.',
        'لما تضغط "Reject": بيطلع لك سؤال عن السبب، والسبب إلزامي. النسخة بتصير "Rejected" وبيظهر سببها جنبها.',
        'ما في حذف للنسخ. لو رفعت نسخة غلط، ارفضها بسبب واضح وارفع الصحيحة كنسخة جديدة.',
    ])
    gap(0.1)
    el.append(callout('اعتماد أول مخطط مع BOQ مسعّر بالكامل هو شرط إكمال المرحلة الأخيرة "Start work from approved drawings" بصفحة Workflow، واللي بتنقل المشروع من Planning إلى Active. '
                      'بعد الاعتماد اضغط إكمال المرحلة من صفحة Workflow.', '#e8f1ff', '#0d6efd'))
    el.append(PageBreak())

    # ================================================================== 6. AI
    heading('الخطوة 4: قراءة المخطط بالذكاء الاصطناعي')
    el.append(para('بجنب كل نسخة بصفحة المخططات بيظهر ما يخص المساعد الذكي (AI Assistant)، وبيقرأ المكتوب على المخطط: المواد والكميات، وبيربطها بالـ BOQ المسعّر، '
                   'وبيجمع بيانات المباني الخضراء (EDGE).'))
    gap(0.08)
    w = [0.62, 0.38]
    el.append(table(['شو معناه', 'الزر أو العلامة'], [
        [cell('بيبدأ لحاله بعد الرفع إذا كان المساعد مفعّل. بتظهر رسالة، وبالجدول علامة "Analyzing...".', page_width * w[0]), cell('تلقائي عند الرفع', page_width * w[1], True)],
        [cell('اضغطه لقراءة النسخة يدوياً. للأدمن ومدير الهندسة ومدير المشروع، ويظهر فقط إذا المساعد مفعّل. بعد أول قراءة بيصير "Re-analyze".', page_width * w[0]), cell('Analyze', page_width * w[1], True, GREEN)],
        [cell('انتهت القراءة. اضغطه لتشوف المواد والكميات ومقارنتها بالـ BOQ وبيانات EDGE، وتنزّل قائمة Excel.', page_width * w[0]), cell('AI analysis', page_width * w[1], True, GREEN)],
        [cell('فشلت القراءة. مرّر الماوس أو افتحها لتشوف السبب (مثلاً ملف DWG أو مفتاح غير مضبوط).', page_width * w[0]), cell('AI failed', page_width * w[1], True, RED)],
    ], w, font_size=9))
    gap(0.12)
    el += bullets([
        'القراءة تنقل المكتوب على المخطط فقط (جداول، ملاحظات، مساحات مطبوعة). ما بتقيس بالمسطرة ولا بتعدّ الرموز، فالكمية غير المكتوبة بتضل فاضية.',
        'صفحة "Green-building summary" بتجمع نقاط EDGE من كل المخططات وبتبين الناقص لتطلبه من المصمم. النظام ما بيحسب وفورات EDGE، الحساب بتطبيق EDGE الرسمي.',
        'شرح النتائج بالتفصيل بدليل التسعير ومتابعة التكلفة (قسم تحليل المخططات).',
    ])
    gap(0.12)
    el.append(callout('راجع الأرقام المهمة بالمخطط الأصلي قبل ما تعتمد عليها: القراءة ممكن تغلط، خصوصاً بالمخططات المعقدة أو الممسوحة ضوئياً. '
                      'مع مزوّد Claude الملف بينرسل لخدمة Anthropic، ومع Ollama المحلي بيضل على جهاز الشركة.'))
    el.append(PageBreak())

    # ================================================================== 7. FAQ
    heading('أسئلة شائعة')
    faq = [
        ('صفحة المخططات مقفولة وما بقدر أرفع', 'مرحلتا التأمين ووثائق العطاء لازم تكتملا أول (صفحة Workflow). الرسالة الصفراء بتوديك لهناك.'),
        ('ما ظهر زر Approve', 'الاعتماد للأدمن ومدير الهندسة ومدير المشروع نفسه فقط، وعلى نسخة بحالة "Awaiting approval". موظف الموقع بيرفع بس.'),
        ('طلع "Drawing already exists"', 'رقم الورقة موجود بالمشروع. افتحها واضغط "New revision" بدل ما ترفعها ورقة جديدة.'),
        ('طلع "Revision already uploaded"', 'رقم النسخة مستخدم على نفس الورقة. استخدم حرف أو رقم جديد.'),
        ('رفعت نسخة غلط', 'ما في حذف. إذا لسا بانتظار الاعتماد اضغط "Reject" مع السبب، وارفع الصحيحة كنسخة جديدة.'),
        ('اعتمدت المخطط وما صار المشروع Active', 'لازم تكمل المرحلة الأخيرة من صفحة Workflow، وشرطها BOQ مسعّر بالكامل (كمية وسعر تكلفة وسعر عقد لكل بند).'),
        ('ظهر "Work is blocked" على المشروع', 'المشروع لسا Planning أو ما عليه تأمين ساري أو BOQ مسعّر بالكامل. الشريط الأحمر بصفحة المشروع بيبين السبب. رفع المخططات نفسه ما بينقفل.'),
        ('المساعد ما قرا ملف DWG', 'المساعد الذكي بيقرا PDF والصور. صدّر الرسم PDF وارفعه كنسخة جديدة، أو اضغط "Analyze" على النسخة الجديدة.'),
        ('ما بشوف زر Analyze', 'المساعد غير مفعّل بالخادم، أو الدور ما إله صلاحية. اطلب من المسؤول يضبطه بملف .env.'),
        ('كم حجم الملف الأقصى', f'{max_mb} ميغابايت للملف الواحد. المخطط الأكبر قسّمه أو صغّر حجمه.'),
    ]
    el.append(table(['الجواب', 'السؤال'], [[cell(a, page_width * 0.58), cell(q, page_width * 0.42, True)] for q, a in faq], [0.58, 0.42], font_size=9))
    gap(0.15)
    el.append(para(f'أنواع الملفات المقبولة: {extensions}', 'note'))

    doc.build(el)
    return buffer.getvalue()
