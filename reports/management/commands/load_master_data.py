"""
Management Command: Load Master Data

This command loads predefined workforce categories, labor classifications,
and equipment into the database.

Usage:
    python manage.py load_master_data
"""

from django.core.management.base import BaseCommand
from reports.master_data_models import WorkforceCategory, LaborClassification, EquipmentMaster


class Command(BaseCommand):
    help = 'Load master data for workforce categories, labor classifications, and equipment'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Loading master data...'))
        
        # Load Workforce Categories and Labor Classifications
        self.load_workforce_data()
        
        # Load Equipment Master Data
        self.load_equipment_data()
        
        self.stdout.write(self.style.SUCCESS('Master data loaded successfully!'))
    
    def load_workforce_data(self):
        """Load workforce categories and labor classifications"""
        
        self.stdout.write('Loading workforce categories...')
        
        # Project Management Category
        pm_category, created = WorkforceCategory.objects.get_or_create(
            name='Project Management',
            defaults={
                'description': 'Project management and supervision staff',
                'is_active': True,
                'order': 1
            }
        )
        
        pm_classifications = [
            ('Project Manager', 'M'),
            ('Civil Engineer', 'M'),
            ('Mechanical Engineer', 'M'),
            ('Electrical Engineer', 'M'),
            ('Safety Manager', 'M'),
            ('Office Engineer', 'F'),
            ('Training Engineer', 'M'),
            ('Office Boy', 'M'),
        ]
        
        for name, gender in pm_classifications:
            LaborClassification.objects.get_or_create(
                category=pm_category,
                name=name,
                defaults={
                    'default_gender': gender,
                    'is_active': True,
                    'order': pm_classifications.index((name, gender))
                }
            )
        
        # Work Force Category
        wf_category, created = WorkforceCategory.objects.get_or_create(
            name='Work Force',
            defaults={
                'description': 'Construction and labor workforce',
                'is_active': True,
                'order': 2
            }
        )
        
        wf_classifications = [
            ('Equipment Operator', 'M'),
            ('Guard', 'M'),
            ('Skilled Labor', 'M'),
            ('Unskilled Labor', 'M'),
            ('Painter', 'M'),
            ('Carpenter', 'M'),
            ('Gypsum Works', 'M'),
            ('Plumber 1st team', 'M'),
            ('Electrician', 'M'),
            ('Plaster', 'M'),
            ('Tile workers', 'M'),
            ('Iron sheet Workers', 'M'),
            ('Welder', 'M'),
            ('Block Mason', 'M'),
            ('Masonry', 'M'),
            ('Medical Gases Worker', 'M'),
            ('Aluminium Workers', 'M'),
        ]
        
        for name, gender in wf_classifications:
            LaborClassification.objects.get_or_create(
                category=wf_category,
                name=name,
                defaults={
                    'default_gender': gender,
                    'is_active': True,
                    'order': wf_classifications.index((name, gender))
                }
            )
        
        self.stdout.write(self.style.SUCCESS(f'✓ Loaded {len(pm_classifications) + len(wf_classifications)} labor classifications'))
    
    def load_equipment_data(self):
        """Load equipment master data"""
        
        self.stdout.write('Loading equipment master data...')
        
        equipment_list = [
            ('Fixed Winch', 'Lifting', 'Various', ''),
            ('Chain Excavator', 'Excavation', 'Various', ''),
            ('Dump Truck', 'Transport', 'Various', ''),
            ('Truck Mounted Crane', 'Lifting', 'Various', ''),
            ('Wheel Excavator', 'Excavation', 'Various', ''),
            ('Concrete Mixer', 'Concrete', 'Various', ''),
            ('Concrete Pump', 'Concrete', 'Various', ''),
            ('Back hoe loader, JCB', 'Excavation', 'JCB', ''),
            ('Steel Roller, Bomag 120', 'Compaction', 'Bomag', '120'),
            ('Tele handler, JCB', 'Lifting', 'JCB', ''),
            ('Single size Pump', 'Pumping', 'Various', ''),
            ('Concrete helicopter', 'Concrete', 'Various', ''),
            ('Sandblasting Machines', 'Surface Treatment', 'Various', ''),
            ('Scaffolding System', 'Support', 'Various', ''),
            ('Formwork System', 'Support', 'Various', ''),
            ('Power Generator', 'Power', 'Various', ''),
            ('Air Compressor', 'Air Supply', 'Various', ''),
            ('Welding Machine', 'Welding', 'Various', ''),
            ('Cutting Machine', 'Cutting', 'Various', ''),
            ('Vibrator', 'Concrete', 'Various', ''),
        ]
        
        for name, category, manufacturer, model in equipment_list:
            EquipmentMaster.objects.get_or_create(
                name=name,
                defaults={
                    'category': category,
                    'manufacturer': manufacturer,
                    'model': model,
                    'is_active': True
                }
            )
        
        self.stdout.write(self.style.SUCCESS(f'✓ Loaded {len(equipment_list)} equipment items'))
