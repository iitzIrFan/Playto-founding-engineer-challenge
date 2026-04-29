from django.core.management.base import BaseCommand

from ledger.models import LedgerEntry
from merchants.models import Merchant


class Command(BaseCommand):
    help = "Seed sample merchants and opening credits."

    def handle(self, *args, **options):
        seed_rows = [
            ("Acme Store", 500_000),
            ("Nova Mart", 350_000),
            ("Zen Bazaar", 750_000),
        ]

        for merchant_name, amount_paise in seed_rows:
            merchant, _ = Merchant.objects.get_or_create(name=merchant_name)
            LedgerEntry.objects.create(
                merchant=merchant,
                amount_paise=amount_paise,
                type=LedgerEntry.EntryType.CREDIT,
                reference_id=f"seed:{merchant.id}",
            )
        self.stdout.write(self.style.SUCCESS("Seeded merchants and opening balances."))
