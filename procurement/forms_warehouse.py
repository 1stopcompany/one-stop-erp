from __future__ import annotations

from decimal import Decimal

from django import forms

from projects import readiness
from projects.models import Project
from .models import ItemMaster, Warehouse


def _item_field():
    field = forms.ModelChoiceField(
        queryset=ItemMaster.objects.filter(status="active").order_by("full_code"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    field.label_from_instance = lambda obj: f"{obj.full_code} — {obj.description}"
    return field


def _warehouse_field():
    return forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True), empty_label=None,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


def _qty_field(label, min_value=Decimal("0.01"), help_text=""):
    return forms.DecimalField(
        label=label, max_digits=14, decimal_places=2, min_value=min_value, help_text=help_text,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["name", "location", "project", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "project": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class StockLimitForm(forms.Form):
    """Set the minimum stock (and re-order quantity) for one item in one warehouse."""
    warehouse = _warehouse_field()
    item = _item_field()
    min_quantity = _qty_field(
        "Minimum stock", min_value=Decimal("0"),
        help_text="The quantity on hand must not drop below this. Once it reaches it, the item has to be re-ordered. 0 = no limit.",
    )
    reorder_quantity = _qty_field(
        "Quantity to order when low", min_value=Decimal("0"),
        help_text="0 = order enough to get back to twice the minimum.",
    )


class StockIssueForm(forms.Form):
    """Take material out of a warehouse for a project."""
    warehouse = _warehouse_field()
    item = _item_field()
    quantity = _qty_field("Quantity to issue")
    project = forms.ModelChoiceField(
        queryset=readiness.ready_projects().order_by("name"), widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Only projects that are ready for work are listed (valid insurance and a fully priced BOQ).",
    )
    remarks = forms.CharField(
        required=False, max_length=255, widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class StockAdjustForm(forms.Form):
    """Set the real counted quantity (stock-take, or the opening balance of a new item)."""
    warehouse = _warehouse_field()
    item = _item_field()
    counted_quantity = _qty_field("Actual quantity counted", min_value=Decimal("0"))
    remarks = forms.CharField(
        required=False, max_length=255, widget=forms.TextInput(attrs={"class": "form-control"}),
        help_text="Why (e.g. opening balance, stock-take, damaged goods)",
    )


class ReorderForm(forms.Form):
    """Project + date for the draft purchase requisition created from the re-order list."""
    project = forms.ModelChoiceField(
        queryset=readiness.ready_projects().order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="A purchase requisition always belongs to a project -- pick the one this stock is bought under "
                  "(only projects that are ready for work are listed).",
    )
    required_date = forms.DateField(widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
