"""
Services for Material Tracking System - Report Generation and Analysis
"""

from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import calendar

from .models_materials import (
    MaterialEntry, MonthlyMaterialReport, MonthlyMaterialReportItem,
    MaterialCategory, MaterialType, MaterialBudget, MaterialBudgetItem,
    Project
)


class MaterialReportService:
    """Service for generating material reports"""
    
    @staticmethod
    def generate_monthly_report(project, report_month):
        """
        Generate monthly material report from entries
        
        Args:
            project: Project instance
            report_month: datetime object for the month
        
        Returns:
            MonthlyMaterialReport instance
        """
        # Get or create report
        report, created = MonthlyMaterialReport.objects.get_or_create(
            project=project,
            report_month=report_month.replace(day=1)
        )
        
        # Get all entries for the month
        start_date = report_month.replace(day=1)
        end_date = start_date.replace(day=calendar.monthrange(start_date.year, start_date.month)[1])
        
        entries = MaterialEntry.objects.filter(
            project=project,
            entry_date__gte=start_date,
            entry_date__lte=end_date
        )
        
        # Update report totals
        report.total_entries = entries.count()
        report.total_quantity = entries.aggregate(Sum('quantity'))['quantity__sum'] or 0
        report.total_cost = entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0
        report.save()
        
        # Clear existing items
        report.items.all().delete()
        
        # Create report items by material type
        for material_type in MaterialType.objects.filter(is_active=True):
            mat_entries = entries.filter(material_type=material_type)
            if mat_entries.exists():
                quantity = mat_entries.aggregate(Sum('quantity'))['quantity__sum'] or 0
                total_cost = mat_entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0
                
                # Calculate cumulative quantities
                cumulative_entries = MaterialEntry.objects.filter(
                    project=project,
                    material_type=material_type,
                    entry_date__lte=end_date
                )
                cumulative_quantity = cumulative_entries.aggregate(Sum('quantity'))['quantity__sum'] or 0
                cumulative_cost = cumulative_entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0
                
                MonthlyMaterialReportItem.objects.create(
                    report=report,
                    material_type=material_type,
                    quantity=quantity,
                    unit_cost=material_type.unit_cost,
                    total_cost=total_cost,
                    cumulative_quantity=cumulative_quantity,
                    cumulative_cost=cumulative_cost,
                    entry_count=mat_entries.count()
                )
        
        return report
    
    @staticmethod
    def get_cumulative_report(project, end_date=None):
        """
        Get cumulative material report from project start to end_date
        
        Args:
            project: Project instance
            end_date: datetime object (defaults to today)
        
        Returns:
            Dictionary with cumulative data
        """
        if not end_date:
            end_date = timezone.now().date()
        
        entries = MaterialEntry.objects.filter(
            project=project,
            entry_date__lte=end_date
        )
        
        report_data = {
            'project_code': project.code,
            'project_name': project.name,
            'as_of_date': end_date,
            'total_entries': entries.count(),
            'total_quantity': entries.aggregate(Sum('quantity'))['quantity__sum'] or 0,
            'total_cost': entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0,
            'by_category': [],
            'by_supplier': [],
            'by_source': []
        }
        
        # By category
        for category in MaterialCategory.objects.filter(is_active=True):
            cat_entries = entries.filter(material_type__category=category)
            if cat_entries.exists():
                report_data['by_category'].append({
                    'category': category.name,
                    'unit': category.unit,
                    'quantity': float(cat_entries.aggregate(Sum('quantity'))['quantity__sum'] or 0),
                    'cost': float(cat_entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0),
                    'entry_count': cat_entries.count()
                })
        
        # By supplier
        suppliers = entries.values('supplier_name').distinct()
        for supplier in suppliers:
            supplier_entries = entries.filter(supplier_name=supplier['supplier_name'])
            report_data['by_supplier'].append({
                'supplier': supplier['supplier_name'] or 'Unknown',
                'quantity': float(supplier_entries.aggregate(Sum('quantity'))['quantity__sum'] or 0),
                'cost': float(supplier_entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0),
                'entry_count': supplier_entries.count()
            })
        
        # By source
        sources = entries.values('source').distinct()
        for source in sources:
            source_entries = entries.filter(source=source['source'])
            report_data['by_source'].append({
                'source': source_entries.first().get_source_display(),
                'quantity': float(source_entries.aggregate(Sum('quantity'))['quantity__sum'] or 0),
                'cost': float(source_entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0),
                'entry_count': source_entries.count()
            })
        
        return report_data
    
    @staticmethod
    def get_monthly_comparison(project, months=6):
        """
        Get monthly comparison for the last N months
        
        Args:
            project: Project instance
            months: Number of months to compare
        
        Returns:
            List of monthly data
        """
        comparison = []
        
        for i in range(months, 0, -1):
            month_date = timezone.now().date().replace(day=1) - timedelta(days=30*i)
            start_date = month_date.replace(day=1)
            end_date = start_date.replace(day=calendar.monthrange(start_date.year, start_date.month)[1])
            
            entries = MaterialEntry.objects.filter(
                project=project,
                entry_date__gte=start_date,
                entry_date__lte=end_date
            )
            
            comparison.append({
                'month': start_date.strftime('%Y-%m'),
                'quantity': float(entries.aggregate(Sum('quantity'))['quantity__sum'] or 0),
                'cost': float(entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0),
                'entry_count': entries.count()
            })
        
        return comparison


class MaterialBudgetService:
    """Service for material budget tracking"""
    
    @staticmethod
    def check_budget_status(project):
        """
        Check budget status for a project
        
        Args:
            project: Project instance
        
        Returns:
            Dictionary with budget status
        """
        try:
            budget = MaterialBudget.objects.get(project=project)
        except MaterialBudget.DoesNotExist:
            return None
        
        spent = budget.get_spent_amount()
        remaining = budget.get_remaining_budget()
        percentage = budget.get_budget_percentage()
        
        return {
            'total_budget': float(budget.total_budget),
            'spent_amount': float(spent),
            'remaining_budget': float(remaining),
            'budget_percentage': round(percentage, 2),
            'status': 'OK' if percentage <= 80 else ('WARNING' if percentage <= 100 else 'EXCEEDED'),
            'items': [
                {
                    'material_type': item.material_type.name,
                    'allocated': float(item.allocated_budget),
                    'spent': float(item.get_spent_amount()),
                    'remaining': float(item.get_remaining_budget()),
                    'percentage': round(item.get_budget_percentage(), 2)
                }
                for item in budget.items.all()
            ]
        }
    
    @staticmethod
    def get_budget_alerts(project):
        """
        Get budget alerts for a project
        
        Args:
            project: Project instance
        
        Returns:
            List of alerts
        """
        alerts = []
        
        try:
            budget = MaterialBudget.objects.get(project=project)
        except MaterialBudget.DoesNotExist:
            return alerts
        
        # Check overall budget
        percentage = budget.get_budget_percentage()
        if percentage > 100:
            alerts.append({
                'type': 'CRITICAL',
                'message': f'Project budget exceeded by {percentage - 100:.2f}%',
                'amount': float(budget.get_spent_amount() - budget.total_budget)
            })
        elif percentage > 80:
            alerts.append({
                'type': 'WARNING',
                'message': f'Project budget {percentage:.2f}% utilized',
                'amount': float(budget.get_remaining_budget())
            })
        
        # Check individual items
        for item in budget.items.all():
            item_percentage = item.get_budget_percentage()
            if item_percentage > 100:
                alerts.append({
                    'type': 'CRITICAL',
                    'message': f'{item.material_type.name} budget exceeded by {item_percentage - 100:.2f}%',
                    'amount': float(item.get_spent_amount() - item.allocated_budget)
                })
            elif item_percentage > 80:
                alerts.append({
                    'type': 'WARNING',
                    'message': f'{item.material_type.name} budget {item_percentage:.2f}% utilized',
                    'amount': float(item.get_remaining_budget())
                })
        
        return alerts


class MaterialAnalyticsService:
    """Service for material analytics"""
    
    @staticmethod
    def get_material_statistics(project):
        """
        Get comprehensive material statistics
        
        Args:
            project: Project instance
        
        Returns:
            Dictionary with statistics
        """
        entries = MaterialEntry.objects.filter(project=project)
        
        stats = {
            'total_entries': entries.count(),
            'total_quantity': float(entries.aggregate(Sum('quantity'))['quantity__sum'] or 0),
            'total_cost': float(entries.aggregate(Sum('total_cost'))['total_cost__sum'] or 0),
            'average_cost_per_entry': 0,
            'unique_materials': MaterialType.objects.filter(entries__project=project).distinct().count(),
            'unique_suppliers': entries.values('supplier_name').distinct().count(),
            'date_range': {}
        }
        
        if entries.exists():
            stats['average_cost_per_entry'] = float(stats['total_cost'] / stats['total_entries'])
            stats['date_range'] = {
                'start_date': entries.order_by('entry_date').first().entry_date,
                'end_date': entries.order_by('-entry_date').first().entry_date
            }
        
        return stats
    
    @staticmethod
    def get_top_materials(project, limit=10):
        """
        Get top materials by cost
        
        Args:
            project: Project instance
            limit: Number of top materials to return
        
        Returns:
            List of top materials
        """
        entries = MaterialEntry.objects.filter(project=project)
        
        top_materials = entries.values('material_type__name').annotate(
            total_cost=Sum('total_cost'),
            total_quantity=Sum('quantity'),
            entry_count=Count('id')
        ).order_by('-total_cost')[:limit]
        
        return [
            {
                'material': m['material_type__name'],
                'cost': float(m['total_cost']),
                'quantity': float(m['total_quantity']),
                'entries': m['entry_count']
            }
            for m in top_materials
        ]
    
    @staticmethod
    def get_top_suppliers(project, limit=10):
        """
        Get top suppliers by cost
        
        Args:
            project: Project instance
            limit: Number of top suppliers to return
        
        Returns:
            List of top suppliers
        """
        entries = MaterialEntry.objects.filter(project=project)
        
        top_suppliers = entries.values('supplier_name').annotate(
            total_cost=Sum('total_cost'),
            total_quantity=Sum('quantity'),
            entry_count=Count('id')
        ).order_by('-total_cost')[:limit]
        
        return [
            {
                'supplier': s['supplier_name'] or 'Unknown',
                'cost': float(s['total_cost']),
                'quantity': float(s['total_quantity']),
                'entries': s['entry_count']
            }
            for s in top_suppliers
        ]