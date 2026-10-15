from django.contrib import admin

from .models import PaymentClaim, PaymentClaimLine, PaymentClaimSequence


@admin.register(PaymentClaimSequence)
class PaymentClaimSequenceAdmin(admin.ModelAdmin):
    """The running number of each claim series: change "last number" here if a series has to continue from another number."""
    list_display = ('prefix', 'separator', 'digits', 'last_number', 'project_symbol')


class PaymentClaimLineInline(admin.TabularInline):
    model = PaymentClaimLine
    extra = 0


@admin.register(PaymentClaim)
class PaymentClaimAdmin(admin.ModelAdmin):
    list_display = ('number', 'beneficiary_name', 'project', 'claim_date', 'status')
    list_filter = ('status', 'project')
    search_fields = ('number', 'beneficiary_name')
    inlines = [PaymentClaimLineInline]
