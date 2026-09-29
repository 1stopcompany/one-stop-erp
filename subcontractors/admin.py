from django.contrib import admin

from .models import (
    SubcontractorAgreement, SubcontractorAgreementLine, SubcontractorAgreementPayment, SubcontractorGeneralTerms,
)


@admin.register(SubcontractorGeneralTerms)
class SubcontractorGeneralTermsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'updated_by', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not SubcontractorGeneralTerms.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class SubcontractorAgreementLineInline(admin.TabularInline):
    model = SubcontractorAgreementLine
    extra = 0
    readonly_fields = ('total_price',)


class SubcontractorAgreementPaymentInline(admin.TabularInline):
    model = SubcontractorAgreementPayment
    extra = 0


@admin.register(SubcontractorAgreement)
class SubcontractorAgreementAdmin(admin.ModelAdmin):
    list_display = ('agreement_number', 'project', 'vendor', 'status', 'total_value', 'paid_to_date', 'start_date', 'end_date')
    list_filter = ('status',)
    search_fields = ('agreement_number', 'project__name', 'vendor__name')
    readonly_fields = ('agreement_number', 'total_value')
    inlines = [SubcontractorAgreementLineInline, SubcontractorAgreementPaymentInline]
