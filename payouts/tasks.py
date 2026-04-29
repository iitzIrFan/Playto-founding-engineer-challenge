import random
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from payouts.models import Payout
from payouts.services import PayoutError, fail_and_release_payout, transition_payout_status

MAX_ATTEMPTS = 3
PROCESSING_STALE_SECONDS = 30


@shared_task
def process_pending_payouts_task():
    payout_ids = list(Payout.objects.filter(status=Payout.Status.PENDING).values_list("id", flat=True))
    for payout_id in payout_ids:
        process_single_payout_task.delay(payout_id)


@shared_task(bind=True, max_retries=3)
def process_single_payout_task(self, payout_id: int):
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(pk=payout_id)
        if payout.status in (Payout.Status.COMPLETED, Payout.Status.FAILED):
            return {"status": payout.status}
        if payout.status == Payout.Status.PENDING:
            transition_payout_status(payout, Payout.Status.PROCESSING)
        payout.locked_at = timezone.now()
        payout.attempts += 1
        payout.save(update_fields=["locked_at", "attempts", "updated_at"])

    outcome = random.random()
    if outcome < 0.7:
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(pk=payout_id)
            if payout.status == Payout.Status.PROCESSING:
                transition_payout_status(payout, Payout.Status.COMPLETED)
        return {"status": Payout.Status.COMPLETED}

    if outcome < 0.9:
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(pk=payout_id)
            if payout.status == Payout.Status.PROCESSING:
                fail_and_release_payout(payout)
        return {"status": Payout.Status.FAILED}

    countdown = 2 ** max(0, min(3, self.request.retries))
    raise self.retry(countdown=countdown)


@shared_task
def retry_stuck_processing_payouts_task():
    stale_before = timezone.now() - timedelta(seconds=PROCESSING_STALE_SECONDS)
    stale_ids = list(
        Payout.objects.filter(status=Payout.Status.PROCESSING, locked_at__lt=stale_before).values_list("id", flat=True)
    )

    for payout_id in stale_ids:
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(pk=payout_id)
            if payout.status != Payout.Status.PROCESSING:
                continue
            if payout.attempts >= MAX_ATTEMPTS:
                fail_and_release_payout(payout)
                continue
            countdown = 2 ** max(0, min(3, payout.attempts))
        try:
            process_single_payout_task.apply_async(args=[payout_id], countdown=countdown)
        except PayoutError:
            continue
