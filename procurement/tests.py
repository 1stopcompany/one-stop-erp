from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from projects.models import Project
from projects.testing import make_ready
from .models import (
    ItemMaster, Vendor, PurchaseOrder, PurchaseOrderLine, POReceipt,
    PurchaseRequisition, Warehouse, StockLevel, StockMovement,
)
from .services_warehouse import (
    StockError, record_movement, low_stock_levels, on_order_by_item, create_replenishment_pr,
)

User = get_user_model()


class WarehouseTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user("officer", password="x", role="procurement_officer")
        cls.engineer = User.objects.create_user("engineer", password="x", role="site_engineer")
        cls.project = Project.objects.create(
            name="Tower A", project_symbol="TA", contract_number="C-1", client_name="Client", start_date=date(2025, 1, 1),
        )
        make_ready(cls.project)
        cls.item = ItemMaster.objects.create(
            aa_level="01", bb_category="01", cc_subcategory="01", dd_itemtype="01", eee_attribute="001",
            description="Cement bag", unit="bag",
        )
        cls.wh = Warehouse.objects.create(name="Main")


class StockRulesTests(WarehouseTestBase):
    def test_issue_cannot_take_stock_below_zero(self):
        record_movement(self.wh, self.item, "adjustment", 10)
        with self.assertRaises(StockError):
            record_movement(self.wh, self.item, "issue", -11)
        self.assertEqual(StockLevel.objects.get(warehouse=self.wh, item=self.item).quantity, Decimal("10"))

    def test_ledger_matches_balance(self):
        record_movement(self.wh, self.item, "adjustment", 50)
        record_movement(self.wh, self.item, "issue", -20, project=self.project)
        level = StockLevel.objects.get(warehouse=self.wh, item=self.item)
        self.assertEqual(level.quantity, Decimal("30"))
        self.assertEqual(list(StockMovement.objects.order_by("id").values_list("balance_after", flat=True)),
                         [Decimal("50"), Decimal("30")])

    def test_low_flag_reaches_at_minimum(self):
        record_movement(self.wh, self.item, "adjustment", 30)
        level = StockLevel.objects.get(warehouse=self.wh, item=self.item)
        level.min_quantity = Decimal("20")
        level.save()
        self.assertFalse(level.is_low)
        self.assertEqual(low_stock_levels().count(), 0)
        record_movement(self.wh, self.item, "issue", -10)
        level.refresh_from_db()
        self.assertTrue(level.is_low)  # exactly at the limit counts -- it must not fall below it
        self.assertEqual(level.status, "low")
        self.assertEqual(low_stock_levels().count(), 1)
        # no reorder_quantity set -> back up to twice the minimum: 2*20 - 20 on hand
        self.assertEqual(level.suggested_order_quantity, Decimal("20.00"))
        level.reorder_quantity = Decimal("75")
        self.assertEqual(level.suggested_order_quantity, Decimal("75"))

    def test_no_limit_means_never_low(self):
        record_movement(self.wh, self.item, "adjustment", 1)
        self.assertEqual(low_stock_levels().count(), 0)


class ReceiptSyncTests(WarehouseTestBase):
    def _po_line(self, qty=100):
        vendor = Vendor.objects.create(name="Supplier")
        po = PurchaseOrder.objects.create(project=self.project, vendor=vendor, delivery_date=date.today())
        return PurchaseOrderLine.objects.create(po=po, item=self.item, quantity_ordered=qty, unit="bag", unit_price=5)

    def test_receipt_adds_edit_adjusts_delete_removes(self):
        line = self._po_line()
        receipt = POReceipt.objects.create(po_line=line, quantity_received=40, received_by=self.officer)
        level = StockLevel.objects.get(item=self.item)
        self.assertEqual(level.quantity, Decimal("40"))
        self.assertEqual(level.warehouse, self.wh)  # no site store for this project -> the general warehouse

        receipt.quantity_received = Decimal("55")
        receipt.save()
        level.refresh_from_db()
        self.assertEqual(level.quantity, Decimal("55"))

        receipt.delete()
        level.refresh_from_db()
        self.assertEqual(level.quantity, Decimal("0"))

    def test_project_site_store_gets_the_goods(self):
        site = Warehouse.objects.create(name="Tower A store", project=self.project)
        POReceipt.objects.create(po_line=self._po_line(), quantity_received=12)
        self.assertEqual(StockLevel.objects.get(warehouse=site, item=self.item).quantity, Decimal("12"))

    def test_on_order_counts_outstanding_po_only(self):
        line = self._po_line(qty=100)
        POReceipt.objects.create(po_line=line, quantity_received=30)
        self.assertEqual(on_order_by_item()[self.item.pk], Decimal("70"))


class ReorderTests(WarehouseTestBase):
    def test_replenishment_pr_is_a_draft_with_the_lines(self):
        record_movement(self.wh, self.item, "adjustment", 5)
        level = StockLevel.objects.get(warehouse=self.wh, item=self.item)
        level.min_quantity = Decimal("10")
        level.save()
        pr = create_replenishment_pr([(level, Decimal("40"))], self.project, self.officer)
        self.assertEqual(pr.status, "draft")
        line = pr.lines.get()
        self.assertEqual((line.item, line.quantity_requested, line.unit), (self.item, Decimal("40"), "bag"))


class WarehouseViewTests(WarehouseTestBase):
    def test_everyone_sees_stock_but_only_procurement_changes_it(self):
        self.client.force_login(self.engineer)
        self.assertEqual(self.client.get(reverse("procurement:stock_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("procurement:stock_issue")).status_code, 403)
        self.assertEqual(self.client.get(reverse("procurement:stock_limit")).status_code, 403)

    def test_issue_over_stock_is_rejected_with_message(self):
        record_movement(self.wh, self.item, "adjustment", 5)
        self.client.force_login(self.officer)
        resp = self.client.post(reverse("procurement:stock_issue"), {
            "warehouse": self.wh.pk, "item": self.item.pk, "quantity": "9", "project": self.project.pk,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Only 5 of")
        self.assertEqual(StockLevel.objects.get(item=self.item).quantity, Decimal("5"))

    def test_issue_down_to_minimum_warns_to_reorder(self):
        record_movement(self.wh, self.item, "adjustment", 20)
        self.client.force_login(self.officer)
        self.client.post(reverse("procurement:stock_limit"), {
            "warehouse": self.wh.pk, "item": self.item.pk, "min_quantity": "15", "reorder_quantity": "50",
        })
        resp = self.client.post(reverse("procurement:stock_issue"), {
            "warehouse": self.wh.pk, "item": self.item.pk, "quantity": "6", "project": self.project.pk,
        }, follow=True)
        self.assertContains(resp, "must be re-ordered")

    def test_reorder_page_creates_draft_pr_from_ticked_rows(self):
        record_movement(self.wh, self.item, "adjustment", 3)
        level = StockLevel.objects.get(item=self.item)
        level.min_quantity = Decimal("10")
        level.save()
        self.client.force_login(self.officer)
        resp = self.client.post(reverse("procurement:stock_reorder"), {
            "sel": [level.pk], f"qty_{level.pk}": "25", "project": self.project.pk,
            "required_date": (date.today() + timedelta(days=5)).isoformat(),
        })
        pr = PurchaseRequisition.objects.get()
        self.assertRedirects(resp, reverse("procurement:pr_detail", args=[pr.pk]))
        self.assertEqual(pr.lines.get().quantity_requested, Decimal("25"))
        # the officer who raised it can open and submit it
        self.assertEqual(self.client.get(reverse("procurement:pr_detail", args=[pr.pk])).status_code, 200)


class PlanningProjectGateTests(WarehouseTestBase):
    """Material can't be requested or bought for a project still in the Planning start-up flow."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.planning = Project.objects.create(
            name="Not started", project_symbol="NS", contract_number="C-2", client_name="Client",
            start_date=date(2025, 1, 1), manager=cls.officer, site_engineer=cls.engineer, status="planning",
        )
        cls.project.site_engineer = cls.engineer
        cls.project.save()

    def test_pr_and_po_forms_do_not_offer_planning_projects(self):
        from .forms import PurchaseRequisitionForm, PurchaseOrderForm
        for form in (PurchaseRequisitionForm(), PurchaseOrderForm()):
            offered = set(form.fields["project"].queryset)
            self.assertIn(self.project, offered)
            self.assertNotIn(self.planning, offered)

    def test_site_engineer_cannot_create_pr_for_planning_project(self):
        self.client.force_login(self.engineer)
        resp = self.client.get(reverse("procurement:pr_create"))
        self.assertNotIn(self.planning, set(resp.context["form"].fields["project"].queryset))
        resp = self.client.post(reverse("procurement:pr_create"), {
            "project": self.planning.pk, "required_date": date.today().isoformat(), "remarks": "",
            "lines-TOTAL_FORMS": "0", "lines-INITIAL_FORMS": "0",
        })
        self.assertEqual(PurchaseRequisition.objects.count(), 0)

    def test_draft_pr_on_planning_project_cannot_be_submitted(self):
        pr = PurchaseRequisition.objects.create(project=self.planning, required_date=date.today(), requested_by=self.engineer)
        pr.lines.create(item=self.item, quantity_requested=5, unit="bag")
        self.client.force_login(self.engineer)
        self.client.post(reverse("procurement:pr_submit", args=[pr.pk]))
        pr.refresh_from_db()
        self.assertEqual(pr.status, "draft")

    def test_reorder_list_does_not_offer_planning_projects(self):
        from .forms_warehouse import ReorderForm
        self.assertNotIn(self.planning, set(ReorderForm().fields["project"].queryset))
