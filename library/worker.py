import time

from django.conf import settings
from django.db import transaction

from .models import ProcessingJob
from .services import process_book


def claim_next_job() -> ProcessingJob | None:
    with transaction.atomic():
        job = (
            ProcessingJob.objects.select_for_update()
            .filter(status=ProcessingJob.JobStatus.PENDING)
            .order_by("created_at")
            .first()
        )
        if not job:
            return None
        job.status = ProcessingJob.JobStatus.RUNNING
        job.attempts += 1
        job.save(update_fields=["status", "attempts", "updated_at"])
        return job


def run_job(job: ProcessingJob) -> None:
    try:
        process_book(job.book_id)
        job.status = ProcessingJob.JobStatus.DONE
        job.last_error = ""
        job.save(update_fields=["status", "last_error", "updated_at"])
    except Exception as exc:
        job.status = ProcessingJob.JobStatus.FAILED
        job.last_error = str(exc)
        job.save(update_fields=["status", "last_error", "updated_at"])


def run_worker_loop(once: bool = False) -> None:
    while True:
        job = claim_next_job()
        if not job:
            if once:
                return
            time.sleep(settings.WORKER_POLL_SECONDS)
            continue
        run_job(job)
        if once:
            return
