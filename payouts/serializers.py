from rest_framework import serializers


class PayoutRequestSerializer(serializers.Serializer):
    merchant_id = serializers.IntegerField(min_value=1)
    amount_paise = serializers.IntegerField(min_value=1)
