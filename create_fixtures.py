"""
Script to create sample data for testing the application
Run with: python manage.py shell < create_fixtures.py
"""

from django.utils import timezone
from datetime import datetime, timedelta
from accounts.models import CustomUser
from projects.models import Project, ProjectFloor
from reports.models import MonthlyReport, FloorActivity, ExternalWork, MaterialSupply, UpcomingWork

# Create users
print("Creating users...")

admin_user = CustomUser.objects.create_user(
    username='admin',
    email='admin@example.com',
    password='admin123',
    first_name='Admin',
    last_name='User',
    role='admin',
    designation='System Administrator',
    department='IT'
)

manager_user = CustomUser.objects.create_user(
    username='manager',
    email='manager@example.com',
    password='manager123',
    first_name='John',
    last_name='Manager',
    role='project_manager',
    designation='Project Manager',
    department='Construction'
)

engineer_user = CustomUser.objects.create_user(
    username='engineer',
    email='engineer@example.com',
    password='engineer123',
    first_name='Ahmed',
    last_name='Engineer',
    role='site_engineer',
    designation='Site Engineer',
    department='Construction'
)

print(f"Created users: {admin_user}, {manager_user}, {engineer_user}")

# Create projects
print("\nCreating projects...")

project1 = Project.objects.create(
    name='Downtown Office Complex',
    project_symbol='DOC-2025',
    contract_number='CNT-001-2025',
    client_name='One Stop',
    start_date=datetime(2025, 1, 15).date(),
    maintenance_type='preventive',
    status='active',
    location='Downtown District',
    description='A modern office complex with 15 floors',
    manager=manager_user,
    created_by=admin_user
)

project2 = Project.objects.create(
    name='Shopping Mall Renovation',
    project_symbol='SMR-2025',
    contract_number='CNT-002-2025',
    client_name='One Stop',
    start_date=datetime(2025, 2, 1).date(),
    maintenance_type='corrective',
    status='active',
    location='Commercial Zone',
    description='Renovation and maintenance of shopping mall facilities',
    manager=manager_user,
    created_by=admin_user
)

print(f"Created projects: {project1}, {project2}")

# Create floors
print("\nCreating floors...")

floors_data = [
    ('G', 'Ground Floor', 5000),
    ('1', 'First Floor', 4500),
    ('2', 'Second Floor', 4500),
    ('3', 'Third Floor', 4500),
]

for floor_num, floor_name, area in floors_data:
    ProjectFloor.objects.create(
        project=project1,
        floor_number=floor_num,
        floor_name=floor_name,
        area_sqm=area,
        description=f'{floor_name} of Downtown Office Complex'
    )

print("Created floors for project1")

# Create monthly reports
print("\nCreating monthly reports...")

today = timezone.now().date()
period_from = today.replace(day=1)
period_to = (period_from + timedelta(days=32)).replace(day=1) - timedelta(days=1)

report1 = MonthlyReport.objects.create(
    project=project1,
    site_engineer=engineer_user,
    reporting_period_from=period_from,
    reporting_period_to=period_to,
    weather_conditions='sunny',
    general_description='All maintenance activities completed as scheduled. Ground floor HVAC system serviced. First floor electrical inspection completed. No major issues reported. All systems operational.',
    status='approved',
    approved_by=manager_user,
    approval_date=timezone.now()
)

report2 = MonthlyReport.objects.create(
    project=project1,
    site_engineer=engineer_user,
    reporting_period_from=period_from - timedelta(days=30),
    reporting_period_to=period_from - timedelta(days=1),
    weather_conditions='rainy',
    general_description='Preventive maintenance activities ongoing. Water proofing inspection on all floors. Drainage system cleaned. Minor repairs on second floor completed.',
    status='submitted'
)

print(f"Created reports: {report1}, {report2}")

# Create floor activities
print("\nCreating floor activities...")

floors = project1.floors.all()
for floor in floors:
    FloorActivity.objects.create(
        report=report1,
        floor=floor,
        activity_description=f'HVAC system inspection and maintenance on {floor.floor_name}',
        completion_percentage=100,
        notes='All systems functioning normally'
    )
    
    FloorActivity.objects.create(
        report=report2,
        floor=floor,
        activity_description=f'Electrical safety inspection on {floor.floor_name}',
        completion_percentage=75,
        notes='Inspection in progress, final report pending'
    )

print("Created floor activities")

# Create external works
print("\nCreating external works...")

ExternalWork.objects.create(
    report=report1,
    activity_description='Parking lot maintenance and line marking',
    completion_percentage=100,
    notes='Completed successfully'
)

ExternalWork.objects.create(
    report=report1,
    activity_description='Landscaping and garden maintenance',
    completion_percentage=85,
    notes='Ongoing, expected completion by end of month'
)

print("Created external works")

# Create material supplies
print("\nCreating material supplies...")

MaterialSupply.objects.create(
    report=report1,
    material_description='HVAC filters and replacement parts',
    quantity=50,
    unit='pieces',
    supplier='ABC Supplies Co.',
    delivery_date=period_from + timedelta(days=5),
    notes='High quality filters for optimal performance'
)

MaterialSupply.objects.create(
    report=report1,
    material_description='Electrical cables and wiring',
    quantity=100,
    unit='meters',
    supplier='XYZ Electrical',
    delivery_date=period_from + timedelta(days=3),
    notes='Certified cables meeting safety standards'
)

print("Created material supplies")

# Create upcoming works
print("\nCreating upcoming works...")

UpcomingWork.objects.create(
    report=report1,
    activity_description='Roof inspection and waterproofing treatment',
    planned_start_date=today + timedelta(days=5),
    planned_end_date=today + timedelta(days=15),
    priority='high',
    notes='Critical maintenance before rainy season'
)

UpcomingWork.objects.create(
    report=report1,
    activity_description='Fire safety system testing and certification',
    planned_start_date=today + timedelta(days=10),
    planned_end_date=today + timedelta(days=12),
    priority='high',
    notes='Annual certification required'
)

UpcomingWork.objects.create(
    report=report1,
    activity_description='General cleaning and pest control',
    planned_start_date=today + timedelta(days=20),
    planned_end_date=today + timedelta(days=22),
    priority='medium',
    notes='Routine maintenance'
)

print("Created upcoming works")

print("\n" + "="*50)
print("✅ Sample data created successfully!")
print("="*50)
print("\nDemo Credentials:")
print("Admin: admin / admin123")
print("Manager: manager / manager123")
print("Engineer: engineer / engineer123")
print("\nYou can now login and explore the application.")
