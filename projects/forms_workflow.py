from django import forms

from .models import ProjectInsurance, ProjectTenderDocument, ProjectRegulatoryApproval, ProjectManagementPlan


class ProjectInsuranceForm(forms.ModelForm):
    class Meta:
        model = ProjectInsurance
        fields = ('policy_type', 'insurer', 'policy_number', 'insured_amount', 'start_date', 'end_date', 'document', 'notes')
        widgets = {
            'policy_type': forms.Select(attrs={'class': 'form-select'}),
            'insurer': forms.TextInput(attrs={'class': 'form-control'}),
            'policy_number': forms.TextInput(attrs={'class': 'form-control'}),
            'insured_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end <= start:
            self.add_error('end_date', 'The expiry date must be after the start date.')
        return cleaned


class ProjectTenderDocumentForm(forms.ModelForm):
    class Meta:
        model = ProjectTenderDocument
        fields = ('category', 'title', 'document', 'notes')
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ProjectRegulatoryApprovalForm(forms.ModelForm):
    class Meta:
        model = ProjectRegulatoryApproval
        fields = ('body', 'title', 'document', 'approval_number', 'approved_date', 'notes')
        widgets = {
            'body': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'approval_number': forms.TextInput(attrs={'class': 'form-control'}),
            'approved_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ProjectManagementPlanForm(forms.ModelForm):
    class Meta:
        model = ProjectManagementPlan
        fields = ('category', 'title', 'document', 'notes')
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }


class SiteManagementChecklistForm(forms.ModelForm):
    class Meta:
        model = ProjectManagementPlan
        fields = ProjectManagementPlan.CHECKLIST_FIELDS
        widgets = {field: forms.CheckboxInput(attrs={'class': 'form-check-input'}) for field in ProjectManagementPlan.CHECKLIST_FIELDS}
