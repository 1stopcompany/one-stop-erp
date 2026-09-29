import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from procurement.forms import PurchaseRequisitionLineFormSet, PurchaseRequisitionForm
from procurement.models import (
    ItemMaster, POReceipt, PurchaseOrder, PurchaseOrderLine, PurchaseRequisition, PurchaseRequisitionLine,
    StockLevel, StockMovement, Vendor, Warehouse,
)
from projects.models import Project
from projects.testing import add_insurance
from reports.progress_models import (
    ProjectPhase, ProjectPhaseProgressEntry, ProjectPhaseSubItem, recalculate_weights_from_contract,
)

from .services import project_cost_summary

User = get_user_model()
D = Decimal


class CostingBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("adm", password="x", role="admin", is_superuser=True)
        cls.pm = User.objects.create_user("pm", password="x", role="project_manager")
        cls.other_pm = User.objects.create_user("pm2", password="x", role="project_manager")
        cls.em = User.objects.create_user("em", password="x", role="engineering_manager")
        cls.engineer = User.objects.create_user("eng", password="x", role="site_engineer")

        def project(symbol, manager):
            return Project.objects.create(
                name=f"Project {symbol}", project_symbol=symbol, contract_number=symbol, client_name="C",
                start_date=date(2025, 1, 1), manager=manager, site_engineer=cls.engineer, status="active",
            )

        cls.project, cls.other = project("P1", cls.pm), project("P2", cls.other_pm)
        add_insurance(cls.project)   # priced BOQ items are added by each test through sub()
        cls.vendor = Vendor.objects.create(name="Supplier")
        cls.cement = ItemMaster.objects.create(
            aa_level="03", bb_category="04", cc_subcategory="01", dd_itemtype="01", eee_attribute="001",
            description="Cement", unit="bag",
        )
        cls.phase = ProjectPhase.objects.create(project=cls.project, code="1", section="Civil", name_ar="أساسات", name_en="Foundations", weight_percentage=0)

    # ---- helpers
    def sub(self, code="1.1", qty=100, budget=10, contract=15, unit="m2", phase=None, name="بند"):
        return ProjectPhaseSubItem.objects.create(
            phase=phase or self.phase, code=code, name_ar=name, weight_percentage=0, unit=unit,
            quantity=D(qty), budget_unit_price=D(budget), contract_unit_price=D(contract),
        )

    def progress(self, sub, pct):
        ProjectPhaseProgressEntry.objects.create(sub_item=sub, report_date=date(2025, 6, 1), execution_percentage=pct)

    def po(self, qty, price, sub_item=None, status="confirmed", pr_line=None):
        po = PurchaseOrder.objects.create(project=self.project, vendor=self.vendor, delivery_date=date.today(), status=status)
        return PurchaseOrderLine.objects.create(
            po=po, item=self.cement, sub_item=sub_item, pr_line=pr_line, quantity_ordered=qty, unit="bag", unit_price=price,
        )

    def line(self, sub):
        return next(r for r in project_cost_summary(self.project)["lines"] if r["sub_item"].pk == sub.pk)


class PricingModelTests(CostingBase):
    def test_sub_item_totals_and_phase_rollup(self):
        a, b = self.sub("1.1", 100, 10, 15), self.sub("1.2", 50, 20, 30)
        self.assertEqual((a.budget_total, a.contract_total), (D(1000), D(1500)))
        self.assertEqual((self.phase.budget_total(), self.phase.contract_total()), (D(2000), D(3000)))

    def test_phase_priced_as_a_whole_gets_a_carrier_sub_item(self):
        phase = ProjectPhase.objects.create(
            project=self.project, code="2", name_ar="مقطوع", weight_percentage=0,
            unit="L.S.", quantity=D(1), budget_unit_price=D(5000), contract_unit_price=D(7000),
        )
        phase.sync_whole_item()
        whole = phase.sub_items.get()
        self.assertTrue(whole.is_whole)
        self.assertEqual((whole.budget_total, whole.contract_total), (D(5000), D(7000)))
        self.assertEqual(phase.contract_total(), D(7000))

        phase.budget_unit_price = D(6000)
        phase.save()
        phase.sync_whole_item()  # a re-price flows through to the carrier
        self.assertEqual(phase.sub_items.get().budget_total, D(6000))

    def test_real_sub_items_take_over_from_an_untouched_carrier(self):
        phase = ProjectPhase.objects.create(project=self.project, code="2", name_ar="x", weight_percentage=0, quantity=D(1), unit="L.S.")
        phase.sync_whole_item()
        self.assertEqual(phase.sub_items.filter(is_whole=True).count(), 1)
        self.sub("2.1", phase=phase)
        phase.sync_whole_item()
        self.assertEqual(list(phase.sub_items.values_list("is_whole", flat=True)), [False])

    def test_a_carrier_with_progress_is_kept(self):
        phase = ProjectPhase.objects.create(project=self.project, code="2", name_ar="x", weight_percentage=0, quantity=D(1), unit="L.S.")
        phase.sync_whole_item()
        self.progress(phase.sub_items.get(), 30)
        self.sub("2.1", phase=phase)
        phase.sync_whole_item()
        self.assertEqual(phase.sub_items.count(), 2)

    def test_weights_follow_the_contract_prices(self):
        a = self.sub("1.1", 100, 10, 15)   # contract 1,500
        b = self.sub("1.2", 50, 20, 30)    # contract 1,500
        other = ProjectPhase.objects.create(project=self.project, code="2", name_ar="y", weight_percentage=0)
        c = self.sub("2.1", 100, 10, 30, phase=other)  # contract 3,000
        total = recalculate_weights_from_contract(self.project)
        self.assertEqual(total, D(6000))
        for obj in (a, b, c, self.phase, other):
            obj.refresh_from_db()
        self.assertEqual((a.weight_percentage, b.weight_percentage, c.weight_percentage), (D("25.000"), D("25.000"), D("50.000")))
        self.assertEqual((self.phase.weight_percentage, other.weight_percentage), (D("50.000"), D("50.000")))

    def test_weights_need_a_priced_boq(self):
        with self.assertRaises(ValueError):
            recalculate_weights_from_contract(self.project)


class BoqEditorApiTests(CostingBase):
    def post(self, url, data, method="post"):
        return getattr(self.client, method)(url, json.dumps(data), content_type="application/json")

    def test_create_phase_with_pricing_and_a_bad_number(self):
        self.client.force_login(self.pm)
        url = reverse("reports:api_boq_phase_create", args=[self.project.pk])
        ok = self.post(url, {"code": "9", "name_ar": "س", "section": "Civil", "unit": "m2", "quantity": "12.5",
                             "budget_unit_price": "40", "contract_unit_price": "55"})
        self.assertEqual(ok.status_code, 201)
        phase = ProjectPhase.objects.get(code="9")
        self.assertEqual((phase.quantity, phase.section), (D("12.5"), "Civil"))
        self.assertEqual(phase.sub_items.get().contract_total, D("687.50"))  # 12.5 x 55, via the carrier

        bad = self.post(url, {"code": "10", "name_ar": "ص", "quantity": "abc"})
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(ProjectPhase.objects.filter(code="10").exists())

    def test_sub_item_pricing_and_recalculate(self):
        self.client.force_login(self.pm)
        resp = self.post(reverse("reports:api_boq_subitem_create", args=[self.project.pk, self.phase.pk]),
                         {"code": "1.7", "name_ar": "بند", "unit": "No.", "quantity": "4", "budget_unit_price": "100", "contract_unit_price": "150"})
        self.assertEqual(resp.status_code, 201)
        sub = ProjectPhaseSubItem.objects.get(code="1.7")
        self.assertEqual(sub.contract_total, D(600))
        resp = self.client.post(reverse("reports:api_boq_recalculate_weights", args=[self.project.pk]))
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.weight_percentage, D("100.000"))

    def test_who_may_edit(self):
        url = reverse("reports:api_boq_recalculate_weights", args=[self.project.pk])
        self.sub()
        self.client.force_login(self.engineer)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.other_pm)
        self.assertEqual(self.client.post(url).status_code, 403)
        for user in (self.em, self.pm):
            self.client.force_login(user)
            self.assertEqual(self.client.post(url).status_code, 200)

    def test_editor_page_renders_with_prices(self):
        self.sub()
        self.client.force_login(self.pm)
        resp = self.client.get(reverse("reports:boq_editor", args=[self.project.pk]))
        self.assertContains(resp, "Weights from prices")
        self.assertContains(resp, "Contract total")


class CostSummaryTests(CostingBase):
    def test_committed_counts_issued_orders_and_follows_the_boq_item(self):
        s = self.sub()
        self.po(60, 10, s, "confirmed")
        self.po(10, 10, s, "draft")
        self.po(20, 10, s, "cancelled")
        row = self.line(s)
        self.assertEqual((row["committed"], row["status"]), (D(600), "ordered"))

    def test_a_requisition_lines_boq_item_carries_through_to_its_order(self):
        s = self.sub()
        pr = PurchaseRequisition.objects.create(project=self.project, required_date=date.today(), requested_by=self.pm)
        pr_line = PurchaseRequisitionLine.objects.create(pr=pr, item=self.cement, sub_item=s, quantity_requested=5, unit="bag")
        self.po(5, 10, None, pr_line=pr_line)
        self.assertEqual(self.line(s)["committed"], D(50))

    def test_purchases_without_a_boq_item_are_reported_separately(self):
        self.sub()
        line = self.po(10, 10, None)
        POReceipt.objects.create(po_line=line, quantity_received=4)
        summary = project_cost_summary(self.project)
        self.assertEqual(summary["unassigned"], {"committed": D(100), "actual": D(40)})
        self.assertEqual(summary["totals"]["actual"], D(0))

    def test_actual_is_valued_at_po_prices_across_orders(self):
        s = self.sub()
        POReceipt.objects.create(po_line=self.po(10, 10, s), quantity_received=10)
        POReceipt.objects.create(po_line=self.po(30, 12, s), quantity_received=30)
        self.assertEqual(self.line(s)["actual"], D("460.00"))  # 10*10 + 30*12

    def test_earned_value_follows_the_sub_items_own_progress(self):
        s = self.sub(qty=100, budget=10)
        self.progress(s, 40)
        row = self.line(s)
        self.assertEqual((row["progress_pct"], row["earned"], row["executed_qty"]), (D("40.00"), D(400), D(40)))

    def test_saving_then_overrun_even_though_under_the_whole_budget(self):
        s = self.sub(qty=100, budget=10)  # budget 1,000
        self.progress(s, 40)              # earned 400
        POReceipt.objects.create(po_line=self.po(30, D("10.5"), s), quantity_received=30)  # actual 315
        row = self.line(s)
        self.assertEqual((row["cost_variance"], row["cpi"], row["status"]), (D("85.00"), D("1.27"), "saving"))

        POReceipt.objects.create(po_line=self.po(50, D("10.5"), s), quantity_received=50)  # actual now 840
        row = self.line(s)
        self.assertEqual((row["status"], row["cpi"]), ("overrun", D("0.48")))
        self.assertLess(row["actual"], row["budget"])  # still far below the full budget

    def test_forecast_unit_cost_and_the_floor(self):
        s = self.sub(qty=100, budget=10)
        self.progress(s, 40)
        POReceipt.objects.create(po_line=self.po(80, D("10.5"), s), quantity_received=80)  # actual 840, earned 400
        row = self.line(s)
        self.assertEqual((row["eac"], row["vac"]), (D("2100.00"), D("-1100.00")))
        self.assertEqual(row["actual_unit_cost"], D("21.00"))       # 840 / 40 units executed
        self.assertEqual(row["unit_cost_variance"], D("11.00"))      # vs a budget of 10
        # the forecast is never below what is already ordered
        s2 = self.sub("1.2", qty=100, budget=10)
        self.progress(s2, 100)
        self.po(150, 10, s2)
        row2 = self.line(s2)
        self.assertGreaterEqual(row2["eac"], row2["committed"])

    def test_ordering_more_than_the_budget_and_spent_with_no_progress(self):
        a, b = self.sub("1.1", 100, 10), self.sub("1.2", 100, 10)
        self.po(120, 10, a)
        self.assertEqual(self.line(a)["status"], "over_committed")
        POReceipt.objects.create(po_line=self.po(10, 10, b), quantity_received=10)
        self.assertEqual(self.line(b)["status"], "no_progress")

    def test_phase_section_and_project_rollups_with_margin(self):
        a, b = self.sub("1.1", 100, 10, 15), self.sub("1.2", 50, 20, 30)
        other = ProjectPhase.objects.create(project=self.project, code="2", section="Electrical", name_ar="ك", weight_percentage=0)
        c = self.sub("2.1", 10, 100, 160, phase=other)
        self.progress(a, 100)
        summary = project_cost_summary(self.project)
        civil, electrical = summary["sections"]
        self.assertEqual((civil["name"], civil["row"]["budget"], civil["row"]["contract"]), ("Civil", D(2000), D(3000)))
        self.assertEqual(civil["phases"][0]["row"]["earned"], D(1000))
        self.assertEqual((electrical["name"], electrical["row"]["budget"]), ("Electrical", D(1000)))
        totals = summary["totals"]
        self.assertEqual((totals["budget"], totals["contract"], totals["planned_margin"]), (D(3000), D(4600), D(1600)))
        self.assertEqual(len(summary["lines"]), 3)

    def test_unpriced_items_without_spending_are_left_out(self):
        self.sub("1.1", qty=0, budget=0, contract=0)
        self.assertEqual(project_cost_summary(self.project)["lines"], [])


class AllocationFormTests(CostingBase):
    def test_a_line_cannot_be_charged_to_another_projects_boq_item(self):
        other_phase = ProjectPhase.objects.create(project=self.other, code="1", name_ar="ج", weight_percentage=0)
        foreign = self.sub("9.9", phase=other_phase)
        own = self.sub("1.1")
        pr = PurchaseRequisition.objects.create(project=self.project, required_date=date.today(), requested_by=self.pm)

        def formset(sub_item):
            return PurchaseRequisitionLineFormSet({
                "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "1000",
                "lines-0-item": self.cement.pk, "lines-0-sub_item": sub_item.pk,
                "lines-0-quantity_requested": "5", "lines-0-unit": "bag",
            }, instance=pr)

        self.assertFalse(formset(foreign).is_valid())
        self.assertTrue(formset(own).is_valid())

    def test_the_boq_item_list_carries_each_options_project(self):
        self.sub("1.1")
        html = str(PurchaseRequisitionLineFormSet(instance=PurchaseRequisition(project=self.project)).forms[0]["sub_item"])
        self.assertIn(f'data-project="{self.project.pk}"', html)

    def test_a_planning_projects_boq_items_are_not_offered(self):
        planning = Project.objects.create(
            name="Planning", project_symbol="PL", contract_number="PL", client_name="C", start_date=date(2025, 1, 1),
            manager=self.pm, status="planning",
        )
        phase = ProjectPhase.objects.create(project=planning, code="1", name_ar="خ", weight_percentage=0)
        hidden = self.sub("1.1", phase=phase)
        queryset = PurchaseRequisitionLineFormSet(instance=PurchaseRequisition(project=self.project)).forms[0].fields["sub_item"].queryset
        self.assertNotIn(hidden, queryset)


class PagesTests(CostingBase):
    def test_pages_render(self):
        s = self.sub()
        self.progress(s, 40)
        POReceipt.objects.create(po_line=self.po(30, 10, s), quantity_received=30)
        self.client.force_login(self.admin)
        for url in (
            reverse("cost_control:budget_list"), reverse("cost_control:budget_list") + f"?project={self.project.pk}",
            reverse("cost_control:budget_detail", args=[s.pk]), reverse("cost_control:budget_create"),
            reverse("cost_control:dashboard") + f"?project={self.project.pk}",
            reverse("cost_control:api_budget_vs_actual") + f"?project_id={self.project.pk}",
            reverse("cost_control:api_variance_analysis") + f"?project_id={self.project.pk}",
            reverse("cost_control:manual_pdf"),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_chart_api_carries_the_four_series_per_phase(self):
        self.sub()
        self.client.force_login(self.admin)
        data = self.client.get(reverse("cost_control:api_budget_vs_actual") + f"?project_id={self.project.pk}").json()
        self.assertEqual(data["labels"], ["1"])
        self.assertTrue({"budgeted", "committed", "earned", "actual"} <= set(data))

    def test_another_projects_manager_cannot_open_an_item(self):
        s = self.sub()
        self.client.force_login(self.other_pm)
        self.assertEqual(self.client.get(reverse("cost_control:budget_detail", args=[s.pk])).status_code, 404)

    def test_user_guide_is_a_pdf(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("cost_control:manual_pdf"))
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))


class ImportAndDemoTests(CostingBase):
    def test_faten_import_loads_the_tender_boq_and_clears_cleanly(self):
        faten = Project.objects.create(
            name="FATEN", project_symbol="FTN", contract_number="F", client_name="F", start_date=date(2026, 9, 1),
            manager=self.pm, status="planning",
        )
        call_command("import_faten_boq")
        self.assertEqual(faten.phases.count(), 51)
        self.assertEqual({p.section for p in faten.phases.all()}, {"الأعمال المدنية", "الأعمال الكهربائية", "الأعمال الميكانيكية"})
        blocks = faten.phases.get(code="1.03")
        self.assertEqual(sorted((s.code, s.quantity) for s in blocks.sub_items.all()), [("1.03.أ", None), ("1.03.ب", D("50"))])
        # a phase the document prices as a whole carries its own unit and quantity
        plaster = faten.phases.get(code="1.04")
        self.assertEqual((plaster.unit, plaster.quantity), ("م²", D("100")))
        self.assertTrue(plaster.sub_items.get().is_whole)
        call_command("import_faten_boq")  # second run is a no-op
        self.assertEqual(faten.phases.count(), 51)
        call_command("import_faten_boq", "--clear")
        self.assertEqual(faten.phases.count(), 0)

    def test_import_refuses_to_mix_into_an_existing_boq(self):
        Project.objects.create(name="F", project_symbol="FTN", contract_number="F", client_name="F", start_date=date(2026, 9, 1),
                               manager=self.pm, status="planning")
        ProjectPhase.objects.create(project=Project.objects.get(project_symbol="FTN"), code="X", name_ar="x", weight_percentage=0)
        with self.assertRaises(CommandError):
            call_command("import_faten_boq")

    def test_demo_seed_shows_every_status_and_clears_cleanly(self):
        for code in ("OS.03.08.01.01.004", "OS.03.09.01.02.012", "OS.03.04.01.01.000", "OS.05.02.11.01.002",
                     "OS.09.03.01.01.000", "OS.09.04.03.01.000", "OS.04.03.01.04.001", "OS.09.04.02.01.000"):
            aa, bb, cc, dd, eee = code.split(".")[1:]
            ItemMaster.objects.create(aa_level=aa, bb_category=bb, cc_subcategory=cc, dd_itemtype=dd,
                                      eee_attribute=eee, description=code, unit="pcs")
        real_warehouses = Warehouse.objects.count()

        call_command("seed_costing_demo")
        demo = Project.objects.get(project_symbol="DEMOCC")
        summary = project_cost_summary(demo)
        self.assertEqual({row["status"] for row in summary["lines"]},
                         {"overrun", "saving", "on_track", "ordered", "not_started", "over_committed", "no_progress"})
        self.assertEqual(len(summary["lines"]), 8)
        self.assertEqual(summary["unassigned"]["committed"], D("1100.00"))
        self.assertFalse(StockLevel.objects.exclude(warehouse__project=demo).exists())  # receipts stayed in the demo's own store

        call_command("seed_costing_demo")  # second run is a no-op
        self.assertEqual(Project.objects.filter(project_symbol="DEMOCC").count(), 1)
        call_command("seed_costing_demo", "--clear")
        self.assertFalse(Project.objects.filter(project_symbol="DEMOCC").exists())
        self.assertEqual(Warehouse.objects.count(), real_warehouses)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertFalse(Vendor.objects.filter(name="[DEMO] Supplier").exists())


class PrintOutTests(CostingBase):
    """The BOQ and cost report print-outs: management only, and they open as real PDFs."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.gm = User.objects.create_user("gm", password="x", role="general_manager")

    def pdf(self, user, name, **query):
        self.client.force_login(user)
        url = reverse(name, args=[self.project.pk]) if name == "reports:boq_pdf" else reverse(name) + f"?project={self.project.pk}"
        return self.client.get(url)

    def test_general_manager_can_print_both(self):
        s = self.sub()
        self.progress(s, 40)
        POReceipt.objects.create(po_line=self.po(30, 10, s), quantity_received=30)
        for name in ("reports:boq_pdf", "cost_control:report_pdf"):
            resp = self.pdf(self.gm, name)
            self.assertEqual(resp.status_code, 200, name)
            self.assertEqual(resp["Content-Type"], "application/pdf")
            self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_management_roles_and_the_projects_own_manager_may_print(self):
        for user in (self.admin, self.em, self.pm):
            for name in ("reports:boq_pdf", "cost_control:report_pdf"):
                self.assertEqual(self.pdf(user, name).status_code, 200, (user.role, name))

    def test_site_engineers_and_other_projects_managers_may_not(self):
        for user in (self.engineer, self.other_pm):
            self.assertEqual(self.pdf(user, "reports:boq_pdf").status_code, 403, user.role)
        self.assertEqual(self.pdf(self.engineer, "cost_control:report_pdf").status_code, 403)

    def test_an_empty_boq_still_prints(self):
        for name in ("reports:boq_pdf", "cost_control:report_pdf"):
            self.assertEqual(self.pdf(self.gm, name).status_code, 200)

    def test_the_faten_boq_prints_across_pages(self):
        faten = Project.objects.create(name="FATEN", project_symbol="FTN", contract_number="F", client_name="F",
                                       start_date=date(2026, 9, 1), manager=self.pm, status="planning")
        call_command("import_faten_boq")
        self.client.force_login(self.gm)
        resp = self.client.get(reverse("reports:boq_pdf", args=[faten.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(resp.content.count(b"/Type /Page"), 3)

    def test_print_buttons_are_on_the_project_and_budget_pages_for_the_general_manager(self):
        self.sub()
        self.client.force_login(self.gm)
        page = self.client.get(reverse("projects:project_detail", args=[self.project.pk]))
        self.assertContains(page, reverse("reports:boq_pdf", args=[self.project.pk]))
        page = self.client.get(reverse("cost_control:budget_list") + f"?project={self.project.pk}")
        self.assertContains(page, "Print report")
        self.assertNotContains(page, "bi-list-columns-reverse")  # no Manage BOQ button: the general manager prints; editing stays with the managers
