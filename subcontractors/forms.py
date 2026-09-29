from django import forms

from reports.progress_models import ProjectPhaseSubItem

from .models import (
    SubcontractorAgreement, SubcontractorAgreementLine, SubcontractorAgreementPayment, SubcontractorGeneralTerms,
)


class SubcontractorAgreementForm(forms.ModelForm):
    class Meta:
        model = SubcontractorAgreement
        fields = ('language', 'vendor', 'scope_description', 'start_date', 'end_date', 'signed_document')
        widgets = {
            'language': forms.Select(attrs={'class': 'form-select'}),
            'vendor': forms.Select(attrs={'class': 'form-select'}),
            'scope_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'signed_document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class SubcontractorAgreementLineForm(forms.ModelForm):
    class Meta:
        model = SubcontractorAgreementLine
        fields = ('sub_item', 'description', 'unit', 'quantity', 'unit_price')
        widgets = {
            'sub_item': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project is not None:
            self.fields['sub_item'].queryset = ProjectPhaseSubItem.objects.filter(phase__project=project).order_by('phase__order', 'order')


class SubcontractorAgreementPaymentForm(forms.ModelForm):
    class Meta:
        model = SubcontractorAgreementPayment
        fields = ('amount', 'payment_date', 'notes')
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }


class SubcontractorGeneralTermsForm(forms.ModelForm):
    class Meta:
        model = SubcontractorGeneralTerms
        fields = ('general_terms', 'penalty_clauses', 'code_of_conduct', 'safety_commitment')
        widgets = {
            'general_terms': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'penalty_clauses': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'code_of_conduct': forms.Textarea(attrs={'class': 'form-control', 'rows': 8}),
            'safety_commitment': forms.Textarea(attrs={'class': 'form-control', 'rows': 8}),
        }
