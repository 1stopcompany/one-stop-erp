from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DetailView, DeleteView, View

from rest_framework import viewsets, permissions

from .models import (
    ItemMaster, Vendor,
    PurchaseRequisition, PurchaseRequisitionLine,
    RequestForQuotation, RFQVendor, VendorQuote, VendorQuoteLine,
    PurchaseOrder, PurchaseOrderLine, POReceipt,
    ItemFamily, ItemGroup, ItemClassification, ItemBrand,
)
from .forms import (
    ItemMasterForm, VendorForm,
    PurchaseRequisitionForm, PurchaseRequisitionLineFormSet, PRRejectForm,
    RFQForm, VendorQuoteForm, VendorQuoteLineFormSet,
    PurchaseOrderForm, PurchaseOrderLineFormSet, POReceiptForm,
)
from .serializers import (
    ItemMasterSerializer, PRSerializer, POSerializer, VendorSerializer, ReceiptSerializer,
)
from .pdf import generate_pr_pdf, generate_po_pdf


# ==================== Permission helpers ====================

def _can_manage_pr(user, pr) -> bool:
    """Create/edit/submit/delete a draft PR: the site engineer who owns the project, an admin, or the
    procurement officer who raised it (warehouse re-order PRs are created by procurement, not a site)."""
    if user.is_anonymous:
        return False
    if user.is_admin():
        return True
    if user.is_procurement_officer() and pr.requested_by_id == user.id:
        return True
    return user.is_site_engineer() and pr.project.site_engineer_id == user.id


def _can_approve_pr(user, pr) -> bool:
    """Approve/reject a submitted PR: that project's manager, or an admin."""
    if user.is_anonymous:
        return False
    if user.is_admin():
        return True
    return user.is_project_manager() and pr.project.manager_id == user.id


def _can_work_procurement(user) -> bool:
    """Run RFQs / issue POs: any procurement officer, or an admin."""
    if user.is_anonymous:
        return False
    return user.is_admin() or user.is_procurement_officer()


def _can_receive_on_site(user, po) -> bool:
    """Record site receipts against a PO: that project's site engineer, procurement, or admin."""
    if user.is_anonymous:
        return False
    if user.is_admin() or user.is_procurement_officer():
        return True
    return user.is_site_engineer() and po.project.site_engineer_id == user.id


# ==================== Dashboard ====================

class ProcurementDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "procurement/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["total_items"] = ItemMaster.objects.count()
        context["active_items"] = ItemMaster.objects.filter(status="active").count()

        context["total_prs"] = PurchaseRequisition.objects.count()
        context["pending_prs"] = PurchaseRequisition.objects.filter(status="submitted").count()
        context["approved_prs"] = PurchaseRequisition.objects.filter(status__in=["approved", "in_procurement"]).count()

        context["total_pos"] = PurchaseOrder.objects.count()
        context["pending_pos"] = PurchaseOrder.objects.filter(status__in=["sent", "confirmed"]).count()

        context["total_vendors"] = Vendor.objects.filter(is_active=True).count()

        context["recent_prs"] = PurchaseRequisition.objects.select_related("project").order_by("-created_date")[:5]
        context["recent_pos"] = PurchaseOrder.objects.select_related("vendor", "project").order_by("-created_date")[:5]

        context["statuses_receivable"] = ["sent", "confirmed", "partial_received"]
        context["can_work_procurement"] = _can_work_procurement(self.request.user)

        from .services_warehouse import low_stock_levels
        context["low_stock_count"] = low_stock_levels().count()

        return context


# ==================== ItemMaster ====================
def _item_classification_tree():
    """
    Family -> Group -> Classification -> Brand, nested, for the Add/Edit
    Item form's cascading picker (see templates/procurement/form.html
    and procurement/forms.py) -- passed to the template as a plain
    Python structure and embedded safely via the `json_script` filter
    (not pre-serialized here, to avoid double-encoding). Small
    (18/102/369/563 rows total) and rarely changes, so it's fine to
    rebuild on every request -- with prefetch_related, this is a handful
    of queries, not one per family.
    """
    families = ItemFamily.objects.prefetch_related("groups__classifications__brands")
    return [
        {
            "code": family.code,
            "name": family.name,
            "groups": [
                {
                    "code": group.code,
                    "name": group.name,
                    "classifications": [
                        {
                            "code": classification.code,
                            "name": classification.name,
                            "brands": [
                                {"code": brand.code, "name": brand.name}
                                for brand in classification.brands.all()
                            ],
                        }
                        for classification in group.classifications.all()
                    ],
                }
                for group in family.groups.all()
            ],
        }
        for family in families
    ]


class ItemListView(LoginRequiredMixin, ListView):
    model = ItemMaster
    template_name = "procurement/item_master_list.html"
    context_object_name = "items"
    paginate_by = 100

    def get_queryset(self):
        qs = ItemMaster.objects.all()
        search = self.request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(description__icontains=search)
                | Q(full_code__icontains=search)
                | Q(source_code__icontains=search)
                | Q(brand__icontains=search)
                | Q(barcode_value=search)
            )
        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)
        return qs


class ItemCreateView(LoginRequiredMixin, CreateView):
    model = ItemMaster
    form_class = ItemMasterForm
    template_name = "procurement/form.html"
    success_url = reverse_lazy("procurement:item_master_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Create Item"
        ctx["item_hierarchy"] = _item_classification_tree()
        return ctx

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.created_by = self.request.user
        obj.save()
        return redirect(self.success_url)


class ItemUpdateView(LoginRequiredMixin, UpdateView):
    model = ItemMaster
    form_class = ItemMasterForm
    template_name = "procurement/form.html"
    success_url = reverse_lazy("procurement:item_master_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Update Item"
        ctx["item_hierarchy"] = _item_classification_tree()
        return ctx


class ItemDetailView(LoginRequiredMixin, DetailView):
    model = ItemMaster
    template_name = "procurement/item_detail.html"
    context_object_name = "item"

    def get_context_data(self, **kwargs):
        """
        Resolve the item's aa/bb/cc/dd codes to their Family/Group/
        Classification/Brand names (see procurement.models.ItemFamily
        and friends) -- ItemMaster only stores the plain codes, not FKs
        to these lookup tables, so this is a small independent lookup
        per level, each falling back to "just the code" if that level
        isn't in the reference workbook (see ItemMasterForm's own
        "not in reference list" fallback in the Add/Edit form for the
        same situation).
        """
        ctx = super().get_context_data(**kwargs)
        item = self.object

        family = ItemFamily.objects.filter(code=item.aa_level).first()
        group = ItemGroup.objects.filter(family=family, code=item.bb_category).first() if family else None
        classification = ItemClassification.objects.filter(group=group, code=item.cc_subcategory).first() if group else None
        brand = ItemBrand.objects.filter(classification=classification, code=item.dd_itemtype).first() if classification else None

        ctx["classification_trail"] = [
            {"level": "Family", "code": item.aa_level, "name": family.name if family else None},
            {"level": "Group", "code": item.bb_category, "name": group.name if group else None},
            {"level": "Classification", "code": item.cc_subcategory, "name": classification.name if classification else None},
            {"level": "Brand", "code": item.dd_itemtype, "name": brand.name if brand else None},
        ]
        return ctx


class ItemBarcodeImageView(LoginRequiredMixin, View):
    """Renders the item's Code128 barcode (see ItemMaster.barcode_value) as a PNG."""
    def get(self, request, pk):
        from .barcode_utils import render_barcode_png
        item = get_object_or_404(ItemMaster, pk=pk)
        png_bytes = render_barcode_png(item.barcode_value)
        return HttpResponse(png_bytes, content_type="image/png")


class ItemLabelPdfView(LoginRequiredMixin, View):
    """A single printable barcode label (item code + description) for this item."""
    def get(self, request, pk):
        from .barcode_utils import generate_item_label_pdf
        item = get_object_or_404(ItemMaster, pk=pk)
        pdf = generate_item_label_pdf(item)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="label-{item.full_code}.pdf"'
        return response


class ProcurementManualPdfView(LoginRequiredMixin, View):
    """
    Downloads the illustrated "how to use the procurement system" guide,
    built live from real demo/example data already in the database (see
    procurement.manual_pdf and management command generate_procurement_manual).
    """
    def get(self, request):
        from .manual_pdf import generate_procurement_manual_pdf
        from .management.commands.generate_procurement_manual import build_demo_data
        from django.core.management.base import CommandError

        full_pr = PurchaseRequisition.objects.filter(status="completed", remarks__startswith="[DEMO]").select_related("project").order_by("-created_date").first()
        if not full_pr:
            messages.error(request, "Not enough example data yet to build the manual. Run seed_procurement_demo.")
            return redirect("procurement:dashboard")

        try:
            demo_data = build_demo_data(full_pr.project)
        except CommandError as exc:
            messages.error(request, str(exc))
            return redirect("procurement:dashboard")

        pdf = generate_procurement_manual_pdf(demo_data)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="procurement-user-guide.pdf"'
        return response


def item_scan_lookup(request):
    """
    Looks up an item by its scanned barcode value (exact match) and
    redirects to its detail page -- the same endpoint a camera-based
    scanner (or a handheld USB/Bluetooth scanner acting as a keyboard)
    would submit to.
    """
    code = request.GET.get("code", "").strip()
    if not code:
        messages.error(request, "No barcode value provided.")
        return redirect("procurement:item_list")
    item = ItemMaster.objects.filter(barcode_value=code).first()
    if not item:
        messages.error(request, f"No item found for barcode {code}.")
        return redirect("procurement:item_list")
    return redirect("procurement:item_detail", pk=item.pk)


@login_required
def item_code_check(request):
    """
    Live duplicate check for the item form: given the picked Family/Group/
    Classification/Brand/Attribute, reports whether that Full Code already
    belongs to another item (same rule as ItemMasterForm.clean()).
    """
    parts = [request.GET.get(k, "") for k in ("aa", "bb", "cc", "dd", "eee")]
    if not all(p.isdigit() for p in parts):
        return JsonResponse({"exists": False})
    aa, bb, cc, dd = (p.zfill(2) for p in parts[:4])
    eee = parts[4].zfill(3)
    variant = request.GET.get("variant", "")
    full_code = f"OS.{aa}.{bb}.{cc}.{dd}.{eee}"
    if variant.isdigit() and int(variant):
        full_code += f".{int(variant)}"

    qs = ItemMaster.objects.filter(full_code=full_code)
    exclude = request.GET.get("exclude", "")
    if exclude.isdigit():
        qs = qs.exclude(pk=int(exclude))
    clash = qs.first()
    if not clash:
        return JsonResponse({"exists": False, "full_code": full_code})
    return JsonResponse({
        "exists": True, "full_code": full_code, "description": clash.description,
        "url": reverse("procurement:item_detail", args=[clash.pk]),
    })


class ItemDeleteView(LoginRequiredMixin, DeleteView):
    model = ItemMaster
    template_name = "procurement/confirm_delete.html"
    success_url = reverse_lazy("procurement:item_list")


# ==================== Purchase Requisition ====================

class PRListView(LoginRequiredMixin, ListView):
    model = PurchaseRequisition
    template_name = "procurement/pr_list.html"
    context_object_name = "prs"

    def get_queryset(self):
        user = self.request.user
        qs = PurchaseRequisition.objects.select_related("project", "requested_by", "approved_by")
        if user.is_admin():
            return qs
        if user.is_site_engineer():
            return qs.filter(project__site_engineer=user)
        if user.is_project_manager():
            return qs.filter(project__manager=user)
        if user.is_procurement_officer():
            return qs.filter(status__in=["approved", "in_procurement", "completed"])
        return qs.none()


def pr_create(request):
    user = request.user
    if not user.is_authenticated or not (user.is_site_engineer() or user.is_admin()):
        return HttpResponseForbidden("Only site engineers can create purchase requisitions.")

    if request.method == "POST":
        form = PurchaseRequisitionForm(request.POST)
        if user.is_site_engineer():
            form.fields["project"].queryset = form.fields["project"].queryset.filter(site_engineer=user)
        if form.is_valid():
            pr = form.save(commit=False)
            pr.requested_by = user
            pr.save()
            formset = PurchaseRequisitionLineFormSet(request.POST, instance=pr)
            if formset.is_valid():
                formset.save()
                messages.success(request, f"Purchase requisition {pr.pr_number} created.")
                return redirect("procurement:pr_detail", pk=pr.pk)
            # formset invalid: keep the PR as a draft the user can fix via edit
        else:
            formset = PurchaseRequisitionLineFormSet(request.POST)
    else:
        form = PurchaseRequisitionForm()
        if user.is_site_engineer():
            from projects.models import Project
            form.fields["project"].queryset = form.fields["project"].queryset.filter(site_engineer=user)
        formset = PurchaseRequisitionLineFormSet()

    return render(request, "procurement/pr_form.html", {"form": form, "formset": formset, "title": "New Purchase Requisition"})


def pr_edit(request, pk):
    pr = get_object_or_404(PurchaseRequisition, pk=pk)
    if not _can_manage_pr(request.user, pr):
        return HttpResponseForbidden("You cannot edit this purchase requisition.")
    if pr.status != "draft":
        messages.error(request, "Only draft requisitions can be edited.")
        return redirect("procurement:pr_detail", pk=pk)

    if request.method == "POST":
        form = PurchaseRequisitionForm(request.POST, instance=pr)
        formset = PurchaseRequisitionLineFormSet(request.POST, instance=pr)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Purchase requisition {pr.pr_number} updated.")
            return redirect("procurement:pr_detail", pk=pk)
    else:
        form = PurchaseRequisitionForm(instance=pr)
        formset = PurchaseRequisitionLineFormSet(instance=pr)

    return render(request, "procurement/pr_form.html", {"form": form, "formset": formset, "title": f"Edit {pr.pr_number}", "pr": pr})


class PRDetailView(LoginRequiredMixin, DetailView):
    model = PurchaseRequisition
    template_name = "procurement/pr_detail.html"
    context_object_name = "pr"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pr = self.object
        user = self.request.user
        ctx["lines"] = pr.lines.select_related("item").all()
        ctx["can_manage"] = _can_manage_pr(user, pr)
        ctx["can_approve"] = _can_approve_pr(user, pr)
        ctx["can_work_procurement"] = _can_work_procurement(user)
        ctx["rfqs"] = pr.rfqs.all().order_by("-created_date")
        return ctx


class PRDeleteView(LoginRequiredMixin, DeleteView):
    model = PurchaseRequisition
    template_name = "procurement/confirm_delete.html"
    success_url = reverse_lazy("procurement:pr_list")

    def dispatch(self, request, *args, **kwargs):
        pr = self.get_object()
        if not _can_manage_pr(request.user, pr) or pr.status != "draft":
            return HttpResponseForbidden("Only the owner can delete a draft requisition.")
        return super().dispatch(request, *args, **kwargs)


class PRSubmitView(LoginRequiredMixin, View):
    def post(self, request, pk):
        pr = get_object_or_404(PurchaseRequisition, pk=pk)
        if not _can_manage_pr(request.user, pr):
            return HttpResponseForbidden("You cannot submit this purchase requisition.")
        if pr.status == "draft":
            if pr.project.status == "planning":
                messages.error(
                    request,
                    f"{pr.project.name} is still in Planning. Finish its start-up stages "
                    f"(insurance, tender documents, approved drawings) before requesting material.",
                )
                return redirect("procurement:pr_detail", pk=pk)
            if not pr.lines.exists():
                messages.error(request, "Add at least one item before submitting.")
                return redirect("procurement:pr_detail", pk=pk)
            pr.status = "submitted"
            pr.submitted_date = timezone.now()
            pr.save()
            messages.success(request, f"{pr.pr_number} submitted for approval.")
        return redirect("procurement:pr_detail", pk=pk)


class PRApproveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        pr = get_object_or_404(PurchaseRequisition, pk=pk)
        if not _can_approve_pr(request.user, pr):
            return HttpResponseForbidden("Only this project's manager can approve this requisition.")
        if pr.status == "submitted":
            pr.status = "approved"
            pr.approved_by = request.user
            pr.approved_date = timezone.now()
            pr.save()
            messages.success(request, f"{pr.pr_number} approved.")
        return redirect("procurement:pr_detail", pk=pk)


class PRRejectView(LoginRequiredMixin, View):
    def post(self, request, pk):
        pr = get_object_or_404(PurchaseRequisition, pk=pk)
        if not _can_approve_pr(request.user, pr):
            return HttpResponseForbidden("Only this project's manager can reject this requisition.")
        form = PRRejectForm(request.POST)
        if pr.status == "submitted" and form.is_valid():
            pr.status = "rejected"
            pr.approved_by = request.user
            pr.approved_date = timezone.now()
            pr.rejected_reason = form.cleaned_data["rejected_reason"]
            pr.save()
            messages.success(request, f"{pr.pr_number} rejected.")
        return redirect("procurement:pr_detail", pk=pk)


class PRClaimView(LoginRequiredMixin, View):
    """A procurement officer picks up an approved PR to start working RFQs."""
    def post(self, request, pk):
        pr = get_object_or_404(PurchaseRequisition, pk=pk)
        if not _can_work_procurement(request.user):
            return HttpResponseForbidden("Only procurement officers can pick up requisitions.")
        if pr.status == "approved":
            pr.status = "in_procurement"
            pr.assigned_to = request.user
            pr.save()
            messages.success(request, f"{pr.pr_number} is now in procurement.")
        return redirect("procurement:pr_detail", pk=pk)


class PRPdfView(LoginRequiredMixin, View):
    def get(self, request, pk):
        pr = get_object_or_404(PurchaseRequisition, pk=pk)
        user = request.user
        allowed = (
            user.is_admin() or _can_manage_pr(user, pr) or _can_approve_pr(user, pr)
            or _can_work_procurement(user)
        )
        if not allowed:
            return HttpResponseForbidden("You do not have permission to view this PDF.")
        pdf = generate_pr_pdf(pr)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{pr.pr_number}.pdf"'
        return response


# ==================== RFQ ====================

def rfq_create(request, pr_id):
    pr = get_object_or_404(PurchaseRequisition, pk=pr_id)
    if not _can_work_procurement(request.user):
        return HttpResponseForbidden("Only procurement officers can create an RFQ.")
    if pr.status not in ("approved", "in_procurement"):
        messages.error(request, "Only approved requisitions can go out for quotation.")
        return redirect("procurement:pr_detail", pk=pr_id)

    if request.method == "POST":
        form = RFQForm(request.POST)
        if form.is_valid():
            rfq = RequestForQuotation.objects.create(
                pr=pr, due_date=form.cleaned_data["due_date"], notes=form.cleaned_data["notes"],
                created_by=request.user,
            )
            for vendor in form.cleaned_data["vendors"]:
                RFQVendor.objects.create(rfq=rfq, vendor=vendor)
            if pr.status == "approved":
                pr.status = "in_procurement"
                pr.assigned_to = request.user
                pr.save()
            messages.success(request, f"{rfq.rfq_number} created with {form.cleaned_data['vendors'].count()} vendor(s) invited.")
            return redirect("procurement:rfq_detail", pk=rfq.pk)
    else:
        form = RFQForm()

    return render(request, "procurement/rfq_form.html", {"form": form, "pr": pr})


class RFQListView(LoginRequiredMixin, ListView):
    model = RequestForQuotation
    template_name = "procurement/rfq_list.html"
    context_object_name = "rfqs"

    def get_queryset(self):
        return RequestForQuotation.objects.select_related("pr", "pr__project").order_by("-created_date")


class RFQDetailView(LoginRequiredMixin, DetailView):
    model = RequestForQuotation
    template_name = "procurement/rfq_detail.html"
    context_object_name = "rfq"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rfq = self.object
        ctx["invited_vendors"] = rfq.invited_vendors.select_related("vendor").all()
        quotes = list(rfq.quotes.select_related("vendor").prefetch_related("lines").all())
        ctx["quotes"] = quotes
        pr_lines = list(rfq.pr.lines.select_related("item").all())
        ctx["pr_lines"] = pr_lines
        ctx["can_work_procurement"] = _can_work_procurement(self.request.user)

        # Per-line comparison: one row per PR line, one option per vendor quote
        # (see VendorQuoteLine.is_selected docstring for why selection lives here,
        # not on the whole VendorQuote -- an RFQ can be split across vendors).
        line_rows = []
        all_selected = True
        for pr_line in pr_lines:
            options = []
            has_selection = False
            for quote in quotes:
                qline = next((l for l in quote.lines.all() if l.pr_line_id == pr_line.id), None)
                if qline is None:
                    continue
                options.append({"quote_line": qline, "vendor": quote.vendor})
                if qline.is_selected:
                    has_selection = True
            line_rows.append({"pr_line": pr_line, "options": options})
            if not has_selection:
                all_selected = False
        ctx["line_rows"] = line_rows
        ctx["all_lines_selected"] = all_selected and bool(pr_lines)

        # Sourcing summary: currently-selected lines, grouped by vendor.
        by_vendor = {}
        for pr_line in pr_lines:
            for quote in quotes:
                qline = next((l for l in quote.lines.all() if l.pr_line_id == pr_line.id and l.is_selected), None)
                if qline:
                    by_vendor.setdefault(quote.vendor, []).append(qline)
        ctx["sourcing_summary"] = [
            {"vendor": vendor, "lines": lines, "total": sum((l.total_price for l in lines), Decimal("0.00"))}
            for vendor, lines in by_vendor.items()
        ]
        return ctx


class RFQSendView(LoginRequiredMixin, View):
    def post(self, request, pk):
        rfq = get_object_or_404(RequestForQuotation, pk=pk)
        if not _can_work_procurement(request.user):
            return HttpResponseForbidden("Only procurement officers can send this RFQ.")
        if rfq.status == "draft":
            rfq.status = "sent"
            rfq.sent_date = timezone.now()
            rfq.save()
            rfq.invited_vendors.update(sent_at=timezone.now())
            messages.success(request, f"{rfq.rfq_number} marked as sent to vendors.")
        return redirect("procurement:rfq_detail", pk=pk)


def rfq_add_quote(request, pk):
    rfq = get_object_or_404(RequestForQuotation, pk=pk)
    if not _can_work_procurement(request.user):
        return HttpResponseForbidden("Only procurement officers can record vendor quotes.")

    pr_lines = list(rfq.pr.lines.select_related("item").all())

    if request.method == "POST":
        form = VendorQuoteForm(request.POST)
        if form.is_valid():
            quote = form.save(commit=False)
            quote.rfq = rfq
            quote.entered_by = request.user
            quote.save()
            formset = VendorQuoteLineFormSet(request.POST, instance=quote)
            if formset.is_valid():
                formset.save()
                messages.success(request, f"Quote from {quote.vendor.name} recorded.")
                return redirect("procurement:rfq_detail", pk=rfq.pk)
        else:
            formset = VendorQuoteLineFormSet(request.POST)
    else:
        form = VendorQuoteForm()
        formset = VendorQuoteLineFormSet(initial=[{"pr_line": pl.pk} for pl in pr_lines])

    return render(request, "procurement/rfq_quote_form.html", {
        "form": form, "formset": formset, "rfq": rfq, "pr_lines": pr_lines,
    })


def rfq_select_lines(request, pk):
    """
    Saves the procurement officer's per-item vendor choices from the
    comparison table: for each PR line, which vendor's VendorQuoteLine
    wins it. A single RFQ can end up split across several vendors this
    way (see VendorQuoteLine.is_selected).
    """
    rfq = get_object_or_404(RequestForQuotation, pk=pk)
    if not _can_work_procurement(request.user):
        return HttpResponseForbidden("Only procurement officers can select item sourcing.")
    if request.method != "POST":
        return redirect("procurement:rfq_detail", pk=pk)

    pr_lines = rfq.pr.lines.all()
    changed = 0
    for pr_line in pr_lines:
        chosen_id = request.POST.get(f"line_{pr_line.id}")
        qlines = VendorQuoteLine.objects.filter(quote__rfq=rfq, pr_line=pr_line)
        for qline in qlines:
            should_be_selected = str(qline.id) == chosen_id
            if qline.is_selected != should_be_selected:
                qline.is_selected = should_be_selected
                qline.save(update_fields=["is_selected"])
                changed += 1
    messages.success(request, "Sourcing selection saved." if changed else "No changes to save.")
    return redirect("procurement:rfq_detail", pk=pk)


def po_create_from_rfq(request, pk):
    """
    Creates one Purchase Order per vendor from the RFQ's currently
    selected lines (rfq_select_lines) -- a vendor that won only some of
    the items gets a PO for just those items, not the whole RFQ.
    """
    rfq = get_object_or_404(RequestForQuotation, pk=pk)
    if not _can_work_procurement(request.user):
        return HttpResponseForbidden("Only procurement officers can issue a purchase order.")
    pr = rfq.pr

    pr_lines = list(pr.lines.all())
    by_vendor = {}
    for pr_line in pr_lines:
        qline = VendorQuoteLine.objects.filter(quote__rfq=rfq, pr_line=pr_line, is_selected=True).select_related("quote__vendor", "pr_line__item").first()
        if qline:
            by_vendor.setdefault(qline.quote, []).append(qline)

    if not by_vendor:
        messages.error(request, "Select a vendor for at least one item before creating a purchase order.")
        return redirect("procurement:rfq_detail", pk=pk)

    if request.method == "POST":
        delivery_date = request.POST.get("delivery_date")
        if not delivery_date:
            messages.error(request, "Delivery date is required.")
            return redirect("procurement:rfq_detail", pk=pk)

        created_pos = []
        for quote, qlines in by_vendor.items():
            po = PurchaseOrder.objects.create(
                project=pr.project, vendor=quote.vendor, pr=pr, source_quote=quote,
                delivery_date=delivery_date, created_by=request.user,
            )
            for qline in qlines:
                PurchaseOrderLine.objects.create(
                    po=po, item=qline.pr_line.item, pr_line=qline.pr_line, sub_item=qline.pr_line.sub_item,
                    quantity_ordered=qline.pr_line.quantity_requested, unit=qline.pr_line.unit,
                    unit_price=qline.unit_price,
                )
            po.refresh_from_db()
            created_pos.append(po)

        pr.status = "completed"
        pr.save(update_fields=["status"])
        if len(created_pos) == 1:
            messages.success(request, f"{created_pos[0].po_number} created.")
            return redirect("procurement:po_detail", pk=created_pos[0].pk)
        messages.success(request, f"{len(created_pos)} purchase orders created: " + ", ".join(po.po_number for po in created_pos))
        return redirect("procurement:pr_detail", pk=pr.pk)

    summary = [{"vendor": quote.vendor, "lines": qlines, "total": sum((l.total_price for l in qlines), Decimal("0.00"))}
               for quote, qlines in by_vendor.items()]
    return render(request, "procurement/po_from_rfq_confirm.html", {"rfq": rfq, "pr": pr, "summary": summary})


# ==================== Purchase Order ====================

class POListView(LoginRequiredMixin, ListView):
    model = PurchaseOrder
    template_name = "procurement/po_list.html"
    context_object_name = "pos"

    def get_queryset(self):
        return PurchaseOrder.objects.select_related("vendor", "project").order_by("-po_date")


def po_create(request):
    if not _can_work_procurement(request.user):
        return HttpResponseForbidden("Only procurement officers can create a purchase order.")

    if request.method == "POST":
        form = PurchaseOrderForm(request.POST)
        if form.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            formset = PurchaseOrderLineFormSet(request.POST, instance=po)
            if formset.is_valid():
                formset.save()
                po.recalculate_total()
                messages.success(request, f"{po.po_number} created.")
                return redirect("procurement:po_detail", pk=po.pk)
        else:
            formset = PurchaseOrderLineFormSet(request.POST)
    else:
        form = PurchaseOrderForm()
        formset = PurchaseOrderLineFormSet()

    return render(request, "procurement/po_form.html", {"form": form, "formset": formset, "title": "New Purchase Order (Direct)"})


class PODetailView(LoginRequiredMixin, DetailView):
    model = PurchaseOrder
    template_name = "procurement/po_detail.html"
    context_object_name = "po"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["lines"] = self.object.lines.select_related("item").all()
        ctx["can_work_procurement"] = _can_work_procurement(self.request.user)
        ctx["can_receive_on_site"] = _can_receive_on_site(self.request.user, self.object)
        return ctx


def po_site_receive(request, pk):
    """
    A separate, deliberately "blind" receiving screen for the site: shows
    each PO line's item (with its barcode, to confirm it's the right
    material) and asks only "how much do you have in front of you right
    now" -- it never shows the ordered quantity, since procurement may
    not have approved the exact quantity the site originally requested,
    and the point is an honest physical count, not a guess anchored on
    what was supposed to arrive.
    """
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if not _can_receive_on_site(request.user, po):
        return HttpResponseForbidden("You do not have permission to record receipts for this purchase order.")

    lines = list(po.lines.select_related("item").all())

    if request.method == "POST":
        recorded = []
        for line in lines:
            raw_qty = request.POST.get(f"qty_{line.id}", "").strip()
            if not raw_qty:
                continue
            try:
                qty = Decimal(raw_qty)
            except Exception:
                continue
            if qty <= 0:
                continue
            POReceipt.objects.create(
                po_line=line, quantity_received=qty, received_by=request.user,
                remarks=request.POST.get(f"remarks_{line.id}", "").strip(),
            )
            recorded.append({"item": line.item, "qty": qty, "unit": line.get_unit_display()})
        return render(request, "procurement/po_site_receive_done.html", {"po": po, "recorded": recorded})

    return render(request, "procurement/po_site_receive.html", {"po": po, "lines": lines})


class POSendView(LoginRequiredMixin, View):
    def post(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        if not _can_work_procurement(request.user):
            return HttpResponseForbidden("Only procurement officers can send this order.")
        if po.status == "draft":
            po.status = "sent"
            po.save()
        return redirect("procurement:po_detail", pk=pk)


class PODeleteView(LoginRequiredMixin, DeleteView):
    model = PurchaseOrder
    template_name = "procurement/confirm_delete.html"
    success_url = reverse_lazy("procurement:po_list")

    def dispatch(self, request, *args, **kwargs):
        if not _can_work_procurement(request.user):
            return HttpResponseForbidden("Only procurement officers can delete a purchase order.")
        return super().dispatch(request, *args, **kwargs)


class POPdfView(LoginRequiredMixin, View):
    def get(self, request, pk):
        po = get_object_or_404(PurchaseOrder, pk=pk)
        pdf = generate_po_pdf(po)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{po.po_number}.pdf"'
        return response


# ==================== Vendors ====================
class VendorListView(LoginRequiredMixin, ListView):
    model = Vendor
    template_name = "procurement/vendor_list.html"
    context_object_name = "vendors"


class VendorCreateView(LoginRequiredMixin, CreateView):
    model = Vendor
    form_class = VendorForm
    template_name = "procurement/form.html"
    success_url = reverse_lazy("procurement:vendor_list")


class VendorDetailView(LoginRequiredMixin, DetailView):
    model = Vendor
    template_name = "procurement/vendor_detail.html"
    context_object_name = "vendor"


class VendorUpdateView(LoginRequiredMixin, UpdateView):
    model = Vendor
    form_class = VendorForm
    template_name = "procurement/form.html"
    success_url = reverse_lazy("procurement:vendor_list")


class VendorDeleteView(LoginRequiredMixin, DeleteView):
    model = Vendor
    template_name = "procurement/confirm_delete.html"
    success_url = reverse_lazy("procurement:vendor_list")


# ==================== Receipts ====================
class POReceiptListView(LoginRequiredMixin, ListView):
    model = POReceipt
    template_name = "procurement/receipt_list.html"
    context_object_name = "receipts"


class POReceiptCreateView(LoginRequiredMixin, CreateView):
    model = POReceipt
    form_class = POReceiptForm
    template_name = "procurement/form.html"
    success_url = reverse_lazy("procurement:receipt_list")

    def get_initial(self):
        initial = super().get_initial()
        po_line_id = self.request.GET.get("po_line")
        if po_line_id:
            initial["po_line"] = po_line_id
        return initial

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.received_by = self.request.user
        obj.save()
        return redirect(reverse_lazy("procurement:po_detail", kwargs={"pk": obj.po_line.po_id}))


class POReceiptDetailView(LoginRequiredMixin, DetailView):
    model = POReceipt
    template_name = "procurement/receipt_detail.html"
    context_object_name = "receipt"


class POReceiptUpdateView(LoginRequiredMixin, UpdateView):
    model = POReceipt
    form_class = POReceiptForm
    template_name = "procurement/form.html"
    success_url = reverse_lazy("procurement:receipt_list")


# ==================== DRF API ====================
class ItemViewSet(viewsets.ModelViewSet):
    queryset = ItemMaster.objects.all()
    serializer_class = ItemMasterSerializer
    permission_classes = [permissions.IsAuthenticated]


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [permissions.IsAuthenticated]


class PRViewSet(viewsets.ModelViewSet):
    queryset = PurchaseRequisition.objects.select_related("project").prefetch_related("lines").all()
    serializer_class = PRSerializer
    permission_classes = [permissions.IsAuthenticated]


class POViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related("project", "vendor", "pr").prefetch_related("lines").all()
    serializer_class = POSerializer
    permission_classes = [permissions.IsAuthenticated]


class ReceiptViewSet(viewsets.ModelViewSet):
    queryset = POReceipt.objects.select_related("po_line").all()
    serializer_class = ReceiptSerializer
    permission_classes = [permissions.IsAuthenticated]
