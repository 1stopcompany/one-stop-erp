"""
The schedule (Gantt) side: the CPM engine against hand-worked examples, the data the page draws, the demo schedule's consistency
with its own links, and who can open the page.
"""
import json
import re
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from projects.models import Project
from reports import schedule_demo
from reports.progress_models import ProjectMilestone, ProjectPhase
from reports.schedule_models import ScheduleTask
from reports.services import cpm
from reports.services.schedule_view import build_schedule, parse_lag, parse_predecessors

User = get_user_model()

SAT = date(2026, 9, 19)      # a Saturday: the first day of the company's work week


def act(key, duration, *links, **extra):
    return {"id": key, "duration": duration, "links": list(links), **extra}


class CalendarTests(SimpleTestCase):
    def test_friday_is_the_day_off(self):
        self.assertTrue(cpm.is_workday(date(2026, 9, 19)))            # Saturday
        self.assertTrue(cpm.is_workday(date(2026, 9, 24)))            # Thursday
        self.assertFalse(cpm.is_workday(date(2026, 9, 25)))           # Friday
        self.assertEqual(cpm.next_workday(date(2026, 9, 25)), date(2026, 9, 26))

    def test_slots_skip_fridays_and_holidays(self):
        calendar = cpm.Calendar(SAT, holidays=[date(2026, 9, 20)])
        self.assertEqual([calendar.date_of(i) for i in range(4)], [date(2026, 9, 19), date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)])
        self.assertEqual(calendar.slot_of(date(2026, 9, 25)), calendar.slot_of(date(2026, 9, 26)))


class CpmTests(SimpleTestCase):
    def run_cpm(self, *activities, **kwargs):
        return cpm.schedule(list(activities), kwargs.get("start", SAT), kwargs.get("holidays", ()))

    def test_a_chain_of_finish_to_start_links_skips_the_weekly_day_off(self):
        result = self.run_cpm(act("A", 3), act("B", 2, ("A", "FS", 0)), act("C", 4, ("B", "FS", 0)))["activities"]
        self.assertEqual((result["A"]["start"], result["A"]["finish"]), (date(2026, 9, 19), date(2026, 9, 21)))   # Sat, Sun, Mon
        self.assertEqual((result["B"]["start"], result["B"]["finish"]), (date(2026, 9, 22), date(2026, 9, 23)))   # Tue, Wed
        self.assertEqual((result["C"]["start"], result["C"]["finish"]), (date(2026, 9, 24), date(2026, 9, 28)))   # Thu, (Fri off) Sat, Sun, Mon
        self.assertTrue(all(r["critical"] and r["float"] == 0 for r in result.values()))

    def test_float_and_the_critical_path(self):
        result = self.run_cpm(act("A", 2), act("SHORT", 1, ("A", "FS", 0)), act("LONG", 5, ("A", "FS", 0)), act("END", 1, ("SHORT", "FS", 0), ("LONG", "FS", 0)))
        activities = result["activities"]
        self.assertEqual((activities["SHORT"]["float"], activities["SHORT"]["critical"]), (4, False))
        self.assertEqual((activities["LONG"]["float"], activities["LONG"]["critical"]), (0, True))
        self.assertEqual(activities["SHORT"]["late_start"] > activities["SHORT"]["start"], True)
        self.assertEqual(result["finish"], activities["END"]["finish"])

    def test_lag_on_finish_to_start(self):
        result = self.run_cpm(act("A", 3), act("B", 1, ("A", "FS", 2)))["activities"]
        self.assertEqual(result["B"]["start"], date(2026, 9, 24))         # slot 5: two work days after A's finish

    def test_start_to_start_finish_to_finish_and_start_to_finish(self):
        ss = self.run_cpm(act("A", 3), act("B", 4, ("A", "SS", 1)))["activities"]
        self.assertEqual(ss["B"]["start"], date(2026, 9, 20))
        ff = self.run_cpm(act("A", 3), act("B", 2, ("A", "FF", 0)))["activities"]
        self.assertEqual((ff["B"]["start"], ff["B"]["finish"]), (date(2026, 9, 20), date(2026, 9, 21)), "B ends when A ends")
        sf = self.run_cpm(act("A", 3, not_before=date(2026, 9, 22)), act("B", 2, ("A", "SF", 1)))["activities"]
        self.assertEqual(sf["A"]["start"], date(2026, 9, 22))
        self.assertLessEqual(sf["B"]["start"], sf["A"]["start"], "a start-to-finish successor finishes after its predecessor starts")

    def test_milestones_sit_on_the_next_work_day(self):
        result = self.run_cpm(act("A", 3), act("M", 0, ("A", "FS", 0)))["activities"]
        self.assertEqual((result["M"]["start"], result["M"]["finish"]), (date(2026, 9, 22), date(2026, 9, 22)))

    def test_not_before_and_holidays(self):
        result = self.run_cpm(act("A", 2, not_before=date(2026, 9, 25)))["activities"]     # a Friday: starts the next work day
        self.assertEqual(result["A"]["start"], date(2026, 9, 26))
        held = self.run_cpm(act("A", 3), holidays=[date(2026, 9, 20)])["activities"]
        self.assertEqual(held["A"]["finish"], date(2026, 9, 22))

    def test_bad_networks_are_rejected(self):
        with self.assertRaises(cpm.ScheduleError):
            self.run_cpm(act("A", 1, ("B", "FS", 0)), act("B", 1, ("A", "FS", 0)))
        with self.assertRaises(cpm.ScheduleError):
            self.run_cpm(act("A", 1, ("GHOST", "FS", 0)))
        with self.assertRaises(cpm.ScheduleError):
            self.run_cpm(act("A", 1), act("A", 2))
        with self.assertRaises(cpm.ScheduleError):
            self.run_cpm(act("A", -1))
        with self.assertRaises(cpm.ScheduleError):
            self.run_cpm(act("A", 1, ("A", "XX", 0)))


class PredecessorParsingTests(SimpleTestCase):
    def test_lags(self):
        self.assertEqual([parse_lag(t) for t in ("+14 days", "-2d", "+1 wk", "+2 weeks", "+3", "+50%", "+4 hrs", "")], [14, -2, 7, 14, 3, 0, 0, 0])

    def test_ms_project_and_activity_id_styles(self):
        by_uid, by_activity = {1: 101, 5: 105, 7: 107}, {"A1010": 201}
        links = parse_predecessors("5,7FS+3 days,1SS-2d,A1010FF,99,junk!", by_uid, by_activity)
        self.assertEqual([(l["from"], l["type"], l["lag"]) for l in links], [(105, "FS", 0), (107, "FS", 3), (101, "SS", -2), (201, "FF", 0)])
        self.assertEqual(parse_predecessors("", by_uid, by_activity), [])
        self.assertEqual(parse_predecessors("a1010SF+1d", by_uid, by_activity)[0]["type"], "SF")


def make_project(symbol="SCH", manager=None, engineer=None, start=date(2026, 5, 1)):
    return Project.objects.create(name=f"Project {symbol}", project_symbol=symbol, contract_number=f"C-{symbol}", client_name="C",
                                  start_date=start, status="active", manager=manager, site_engineer=engineer)


def task(project, uid, name, level=1, **fields):
    defaults = dict(unique_id=uid, is_summary=False, is_milestone=False, percent_complete=Decimal("0"), is_critical=False)
    defaults.update(fields)
    return ScheduleTask.objects.create(project=project, source_task_id=uid, name=name, outline_level=level, **defaults)


class BuildScheduleTests(TestCase):
    def setUp(self):
        self.project = make_project()
        d = date
        task(self.project, 1, "Structure", 1, is_summary=True, start_date=None, finish_date=None)
        task(self.project, 2, "Columns", 2, start_date=d(2026, 6, 1), finish_date=d(2026, 6, 30), duration_text="30 days", percent_complete=Decimal("50"),
             is_critical=True, total_slack_days=Decimal("0"), baseline_start=d(2026, 6, 1), baseline_finish=d(2026, 6, 20), activity_id="A100")
        task(self.project, 3, "Slab", 2, start_date=d(2026, 7, 1), finish_date=d(2026, 7, 20), predecessors="2,A100SS+3 days", activity_id="A110")
        task(self.project, 4, "Handover", 1, is_milestone=True, start_date=d(2026, 8, 1), finish_date=d(2026, 8, 1), predecessors="3FS+2 days")
        phase = ProjectPhase.objects.create(project=self.project, code="1", name_ar="a", name_en="Civil", weight_percentage=0, order=1)
        ProjectMilestone.objects.create(phase=phase, name_ar="رخصة", name_en="Permit", baseline_date=d(2026, 5, 10), forecast_date=d(2026, 5, 20), actual_date=d(2026, 5, 22))

    def test_wbs_parents_summary_dates_links_and_baseline(self):
        data = build_schedule(self.project, today=date(2026, 6, 15))
        rows = {r["uid"]: r for r in data["tasks"] if r["uid"]}
        self.assertEqual((rows[2]["parent"], rows[3]["parent"], rows[4]["parent"]), (rows[1]["id"], rows[1]["id"], None))
        self.assertTrue(rows[1]["summary"])
        self.assertEqual((rows[1]["start"], rows[1]["finish"]), ("2026-06-01", "2026-07-20"), "a summary without dates takes them from its children")
        self.assertEqual((rows[2]["baseline_finish"], rows[2]["critical"], rows[2]["percent"], rows[2]["duration"]), ("2026-06-20", True, 50.0, "30d"))
        self.assertEqual([(l["from"], l["type"], l["lag"]) for l in rows[3]["links"]], [(rows[2]["id"], "FS", 0), (rows[2]["id"], "SS", 3)])
        self.assertEqual(rows[4]["links"][0]["lag"], 2)
        self.assertEqual(rows[4]["duration"], "0d")

    def test_key_milestones_are_added_as_a_group(self):
        data = build_schedule(self.project, today=date(2026, 6, 15))
        group = data["tasks"][-2]
        milestone = data["tasks"][-1]
        self.assertEqual((group["name"], group["summary"], group["synthetic"]), ("Key milestones", True, True))
        self.assertEqual((milestone["name"], milestone["milestone"], milestone["parent"], milestone["start"], milestone["baseline_start"], milestone["percent"]),
                         ("Permit", True, group["id"], "2026-05-22", "2026-05-10", 100.0), "an achieved milestone sits on its actual date")

    def test_statistics(self):
        stats = build_schedule(self.project, today=date(2026, 6, 15))["stats"]
        self.assertEqual((stats["activities"], stats["completed"], stats["in_progress"], stats["critical"]), (3, 0, 1, 1))
        self.assertEqual(stats["finish"], "2026-08-01")
        self.assertGreater(stats["percent_complete"], 0)
        self.assertEqual(stats["remaining_days"], (date(2026, 8, 1) - date(2026, 6, 15)).days)

    def test_an_empty_project_has_no_rows(self):
        data = build_schedule(make_project("EMP"))
        self.assertEqual((data["tasks"], data["stats"]["activities"], data["stats"]["finish"]), ([], 0, None))


class DemoScheduleTests(TestCase):
    def setUp(self):
        self.project = make_project("DEMOCC", start=date(2026, 5, 24))
        self.today = date(2026, 9, 21)
        schedule_demo.seed(self.project, today=self.today)
        self.tasks = {t.activity_id: t for t in ScheduleTask.objects.filter(project=self.project)}

    def test_every_link_holds_in_the_stored_dates(self):
        by_uid = {t.source_task_id: t for t in self.tasks.values()}
        checked = 0
        for t in self.tasks.values():
            for link in parse_predecessors(t.predecessors, {u: u for u in by_uid}, {}):
                pred, lag = by_uid[link["from"]], int(link["lag"])
                if link["type"] == "FS":
                    # a milestone sits at the start of its day, so what waits for it may start that same day
                    later = t.start_date >= pred.finish_date if pred.is_milestone else t.start_date > pred.finish_date
                    self.assertTrue(later, f"{t.activity_id} starts after {pred.activity_id} finishes")
                elif link["type"] == "SS":
                    self.assertGreaterEqual(t.start_date, pred.start_date)
                elif link["type"] == "FF":
                    self.assertGreaterEqual(t.finish_date, pred.finish_date)
                checked += 1
        self.assertGreater(checked, 30)

    def test_shape_of_the_network(self):
        rows = list(ScheduleTask.objects.filter(project=self.project).order_by("source_task_id"))
        self.assertEqual(len(rows), len(schedule_demo.ROWS))
        self.assertEqual({r.outline_level for r in rows}, {1, 2, 3})
        self.assertTrue(any(r.is_milestone for r in rows) and any(r.is_summary for r in rows))
        self.assertTrue(any(r.is_critical for r in rows) and any(not r.is_critical and not r.is_summary and r.total_slack_days > 0 for r in rows))
        text = " ".join(r.predecessors for r in rows)
        for kind in ("SS", "FF"):
            self.assertIn(kind, text, f"the demo should show {kind} links")
        self.assertRegex(text, r"FS\+\d+ days", "and a lag")

    def test_the_current_schedule_has_slipped_against_the_baseline(self):
        slipped = [t for t in self.tasks.values() if t.baseline_finish and t.finish_date > t.baseline_finish]
        self.assertGreater(len(slipped), 5)
        self.assertTrue(all(t.finish_date >= t.baseline_finish for t in self.tasks.values() if t.baseline_finish))
        stats = build_schedule(self.project, today=self.today)["stats"]
        self.assertGreater(stats["finish_variance_days"], 0)

    def test_progress_matches_the_data_date(self):
        for t in self.tasks.values():
            if t.is_summary:
                continue
            if t.finish_date <= self.today:
                self.assertEqual(t.percent_complete, Decimal("100.0"), t.activity_id)
                self.assertEqual(t.actual_finish, t.finish_date)
            elif t.start_date > self.today:
                self.assertEqual(t.percent_complete, 0, t.activity_id)
                self.assertIsNone(t.actual_start)
            else:
                self.assertTrue(0 < t.percent_complete < 100, t.activity_id)

    def test_summaries_span_their_children_and_seeding_again_replaces_them(self):
        structure = self.tasks["S011"]
        children = [self.tasks[k] for k in ("A3000", "A3040", "A3025")]
        self.assertLessEqual(structure.start_date, min(c.start_date for c in children))
        self.assertGreaterEqual(structure.finish_date, max(c.finish_date for c in children))
        before = ScheduleTask.objects.filter(project=self.project).count()
        schedule_demo.seed(self.project, today=self.today)
        self.assertEqual(ScheduleTask.objects.filter(project=self.project).count(), before)
        self.assertEqual(schedule_demo.clear(self.project), before)

    def test_the_command_seeds_and_clears(self):
        ScheduleTask.objects.all().delete()
        out = StringIO()
        call_command("seed_schedule_demo", stdout=out)
        self.assertIn("Seeded", out.getvalue())
        self.assertGreater(ScheduleTask.objects.count(), 30)
        call_command("seed_schedule_demo", clear=True, stdout=out)
        self.assertEqual(ScheduleTask.objects.count(), 0)

    def test_real_imported_rows_are_left_alone_by_clear(self):
        ScheduleTask.objects.create(project=self.project, source_task_id=999, unique_id=999, name="Imported", source_file_name="real.mpp")
        schedule_demo.clear(self.project)
        self.assertEqual(list(ScheduleTask.objects.values_list("name", flat=True)), ["Imported"])


class SchedulePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("adm", password="x", role="admin", is_superuser=True)
        cls.pm = User.objects.create_user("pm", password="x", role="project_manager")
        cls.other_pm = User.objects.create_user("pm2", password="x", role="project_manager")
        cls.engineer = User.objects.create_user("eng", password="x", role="site_engineer")
        cls.project = make_project("PG", manager=cls.pm, engineer=cls.engineer)
        cls.url = reverse("reports:project_schedule", args=[cls.project.pk])

    def test_a_project_without_a_schedule_explains_how_to_get_one(self):
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertContains(response, "no schedule yet")
        self.assertContains(response, "import_ms_project_schedule")
        self.assertNotContains(response, "pv-data")

    def test_the_page_carries_the_schedule_as_json_for_the_chart(self):
        schedule_demo.seed(self.project)
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertContains(response, "Project Schedule")
        for text in ("Critical path", "Baseline", "Relationships", "Compact columns", "Data date", "Quarter", "Fit"):
            self.assertContains(response, text)
        match = re.search(r'<script id="pv-data" type="application/json">(.*?)</script>', response.content.decode(), re.S)
        data = json.loads(match.group(1))
        self.assertEqual(len(data["tasks"]), len(schedule_demo.ROWS))
        self.assertIn("A1000", {t["activity_id"] for t in data["tasks"]})
        self.assertTrue(all(key in data["tasks"][0] for key in ("start", "finish", "baseline_start", "critical", "links", "float", "percent")))

    def test_names_are_escaped_in_the_data(self):
        task(self.project, 1, "</script><b>x</b>", start_date=date(2026, 6, 1), finish_date=date(2026, 6, 2))
        self.client.force_login(self.admin)
        html = self.client.get(self.url).content.decode()
        self.assertNotIn("</script><b>x</b>", html)
        self.assertIn("\\u003C/script\\u003E", html)

    def test_who_can_open_it(self):
        for user, code in [(self.admin, 200), (self.pm, 200), (self.engineer, 200), (self.other_pm, 403)]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, code, user.username)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_the_project_page_links_to_it(self):
        self.client.force_login(self.pm)
        self.assertContains(self.client.get(reverse("projects:project_detail", args=[self.project.pk])), self.url)
