# Construction Reports Management System - User Manual

## Table of Contents

1. [Getting Started](#getting-started)
2. [Dashboard Overview](#dashboard-overview)
3. [Daily Reports](#daily-reports)
4. [Monthly Reports](#monthly-reports)
5. [Project Management](#project-management)
6. [Report Approval](#report-approval)
7. [Exporting Reports](#exporting-reports)
8. [User Roles](#user-roles)
9. [FAQ](#faq)
10. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Login

1. Navigate to the application URL
2. Enter your username and password
3. Click "Login"
4. You will be redirected to your dashboard

**Default Credentials** (for testing):
- **Engineer**: username: `engineer1`, password: `testpass123`
- **Manager**: username: `manager1`, password: `testpass123`
- **Admin**: username: `admin`, password: (your superuser password)

### Changing Your Password

1. Click your profile icon (top right)
2. Select "Change Password"
3. Enter your current password
4. Enter your new password twice
5. Click "Update Password"

---

## Dashboard Overview

### Engineer Dashboard

The engineer dashboard shows your personal report statistics and recent activity.

**Key Metrics**:
- **Reports Submitted Today**: Number of daily reports submitted today
- **Daily Reports Submitted**: Total submitted reports awaiting approval
- **Monthly Reports Pending**: Monthly reports awaiting approval
- **Draft Reports**: Reports you're still working on

**Quick Actions**:
- Create Daily Report
- Create Monthly Report
- View Recent Reports
- Export to PDF

### Manager Dashboard

The manager dashboard shows project-level statistics and approval queue.

**Key Metrics**:
- **Projects**: Number of active projects
- **Daily Reports Pending**: Daily reports awaiting your approval
- **Monthly Reports Pending**: Monthly reports awaiting your approval
- **Reports Approved**: Total approved reports

**Quick Actions**:
- View Projects
- Approve Reports
- View Audit Trail
- Generate Reports

### Admin Dashboard

The admin dashboard provides system-wide statistics and management tools.

**Key Metrics**:
- **Total Projects**: All projects in system
- **Total Daily Reports**: All daily reports
- **Total Monthly Reports**: All monthly reports
- **Total Users**: System users
- **Recent Activities**: Audit log of all actions

---

## Daily Reports

### Creating a Daily Report

1. Click **"Create Daily Report"** button
2. Select the **Project** from dropdown
3. Enter **Report Date** (defaults to today)
4. Select **Weather** condition (Sunny, Cloudy, Rainy, Stormy)
5. Enter **Temperature** (optional)
6. Add **Remarks** (optional)

### Adding Workforce

1. In the "Workforce" section, click **"Add Workforce"**
2. Enter **Category** (e.g., Laborers, Engineers, Supervisors)
3. Enter **Count** (number of workers)
4. Click **"Add Another"** to add more categories

**Example**:
- Category: Laborers, Count: 25
- Category: Engineers, Count: 5
- Category: Supervisors, Count: 2

### Adding Equipment

1. In the "Equipment" section, click **"Add Equipment"**
2. Enter **Equipment Name** (e.g., Excavator, Crane)
3. Enter **Quantity**
4. Select **Status** (Operational, Maintenance, Idle)

### Recording Activities

1. In the "Activities" section, click **"Add Activity"**
2. Enter **Description** of the activity
3. Enter **Progress Percentage** (0-100)

**Example**:
- Description: "Foundation excavation completed"
- Progress: 85%

### Adding Materials

1. In the "Materials" section, click **"Add Material"**
2. Enter **Material Name** (e.g., Concrete, Steel)
3. Enter **Quantity**
4. Select **Unit** (cubic meters, tons, pieces, etc.)

### Recording Visitors

1. In the "Visitors" section, click **"Add Visitor"**
2. Enter **Visitor Name**
3. Enter **Purpose of Visit**
4. Enter **Time In** (entry time)
5. Enter **Time Out** (exit time, optional)

### Attaching Files

1. In the "Attachments" section, click **"Choose File"**
2. Select image or document from your computer
3. Enter **Description** (optional)
4. Click **"Upload"**

### Saving Your Report

**As Draft**:
- Click **"Save as Draft"** to save without submitting
- You can edit draft reports later

**Submit for Approval**:
1. Complete all required fields
2. Click **"Submit Report"**
3. Report status changes to "Submitted"
4. Project manager will review and approve

---

## Monthly Reports

### Creating a Monthly Report

1. Click **"Create Monthly Report"** button
2. Select the **Project**
3. Select **Reporting Month** (defaults to current month)
4. Add **Remarks** (optional)

### Adding Floor Activities

1. In the "Floor Activities" section, click **"Add Activity"**
2. Enter **Floor Number** (1, 2, 3, etc.)
3. Enter **Description** of work on that floor
4. Enter **Completion Percentage** (0-100)

**Example**:
- Floor: 1
- Description: "Ground floor renovation - walls painted, flooring in progress"
- Completion: 75%

### Adding External Works

1. In the "External Works" section, click **"Add Work"**
2. Enter **Description** of external work
3. Enter **Contractor Name** (optional)
4. Select **Status** (Ongoing, Completed, On Hold)

**Example**:
- Description: "Electrical wiring installation"
- Contractor: "ElectroWorks Inc"
- Status: Ongoing

### Recording Material Supplies

1. In the "Material Supplies" section, click **"Add Supply"**
2. Enter **Material Name**
3. Enter **Quantity**
4. Select **Unit**
5. Enter **Supplier Name** (optional)

**Example**:
- Material: Concrete
- Quantity: 500
- Unit: cubic meters
- Supplier: BuildMaterials Ltd

### Planning Upcoming Works

1. In the "Upcoming Works" section, click **"Add Work"**
2. Enter **Description** of planned work
3. Select **Planned Start Date**
4. Enter **Estimated Duration** (in days)

**Example**:
- Description: "Interior finishing and painting"
- Start Date: 2025-12-25
- Duration: 30 days

### Submitting Monthly Report

1. Complete all sections
2. Click **"Submit Report"**
3. Report is sent for manager approval
4. Status changes to "Submitted"

---

## Project Management

### Viewing Projects

1. Click **"Projects"** in main menu
2. View list of all projects
3. Click on a project name to view details

### Project Details

Each project shows:
- **Project Name**: Name of the project
- **Location**: Project location
- **Manager**: Project manager assigned
- **Status**: Current status (Planning, Active, Paused, Completed)
- **Start Date**: Project start date
- **End Date**: Project end date
- **Budget**: Project budget
- **Site Engineers**: Team members assigned

### Filtering Projects

1. Use **Status Filter** to show only Active, Completed, etc.
2. Use **Search** to find projects by name
3. Use **Date Range** to find projects by dates

---

## Report Approval

### Viewing Reports to Approve (Manager Only)

1. Go to **Dashboard**
2. See "Daily Reports Pending" and "Monthly Reports Pending"
3. Click **"View Pending Reports"**

### Approving a Report

1. Click on the report to view details
2. Review all information:
   - Workforce details
   - Equipment status
   - Activities and progress
   - Materials used
   - Remarks
3. Click **"Approve Report"**
4. Optionally add approval comments
5. Click **"Confirm Approval"**

### Rejecting a Report

1. Click on the report
2. Click **"Reject Report"**
3. Enter **Rejection Reason**
4. Click **"Confirm Rejection"**
5. Engineer receives notification to revise

### Report Status Workflow

```
Draft → Submitted → Approved → Archived
         ↓
       (Rejected)
         ↓
       Draft (for revision)
```

---

## Exporting Reports

### Export to PDF

1. Open the report you want to export
2. Click **"Export to PDF"** button
3. File downloads automatically
4. Open in PDF reader

### PDF Contents

**Daily Report PDF includes**:
- Report header with number and date
- Project and engineer information
- Weather conditions
- Workforce summary
- Equipment list
- Activities and progress
- Materials used
- Visitor log
- Remarks

**Monthly Report PDF includes**:
- Report header with number and month
- Project information
- Floor-by-floor activities
- External works status
- Material supplies
- Upcoming works
- Remarks

### Printing Reports

1. Export to PDF
2. Open PDF file
3. Click **Print** (Ctrl+P or Cmd+P)
4. Select printer and settings
5. Click **Print**

---

## User Roles

### Site Engineer

**Permissions**:
- Create daily and monthly reports
- View own reports
- Submit reports for approval
- Edit draft reports
- Export own reports to PDF
- View project information

**Cannot**:
- Approve reports
- View other engineers' reports
- Delete reports
- Manage projects

**Dashboard**: Personal metrics and recent reports

---

### Project Manager

**Permissions**:
- View all project reports
- Approve or reject reports
- View project details
- Export reports
- View audit logs
- Manage assigned projects

**Cannot**:
- Create reports
- Delete reports
- Manage users
- System administration

**Dashboard**: Project metrics and approval queue

---

### Administrator

**Permissions**:
- Full system access
- Manage all users
- Manage all projects
- View all reports
- Access Django admin panel
- View audit logs
- System configuration

**Cannot**:
- Create reports (unless assigned as engineer)

**Dashboard**: System-wide metrics and activity

---

## FAQ

### Q: Can I edit a report after submitting it?

**A**: No, once submitted, reports cannot be edited. Only draft reports can be edited. If you need to make changes after submission, contact your project manager.

### Q: How do I know if my report was approved?

**A**: You'll receive an email notification when your report is approved. You can also check the report status on your dashboard.

### Q: Can I delete a report?

**A**: No, reports cannot be deleted for audit purposes. If you need to archive a report, contact your administrator.

### Q: What if I forgot my password?

**A**: Click "Forgot Password" on the login page and follow the email instructions to reset it.

### Q: How often should I create daily reports?

**A**: Daily reports should be created at the end of each working day to capture the day's activities.

### Q: Can multiple engineers work on the same project?

**A**: Yes, multiple engineers can be assigned to the same project. Each engineer creates their own reports.

### Q: What's the difference between daily and monthly reports?

**A**: 
- **Daily Reports**: Detailed daily activities, weather, workforce, equipment
- **Monthly Reports**: Monthly summary, floor progress, external works, upcoming plans

### Q: Can I export reports in other formats?

**A**: Currently, PDF export is supported. Other formats may be available in future versions.

### Q: How long are reports stored?

**A**: Reports are stored indefinitely in the system for audit and compliance purposes.

### Q: Can I create a report for a past date?

**A**: Yes, you can select any date when creating a report. However, it's recommended to create reports on the same day.

---

## Troubleshooting

### I can't login

**Solution**:
1. Check that you're using the correct username
2. Verify CAPS LOCK is off
3. Reset your password if forgotten
4. Contact administrator if account is locked

### The page is loading slowly

**Solution**:
1. Check your internet connection
2. Clear browser cache (Ctrl+Shift+Delete)
3. Try a different browser
4. Contact administrator if issue persists

### I can't upload a file

**Solution**:
1. Check file size (max 100MB)
2. Check file format (images, PDFs, documents)
3. Check internet connection
4. Try a different file
5. Contact administrator for help

### My report disappeared

**Solution**:
1. Check if you're looking at the correct project
2. Use search to find the report
3. Check if report was archived
4. Contact administrator to recover

### I can't approve a report

**Solution**:
1. Verify you have manager role
2. Check that report is in "Submitted" status
3. Verify you're the project manager
4. Contact administrator if issue persists

### PDF export is not working

**Solution**:
1. Check internet connection
2. Try a different browser
3. Clear browser cache
4. Contact administrator for help

### I received an error message

**Solution**:
1. Note the exact error message
2. Screenshot the error
3. Contact administrator with details
4. Provide information about what you were doing

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+S | Save draft |
| Ctrl+P | Print |
| Ctrl+F | Find on page |
| Escape | Close dialog |
| Tab | Move to next field |
| Shift+Tab | Move to previous field |
| Enter | Submit form |

---

## Browser Compatibility

**Supported Browsers**:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

**Not Supported**:
- Internet Explorer
- Older browser versions

**Recommended**: Chrome or Firefox for best experience

---

## Mobile Access

The application is responsive and works on mobile devices:
- Tablets: Full functionality
- Smartphones: Full functionality with optimized layout
- Minimum screen width: 320px

---

## Data Privacy

- Your data is encrypted in transit (HTTPS)
- Passwords are securely hashed
- Access logs are maintained for security
- Regular backups are performed
- Data is not shared with third parties

---

## Support

For additional help:
- Contact your project manager
- Email: support@your-domain.com
- Phone: +1-XXX-XXX-XXXX
- Documentation: https://docs.your-domain.com

---

**Last Updated**: December 19, 2025  
**Version**: 1.0.0  
**Status**: Production Ready
