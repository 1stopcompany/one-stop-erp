from django import forms

from .models import SpecificationSection, SpecificationVolume


class SpecificationVolumeForm(forms.ModelForm):
    class Meta:
        model = SpecificationVolume
        fields = ('label', 'title', 'revision', 'document', 'order')
        widgets = {
            'label': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Volume I'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'revision': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Final July 6, 2026'}),
            'document': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class SpecificationSectionForm(forms.ModelForm):
    class Meta:
        model = SpecificationSection
        fields = ('code', 'title', 'order', 'content')
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01010'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Summary of Work'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 12}),
        }
