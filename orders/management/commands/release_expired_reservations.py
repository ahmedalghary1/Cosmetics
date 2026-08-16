from django.core.management.base import BaseCommand

from orders.services import release_expired_reservations


class Command(BaseCommand):
    help = "Release expired inventory and coupon reservations safely."

    def handle(self, *args, **options):
        count = release_expired_reservations()
        self.stdout.write(self.style.SUCCESS(f"Released {count} expired order reservation(s)."))
