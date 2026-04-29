from datetime import timedelta

from django.db import transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from ledger.models import LedgerEntry
from ledger.services import get_merchant_balance_paise
from merchants.models import Merchant
from payouts.models import IdempotencyKey, Payout


class PayoutError(Exception):
    pass


class InsufficientBalanceError(PayoutError):
    pass


ALLOWED_TRANSITIONS = {
    Payout.Status.PENDING: {Payout.Status.PROCESSING},
    Payout.Status.PROCESSING: {Payout.Status.COMPLETED, Payout.Status.FAILED},
}


def transition_payout_status(payout: Payout, target_status: str) -> Payout:
    if target_status not in ALLOWED_TRANSITIONS.get(payout.status, set()):
        raise PayoutError(f"Invalid transition: {payout.status} -> {target_status}")
    payout.status = target_status
    payout.save(update_fields=["status", "updated_at"])
    return payout


@transaction.atomic
def get_or_lock_idempotency_key(merchant_id: int, key: str) -> IdempotencyKey:
    try:
        return IdempotencyKey.objects.select_for_update().get(merchant_id=merchant_id, key=key)
    except IdempotencyKey.DoesNotExist:
        try:
            return IdempotencyKey.objects.create(
                merchant_id=merchant_id,
                key=key,
                expires_at=timezone.now() + timedelta(hours=24),
            )
        except IntegrityError:
            return IdempotencyKey.objects.select_for_update().get(merchant_id=merchant_id, key=key)


@transaction.atomic
def create_payout_with_hold(*, merchant_id: int, amount_paise: int, idempotency_key: IdempotencyKey) -> Payout:
    merchant = Merchant.objects.select_for_update().get(pk=merchant_id)
    balance = get_merchant_balance_paise(merchant.id)
    if balance < amount_paise:
        raise InsufficientBalanceError("Insufficient available balance")

    payout = Payout.objects.create(
        merchant=merchant,
        amount_paise=amount_paise,
        status=Payout.Status.PENDING,
        idempotency_key=idempotency_key,
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        amount_paise=-amount_paise,
        type=LedgerEntry.EntryType.HOLD,
        reference_id=f"payout:{payout.id}",
    )
    return payout


@transaction.atomic
def fail_and_release_payout(payout: Payout) -> Payout:
    payout = Payout.objects.select_for_update().get(pk=payout.pk)
    if payout.status != Payout.Status.PROCESSING:
        raise PayoutError("Only processing payouts can be failed")

    transition_payout_status(payout, Payout.Status.FAILED)
    LedgerEntry.objects.create(
        merchant=payout.merchant,
        amount_paise=payout.amount_paise,
        type=LedgerEntry.EntryType.RELEASE,
        reference_id=f"payout:{payout.id}",
    )
    return payout
