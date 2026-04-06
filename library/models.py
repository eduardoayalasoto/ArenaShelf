from django.db import models


class Book(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VALIDATING = "validating", "Validating"
        SCANNED = "scanned", "Scanned"
        ENRICHED = "enriched", "Enriched"
        READY = "ready", "Ready"
        REJECTED = "rejected", "Rejected"
        ERROR = "error", "Error"

    title_user = models.CharField(max_length=255)
    author_user = models.CharField(max_length=255)
    title_ai = models.CharField(max_length=255, blank=True)
    author_ai = models.CharField(max_length=255, blank=True)
    genre = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=32, blank=True)
    summary = models.TextField(blank=True)
    tags_json = models.JSONField(default=list, blank=True)
    published_date = models.CharField(max_length=20, blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    publisher = models.CharField(max_length=255, blank=True)

    original_filename = models.CharField(max_length=255)
    normalized_filename = models.CharField(max_length=255, blank=True)
    extension = models.CharField(max_length=16, blank=True)
    mime_type = models.CharField(max_length=120, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    file_blob = models.BinaryField()
    file_size = models.PositiveIntegerField(default=0)
    alt_blob = models.BinaryField(null=True, blank=True)
    alt_extension = models.CharField(max_length=16, blank=True)
    cover_blob = models.BinaryField(null=True, blank=True)
    cover_url = models.URLField(max_length=500, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    scan_report = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["title_ai"]),
            models.Index(fields=["author_ai"]),
            models.Index(fields=["genre"]),
            models.Index(fields=["language"]),
            models.Index(fields=["sha256"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title_ai or self.title_user} - {self.author_ai or self.author_user}"


class ProcessingJob(models.Model):
    class JobStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="jobs")
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]
        ordering = ["created_at"]

    def __str__(self):
        return f"Job#{self.pk} for Book#{self.book_id} ({self.status})"
