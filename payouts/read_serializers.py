from rest_framework import serializers

from merchants.models import Merchant
from payouts.models import Payout


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ("id", "name")


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = ("id", "amount_paise", "status", "attempts", "locked_at", "created_at")
