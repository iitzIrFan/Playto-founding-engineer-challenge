from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from merchants.models import Merchant


class IdempotencyKey(models.Model):
    key = models.CharField(max_length=128)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name="idempotency_keys")
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["merchant", "key"], name="uniq_merchant_idempotency_key"),
        ]

    @classmethod
    def default_expiry(cls):
        return timezone.now() + timezone.timedelta(hours=24)


class Payout(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name="payouts")
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    idempotency_key = models.OneToOneField(
        IdempotencyKey,
        on_delete=models.PROTECT,
        related_name="payout",
    )
    attempts = models.PositiveIntegerField(default=0)
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "locked_at"]),
            models.Index(fields=["merchant", "created_at"]),
        ]
