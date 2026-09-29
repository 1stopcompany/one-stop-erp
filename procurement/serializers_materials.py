"""
Serializers for Material Tracking System
"""

from rest_framework import serializers
from .models_materials import (
    MaterialCategory, MaterialType, Project, MaterialEntry,
    MonthlyMaterialReport, MonthlyMaterialReportItem,
    MaterialBudget, MaterialBudgetItem, MaterialSupplier,
    MaterialInvoice, MaterialInvoiceItem
)


class MaterialCategorySerializer(serializers.ModelSerializer):
    """Serializer for Material Categories"""
    
    class Meta:
        model = MaterialCategory
        fields = ['id', 'name', 'description', 'unit', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class MaterialTypeSerializer(serializers.ModelSerializer):
    """Serializer for Material Types"""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = MaterialType
        fields = ['id', 'category', 'category_name', 'name', 'description', 'unit', 
                  'unit_cost', 'supplier', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Projects"""
    
    class Meta:
        model = Project
        fields = ['id', 'code', 'name', 'location', 'start_date', 'end_date', 
                  'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class MaterialEntrySerializer(serializers.ModelSerializer):
    """Serializer for Material Entries"""
    
    material_type_name = serializers.CharField(source='material_type.name', read_only=True)
    project_code = serializers.CharField(source='project.code', read_only=True)
    
    class Meta:
        model = MaterialEntry
        fields = ['id', 'project', 'project_code', 'material_type', 'material_type_name',
                  'entry_date', 'quantity', 'unit_cost', 'total_cost', 'source',
                  'invoice_number', 'supplier_name', 'notes', 'recorded_by',
                  'recorded_date', 'updated_date']
        read_only_fields = ['total_cost', 'recorded_date', 'updated_date']


class MonthlyMaterialReportItemSerializer(serializers.ModelSerializer):
    """Serializer for Monthly Report Items"""
    
    material_type_name = serializers.CharField(source='material_type.name', read_only=True)
    category_name = serializers.CharField(source='material_type.category.name', read_only=True)
    unit = serializers.CharField(source='material_type.unit', read_only=True)
    
    class Meta:
        model = MonthlyMaterialReportItem
        fields = ['id', 'material_type', 'material_type_name', 'category_name', 'unit',
                  'quantity', 'unit_cost', 'total_cost', 'cumulative_quantity',
                  'cumulative_cost', 'entry_count']
        read_only_fields = ['cumulative_quantity', 'cumulative_cost', 'entry_count']


class MonthlyMaterialReportSerializer(serializers.ModelSerializer):
    """Serializer for Monthly Material Reports"""
    
    project_code = serializers.CharField(source='project.code', read_only=True)
    items = MonthlyMaterialReportItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = MonthlyMaterialReport
        fields = ['id', 'project', 'project_code', 'report_month', 'report_date',
                  'total_entries', 'total_quantity', 'total_cost', 'is_approved',
                  'approved_by', 'approved_date', 'notes', 'items']
        read_only_fields = ['report_date', 'total_entries', 'total_quantity', 'total_cost']


class MaterialBudgetItemSerializer(serializers.ModelSerializer):
    """Serializer for Material Budget Items"""
    
    material_type_name = serializers.CharField(source='material_type.name', read_only=True)
    spent_amount = serializers.SerializerMethodField()
    remaining_budget = serializers.SerializerMethodField()
    budget_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = MaterialBudgetItem
        fields = ['id', 'material_type', 'material_type_name', 'allocated_budget',
                  'spent_amount', 'remaining_budget', 'budget_percentage']
        read_only_fields = ['spent_amount', 'remaining_budget', 'budget_percentage']
    
    def get_spent_amount(self, obj):
        return float(obj.get_spent_amount())
    
    def get_remaining_budget(self, obj):
        return float(obj.get_remaining_budget())
    
    def get_budget_percentage(self, obj):
        return round(obj.get_budget_percentage(), 2)


class MaterialBudgetSerializer(serializers.ModelSerializer):
    """Serializer for Material Budgets"""
    
    project_code = serializers.CharField(source='project.code', read_only=True)
    items = MaterialBudgetItemSerializer(many=True, read_only=True)
    spent_amount = serializers.SerializerMethodField()
    remaining_budget = serializers.SerializerMethodField()
    budget_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = MaterialBudget
        fields = ['id', 'project', 'project_code', 'total_budget', 'spent_amount',
                  'remaining_budget', 'budget_percentage', 'created_date', 'updated_date', 'items']
        read_only_fields = ['created_date', 'updated_date', 'spent_amount', 
                           'remaining_budget', 'budget_percentage']
    
    def get_spent_amount(self, obj):
        return float(obj.get_spent_amount())
    
    def get_remaining_budget(self, obj):
        return float(obj.get_remaining_budget())
    
    def get_budget_percentage(self, obj):
        return round(obj.get_budget_percentage(), 2)


class MaterialSupplierSerializer(serializers.ModelSerializer):
    """Serializer for Material Suppliers"""
    
    class Meta:
        model = MaterialSupplier
        fields = ['id', 'name', 'contact_person', 'phone', 'email', 'address',
                  'city', 'country', 'tax_id', 'payment_terms', 'is_active',
                  'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class MaterialInvoiceItemSerializer(serializers.ModelSerializer):
    """Serializer for Material Invoice Items"""
    
    material_type_name = serializers.CharField(source='material_type.name', read_only=True)
    unit = serializers.CharField(source='material_type.unit', read_only=True)
    
    class Meta:
        model = MaterialInvoiceItem
        fields = ['id', 'material_type', 'material_type_name', 'unit', 'quantity',
                  'unit_price', 'total_amount', 'description']
        read_only_fields = ['total_amount']


class MaterialInvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Material Invoices"""
    
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    project_code = serializers.CharField(source='project.code', read_only=True)
    items = MaterialInvoiceItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = MaterialInvoice
        fields = ['id', 'project', 'project_code', 'supplier', 'supplier_name',
                  'invoice_number', 'invoice_date', 'due_date', 'subtotal',
                  'tax_percentage', 'tax_amount', 'total_amount', 'status',
                  'notes', 'created_at', 'updated_at', 'items']
        read_only_fields = ['subtotal', 'tax_amount', 'total_amount', 'created_at', 'updated_at']


class MaterialReportSummarySerializer(serializers.Serializer):
    """Serializer for Material Report Summary"""
    
    project_code = serializers.CharField()
    project_name = serializers.CharField()
    report_month = serializers.DateField()
    total_entries = serializers.IntegerField()
    total_quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    total_cost = serializers.DecimalField(max_digits=14, decimal_places=2)
    budget_allocated = serializers.DecimalField(max_digits=14, decimal_places=2)
    budget_spent = serializers.DecimalField(max_digits=14, decimal_places=2)
    budget_remaining = serializers.DecimalField(max_digits=14, decimal_places=2)
    budget_percentage = serializers.FloatField()
    categories = serializers.ListField(child=serializers.DictField())
