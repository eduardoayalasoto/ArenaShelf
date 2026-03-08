from django.contrib import admin

from .models import Book, ProcessingJob


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("id", "title_ai", "author_ai", "genre", "language", "status", "created_at")
    list_filter = ("status", "genre", "language")
    search_fields = ("title_ai", "title_user", "author_ai", "author_user", "sha256")


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = ("id", "book", "status", "attempts", "created_at")
    list_filter = ("status",)
