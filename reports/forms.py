"""
Reports Forms - Unified Daily and Monthly Reporting System

This module contains all forms for creating and editing reports.
"""

from django import forms
from django.forms import inlineformset_factory, modelformset_factory
from .models import (
    DailyReport, DailyWorkForce, DailyEquipment, DailyActivity, DailyMaterial, DailyVisitor,
    MonthlyReport, FloorActivity, ExternalWork, MaterialSupply, UpcomingWork
)
from .owner_financial_models import OwnerFinancialReport


# ==================== DAILY REPORT FORMS ====================

class DailyReportForm(forms.ModelForm):
    """Form for creating/editing daily reports"""
    
    class Meta:
        model = DailyReport
        fields = ['project', 'report_date', 'site_status', 'idle_reason', 'weather_conditions', 'remarks', 'work_hours_note']
        widgets = {
            'site_status': forms.RadioSelect(),
            'idle_reason': forms.Select(attrs={'class': 'form-control'}),
            'project': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'report_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True,
            }),
            'weather_conditions': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter any additional remarks or notes...'
            }),
            'work_hours_note': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'e.g. "24 hrs staff / 8 hrs workers"'
            }),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('site_status') == 'idle':
            if not cleaned.get('idle_reason'):
                self.add_error('idle_reason', 'Choose why no work was done that day.')
            elif cleaned['idle_reason'] == 'other' and not (cleaned.get('remarks') or '').strip():
                self.add_error('remarks', 'Explain the reason in the remarks.')
        else:
            cleaned['idle_reason'] = ''
        return cleaned


class DailyWorkForceForm(forms.ModelForm):
    """Form for adding workforce to daily reports"""
    
    class Meta:
        model = DailyWorkForce
        fields = ['category', 'designation', 'count']
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-control'
            }),
            'designation': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Site Manager, Laborer'
            }),
            'count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Number of workers'
            }),
        }


class DailyEquipmentForm(forms.ModelForm):
    """Form for adding equipment to daily reports"""
    
    class Meta:
        model = DailyEquipment
        fields = ['equipment_name', 'hours_worked', 'quantity_idle']
        widgets = {
            'equipment_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Excavator, Crane'
            }),
            'hours_worked': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '24',
                'placeholder': 'Hours worked (0-24)'
            }),
            'quantity_idle': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Quantity idle'
            }),
        }


class DailyActivityForm(forms.ModelForm):
    """Form for adding activities to daily reports"""
    
    class Meta:
        model = DailyActivity
        fields = ['activity_type', 'location', 'activity_description']
        widgets = {
            'activity_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Location on site'
            }),
            'activity_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Detailed description of the activity'
            }),
        }


class DailyMaterialForm(forms.ModelForm):
    """Form for adding materials to daily reports"""
    
    class Meta:
        model = DailyMaterial
        fields = ['material_description', 'quantity', 'unit']
        widgets = {
            'material_description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Concrete Grade M30'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Quantity'
            }),
            'unit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., cubic meters, tons'
            }),
        }


class DailyVisitorForm(forms.ModelForm):
    """Form for adding visitors to daily reports"""
    
    class Meta:
        model = DailyVisitor
        fields = ['visit_time', 'visitor_name', 'representing']
        widgets = {
            'visit_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'visitor_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Visitor name'
            }),
            'representing': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Organization (optional)'
            }),
        }


# Formsets for Daily Reports
DailyWorkForceFormSet = inlineformset_factory(
    DailyReport, DailyWorkForce,
    form=DailyWorkForceForm,
    extra=1,
    can_delete=True
)

DailyEquipmentFormSet = inlineformset_factory(
    DailyReport, DailyEquipment,
    form=DailyEquipmentForm,
    extra=1,
    can_delete=True
)

DailyActivityFormSet = inlineformset_factory(
    DailyReport, DailyActivity,
    form=DailyActivityForm,
    extra=1,
    can_delete=True
)

DailyMaterialFormSet = inlineformset_factory(
    DailyReport, DailyMaterial,
    form=DailyMaterialForm,
    extra=1,
    can_delete=True
)

DailyVisitorFormSet = inlineformset_factory(
    DailyReport, DailyVisitor,
    form=DailyVisitorForm,
    extra=1,
    can_delete=True
)


# ==================== MONTHLY REPORT FORMS ====================

class MonthlyReportForm(forms.ModelForm):
    """Form for creating/editing monthly reports"""
    
    class Meta:
        model = MonthlyReport
        fields = ['project', 'reporting_period_from', 'reporting_period_to', 
                  'weather_conditions', 'general_description']
        widgets = {
            'project': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'reporting_period_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True
            }),
            'reporting_period_to': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True
            }),
            'weather_conditions': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'general_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'General description of activities during the period'
            }),
        }


class FloorActivityForm(forms.ModelForm):
    """Form for adding floor activities to monthly reports"""
    
    class Meta:
        model = FloorActivity
        fields = ['floor', 'activity_description', 'completion_percentage']
        widgets = {
            'floor': forms.Select(attrs={
                'class': 'form-control'
            }),
            'activity_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description of activities on this floor'
            }),
            'completion_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'placeholder': 'Completion percentage (0-100)'
            }),
        }


class ExternalWorkForm(forms.ModelForm):
    """Form for adding external works to monthly reports"""
    
    class Meta:
        model = ExternalWork
        fields = ['work_description', 'completion_percentage']
        widgets = {
            'work_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description of external work'
            }),
            'completion_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'placeholder': 'Completion percentage (0-100)'
            }),
        }


class MaterialSupplyForm(forms.ModelForm):
    """Form for adding material supplies to monthly reports"""
    
    class Meta:
        model = MaterialSupply
        fields = ['material_description', 'quantity', 'unit']
        widgets = {
            'material_description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Material description'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Quantity'
            }),
            'unit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Unit of measurement'
            }),
        }


class UpcomingWorkForm(forms.ModelForm):
    """Form for adding upcoming works to monthly reports"""
    
    class Meta:
        model = UpcomingWork
        fields = ['work_description', 'planned_start_date', 'planned_end_date']
        widgets = {
            'work_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description of upcoming work'
            }),
            'planned_start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'planned_end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }


# Formsets for Monthly Reports
FloorActivityFormSet = inlineformset_factory(
    MonthlyReport, FloorActivity,
    form=FloorActivityForm,
    extra=1,
    can_delete=True
)

ExternalWorkFormSet = inlineformset_factory(
    MonthlyReport, ExternalWork,
    form=ExternalWorkForm,
    extra=1,
    can_delete=True
)

MaterialSupplyFormSet = inlineformset_factory(
    MonthlyReport, MaterialSupply,
    form=MaterialSupplyForm,
    extra=1,
    can_delete=True
)

UpcomingWorkFormSet = inlineformset_factory(
    MonthlyReport, UpcomingWork,
    form=UpcomingWorkForm,
    extra=1,
    can_delete=True
)


# ==================== OWNER FINANCIAL REPORT FORMS ====================

STANDARD_CLOSING_NOTE = (
    'حرصًا على الحفاظ على وتيرة التنفيذ الحالية وضمان السير وفق البرنامج الزمني المعتمد، '
    'فإن انتظام التدفقات المالية بما يتوافق مع نسب الإنجاز الفعلية يسهم في دعم استمرارية توريد المواد، '
    'واستقرار الترتيبات التشغيلية، وتنفيذ الأعمال وفق مستويات الجودة المخططة.\n\n'
    'كما أن مواءمة الجوانب المالية مع القيم التراكمية للأعمال المنجزة تدعم تقدم المشروع بسلاسة، '
    'وتساعد في تجنب أي تأثير محتمل على الجدول الزمني أو مراحل التنفيذ القادمة.\n\n'
    'نثمّن تعاونكم الدائم، ونتطلع إلى استمرار العمل بروح التنسيق القائمة بما يحقق أهداف المشروع '
    'ضمن الإطار الزمني ومستويات الجودة المعتمدة.'
)


class OwnerFinancialReportForm(forms.ModelForm):
    """
    Form for creating/editing the owner financial report.

    Contract-term snapshot fields (contract_value_snapshot,
    advance_payment_value_snapshot, performance_retention_rate_snapshot)
    are deliberately excluded here -- the view populates them from the
    selected project's own contract terms at save time, so the user isn't
    re-typing numbers the system already knows.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['closing_note'].initial = STANDARD_CLOSING_NOTE

    class Meta:
        model = OwnerFinancialReport
        fields = [
            'project', 'reporting_period_from', 'reporting_period_to',
            'previous_payments_total',
            'progress_summary', 'next_month_expected_works', 'next_month_expected_completion_pct',
            'material_price_note', 'closing_note',
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'form-control', 'required': True}),
            'reporting_period_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'reporting_period_to': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': True}),
            'previous_payments_total': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'progress_summary': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'ملخص سير المشروع'}),
            'next_month_expected_works': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'الأعمال المتوقعة للشهر القادم'}),
            'next_month_expected_completion_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'material_price_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'الوضع الراهن لأسعار المواد'}),
            'closing_note': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'ملاحظة تنظيمية متعلقة بالتدفق المالي للمشروع'}),
        }
