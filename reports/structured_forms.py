"""
Structured Forms for Daily Reports

Forms for adding workforce, equipment, and materials from master data
"""

from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from .master_data_models import (
    WorkforceCategory, LaborClassification, EquipmentMaster,
    ReportMaterialItem, DailyReportWorkforceEntry, DailyReportEquipmentEntry,
    DailyReportMaterialEntry
)
from .models import DailyReport


class WorkforceCategorySelectionForm(forms.Form):
    """Form to select workforce category"""
    
    category = forms.ModelChoiceField(
        queryset=WorkforceCategory.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'workforceCategory'
        }),
        label='Workforce Category',
        empty_label='-- Select Category --'
    )


class DailyReportWorkforceEntryForm(forms.ModelForm):
    """Form for adding workforce entries"""
    
    labor_classification = forms.ModelChoiceField(
        queryset=LaborClassification.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'laborClassification'
        }),
        label='Labor Classification'
    )
    
    class Meta:
        model = DailyReportWorkforceEntry
        fields = ['labor_classification', 'number_of_employees', 'gender', 'hours_worked', 'notes']
        widgets = {
            'number_of_employees': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Number of employees'
            }),
            'gender': forms.Select(attrs={
                'class': 'form-select'
            }),
            'hours_worked': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.5',
                'placeholder': 'Hours worked'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Additional notes'
            })
        }
    
    def __init__(self, *args, **kwargs):
        category_id = kwargs.pop('category_id', None)
        super().__init__(*args, **kwargs)
        
        if category_id:
            self.fields['labor_classification'].queryset = LaborClassification.objects.filter(
                category_id=category_id,
                is_active=True
            )


class DailyReportWorkforceFormSet(BaseInlineFormSet):
    """Formset for multiple workforce entries"""
    pass


WorkforceEntryFormSet = inlineformset_factory(
    DailyReport,
    DailyReportWorkforceEntry,
    form=DailyReportWorkforceEntryForm,
    formset=DailyReportWorkforceFormSet,
    extra=1,
    can_delete=True
)


class DailyReportEquipmentEntryForm(forms.ModelForm):
    """Form for adding equipment entries"""
    
    equipment = forms.ModelChoiceField(
        queryset=EquipmentMaster.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'equipment'
        }),
        label='Equipment'
    )
    
    class Meta:
        model = DailyReportEquipmentEntry
        fields = ['equipment', 'quantity_in_use', 'hours_worked', 'quantity_idle', 'remarks']
        widgets = {
            'quantity_in_use': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Quantity in use'
            }),
            'hours_worked': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.5',
                'placeholder': 'Hours worked'
            }),
            'quantity_idle': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'Quantity idle'
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Remarks about equipment'
            })
        }


class DailyReportEquipmentFormSet(BaseInlineFormSet):
    """Formset for multiple equipment entries"""
    pass


EquipmentEntryFormSet = inlineformset_factory(
    DailyReport,
    DailyReportEquipmentEntry,
    form=DailyReportEquipmentEntryForm,
    formset=DailyReportEquipmentFormSet,
    extra=1,
    can_delete=True
)


class DailyReportMaterialEntryForm(forms.ModelForm):
    """Form for adding material entries"""
    
    boq_item = forms.ModelChoiceField(
        queryset=ReportMaterialItem.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'boqItem'
        }),
        label='Material (from BOQ)'
    )
    
    class Meta:
        model = DailyReportMaterialEntry
        fields = ['boq_item', 'quantity_used', 'quantity_wasted', 'remarks']
        widgets = {
            'quantity_used': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'placeholder': 'Quantity used'
            }),
            'quantity_wasted': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'placeholder': 'Quantity wasted'
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Remarks about material usage'
            })
        }
    
    def __init__(self, *args, **kwargs):
        project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        
        if project:
            self.fields['boq_item'].queryset = ReportMaterialItem.objects.filter(
                project=project,
                is_active=True
            )


class DailyReportMaterialFormSet(BaseInlineFormSet):
    """Formset for multiple material entries"""
    pass


MaterialEntryFormSet = inlineformset_factory(
    DailyReport,
    DailyReportMaterialEntry,
    form=DailyReportMaterialEntryForm,
    formset=DailyReportMaterialFormSet,
    extra=1,
    can_delete=True
)


class StructuredDailyReportForm(forms.ModelForm):
    """Main form for structured daily report"""
    
    class Meta:
        model = DailyReport
        fields = ['weather_conditions', 'remarks']
        widgets = {
            'weather_conditions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe weather conditions'
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'General remarks about the day'
            })
        }
