from django.db import models
from django.utils.translation import gettext_lazy as _

from merchants.models import Merchant


class LedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        CREDIT = "CREDIT", _("Credit")
        HOLD = "HOLD", _("Hold")
        RELEASE = "RELEASE", _("Release")

    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name="ledger_entries")
    amount_paise = models.BigIntegerField()
    type = models.CharField(max_length=16, choices=EntryType.choices)
    reference_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_entry"
        indexes = [
            models.Index(fields=["merchant", "created_at"]),
            models.Index(fields=["reference_id"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk and not kwargs.get("force_insert"):
            raise ValueError("Ledger entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)
