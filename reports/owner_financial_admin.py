"""
Django Admin Configuration for the Owner Financial & Technical Report.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .owner_financial_models import OwnerFinancialReport, OwnerReportPriceComparisonItem, OwnerReportPhaseUpdate


class OwnerReportPriceComparisonItemInline(admin.TabularInline):
    model = OwnerReportPriceComparisonItem
    extra = 1
    fields = ('item_type', 'item_name', 'unit', 'quantity', 'old_unit_price', 'new_unit_price', 'price_difference')
    readonly_fields = ('price_difference',)


class OwnerReportPhaseUpdateInline(admin.TabularInline):
    model = OwnerReportPhaseUpdate
    extra = 1
    fields = ('phase', 'status', 'work_performed', 'order')


@admin.register(OwnerFinancialReport)
class OwnerFinancialReportAdmin(admin.ModelAdmin):
    list_display = (
        'report_number', 'project', 'reporting_period_to', 'status',
        'earned_value_to_date', 'amount_due',
    )
    list_filter = ('status', 'reporting_period_to', 'project')
    search_fields = ('report_number', 'project__name')
    readonly_fields = (
        'report_number', 'created_at', 'updated_at', 'approval_date',
        'earned_value_to_date', 'advance_retention_rate', 'advance_retention_amount',
        'performance_retention_amount', 'amount_due',
    )
    inlines = [OwnerReportPhaseUpdateInline, OwnerReportPriceComparisonItemInline]
    ordering = ('-reporting_period_to',)

    fieldsets = (
        (_('Report Information'), {
            'fields': ('report_number', 'project', 'site_engineer', 'reporting_period_from', 'reporting_period_to')
        }),
        (_('Contract Terms Snapshot'), {
            'fields': ('contract_value_snapshot', 'advance_payment_value_snapshot', 'performance_retention_rate_snapshot', 'previous_payments_total')
        }),
        (_('Computed Payment Summary'), {
            'fields': (
                'earned_value_to_date', 'advance_retention_rate', 'advance_retention_amount',
                'performance_retention_amount', 'amount_due',
            )
        }),
        (_('Narrative'), {
            'fields': ('progress_summary', 'next_month_expected_works', 'next_month_expected_completion_pct', 'material_price_note', 'closing_note')
        }),
        (_('Approval'), {
            'fields': ('status', 'approved_by', 'approval_date')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def earned_value_to_date(self, obj):
        return obj.earned_value_to_date()
    earned_value_to_date.short_description = _('Earned Value to Date')

    def advance_retention_rate(self, obj):
        return obj.advance_retention_rate()
    advance_retention_rate.short_description = _('Advance Retention Rate %')

    def advance_retention_amount(self, obj):
        return obj.advance_retention_amount()
    advance_retention_amount.short_description = _('Advance Retention Amount')

    def performance_retention_amount(self, obj):
        return obj.performance_retention_amount()
    performance_retention_amount.short_description = _('Performance Retention Amount')

    def amount_due(self, obj):
        return obj.amount_due()
    amount_due.short_description = _('Amount Due')


@admin.register(OwnerReportPriceComparisonItem)
class OwnerReportPriceComparisonItemAdmin(admin.ModelAdmin):
    list_display = ('report', 'item_type', 'item_name', 'quantity', 'old_unit_price', 'new_unit_price', 'price_difference')
    list_filter = ('item_type', 'report__project')
    search_fields = ('report__report_number', 'item_name')
    readonly_fields = ('price_difference', 'created_at')
