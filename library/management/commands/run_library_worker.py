from django.core.management.base import BaseCommand

from library.worker import run_worker_loop


class Command(BaseCommand):
    help = "Runs the library background worker for scan + AI enrichment."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one pending job and exit")

    def handle(self, *args, **options):
        run_worker_loop(once=options["once"])
