from django.http import JsonResponse
from django.db.models import Q
from django.views import View

from .models import Book


class BookListApiView(View):
    def get(self, request):
        books = Book.objects.filter(status=Book.Status.READY)
        q = request.GET.get("q", "").strip()
        genre = request.GET.get("genre", "").strip()
        language = request.GET.get("language", "").strip()
        tag = request.GET.get("tag", "").strip().lower()

        if q:
            books = books.filter(Q(title_ai__icontains=q) | Q(author_ai__icontains=q))
        if genre:
            books = books.filter(genre__iexact=genre)
        if language:
            books = books.filter(language__iexact=language)

        rows = []
        for b in books:
            tags = [t.lower() for t in b.tags_json]
            if tag and tag not in tags:
                continue
            rows.append(
                {
                    "id": b.id,
                    "title": b.title_ai or b.title_user,
                    "author": b.author_ai or b.author_user,
                    "genre": b.genre,
                    "language": b.language,
                    "tags": b.tags_json,
                    "summary": b.summary,
                    "download_url": f"/books/{b.id}/download",
                }
            )

        return JsonResponse({"count": len(rows), "results": rows})
