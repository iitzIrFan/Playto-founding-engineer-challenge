import json
from typing import Any, Optional

from django.db import OperationalError, transaction
from django.http import JsonResponse

from payouts.services import get_or_lock_idempotency_key


class IdempotencyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not self._should_handle(request):
            return self.get_response(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return JsonResponse(
                {"detail": "Idempotency-Key header is required."},
                status=400,
            )

        merchant_id = self._extract_merchant_id(request)
        if merchant_id is None:
            return self.get_response(request)

        with transaction.atomic():
            try:
                idempotency = get_or_lock_idempotency_key(merchant_id, idempotency_key)
            except OperationalError:
                return JsonResponse(
                    {"detail": "Request is already being processed. Please retry."},
                    status=409,
                )

            if idempotency.response_body is not None:
                return JsonResponse(idempotency.response_body, status=200)

            request.idempotency_key = idempotency
            response = self.get_response(request)
            self._store_response(idempotency, response)
            return response

    @staticmethod
    def _should_handle(request) -> bool:
        return request.method.upper() == "POST" and request.path.rstrip("/") == "/api/v1/payouts"

    @staticmethod
    def _extract_merchant_id(request) -> Optional[int]:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return None

        merchant_id = payload.get("merchant_id")
        try:
            return int(merchant_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _store_response(idempotency, response) -> None:
        if idempotency.response_body is not None:
            return

        payload: Optional[Any] = None
        if hasattr(response, "data"):
            payload = response.data
        elif getattr(response, "content", None):
            try:
                payload = json.loads(response.content)
            except json.JSONDecodeError:
                payload = None

        if payload is None:
            return

        idempotency.response_body = payload
        idempotency.save(update_fields=["response_body"])
