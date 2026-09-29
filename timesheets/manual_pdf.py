"""
"How to use the HR System" user manual -- PDF, Arabic-narrated with the
real English on-screen button/field labels quoted verbatim, illustrated
with UI mockups (styled to match the real screens: same colors, buttons,
status badges, table layout) populated with REAL data pulled live from
the database wherever it exists (falls back to a small generic example
otherwise, so the guide still builds on a freshly-installed system).

Same approach as procurement/manual_pdf.py -- these are drawn mockups,
not literal screenshots (this machine has no headless-browser tooling to
render an authenticated page to an image).
"""

from io import BytesIO
from datetime import date, datetime, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from reports.utils import _t, rtl_paragraph, FONT_NAME, FONT_BOLD_NAME, _owner_report_logo_path

BLUE = '#1f4788'
GREEN = '#198754'
RED = '#dc3545'
AMBER = '#ffc107'
GREY = '#6c757d'
LIGHT = '#f4f6fb'


def _styles():
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('HTitle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor(BLUE),
                                 alignment=TA_CENTER, fontName=FONT_BOLD_NAME, spaceAfter=8),
        'sub': ParagraphStyle('HSub', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#555555'),
                               alignment=TA_CENTER, fontName=FONT_NAME, spaceAfter=4),
        'step_title': ParagraphStyle('HStepTitle', parent=styles['Heading2'], fontSize=15, textColor=colors.white,
                                      backColor=colors.HexColor(BLUE), fontName=FONT_BOLD_NAME, spaceBefore=4,
                                      spaceAfter=10, alignment=TA_RIGHT, borderPadding=(6, 8, 6, 8)),
        'screen_title': ParagraphStyle('HScreenTitle', parent=styles['Normal'], fontSize=11, textColor=colors.white,
                                        backColor=colors.HexColor('#2c3e50'), fontName=FONT_BOLD_NAME,
                                        alignment=TA_RIGHT, borderPadding=(6, 10, 6, 10)),
        'body': ParagraphStyle('HBody', parent=styles['Normal'], fontSize=10.5, alignment=TA_RIGHT,
                                fontName=FONT_NAME, leading=16),
        'note': ParagraphStyle('HNote', parent=styles['Normal'], fontSize=9, alignment=TA_RIGHT,
                                fontName=FONT_NAME, leading=13, textColor=colors.HexColor('#a15c00')),
        'cell': ParagraphStyle('HCell', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER,
                                fontName=FONT_NAME, leading=12),
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
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
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
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    return t


def build_demo_data():
    """
    Pulls whatever real records already exist in the database to illustrate
    each screen with real names/numbers; falls back to small generic
    placeholders for any piece that doesn't exist yet (a brand-new system).
    """
    from .models import Employee, LeaveRequest, Payslip, DailyAttendanceRecord

    employee = Employee.objects.select_related('department', 'position').filter(
        employment_status='active',
    ).order_by('employee_id').first()

    leave_request = LeaveRequest.objects.filter(status='approved').select_related('employee').order_by('-submitted_date').first()

    payslip = Payslip.objects.select_related('employee').order_by('-period_start').first()

    return {
        'employee': employee,
        'leave_request': leave_request,
        'payslip': payslip,
    }


def generate_hr_manual_pdf(demo_data=None):
    if demo_data is None:
        demo_data = build_demo_data()

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
        inner = [[Paragraph(_t(title), S['screen_title'])]]
        for f in body_flowables:
            inner.append([f])
        if buttons:
            inner.append([Table([buttons], colWidths=None, hAlign='RIGHT')])
        t = Table(inner, colWidths=[page_width])
        t.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor('#d0d5dd')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, 0), 0), ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
            ('TOPPADDING', (0, 1), (-1, -1), 8), ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 1), (-1, -1), 10), ('RIGHTPADDING', (0, 1), (-1, -1), 10),
        ]))
        return t

    def data_table(headers, rows, col_widths=None, font_size=8.5, cell_colors=None):
        table_rows = [[Paragraph(_t(h), ParagraphStyle('h', parent=S['cell'], fontName=FONT_BOLD_NAME, textColor=colors.white)) for h in headers]]
        table_rows += rows
        t = Table(table_rows, colWidths=col_widths, repeatRows=1)
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)),
            ('GRID', (0, 0), (-1, -1), 0.6, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), font_size),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT)]),
        ]
        if cell_colors:
            for (r, c), hexcolor in cell_colors.items():
                style_cmds.append(('BACKGROUND', (c, r), (c, r), colors.HexColor(hexcolor)))
        t.setStyle(TableStyle(style_cmds))
        return t

    def _cell(text):
        return Paragraph(_t(str(text)), S['cell'])

    employee = demo_data.get('employee')
    employee_name = employee.full_name if employee else 'Ahmad Khalil'
    employee_id = employee.employee_id if employee else 'EMP001'
    department_name = employee.department.name if employee and employee.department_id else 'Site Operations'
    position_title = employee.position.title if employee and employee.position_id else 'Site Engineer'
    if employee:
        from datetime import date as _date
        from .services.attendance_service import _annual_leave_allocation
        annual_leave_days = _annual_leave_allocation(employee, _date.today().year)
    else:
        annual_leave_days = 14

    # ================= Cover =================
    logo_path = _owner_report_logo_path()
    if logo_path:
        logo = Image(logo_path, width=3.2 * inch, height=0.75 * inch, kind='proportional')
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(_t('دليل استخدام نظام شؤون الموظفين (HR)'), S['title']))
    elements.append(Paragraph('HR System — User Guide', S['sub']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(_t('من ملف الموظف حتى احتساب راتبه الشهري'), S['sub']))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        _t('تنويه: الشاشات في هذا الدليل هي محاكاة مرسومة لنفس شكل النظام الفعلي (نفس الأزرار والجداول والألوان) '
           'ومعبّأة ببيانات حقيقية من النظام حيثما توفرت، وليست لقطات شاشة حرفية.'),
        S['note'],
    ))
    elements.append(PageBreak())

    # ================= Flow overview =================
    elements.append(Paragraph(_t('دورة حياة الموظف داخل النظام'), S['step_title']))
    flow_steps = [
        'إنشاء ملف الموظف (Employee)',
        'تسجيل الحضور اليومي عبر تطبيق الموبايل (GPS)',
        'مراجعة وتصحيح كشف الدوام اليومي (DTR)',
        'تقديم واعتماد طلبات الإجازة',
        'تشغيل الرواتب: مراجعة ← تعديل ← ترحيل',
    ]
    for i, step in enumerate(flow_steps):
        box = Table([[Paragraph(_t(f'{i + 1}. {step}'), ParagraphStyle('fb', parent=S['cell'], fontName=FONT_BOLD_NAME, textColor=colors.white, fontSize=10.5))]], colWidths=[page_width * 0.8])
        box.hAlign = 'CENTER'
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(BLUE)),
            ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ]))
        elements.append(box)
        if i < len(flow_steps) - 1:
            elements.append(Paragraph('↓', ParagraphStyle('arrow', parent=S['cell'], fontSize=14, textColor=colors.HexColor(BLUE), fontName=FONT_BOLD_NAME)))
    elements.append(PageBreak())

    # ================= Step 1: Employee profile =================
    elements.append(Paragraph(_t('الخطوة 1: ملف الموظف'), S['step_title']))
    elements.append(Paragraph(
        _t('كل موظف له صفحة كاملة تضم بياناته الشخصية والوظيفية، مقسّمة إلى تبويبات: '
           'General Info، Job، Leave، Payroll، Notes.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.1 * inch))
    profile_table = data_table(
        ['القيمة', 'الحقل'],
        [
            [_cell(employee_name), 'Full Name'],
            [_cell(employee_id), 'Employee ID'],
            [_cell(department_name), 'Department'],
            [_cell(position_title), 'Position'],
            [_cell(str(annual_leave_days)), 'Annual Leave Days'],
        ],
        col_widths=[page_width * 0.6, page_width * 0.4], font_size=9.5,
    )
    elements.append(screen_mock(f'Employee Details — {employee_name}', [profile_table],
                                 buttons=[_button('Edit'), _button('Daily Time Record'), _button('Print')]))
    elements.append(PageBreak())

    # ================= Step 2: Job status/type =================
    elements.append(Paragraph(_t('الخطوة 2: الحالة الوظيفية ونوع التوظيف'), S['step_title']))
    elements.append(Paragraph(
        _t('من تبويب "Job"، زر "Update Status" أو "Update Type" يفتح نموذجاً صغيراً لتسجيل تغيير مؤرَّخ '
           '(مع سبب اختياري)، ويُحفظ تلقائياً في جدول تاريخي أسفل نفس التبويب.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.1 * inch))
    status_form = data_table(
        ['القيمة', 'الحقل'],
        [[_cell('On Leave'), 'Status'], [_cell(date.today().strftime('%Y-%m-%d')), 'Effective date'],
         [_cell('Maternity leave'), 'Note']],
        col_widths=[page_width * 0.6, page_width * 0.4], font_size=9.5,
    )
    elements.append(screen_mock('Update Employment Status', [status_form], buttons=[_button('Update Status')]))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(_t('سجل التغييرات (Employment Status History):'), S['body']))
    elements.append(data_table(
        ['بواسطة', 'ملاحظة', 'تاريخ السريان', 'الحالة'],
        [[_cell('HR Manager'), _cell('Maternity leave'), _cell(date.today().strftime('%Y-%m-%d')), _cell('On Leave')],
         [_cell('HR Manager'), _cell('—'), _cell((date.today() - timedelta(days=400)).strftime('%Y-%m-%d')), _cell('Active')]],
        col_widths=[page_width * 0.2] * 4 + [page_width * 0.2], font_size=9,
    ))
    elements.append(PageBreak())

    # ================= Step 3: Leave requests + Friday rule =================
    leave_request = demo_data.get('leave_request')
    elements.append(Paragraph(_t('الخطوة 3: طلبات الإجازة'), S['step_title']))
    elements.append(Paragraph(
        _t('من "Leave Requests" تُعتمد أو تُرفض الطلبات المعلّقة. الأيام ضمن الرصيد السنوي المتبقي تُصنَّف '
           '"On Leave"، وما يتجاوزه يُصنَّف تلقائياً "Unpaid Leave" ويُخصم لاحقاً من الراتب.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(_t('مثال توضيحي: موظف رصيده يومان (2)، وطلب إجازة من الاثنين حتى الجمعة:'), S['body']))
    elements.append(Spacer(1, 0.08 * inch))
    example_rows = [
        ['Mon', 'On Leave (1/2)'], ['Tue', 'On Leave (2/2)'],
        ['Wed', 'Unpaid Leave'], ['Thu', 'Unpaid Leave'], ['Fri', 'Rest Day (لا يُخصم أبداً)'],
    ]
    cell_colors = {(5, 1): '#d1e7dd'}
    elements.append(data_table(['التصنيف', 'اليوم'], [[_cell(r[1]), _cell(r[0])] for r in example_rows],
                                col_widths=[page_width * 0.7, page_width * 0.3], font_size=9.5,
                                cell_colors=cell_colors))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(
        _t('لاحظ: يوم الجمعة (المظلّل) بقي "Rest Day" رغم وقوعه داخل فترة الطلب، ولم يُحتسب لا ضمن '
           'الرصيد المستخدَم ولا ضمن أيام الإجازة غير المدفوعة — هذه قاعدة ثابتة في النظام.'),
        S['note'],
    ))
    elements.append(PageBreak())

    # ================= Step 4: DTR =================
    elements.append(Paragraph(_t('الخطوة 4: كشف الدوام اليومي (DTR)'), S['step_title']))
    elements.append(Paragraph(
        _t('من زر "Daily Time Record" بصفحة الموظف، يظهر جدول بكل أيام الشهر، ويُبنى تلقائياً حسب الأولوية: '
           'إجازة معتمدة ← عطلة رسمية ← يوم جمعة ← حضور فعلي (GPS) ← غياب. كل حقل قابل للتصحيح اليدوي.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.1 * inch))
    dtr_rows = [
        ['2026-11-02', 'Mon', 'Present', '07:02', '15:30', '0'],
        ['2026-11-03', 'Tue', 'Present', '07:10', '16:05', '1.1'],
        ['2026-11-04', 'Wed', 'Unpaid Leave', '—', '—', '0'],
        ['2026-11-05', 'Thu', 'Unpaid Leave', '—', '—', '0'],
        ['2026-11-06', 'Fri', 'Rest Day', '—', '—', '0'],
    ]
    dtr_colors = {(3, 2): '#ffe8cc', (4, 2): '#ffe8cc'}
    elements.append(data_table(
        ['OT (h)', 'Clock Out', 'Clock In', 'Status', 'Day', 'Date'],
        [[_cell(r[5]), _cell(r[4]), _cell(r[3]), _cell(r[2]), _cell(r[1]), _cell(r[0])] for r in dtr_rows],
        col_widths=[page_width * w for w in [0.12, 0.15, 0.15, 0.2, 0.13, 0.25]], font_size=8.5,
    ))
    elements.append(Spacer(1, 0.08 * inch))
    elements.append(Paragraph(_t('من نفس الصفحة يمكن تصدير الشهر كاملاً بصيغة Excel أو PDF بزر "Export".'), S['body']))
    elements.append(PageBreak())

    # ================= Step 5: Payroll =================
    payslip = demo_data.get('payslip')
    base_pay = float(payslip.base_pay) if payslip else 3000.0
    net_pay = float(payslip.net_pay) if payslip else 2800.0
    gross_pay = float(payslip.gross_pay) if payslip else 3000.0
    elements.append(Paragraph(_t('الخطوة 5: تشغيل الرواتب — مراجعة ← تعديل ← ترحيل'), S['step_title']))
    elements.append(Paragraph(
        _t('من "Payroll ← Run Payroll (Review & Post)"، يحسب النظام تلقائياً كشف كل موظف للشهر (بما فيه خصم '
           'الإجازة غير المدفوعة من كشف الدوام). طالما الكشف "Draft" يمكن تعديل أي حقل، وبعد التأكد يُضغط '
           '"Post Payroll (ترحيل)" فتُقفل كشوف الشهر نهائياً.'),
        S['body'],
    ))
    elements.append(Spacer(1, 0.1 * inch))
    payroll_row = data_table(
        ['Net Pay', 'Gross Pay', 'Base Pay', 'الموظف'],
        [[_cell(f'{net_pay:,.2f} ₪'), _cell(f'{gross_pay:,.2f} ₪'), _cell(f'{base_pay:,.2f} ₪'), _cell(employee_name)]],
        col_widths=[page_width * 0.25] * 3 + [page_width * 0.25], font_size=9.5,
    )
    elements.append(screen_mock(
        f'Payroll Run — {date.today().strftime("%B %Y")} — DRAFT',
        [payroll_row],
        buttons=[_button('Export'), _button('Post Payroll (ترحيل)', GREEN)],
    ))
    elements.append(PageBreak())

    # ================= Status glossary =================
    elements.append(Paragraph(_t('مرجع الحالات'), S['step_title']))
    elements.append(Paragraph(_t('حالة الموظف (Employment Status)'), ParagraphStyle('sec', parent=S['body'], fontName=FONT_BOLD_NAME, fontSize=11)))
    elements.append(data_table(
        ['المعنى', 'الحالة'],
        [[_cell('يعمل حالياً بشكل طبيعي'), 'Active'],
         [_cell('متوقف مؤقتاً'), 'Inactive'],
         [_cell('في إجازة'), 'On Leave'],
         [_cell('انتهت خدمته'), 'Terminated']],
        col_widths=[page_width * 0.75, page_width * 0.25], font_size=9.5,
    ))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(_t('حالة كشف الراتب (Payslip)'), ParagraphStyle('sec2', parent=S['body'], fontName=FONT_BOLD_NAME, fontSize=11)))
    elements.append(data_table(
        ['المعنى', 'الحالة'],
        [[_cell('لسا قابل للتعديل قبل الترحيل'), 'Draft'],
         [_cell('مُرحَّل ومقفل نهائياً'), 'Posted']],
        col_widths=[page_width * 0.75, page_width * 0.25], font_size=9.5,
    ))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(_t('حالة يوم الدوام (DTR)'), ParagraphStyle('sec3', parent=S['body'], fontName=FONT_BOLD_NAME, fontSize=11)))
    elements.append(data_table(
        ['المعنى', 'الحالة'],
        [[_cell('حضور فعلي مسجَّل عبر GPS'), 'Present'],
         [_cell('لا حضور ولا إجازة معتمدة -- يحتاج مراجعة يدوية'), 'Absent'],
         [_cell('إجازة ضمن الرصيد المتبقي'), 'On Leave'],
         [_cell('إجازة بعد استنفاذ الرصيد -- تُخصم من الراتب'), 'Unpaid Leave'],
         [_cell('يوم جمعة'), 'Rest Day'],
         [_cell('عطلة رسمية'), 'Holiday']],
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
