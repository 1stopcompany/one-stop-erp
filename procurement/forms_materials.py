"""
Forms for Material Tracking System
"""

from django import forms
from django.forms import inlineformset_factory
from .models_materials import (
    MaterialCategory, MaterialType, Project, MaterialEntry,
    MonthlyMaterialReport, MaterialBudget, MaterialBudgetItem,
    MaterialSupplier, MaterialInvoice, MaterialInvoiceItem
)


class MaterialCategoryForm(forms.ModelForm):
    """Form for Material Categories"""
    
    class Meta:
        model = MaterialCategory
        fields = ['name', 'description', 'unit', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., m³, Ton, Hour'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MaterialTypeForm(forms.ModelForm):
    """Form for Material Types"""
    
    class Meta:
        model = MaterialType
        fields = ['category', 'name', 'description', 'unit', 'unit_cost', 'supplier', 'is_active']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Material name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Unit of measurement'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'supplier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier name'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ProjectForm(forms.ModelForm):
    """Form for Projects"""
    
    class Meta:
        model = Project
        fields = ['code', 'name', 'location', 'start_date', 'end_date', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Project code'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Project name'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Project location'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MaterialEntryForm(forms.ModelForm):
    """Form for Material Entries"""
    
    class Meta:
        model = MaterialEntry
        fields = ['project', 'material_type', 'entry_date', 'quantity', 'unit_cost',
                  'source', 'invoice_number', 'supplier_name', 'notes', 'recorded_by']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-control'}),
            'material_type': forms.Select(attrs={'class': 'form-control'}),
            'entry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'source': forms.Select(attrs={'class': 'form-control'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Invoice number'}),
            'supplier_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier name'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'recorded_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Recorded by'}),
        }


class MaterialEntryBulkForm(forms.Form):
    """Form for bulk material entry"""
    
    project = forms.ModelChoiceField(queryset=Project.objects.filter(is_active=True), 
                                     widget=forms.Select(attrs={'class': 'form-control'}))
    material_type = forms.ModelChoiceField(queryset=MaterialType.objects.filter(is_active=True),
                                          widget=forms.Select(attrs={'class': 'form-control'}))
    entry_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    quantity = forms.DecimalField(decimal_places=3, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}))
    unit_cost = forms.DecimalField(decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    source = forms.ChoiceField(choices=MaterialEntry._meta.get_field('source').choices,
                               widget=forms.Select(attrs={'class': 'form-control'}))
    invoice_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    supplier_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))


class MonthlyMaterialReportForm(forms.ModelForm):
    """Form for Monthly Material Reports"""
    
    class Meta:
        model = MonthlyMaterialReport
        fields = ['project', 'report_month', 'notes', 'is_approved']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-control'}),
            'report_month': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MaterialBudgetForm(forms.ModelForm):
    """Form for Material Budgets"""
    
    class Meta:
        model = MaterialBudget
        fields = ['project', 'total_budget']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-control'}),
            'total_budget': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class MaterialBudgetItemForm(forms.ModelForm):
    """Form for Material Budget Items"""
    
    class Meta:
        model = MaterialBudgetItem
        fields = ['material_type', 'allocated_budget']
        widgets = {
            'material_type': forms.Select(attrs={'class': 'form-control'}),
            'allocated_budget': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


# Formset for Material Budget Items
MaterialBudgetItemFormSet = inlineformset_factory(
    MaterialBudget,
    MaterialBudgetItem,
    form=MaterialBudgetItemForm,
    extra=5,
    can_delete=True
)


class MaterialSupplierForm(forms.ModelForm):
    """Form for Material Suppliers"""
    
    class Meta:
        model = MaterialSupplier
        fields = ['name', 'contact_person', 'phone', 'email', 'address', 'city',
                  'country', 'tax_id', 'payment_terms', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier name'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tax ID'}),
            'payment_terms': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Payment terms'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MaterialInvoiceForm(forms.ModelForm):
    """Form for Material Invoices"""
    
    class Meta:
        model = MaterialInvoice
        fields = ['project', 'supplier', 'invoice_number', 'invoice_date', 'due_date',
                  'tax_percentage', 'status', 'notes']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-control'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Invoice number'}),
            'invoice_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tax_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class MaterialInvoiceItemForm(forms.ModelForm):
    """Form for Material Invoice Items"""
    
    class Meta:
        model = MaterialInvoiceItem
        fields = ['material_type', 'quantity', 'unit_price', 'description']
        widgets = {
            'material_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


# Formset for Material Invoice Items
MaterialInvoiceItemFormSet = inlineformset_factory(
    MaterialInvoice,
    MaterialInvoiceItem,
    form=MaterialInvoiceItemForm,
    extra=5,
    can_delete=True
)


class MaterialReportFilterForm(forms.Form):
    """Form for filtering material reports"""
    
    project = forms.ModelChoiceField(queryset=Project.objects.filter(is_active=True),
                                    required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    material_type = forms.ModelChoiceField(queryset=MaterialType.objects.filter(is_active=True),
                                          required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    source = forms.ChoiceField(choices=[('', 'All Sources')] + list(MaterialEntry._meta.get_field('source').choices),
                               required=False, widget=forms.Select(attrs={'class': 'form-control'}))