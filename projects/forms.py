from django import forms
from .models import Project, ProjectFloor


class ProjectForm(forms.ModelForm):
    """Project creation/update form"""
    
    class Meta:
        model = Project
        fields = ('name', 'project_symbol', 'contract_number', 'client_name', 'start_date', 'end_date', 'maintenance_type', 'status', 'description', 'location', 'manager')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'project_symbol': forms.TextInput(attrs={'class': 'form-control'}),
            'contract_number': forms.TextInput(attrs={'class': 'form-control'}),
            'client_name': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'maintenance_type': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'manager': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            # A new project always starts in Planning and only becomes Active by finishing the
            # start-up flow (insurance -> tender documents -> approved drawings): see projects.workflow.
            del self.fields['status']
            self.instance.status = 'planning'

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('status')
        if self.instance.pk and status in ('active', 'completed') and status != self.instance.status:
            from .workflow import flow_complete, current_stage_label
            if not flow_complete(self.instance):
                self.add_error(
                    'status',
                    f"Finish the project start-up stages first (still open: {current_stage_label(self.instance)}). "
                    f"Completing the last stage makes the project Active automatically.",
                )
        return cleaned


class ProjectFloorForm(forms.ModelForm):
    """Project floor creation/update form"""
    
    class Meta:
        model = ProjectFloor
        fields = ('floor_number', 'floor_name', 'area_sqm', 'description')
        widgets = {
            'floor_number': forms.TextInput(attrs={'class': 'form-control'}),
            'floor_name': forms.TextInput(attrs={'class': 'form-control'}),
            'area_sqm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
