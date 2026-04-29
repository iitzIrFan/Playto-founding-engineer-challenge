from django.db.models import Sum

from ledger.models import LedgerEntry


def get_merchant_balance_paise(merchant_id: int) -> int:
    """Compute balance using DB aggregation only."""
    aggregate = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(total=Sum("amount_paise"))
    return aggregate["total"] or 0
