from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Book",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title_user", models.CharField(max_length=255)),
                ("author_user", models.CharField(max_length=255)),
                ("title_ai", models.CharField(blank=True, max_length=255)),
                ("author_ai", models.CharField(blank=True, max_length=255)),
                ("genre", models.CharField(blank=True, max_length=120)),
                ("language", models.CharField(blank=True, max_length=32)),
                ("summary", models.TextField(blank=True)),
                ("tags_json", models.JSONField(blank=True, default=list)),
                ("original_filename", models.CharField(max_length=255)),
                ("normalized_filename", models.CharField(blank=True, max_length=255)),
                ("extension", models.CharField(blank=True, max_length=16)),
                ("mime_type", models.CharField(blank=True, max_length=120)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("file_blob", models.BinaryField()),
                ("file_size", models.PositiveIntegerField(default=0)),
                ("cover_blob", models.BinaryField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("validating", "Validating"),
                            ("scanned", "Scanned"),
                            ("enriched", "Enriched"),
                            ("ready", "Ready"),
                            ("rejected", "Rejected"),
                            ("error", "Error"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("scan_report", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ProcessingJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("book", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="jobs", to="library.book")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddIndex(model_name="book", index=models.Index(fields=["title_ai"], name="library_book_title_a_f0016b_idx")),
        migrations.AddIndex(model_name="book", index=models.Index(fields=["author_ai"], name="library_book_author__7100c2_idx")),
        migrations.AddIndex(model_name="book", index=models.Index(fields=["genre"], name="library_book_genre_501be8_idx")),
        migrations.AddIndex(model_name="book", index=models.Index(fields=["language"], name="library_book_languag_1ee7b0_idx")),
        migrations.AddIndex(model_name="book", index=models.Index(fields=["sha256"], name="library_book_sha256_f6b6c3_idx")),
        migrations.AddIndex(
            model_name="processingjob",
            index=models.Index(fields=["status", "created_at"], name="library_pro_status_3f0064_idx"),
        ),
    ]
