from rest_framework import serializers
from .models import (
    ItemMaster, Vendor,
    PurchaseRequisition, PurchaseRequisitionLine,
    RequestForQuotation, VendorQuote, VendorQuoteLine,
    PurchaseOrder, PurchaseOrderLine, POReceipt,
)


class ItemMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemMaster
        fields = "__all__"
        read_only_fields = ("organization", "full_code", "short_code", "created_date", "updated_date", "created_by")


class PurchaseRequisitionLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseRequisitionLine
        fields = "__all__"


class PRSerializer(serializers.ModelSerializer):
    lines = PurchaseRequisitionLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseRequisition
        fields = "__all__"
        read_only_fields = ("pr_number", "created_date", "updated_date", "requested_by", "approved_by", "approved_date")


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderLine
        fields = "__all__"
        read_only_fields = ("total_price",)


class POSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = "__all__"
        read_only_fields = ("po_number", "total_price", "po_date", "created_date", "updated_date", "created_by")


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = "__all__"


class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = POReceipt
        fields = "__all__"
        read_only_fields = ("received_date", "received_by")


class RequestForQuotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequestForQuotation
        fields = "__all__"
        read_only_fields = ("rfq_number", "created_date", "updated_date", "created_by")


class VendorQuoteLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorQuoteLine
        fields = "__all__"
        read_only_fields = ("total_price",)


class VendorQuoteSerializer(serializers.ModelSerializer):
    lines = VendorQuoteLineSerializer(many=True, read_only=True)

    class Meta:
        model = VendorQuote
        fields = "__all__"
        read_only_fields = ("created_date", "entered_by")
