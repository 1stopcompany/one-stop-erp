"""
Load the tender bill of quantities of the FATEN project ("Palestine for Credit and Development -
FATEN", fit-out of the new Dura branch, quantities schedule dated 15/09/2026) into the project's
BOQ: one phase per numbered item, one sub-item per lettered / numbered line, grouped in three
sections (Civil, Electrical, Mechanical), with the document's units and quantities.

The tender document has empty price columns, so units and quantities are loaded and every price
and weight stays zero -- enter the budget and contract prices in Manage BOQ, then use "Weights
from prices". Quantities the document leaves blank are left blank.

The document has a few numbering slips that are corrected here (the original number is kept in
each phase's notes): a second "1.05" (floor tiles -> 1.05-2), "7.02" (doors -> 1.21), a second
"1.21" (panel doors -> 1.22), "7.3" (fire door -> 1.23) and a second "2.7.2" (cameras -> 2.7.3).

Usage:
    python manage.py import_faten_boq              # project with symbol FTN
    python manage.py import_faten_boq --clear      # remove what this command imported
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from projects.models import Project
from reports.progress_models import ProjectPhase, ProjectPhaseSubItem

MARK = "[IMPORT:FATEN-BOQ]"
CIVIL, ELEC, MECH = "الأعمال المدنية", "الأعمال الكهربائية", "الأعمال الميكانيكية"
LS, M2, ML, NO = "مقطوع", "م²", "م.ط", "عدد"

# (code, Arabic name, English name, unit, quantity, [sub-items], note)   sub-item: (code, Arabic, unit, quantity)
# A phase with sub-items is priced through them; one without carries its own unit/quantity.
DOC = [
    (CIVIL, [
        ("1.01", "هدم وإزالة القواطع القائمة وترحيل الأنقاض", "Demolition of existing partitions and debris removal", LS, 1, [], ""),
        ("1.02", "إزالة البلاط الأرضي والبانيل القائم", "Removal of existing floor tiles and skirting", LS, 1, [], ""),
        ("1.03", "قواطع من الطوب الإسمنتي المفرغ", "Hollow cement block partitions", None, None, [
            ("1.03.أ", "طوب مفرغ سماكة 20 سم", M2, None), ("1.03.ب", "طوب مفرغ سماكة 10 سم", M2, 50)], ""),
        ("1.04", "قصارة داخلية للجدران", "Internal wall plastering", M2, 100, [], ""),
        ("1.05", "صيانة مكان الواجهات المهدومة", "Repair of the demolished facade areas", LS, 1, [], ""),
        ("1.05-2", "بلاط بورسلان أرضي 60×60 سم", "Porcelain floor tiles 60x60", M2, 60, [], "Numbered 1.05 a second time in the document"),
        ("1.06", "بلاط بورسلان غير قابل للتزحلق للحمامات", "Non-slip porcelain tiles for bathrooms", M2, 7, [], ""),
        ("1.07", "بلاط جدران للحمامات وفوق خزانة المطبخ", "Wall tiles for bathrooms and above the kitchen base cabinets", M2, 36, [], ""),
        ("1.08", "رخام تركي للعتبات", "Turkish marble thresholds", ML, 7, [], ""),
        ("1.09", "قواطع ألواح جبس مقاوم للرطوبة", "Moisture-resistant gypsum board partitions", M2, 2, [], ""),
        ("1.10", "تلبيس جبس للواجهات الخارجية من الداخل ولوحات الكهرباء", "Gypsum lining to external walls and electrical panels", M2, 4, [], ""),
        ("1.11", "سقف مستعار وشراشف من الجبس الأخضر", "Green gypsum false ceiling and bulkheads", M2, 40, [], ""),
        ("1.12", "شبكة أسقف مستعارة أرمسترونج 60×60 سم", "Armstrong 60x60 false ceiling grid", M2, 24, [], ""),
        ("1.13", "أسقف من الصاج المخرم", "Perforated sheet-metal ceilings", M2, 11, [], ""),
        ("1.14", "دهان سوبر كريل للجدران الداخلية", "Super acrylic paint to internal walls", M2, 250, [], ""),
        ("1.15", "دهان إملشن للأسقف الداخلية", "Emulsion paint to internal ceilings", M2, 50, [], ""),
        ("1.16", "قواطع ثابتة من الزجاج المقسى 10 ملم", "Fixed 10 mm tempered glass partitions", M2, 25, [], ""),
        ("1.17", "أبواب زجاج سيكوريت", "Tempered glass doors", None, None, [
            ("1.17.1", "GD01 مقاس 90/210 سم", NO, 1), ("1.17.2", "GD02 مقاس 75/210 سم", NO, 1), ("1.17.3", "GD03 مقاس 100/210 سم", NO, 1)], ""),
        ("1.18", "باب سحاب منزلق لواجهة المدخل", "Sliding entrance glass door", LS, 0, [], ""),
        ("1.19", "باب أباجور للمدخل الرئيسي", "Roller shutter door, main entrance", LS, 0, [], ""),
        ("1.20", "خزائن مطبخ سفلية بسطح غرانيت", "Kitchen base cabinets with granite top", ML, 2, [], ""),
        ("1.21", "أبواب بوليمير مكبوس", "Pressed polymer doors", None, None, [
            ("1.21.أ", "WD01 مقاس 80×205 سم دفة واحدة", NO, 2), ("1.21.ب", "WD02 مقاس 90×205 سم دفة واحدة", NO, 2),
            ("1.21.ج", "WD04 مقاس 90×205 سم دفة واحدة سحاب", NO, 1)], "Numbered 7.02 in the document"),
        ("1.22", "دفات خشبية للوحة الكهرباء الرئيسية وخزانة الشبكات", "MDF doors for the main electrical panel and network cabinet", M2, 8, [], "Numbered 1.21 a second time in the document"),
        ("1.23", "باب معدني مقاوم للحريق SD01 مقاس 100×210 سم", "Fire-rated metal door SD01, 100x210", NO, 1, [], "Numbered 7.3 in the document"),
    ]),
    (ELEC, [
        ("2.1", "اللوحات الكهربائية", "Electrical panels", None, None, [("2.1.1", "لوحة DB", NO, 1), ("2.1.2", "لوحة UDB", NO, 1)], ""),
        ("2.2", "الكوابل الرئيسية", "Main cables", None, None, [("2.2.1", "كوابل XLPE مقطع 5×6 ملم²", ML, 30)], ""),
        ("2.3", "خط كوبرا 2 إنش لخدمة الاتصالات", "2 inch conduit line for telecom", ML, 12, [], ""),
        ("2.4", "نظام القوى", "Power system", None, None, [
            ("2.4.1", "إبريز مفرد", NO, 3), ("2.4.2", "إبريز مفرد مطري", NO, 2), ("2.4.3", "إبريز مزدوج", NO, 7),
            ("2.4.4", "إبريز مزدوج UPS", NO, 6), ("2.4.5", "نقطة 1 فاز لتغذية السخان الكهربائي", NO, 1),
            ("2.4.6", "نقاط UPS خاصة بساعة الدوام وأجهزة الإنذار وخزانة الشبكات", NO, 4),
            ("2.4.7", "نقطة كهرباء خاصة بالبوابة الكهربائية الرئيسية", NO, 0),
            ("2.4.8", "إبريز 1 فاز للمكيفات الجانبية والأجهزة الميكانيكية ومراوح الشفط", NO, 6),
            ("2.4.9", "برابيش خاصة بالثيرموستات لوحدات التكييف", NO, 4),
            ("2.4.10", "مفتاح قطع 3 فاز لوحدة التكييف الخارجية VRF", NO, 1)], ""),
        ("2.5", "نظام الإنارة", "Lighting system", None, None, [
            ("2.5.1", "نقطة إنارة كاملة مع الكوابل والمفاتيح والكبسات", NO, 45), ("2.5.2", "نقطة إنارة لوحدات الطوارئ وEXIT", NO, 4),
            ("2.5.3", "نقطة إنارة مخفية", NO, 4), ("2.5.4", "نقطة إنارة القارمة مع مؤقت زمني", NO, 2)], ""),
        ("2.6", "وحدات الإنارة", "Light fittings", None, None, [
            ("2.6.1", "Type A", NO, 15), ("2.6.2", "Type B", NO, 20), ("2.6.3", "Type *B", NO, 10), ("2.6.4", "Type D", NO, 1),
            ("2.6.5", "Type F", ML, 28), ("2.6.6", "Type Em", NO, 4), ("2.6.7", "Type Exit", NO, 1)], ""),
        ("2.7", "نظام الكمبيوتر والتلفون", "Computer and telephone system", None, None, [
            ("2.7.1", "نقاط كمبيوتر DATA", NO, 15), ("2.7.2", "نقاط تلفون TELEPHONE", NO, 2),
            ("2.7.3", "نقاط كاميرات CAMERA POINT", NO, 6)], "The cameras line is numbered 2.7.2 a second time in the document"),
        ("2.8", "نظام إنذار الحريق (تأسيس)", "Fire alarm system (first fix)", None, None, [
            ("2.8.1", "تأسيس لوحة إنذار الحريق شامل العلبة PT5", NO, 1), ("2.8.2", "تأسيس نقاط لنظام إنذار الحريق", NO, 15)], ""),
        ("2.9", "نظام إنذار ضد السرقة (تأسيس)", "Burglar alarm system (first fix)", None, None, [
            ("2.9.1", "تأسيس لوحة إنذار السرقة شامل العلبة PT5", NO, 1), ("2.9.2", "تأسيس نقاط لنظام إنذار السرقة", NO, 10)], ""),
        ("2.10", "نظام الأرث", "Earthing system", LS, 1, [], ""),
        ("2.11", "نظام UPS بقدرة 6KVA", "6 kVA UPS system", "L.S.", 1, [], ""),
    ]),
    (MECH, [
        ("3.1", "السيفونات وفتحات التنظيف الأرضية", "Floor drains and cleanouts", None, None, [
            ("3.1.1", "مصارف أرضية قياس 4 إنش", NO, 3), ("3.1.2", "فتحات تنظيف قياس 4 إنش", NO, 2)], ""),
        ("3.2", "مواسير الصرف الصحي UPVC", "UPVC drainage pipes", None, None, [
            ("3.2.1", "مواسير قياس 4 إنش", ML, 5), ("3.2.2", "مواسير قياس 2 إنش", ML, 35)], ""),
        ("3.3", "مغاسل معلقة", "Wall-hung wash basins", NO, 2, [], ""),
        ("3.4", "مرحاض إفرنجي معلق", "Wall-hung WC", NO, 2, [], ""),
        ("3.5", "مجلى", "Kitchen sink", NO, 1, [], ""),
        ("3.6", "شبكة مواسير المياه", "Water pipe network", None, None, [
            ("3.6.1", "مواسير قطر 3/4 إنش", ML, 9), ("3.6.2", "برابيش 20 ملم من وإلى البويلر", ML, 10)], ""),
        ("3.7", "مجمعات نحاسية", "Copper manifolds", None, None, [
            ("3.7.1", "مجمع قطر 3/4 إنش (7 عيون بارد و3 عيون ساخن)", NO, 1)], ""),
        ("3.8", "سخان كهربائي سعة 60 لتر", "60 litre electric water heater", NO, 1, [], ""),
        ("3.9", "طفايات حريق يدوية 3 كغم", "3 kg hand fire extinguishers", NO, 0, [], ""),
        ("3.10", "قنوات الهواء الدافع المرنة", "Flexible supply-air ducts", LS, 1, [], ""),
        ("3.14", "مراوح الشفط المركزية", "Central in-line exhaust fans", None, None, [
            ("3.14.1", "مروحة شفط بقدرة 100 لتر/ث", NO, 2)], ""),
        ("3.15", "وحدة التكييف VRF الخارجية", "VRF outdoor unit", None, None, [
            ("3.15.1", "OUT DOOR VRF UNIT (16.0 kW) مع القاعدة المعدنية", LS, 1)], ""),
        ("3.16", "وحدات التكييف الداخلية", "VRF indoor units", None, None, [
            ("3.16.1", "Four way cassette 2.8 kW", NO, 1), ("3.16.2", "Low static ducted 7.1 kW", NO, 2)], ""),
        ("3.17", "شبكة أنابيب النحاس والتفريعات", "Refrigerant piping network and branches", None, None, [
            ("3.17.1", "أنابيب نحاس معزولة لغاز التبريد 410", LS, 1)], ""),
        ("3.18", "قنوات الهواء", "Ductwork", None, None, [("3.18.1", "قنوات هواء معزولة مسبقاً", M2, 25)], ""),
        ("3.19", "جريلات ومشتتات الهواء", "Grills and diffusers", None, None, [
            ("3.19.1", "جريل توريد 2 slot", "Mr.", 4), ("3.19.2", "جريل توريد 4 اتجاهات 30×30 سم", NO, 3),
            ("3.19.3", "جريل رجوع 4 اتجاهات 30×30 سم", NO, 3), ("3.19.4", "Disk valve 4 إنش", NO, 1),
            ("3.19.5", "Disk valve 6 إنش", NO, 2), ("3.19.6", "باب صيانة 60×60 سم مع رجوع", NO, 1),
            ("3.19.7", "جريل مطري 6 إنش مع شبك", NO, 2)], ""),
    ]),
]


def _q(value):
    return None if value is None else Decimal(str(value))


class Command(BaseCommand):
    help = "Load the FATEN tender bill of quantities (units and quantities, no prices) into the FTN project's BOQ"

    def add_arguments(self, parser):
        parser.add_argument("--project", default="FTN", help="Project symbol (default FTN)")
        parser.add_argument("--clear", action="store_true", help="Remove the phases this command imported")

    @transaction.atomic
    def handle(self, *args, **options):
        project = Project.objects.filter(project_symbol=options["project"]).first()
        if not project:
            raise CommandError(f"No project with symbol {options['project']}.")

        imported = ProjectPhase.objects.filter(project=project, notes__contains=MARK)
        if options["clear"]:
            count = imported.count()
            imported.delete()
            self.stdout.write(self.style.SUCCESS(f"Removed {count} imported phase(s) from {project.name}."))
            return
        if imported.exists():
            self.stdout.write("Already imported -- nothing to do (use --clear to reset).")
            return
        if project.phases.exists():
            raise CommandError(f"{project.name} already has its own BOQ phases; refusing to mix the document into them.")

        order = phases = subs = 0
        for section, items in DOC:
            for code, name_ar, name_en, unit, qty, children, note in items:
                order += 1
                phase = ProjectPhase.objects.create(
                    project=project, code=code, name_ar=name_ar, name_en=name_en, section=section, order=order,
                    weight_percentage=0, unit=unit or "", quantity=_q(qty),
                    notes=f"{MARK} {note}".strip(),
                )
                phases += 1
                if children:
                    for i, (sub_code, sub_name, sub_unit, sub_qty) in enumerate(children, start=1):
                        ProjectPhaseSubItem.objects.create(
                            phase=phase, code=sub_code, name_ar=sub_name, weight_percentage=0,
                            unit=sub_unit, quantity=_q(sub_qty), order=i,
                        )
                        subs += 1
                else:
                    phase.sync_whole_item()  # carries progress for an item priced as a whole
                    subs += 1
        self.stdout.write(self.style.SUCCESS(
            f"Imported {phases} items in {len(DOC)} sections ({subs} priced lines) into {project.name}. "
            "Prices and weights are still zero: enter them in Manage BOQ, then use 'Weights from prices'."
        ))
