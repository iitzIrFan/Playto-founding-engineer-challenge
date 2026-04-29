from concurrent.futures import ThreadPoolExecutor

from django.test import TransactionTestCase
from rest_framework.test import APIClient

from ledger.models import LedgerEntry
from merchants.models import Merchant
from payouts.models import IdempotencyKey, Payout
from payouts.services import PayoutError, fail_and_release_payout, transition_payout_status


class PayoutApiTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.client = APIClient()
        self.merchant = Merchant.objects.create(name="Test Merchant")
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=10_000,
            type=LedgerEntry.EntryType.CREDIT,
            reference_id="seed:test-merchant",
        )
        self.url = "/api/v1/payouts"

    def test_parallel_requests_only_one_succeeds_for_single_funding_slot(self):
        def submit_request(key):
            local_client = APIClient()
            return local_client.post(
                self.url,
                {"merchant_id": self.merchant.id, "amount_paise": 10_000},
                format="json",
                HTTP_IDEMPOTENCY_KEY=key,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(submit_request, ["parallel-1", "parallel-2"]))

        status_codes = sorted([response.status_code for response in responses])
        self.assertIn(201, status_codes)
        self.assertTrue(any(code in (400, 409) for code in status_codes))
        self.assertEqual(Payout.objects.count(), 1)

    def test_same_idempotency_key_returns_same_response_without_duplicate_payout(self):
        payload = {"merchant_id": self.merchant.id, "amount_paise": 2_500}
        headers = {"HTTP_IDEMPOTENCY_KEY": "idem-001"}

        first = self.client.post(self.url, payload, format="json", **headers)
        second = self.client.post(self.url, payload, format="json", **headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Payout.objects.count(), 1)
        self.assertEqual(IdempotencyKey.objects.count(), 1)


class PayoutStateMachineTests(TransactionTestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(name="State Merchant")
        self.idempotency_key = IdempotencyKey.objects.create(
            key="state-1",
            merchant=self.merchant,
            expires_at=IdempotencyKey.default_expiry(),
        )
        self.payout = Payout.objects.create(
            merchant=self.merchant,
            amount_paise=1_000,
            idempotency_key=self.idempotency_key,
        )

    def test_invalid_state_transition_is_rejected(self):
        with self.assertRaises(PayoutError):
            transition_payout_status(self.payout, Payout.Status.COMPLETED)

    def test_failed_payout_releases_funds(self):
        LedgerEntry.objects.create(
            merchant=self.merchant,
            amount_paise=1_000,
            type=LedgerEntry.EntryType.CREDIT,
            reference_id="seed:state-merchant",
        )
        transition_payout_status(self.payout, Payout.Status.PROCESSING)
        fail_and_release_payout(self.payout)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, Payout.Status.FAILED)
        self.assertTrue(
            LedgerEntry.objects.filter(
                merchant=self.merchant,
                type=LedgerEntry.EntryType.RELEASE,
                amount_paise=1_000,
                reference_id=f"payout:{self.payout.id}",
            ).exists()
        )
