# Material Tracking System - Complete Guide

## Overview

The Material Tracking System provides comprehensive management of project materials from procurement through monthly reporting. It integrates supplier invoices, site engineer data, and budget tracking into a unified platform.

---

## System Components

### **1. Core Models**

#### **MaterialCategory**
Organizes materials by type (e.g., Concrete, Steel, Timber)
- Name, description, unit of measurement
- Active/inactive status

#### **MaterialType**
Specific material items within categories
- Links to category and supplier
- Unit cost and measurement unit
- Active/inactive status

#### **Project**
Central hub for all material activities
- Project code, name, location
- Start and end dates
- Active/inactive status

#### **MaterialEntry**
Individual material transactions
- Quantity and unit cost
- Entry date and source (Invoice/Site Engineer)
- Supplier information
- Invoice number tracking

#### **MonthlyMaterialReport**
Aggregated monthly summaries
- Report month and date
- Total entries, quantity, and cost
- Approval workflow
- Contains multiple report items

#### **MonthlyMaterialReportItem**
Line items within monthly reports
- Material type and quantity
- Cumulative tracking
- Entry count

#### **MaterialBudget**
Project-level budget allocation
- Total budget amount
- Spent and remaining tracking
- Contains budget items

#### **MaterialBudgetItem**
Individual material budget allocations
- Material type allocation
- Spent vs. allocated comparison

#### **MaterialSupplier**
Supplier information management
- Contact details and payment terms
- Tax ID and location

#### **MaterialInvoice**
Supplier invoices
- Invoice number and date
- Tax calculation
- Status tracking

---

## Workflow

### **Material Entry Process**

```
1. Create Material Entry
   ├─ Select Project
   ├─ Select Material Type
   ├─ Enter Quantity
   ├─ Enter Unit Cost
   ├─ Select Source (Invoice/Site Engineer)
   └─ Save Entry

2. Entry Recorded
   ├─ Total cost calculated automatically
   ├─ Entry date recorded
   ├─ Supplier information stored
   └─ Invoice number linked

3. Monthly Report Generation
   ├─ System aggregates entries by month
   ├─ Calculates cumulative quantities
   ├─ Groups by material type and category
   └─ Creates report items

4. Report Approval
   ├─ Review monthly totals
   ├─ Verify against invoices
   ├─ Approve report
   └─ Lock for historical reference
```

### **Budget Tracking Process**

```
1. Create Material Budget
   ├─ Set total project budget
   └─ Allocate by material type

2. Monitor Spending
   ├─ Track actual vs. budgeted
   ├─ Calculate remaining budget
   ├─ Generate alerts at 80% and 100%
   └─ Identify overspending

3. Budget Reports
   ├─ Monthly budget status
   ├─ Material-level breakdown
   ├─ Supplier comparison
   └─ Variance analysis
```

---

## Key Features

### **Monthly Report Generation**

Automatically aggregates material entries into monthly reports with:

- **Cumulative Tracking**: Tracks total quantities and costs from project start
- **Category Grouping**: Organizes materials by type for easy analysis
- **Entry Count**: Shows number of transactions per material
- **Approval Workflow**: Ensures data accuracy before finalization

### **Budget Management**

Real-time budget monitoring including:

- **Budget Allocation**: Set budgets by material type
- **Spending Tracking**: Monitor actual vs. budgeted amounts
- **Alert System**: Warnings at 80% and critical at 100%
- **Variance Analysis**: Identify cost overruns

### **Excel Export**

Professional Excel reports with:

- **Formatted Headers**: Blue gradient with white text
- **Data Organization**: Clear rows and columns
- **Calculations**: Automatic totals and summaries
- **Professional Layout**: Ready for stakeholder distribution

### **API Integration**

RESTful API endpoints for:

- **Material Entry Management**: CRUD operations
- **Report Generation**: Automated report creation
- **Budget Tracking**: Real-time budget status
- **Data Export**: Excel and JSON formats

---

## Usage Examples

### **Creating a Material Entry**

```python
from procurement.models_materials import MaterialEntry, MaterialType, Project

# Get project and material type
project = Project.objects.get(code='PRJ001')
material = MaterialType.objects.get(name='Concrete')

# Create entry
entry = MaterialEntry.objects.create(
    project=project,
    material_type=material,
    entry_date='2025-01-15',
    quantity=100,
    unit_cost=50.00,
    source='invoice',
    invoice_number='INV-2025-001',
    supplier_name='ABC Suppliers',
    recorded_by='John Doe'
)
```

### **Generating Monthly Report**

```python
from procurement.services_materials import MaterialReportService
from datetime import datetime

# Generate report for January 2025
report = MaterialReportService.generate_monthly_report(
    project=project,
    report_month=datetime(2025, 1, 1)
)

# Approve report
report.is_approved = True
report.approved_by = 'Manager Name'
report.save()
```

### **Checking Budget Status**

```python
from procurement.services_materials import MaterialBudgetService

# Get budget status
status = MaterialBudgetService.check_budget_status(project)

print(f"Budget: {status['total_budget']}")
print(f"Spent: {status['spent_amount']}")
print(f"Remaining: {status['remaining_budget']}")
print(f"Percentage: {status['budget_percentage']}%")
print(f"Status: {status['status']}")
```

### **Getting Analytics**

```python
from procurement.services_materials import MaterialAnalyticsService

# Get statistics
stats = MaterialAnalyticsService.get_material_statistics(project)
print(f"Total Entries: {stats['total_entries']}")
print(f"Total Cost: {stats['total_cost']}")

# Get top materials
top_materials = MaterialAnalyticsService.get_top_materials(project, limit=5)
for material in top_materials:
    print(f"{material['material']}: {material['cost']}")

# Get top suppliers
top_suppliers = MaterialAnalyticsService.get_top_suppliers(project, limit=5)
for supplier in top_suppliers:
    print(f"{supplier['supplier']}: {supplier['cost']}")
```

---

## API Endpoints

### **Material Entries**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/material-entries/` | GET | List all entries |
| `/api/material-entries/` | POST | Create new entry |
| `/api/material-entries/{id}/` | GET | Get entry details |
| `/api/material-entries/{id}/` | PUT | Update entry |
| `/api/material-entries/{id}/` | DELETE | Delete entry |

### **Monthly Reports**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/monthly-reports/` | GET | List reports |
| `/api/monthly-reports/` | POST | Create report |
| `/api/monthly-reports/{id}/generate/` | POST | Generate report |
| `/api/monthly-reports/{id}/approve/` | POST | Approve report |

### **Budgets**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/material-budgets/` | GET | List budgets |
| `/api/material-budgets/{id}/status/` | GET | Get budget status |

### **Projects**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/projects/` | GET | List projects |
| `/api/projects/{id}/summary/` | GET | Get project summary |

---

## Excel Export

### **Monthly Report Export**

```python
from procurement.views_materials import export_monthly_report_excel

# In URL configuration:
path('reports/<int:report_id>/export/', export_monthly_report_excel, name='export_report')

# Usage:
# GET /procurement/reports/1/export/
# Returns: Material_Report_2025-01.xlsx
```

### **Project Materials Export**

```python
from procurement.views_materials import export_project_materials_excel

# In URL configuration:
path('projects/<int:project_id>/materials/export/', export_project_materials_excel, name='export_materials')

# Usage:
# GET /procurement/projects/1/materials/export/
# Returns: Materials_PRJ001.xlsx
```

---

## Database Schema

### **Key Relationships**

```
Project
├── MaterialEntry (1-to-Many)
├── MonthlyMaterialReport (1-to-Many)
├── MaterialBudget (1-to-1)
└── MaterialInvoice (1-to-Many)

MaterialType
├── MaterialEntry (1-to-Many)
├── MaterialBudgetItem (1-to-Many)
└── MaterialInvoiceItem (1-to-Many)

MaterialCategory
└── MaterialType (1-to-Many)

MaterialBudget
└── MaterialBudgetItem (1-to-Many)

MonthlyMaterialReport
└── MonthlyMaterialReportItem (1-to-Many)

MaterialInvoice
└── MaterialInvoiceItem (1-to-Many)
```

---

## Integration with Other Systems

### **With BOQ System**

- Link material entries to BOQ items
- Track BOQ consumption
- Compare BOQ estimates with actual usage

### **With Payment System**

- Link invoices to payment records
- Track payment status
- Generate payment reports

### **With Cost Control**

- Feed material costs to cost reports
- Track budget vs. actual
- Generate financial reports

---

## Security & Permissions

### **Access Control**

- Authenticated users only
- Project-based access control
- Role-based permissions (Admin, Manager, Engineer)

### **Data Integrity**

- Automatic cost calculations
- Audit trail of changes
- Approval workflows

---

## Troubleshooting

### **Common Issues**

**Q: Monthly report shows zero quantities**
- Check if entries exist for the selected month
- Verify entry dates are within the month range
- Ensure material types are active

**Q: Budget exceeds 100% but no alerts**
- Run budget status check manually
- Verify budget items are properly allocated
- Check for recent entries not yet processed

**Q: Excel export fails**
- Ensure openpyxl is installed
- Check file permissions
- Verify data doesn't exceed Excel limits

---

## Performance Optimization

### **Indexing**

Recommended database indexes:
- `MaterialEntry.project_id + entry_date`
- `MaterialEntry.material_type_id`
- `MaterialEntry.supplier_name`
- `MonthlyMaterialReport.project_id + report_month`

### **Caching**

Cache frequently accessed data:
- Material categories and types
- Project summaries
- Budget status

---

## Future Enhancements

- Real-time material tracking with IoT
- Predictive analytics for material requirements
- Automated ordering based on thresholds
- Integration with accounting systems
- Mobile app for site engineers

---

## Support

For questions or issues, contact the development team or refer to the API documentation.