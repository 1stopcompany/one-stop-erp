# Structured Workforce, Equipment, and BOQ Sections - Complete Implementation Guide

## Overview

This implementation adds structured sections to the Daily Report where users can select predefined items from master data lists:

1. **Workforce Section** - Select from predefined labor classifications organized by category
2. **Equipment Section** - Select from predefined equipment master list
3. **Materials Section** - Select from project-specific Bill of Quantities (BOQ)

---

## Architecture

### Master Data Models

#### 1. **WorkforceCategory**
Represents workforce categories (e.g., Project Management, Work Force)

```python
class WorkforceCategory(models.Model):
    name = CharField(max_length=100, unique=True)
    description = TextField()
    is_active = BooleanField(default=True)
    order = IntegerField(default=0)
```

**Examples:**
- Project Management
- Work Force

#### 2. **LaborClassification**
Represents labor types within a category (e.g., Project Manager, Civil Engineer)

```python
class LaborClassification(models.Model):
    category = ForeignKey(WorkforceCategory)
    name = CharField(max_length=100)
    description = TextField()
    default_gender = CharField(choices=[M, F, O])
    is_active = BooleanField(default=True)
    order = IntegerField(default=0)
```

**Examples:**
- Project Manager
- Civil Engineer
- Skilled Labor
- Electrician

#### 3. **EquipmentMaster**
Master list of all equipment

```python
class EquipmentMaster(models.Model):
    name = CharField(max_length=150)
    description = TextField()
    manufacturer = CharField(max_length=100)
    model = CharField(max_length=100)
    year_built = IntegerField()
    category = CharField(max_length=100)
    is_active = BooleanField(default=True)
```

**Examples:**
- Fixed Winch
- Dump Truck
- Concrete Mixer
- Chain Excavator

#### 4. **BillOfQuantities (BOQ)**
Project-specific materials from BOQ

```python
class BillOfQuantities(models.Model):
    project = ForeignKey(Project)
    item_code = CharField(max_length=50)
    description = CharField(max_length=255)
    unit = CharField(max_length=50)
    quantity = DecimalField()
    unit_rate = DecimalField()
    total_amount = DecimalField()
    category = CharField(max_length=100)
    supplier = CharField(max_length=150)
    is_active = BooleanField(default=True)
```

**Examples:**
- Cement (50kg bags)
- Steel Bars (12mm)
- Concrete (m3)
- Bricks (per 1000)

### Daily Report Entry Models

#### 5. **DailyReportWorkforceEntry**
Links daily report to labor classifications

```python
class DailyReportWorkforceEntry(models.Model):
    report = ForeignKey(DailyReport)
    labor_classification = ForeignKey(LaborClassification)
    number_of_employees = IntegerField(default=0)
    gender = CharField(choices=[M, F, O])
    hours_worked = DecimalField()
    notes = TextField()
```

#### 6. **DailyReportEquipmentEntry**
Links daily report to equipment

```python
class DailyReportEquipmentEntry(models.Model):
    report = ForeignKey(DailyReport)
    equipment = ForeignKey(EquipmentMaster)
    quantity_in_use = IntegerField(default=0)
    hours_worked = DecimalField()
    quantity_idle = IntegerField(default=0)
    remarks = TextField()
```

#### 7. **DailyReportMaterialEntry**
Links daily report to BOQ materials

```python
class DailyReportMaterialEntry(models.Model):
    report = ForeignKey(DailyReport)
    boq_item = ForeignKey(BillOfQuantities)
    quantity_used = DecimalField()
    quantity_wasted = DecimalField()
    remarks = TextField()
```

---

## Database Schema

### New Tables

```
WorkforceCategory
├── id (PK)
├── name
├── description
├── is_active
└── order

LaborClassification
├── id (PK)
├── category_id (FK)
├── name
├── description
├── default_gender
├── is_active
└── order

EquipmentMaster
├── id (PK)
├── name
├── description
├── manufacturer
├── model
├── year_built
├── category
└── is_active

BillOfQuantities
├── id (PK)
├── project_id (FK)
├── item_code
├── description
├── unit
├── quantity
├── unit_rate
├── total_amount
├── category
├── supplier
└── is_active

DailyReportWorkforceEntry
├── id (PK)
├── report_id (FK)
├── labor_classification_id (FK)
├── number_of_employees
├── gender
├── hours_worked
└── notes

DailyReportEquipmentEntry
├── id (PK)
├── report_id (FK)
├── equipment_id (FK)
├── quantity_in_use
├── hours_worked
├── quantity_idle
└── remarks

DailyReportMaterialEntry
├── id (PK)
├── report_id (FK)
├── boq_item_id (FK)
├── quantity_used
├── quantity_wasted
└── remarks
```

---

## Installation & Setup

### 1. Add Models to Django

Copy the following files to your project:
- `reports/master_data_models.py` - Master data models
- `reports/structured_forms.py` - Forms for structured entries
- `reports/master_data_admin.py` - Admin configuration

### 2. Update Django Apps

In `config/settings.py`:
```python
INSTALLED_APPS = [
    # ...
    'reports',
]
```

### 3. Create Migrations

```bash
python manage.py makemigrations reports
python manage.py migrate
```

### 4. Load Master Data

```bash
python manage.py load_master_data
```

This command loads:
- **Workforce Categories**: Project Management, Work Force
- **Labor Classifications**: 25+ predefined labor types
- **Equipment**: 20+ predefined equipment items

### 5. Register Admin

In `reports/admin.py`:
```python
from .master_data_admin import *
```

---

## Usage

### Adding Workforce to Daily Report

1. **Select Category** → Choose "Project Management" or "Work Force"
2. **Select Labor Type** → Choose from filtered list (e.g., "Project Manager")
3. **Enter Details**:
   - Number of Employees: 2
   - Gender: M
   - Hours Worked: 8
4. **Save** → Entry added to report

### Adding Equipment to Daily Report

1. **Select Equipment** → Choose from master list (e.g., "Dump Truck")
2. **Enter Details**:
   - Quantity in Use: 3
   - Hours Worked: 8
   - Quantity Idle: 1
3. **Save** → Entry added to report

### Adding Materials to Daily Report

1. **Select Material** → Choose from project BOQ (e.g., "Cement 50kg")
2. **Enter Details**:
   - Quantity Used: 50 (bags)
   - Quantity Wasted: 2 (bags)
3. **Save** → Entry added to report

---

## Forms

### WorkforceCategorySelectionForm
Dropdown to select workforce category

### DailyReportWorkforceEntryForm
Form for adding workforce entries
- Fields: labor_classification, number_of_employees, gender, hours_worked, notes
- Filters labor classifications by selected category

### DailyReportEquipmentEntryForm
Form for adding equipment entries
- Fields: equipment, quantity_in_use, hours_worked, quantity_idle, remarks

### DailyReportMaterialEntryForm
Form for adding material entries
- Fields: boq_item, quantity_used, quantity_wasted, remarks
- Filters BOQ items by project

### Formsets
- `WorkforceEntryFormSet` - Multiple workforce entries
- `EquipmentEntryFormSet` - Multiple equipment entries
- `MaterialEntryFormSet` - Multiple material entries

---

## Admin Interface

### WorkforceCategory Admin
- List view with name, status, order
- Filter by active/inactive
- Inline editing

### LaborClassification Admin
- List view with category, name, gender, status
- Filter by category, status
- Search by name

### EquipmentMaster Admin
- List view with name, category, manufacturer, model
- Filter by category, manufacturer
- Search by name, model

### BillOfQuantities Admin
- List view with item code, project, description, quantity
- Filter by project, category
- Search by item code, description
- Auto-calculate total amount

### Daily Report Entry Admins
- View all entries for a report
- Filter by report date, category
- Search by report number

---

## Master Data Seed Data

### Workforce Categories (2)
1. **Project Management** (8 classifications)
   - Project Manager
   - Civil Engineer
   - Mechanical Engineer
   - Electrical Engineer
   - Safety Manager
   - Office Engineer
   - Training Engineer
   - Office Boy

2. **Work Force** (17 classifications)
   - Equipment Operator
   - Guard
   - Skilled Labor
   - Unskilled Labor
   - Painter
   - Carpenter
   - Gypsum Works
   - Plumber 1st team
   - Electrician
   - Plaster
   - Tile workers
   - Iron sheet Workers
   - Welder
   - Block Mason
   - Masonry
   - Medical Gases Worker
   - Aluminium Workers

### Equipment (20 items)
- Fixed Winch
- Chain Excavator
- Dump Truck
- Truck Mounted Crane
- Wheel Excavator
- Concrete Mixer
- Concrete Pump
- Back hoe loader (JCB)
- Steel Roller (Bomag 120)
- Tele handler (JCB)
- Single size Pump
- Concrete helicopter
- Sandblasting Machines
- Scaffolding System
- Formwork System
- Power Generator
- Air Compressor
- Welding Machine
- Cutting Machine
- Vibrator

---

## Database Queries

### Get all active workforce categories
```python
WorkforceCategory.objects.filter(is_active=True).order_by('order')
```

### Get labor classifications for a category
```python
LaborClassification.objects.filter(
    category__name='Project Management',
    is_active=True
)
```

### Get all active equipment
```python
EquipmentMaster.objects.filter(is_active=True).order_by('category', 'name')
```

### Get BOQ items for a project
```python
BillOfQuantities.objects.filter(
    project=project,
    is_active=True
).order_by('category', 'item_code')
```

### Get workforce entries for a report
```python
DailyReportWorkforceEntry.objects.filter(
    report=daily_report
).select_related('labor_classification__category')
```

### Get equipment entries for a report
```python
DailyReportEquipmentEntry.objects.filter(
    report=daily_report
).select_related('equipment')
```

### Get material entries for a report
```python
DailyReportMaterialEntry.objects.filter(
    report=daily_report
).select_related('boq_item')
```

---

## API Endpoints

### Workforce API
```
GET  /api/workforce-categories/
GET  /api/workforce-categories/<id>/classifications/
POST /api/daily-report/<id>/workforce-entries/
DELETE /api/daily-report/<id>/workforce-entries/<id>/
```

### Equipment API
```
GET  /api/equipment/
GET  /api/equipment/<category>/
POST /api/daily-report/<id>/equipment-entries/
DELETE /api/daily-report/<id>/equipment-entries/<id>/
```

### Materials API
```
GET  /api/boq/<project-id>/
POST /api/daily-report/<id>/material-entries/
DELETE /api/daily-report/<id>/material-entries/<id>/
```

---

## Template Display

### Workforce Table
```
| Labor Classification | Category | # Employees | Gender | Hours Worked | Actions |
|----------------------|----------|-------------|--------|--------------|---------|
| Project Manager      | Mgmt     | 2           | M      | 8            | Edit/Del|
| Civil Engineer       | Mgmt     | 1           | M      | 8            | Edit/Del|
```

### Equipment Table
```
| Equipment Name | Qty in Use | Hours Worked | Qty Idle | Actions |
|----------------|-----------|--------------|----------|---------|
| Dump Truck     | 3         | 8            | 1        | Edit/Del|
| Concrete Mixer | 2         | 6            | 0        | Edit/Del|
```

### Materials Table
```
| Material | Unit | Qty Used | Qty Wasted | Actions |
|----------|------|----------|------------|---------|
| Cement   | bags | 50       | 2          | Edit/Del|
| Steel    | tons | 5        | 0.5        | Edit/Del|
```

---

## Performance Optimization

### Indexes
```python
class Meta:
    indexes = [
        models.Index(fields=['project', 'is_active']),
        models.Index(fields=['category', 'is_active']),
        models.Index(fields=['report', 'labor_classification']),
    ]
```

### Select Related
```python
entries = DailyReportWorkforceEntry.objects.filter(
    report=report
).select_related('labor_classification__category')
```

### Prefetch Related
```python
reports = DailyReport.objects.prefetch_related(
    'workforce_entries',
    'equipment_entries',
    'material_entries'
)
```

---

## Troubleshooting

### Master data not loading
```bash
# Check if command exists
python manage.py help load_master_data

# Run with verbose output
python manage.py load_master_data --verbosity=2
```

### Dropdown showing no options
- Verify master data is loaded
- Check is_active flag on master data
- Verify project has BOQ items

### Duplicate entries
- Check unique_together constraints
- Verify form validation

---

## Future Enhancements

1. **Bulk Import** - Import BOQ from Excel/CSV
2. **Favorites** - Mark frequently used items
3. **Recent Items** - Show recently used items
4. **Search** - Full-text search in dropdowns
5. **Suggestions** - Suggest items based on history
6. **Validation** - Warn if quantities exceed BOQ
7. **Reporting** - Generate reports by category
8. **Analytics** - Track usage patterns

---

## Files Included

1. **master_data_models.py** - Master data models (400+ lines)
2. **structured_forms.py** - Forms and formsets (250+ lines)
3. **master_data_admin.py** - Admin configuration (300+ lines)
4. **load_master_data.py** - Seed data command (150+ lines)
5. **STRUCTURED_SECTIONS_DOCUMENTATION.md** - This documentation

---

**Status**: ✅ Ready for Implementation  
**Version**: 1.0.0  
**Last Updated**: December 25, 2025
