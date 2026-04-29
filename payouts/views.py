from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ledger.services import get_merchant_balance_paise
from merchants.models import Merchant
from payouts.models import Payout
from payouts.read_serializers import MerchantSerializer, PayoutSerializer
from payouts.serializers import PayoutRequestSerializer
from payouts.services import InsufficientBalanceError, create_payout_with_hold


class PayoutCreateView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = PayoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        idempotency_key = getattr(request, "idempotency_key", None)
        if not idempotency_key:
            return Response(
                {"detail": "Idempotency-Key header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        merchant_id = serializer.validated_data["merchant_id"]
        amount_paise = serializer.validated_data["amount_paise"]

        try:
            payout = create_payout_with_hold(
                merchant_id=merchant_id,
                amount_paise=amount_paise,
                idempotency_key=idempotency_key,
            )
            response_body = {
                "payout_id": payout.id,
                "merchant_id": payout.merchant_id,
                "amount_paise": payout.amount_paise,
                "status": payout.status,
            }
            response_status = status.HTTP_201_CREATED
        except InsufficientBalanceError as exc:
            response_body = {"detail": str(exc)}
            response_status = status.HTTP_400_BAD_REQUEST

        return Response(response_body, status=response_status)


class MerchantListView(APIView):
    def get(self, request, *args, **kwargs):
        merchants = Merchant.objects.all().order_by("name")
        return Response(MerchantSerializer(merchants, many=True).data, status=status.HTTP_200_OK)


class DashboardView(APIView):
    def get(self, request, *args, **kwargs):
        merchant_id = request.query_params.get("merchant_id")
        if not merchant_id:
            return Response({"detail": "merchant_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            merchant = Merchant.objects.get(pk=int(merchant_id))
        except (ValueError, Merchant.DoesNotExist):
            return Response({"detail": "Merchant not found."}, status=status.HTTP_404_NOT_FOUND)

        balance_paise = get_merchant_balance_paise(merchant.id)
        payouts = Payout.objects.filter(merchant=merchant).order_by("-created_at")[:50]

        return Response(
            {
                "merchant": MerchantSerializer(merchant).data,
                "balance_paise": balance_paise,
                "payouts": PayoutSerializer(payouts, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
