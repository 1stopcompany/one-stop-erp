from django import forms

from projects import readiness
from projects.models import Project
from django.forms import BaseInlineFormSet, inlineformset_factory

from reports.progress_models import ProjectPhaseSubItem

from .models import (
    ItemMaster, Vendor,
    PurchaseRequisition, PurchaseRequisitionLine,
    RequestForQuotation, VendorQuote, VendorQuoteLine,
    PurchaseOrder, PurchaseOrderLine, POReceipt,
)


PLANNING_HELP = (
    "Only projects that are ready for work are listed: past Planning, with valid insurance and a fully priced BOQ."
)


def _purchasable_projects():
    """Projects that may buy material: the ones ready for work (see projects.readiness)."""
    return readiness.ready_projects().order_by("name")


class WorkItemSelect(forms.Select):
    """A <select> whose options carry their project id, so the page can show only the chosen project's BOQ items."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-project"] = str(instance.phase.project_id)
        return option


def _work_item_field():
    """The "BOQ item" a purchase is charged to: a sub-item of the project's own BOQ (Manage BOQ)."""
    field = forms.ModelChoiceField(
        queryset=(
            ProjectPhaseSubItem.objects.filter(phase__project__in=readiness.ready_projects())
            .select_related("phase__project").order_by("phase__project__name", "phase__order", "phase__code", "order", "id")
        ),
        required=False, label="BOQ item", widget=WorkItemSelect(attrs={"class": "form-select"}),
        empty_label="— not assigned —",
    )
    field.label_from_instance = lambda obj: f"{obj.phase.project.project_symbol} · {obj.code or obj.phase.code} {obj.name_ar}"[:90]
    return field


class BaseWorkItemFormSet(BaseInlineFormSet):
    """Every line's BOQ item must belong to the same project as the requisition / order itself."""

    def clean(self):
        super().clean()
        project_id = getattr(self.instance, "project_id", None)
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            sub_item = form.cleaned_data.get("sub_item")
            if sub_item and project_id and sub_item.phase.project_id != project_id:
                form.add_error("sub_item", "This BOQ item belongs to a different project.")


class ItemMasterForm(forms.ModelForm):
    """
    aa_level/bb_category/cc_subcategory/dd_itemtype are still plain
    2-digit CharFields on the model (unchanged), but rendered here as a
    cascading Family -> Group -> Classification -> Brand picker (see
    templates/procurement/form.html's script block and
    procurement.models.ItemFamily and friends) so nobody has to already
    know the raw code -- they pick by name, and the code comes along for
    free. The widget's own `choices` only ever needs to hold a
    placeholder plus (in edit mode) the item's current value: these are
    plain CharFields, not ChoiceFields, so Django never validates a
    submission against the widget's static choices -- the real options
    are injected client-side from the full hierarchy tree, and
    clean_aa_level() etc. below still do the actual validation.
    """

    class Meta:
        model = ItemMaster
        fields = [
            "aa_level",
            "bb_category",
            "cc_subcategory",
            "dd_itemtype",
            "eee_attribute",
            "description",
            "unit",
            "standard",
            "batch_reference",
            "status",
        ]

        labels = {
            "aa_level": "Family",
            "bb_category": "Group",
            "cc_subcategory": "Classification",
            "dd_itemtype": "Brand",
            "eee_attribute": "Attribute (size/thickness/grade)",
        }

        widgets = {
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "standard": forms.TextInput(attrs={"class": "form-control"}),
            "batch_reference": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("aa_level", "bb_category", "cc_subcategory", "dd_itemtype"):
            # On a validation-error re-render, restore what was actually submitted
            # (not the still-blank instance) so a mistake elsewhere on the form
            # doesn't force re-picking the whole Family/Group/Classification/Item
            # Type chain from scratch.
            if self.is_bound:
                current = self.data.get(self.add_prefix(name), "") or ""
            else:
                current = getattr(self.instance, name, "") or ""
            choices = [("", "— Select —")]
            if current:
                choices.append((current, current))
            self.fields[name].widget = forms.Select(
                choices=choices,
                attrs={"class": "form-select", "data-level": name, "data-initial": current},
            )

    # ---------- helpers ----------
    def _validate_range(self, value, digits, label):
        if not value.isdigit():
            raise forms.ValidationError(f"{label} must be numeric")

        v = int(value)
        max_v = 10**digits - 1
        if not (0 <= v <= max_v):
            raise forms.ValidationError(f"{label} must be between 0 and {max_v}")

        return str(v).zfill(digits)

    def clean_aa_level(self):
        return self._validate_range(self.cleaned_data["aa_level"], 2, "AA Level")

    def clean_bb_category(self):
        return self._validate_range(self.cleaned_data["bb_category"], 2, "BB Category")

    def clean_cc_subcategory(self):
        return self._validate_range(self.cleaned_data["cc_subcategory"], 2, "CC Subcategory")

    def clean_dd_itemtype(self):
        return self._validate_range(self.cleaned_data["dd_itemtype"], 2, "Brand")

    def clean_eee_attribute(self):
        return self._validate_range(self.cleaned_data.get("eee_attribute", "0"), 3, "EEE Attribute")

    def clean(self):
        """
        Prevent a duplicate full_code (the real uniqueness key -- see
        ItemMaster.full_code). Deliberately NOT checked against
        short_code: hundreds of real items legitimately share the same
        Family.Group.Classification.ItemType and differ only by
        eee_attribute (e.g. the same pipe fitting in a dozen sizes), so
        rejecting a new item just because its short_code already exists
        would make it impossible to ever add a second size/variant under
        an already-populated item type.
        """
        cleaned = super().clean()

        aa = cleaned.get("aa_level")
        bb = cleaned.get("bb_category")
        cc = cleaned.get("cc_subcategory")
        dd = cleaned.get("dd_itemtype")
        eee = cleaned.get("eee_attribute")

        if not all([aa, bb, cc, dd, eee]):
            return cleaned

        # Editing a variant item keeps its own suffix (it isn't a form field), so the
        # code being checked must be built the same way ItemMaster.save() builds it.
        full_code = f"OS.{aa}.{bb}.{cc}.{dd}.{eee}"
        if self.instance.variant_suffix:
            full_code += f".{self.instance.variant_suffix}"

        clash = ItemMaster.objects.filter(full_code=full_code)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        clash = clash.first()

        if clash:
            raise forms.ValidationError(
                f"Full Code {full_code} is already used by another item ({clash.description}). "
                f"Each item must have a unique Full Code -- change the Attribute (or the "
                f"Brand/Classification) to give this item its own code."
            )

        return cleaned


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = ["name", "contact_person", "email", "phone", "address", "city", "country", "rating", "is_active"]


# ---------------- Purchase Requisition (header + multi-item lines) ----------------

class PurchaseRequisitionForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequisition
        fields = ["project", "required_date", "remarks"]
        widgets = {
            "project": forms.Select(attrs={"class": "form-select"}),
            "required_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = _purchasable_projects()
        self.fields["project"].help_text = PLANNING_HELP


class PurchaseRequisitionLineForm(forms.ModelForm):
    item = forms.ModelChoiceField(
        queryset=ItemMaster.objects.filter(status="active").order_by("full_code"),
        widget=forms.Select(attrs={"class": "form-select item-select"}),
    )
    sub_item = _work_item_field()

    class Meta:
        model = PurchaseRequisitionLine
        fields = ["item", "sub_item", "quantity_requested", "unit", "remarks"]
        widgets = {
            "quantity_requested": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "remarks": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].label_from_instance = lambda obj: f"{obj.full_code} — {obj.description}"


PurchaseRequisitionLineFormSet = inlineformset_factory(
    PurchaseRequisition, PurchaseRequisitionLine,
    form=PurchaseRequisitionLineForm, formset=BaseWorkItemFormSet,
    extra=1, can_delete=True, min_num=1, validate_min=True,
)


class PRRejectForm(forms.Form):
    rejected_reason = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        label="Reason for rejection",
    )


# ---------------- RFQ ----------------

class RFQForm(forms.Form):
    vendors = forms.ModelMultipleChoiceField(
        queryset=Vendor.objects.filter(is_active=True).order_by("name"),
        widget=forms.CheckboxSelectMultiple,
        label="Invite vendors",
    )
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))


class VendorQuoteForm(forms.ModelForm):
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.filter(is_active=True).order_by("name"),
                                     widget=forms.Select(attrs={"class": "form-select"}))

    class Meta:
        model = VendorQuote
        fields = ["vendor", "received_date", "notes"]
        widgets = {
            "received_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class VendorQuoteLineForm(forms.ModelForm):
    class Meta:
        model = VendorQuoteLine
        fields = ["pr_line", "unit_price", "lead_time_days", "remarks"]
        widgets = {
            "pr_line": forms.HiddenInput(),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "lead_time_days": forms.NumberInput(attrs={"class": "form-control"}),
            "remarks": forms.TextInput(attrs={"class": "form-control"}),
        }


VendorQuoteLineFormSet = inlineformset_factory(
    VendorQuote, VendorQuoteLine,
    form=VendorQuoteLineForm,
    extra=0, can_delete=False,
)


# ---------------- Purchase Order (direct/manual, header + multi-item lines) ----------------

class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["project", "vendor", "pr", "delivery_date", "remarks"]
        widgets = {
            "project": forms.Select(attrs={"class": "form-select"}),
            "vendor": forms.Select(attrs={"class": "form-select"}),
            "pr": forms.Select(attrs={"class": "form-select"}),
            "delivery_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = _purchasable_projects()
        self.fields["project"].help_text = PLANNING_HELP
        self.fields["pr"].required = False
        self.fields["pr"].queryset = PurchaseRequisition.objects.filter(
            status__in=["approved", "in_procurement"]
        ).order_by("-created_date")


class PurchaseOrderLineForm(forms.ModelForm):
    item = forms.ModelChoiceField(
        queryset=ItemMaster.objects.filter(status="active").order_by("full_code"),
        widget=forms.Select(attrs={"class": "form-select item-select"}),
    )

    sub_item = _work_item_field()

    class Meta:
        model = PurchaseOrderLine
        fields = ["item", "sub_item", "quantity_ordered", "unit", "unit_price"]
        widgets = {
            "quantity_ordered": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].label_from_instance = lambda obj: f"{obj.full_code} — {obj.description}"


PurchaseOrderLineFormSet = inlineformset_factory(
    PurchaseOrder, PurchaseOrderLine,
    form=PurchaseOrderLineForm, formset=BaseWorkItemFormSet,
    extra=1, can_delete=True, min_num=1, validate_min=True,
)


class POReceiptForm(forms.ModelForm):
    class Meta:
        model = POReceipt
        fields = ["po_line", "quantity_received", "remarks"]
        widgets = {
            "quantity_received": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "remarks": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
