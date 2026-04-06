from django.contrib import messages
from django.http import Http404, HttpResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import BookUploadForm
from .models import Book, ProcessingJob


class IndexView(View):
    template_name = "library/index.html"

    def get(self, request):
        books = Book.objects.filter(status=Book.Status.READY)
        q = request.GET.get("q", "").strip()
        genre = request.GET.get("genre", "").strip()
        language = request.GET.get("language", "").strip()
        tag = request.GET.get("tag", "").strip().lower()

        if q:
            books = books.filter(
                Q(title_ai__icontains=q) | Q(author_ai__icontains=q) | Q(summary__icontains=q)
            )
        if genre:
            books = books.filter(genre__iexact=genre)
        if language:
            books = books.filter(language__iexact=language)
        books = list(books)
        if tag:
            books = [b for b in books if tag in [t.lower() for t in b.tags_json]]

        genres = sorted({
            g.strip().title()
            for g in Book.objects.exclude(genre="").values_list("genre", flat=True)
            if g.strip()
        })
        languages = sorted({
            l.strip().title()
            for l in Book.objects.exclude(language="").values_list("language", flat=True)
            if l.strip()
        })

        return render(
            request,
            self.template_name,
            {
                "books": books,
                "q": q,
                "genre": genre,
                "language": language,
                "tag": tag,
                "genres": genres,
                "languages": languages,
            },
        )


class UploadView(View):
    template_name = "library/upload.html"

    def get(self, request):
        return render(request, self.template_name, {"form": BookUploadForm()})

    def post(self, request):
        form = BookUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)

        f = form.cleaned_data["file"]
        data = f.read()

        # Parse author and title from filename: "Autor - Titulo.ext"
        name_without_ext = f.name.rsplit(".", 1)[0] if "." in f.name else f.name
        if " - " in name_without_ext:
            raw_author, raw_title = name_without_ext.split(" - ", 1)
            title_user = raw_title.strip()
            author_user = raw_author.strip()
        else:
            title_user = name_without_ext.strip()
            author_user = "Desconocido"

        book = Book.objects.create(
            title_user=title_user,
            author_user=author_user,
            original_filename=f.name,
            file_blob=data,
            file_size=len(data),
            status=Book.Status.PENDING,
        )
        ProcessingJob.objects.create(book=book, status=ProcessingJob.JobStatus.PENDING)
        return render(request, self.template_name, {"form": BookUploadForm(), "uploaded": True})


class DetailView(View):
    template_name = "library/detail.html"

    def get(self, request, book_id: int):
        book = get_object_or_404(Book, id=book_id)
        return render(request, self.template_name, {"book": book})


class DownloadView(View):
    def get(self, request, book_id: int):
        book = get_object_or_404(Book, id=book_id)
        if book.status != Book.Status.READY:
            raise Http404("Book is not ready")

        filename = book.normalized_filename or book.original_filename
        resp = HttpResponse(bytes(book.file_blob), content_type=book.mime_type or "application/octet-stream")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


def _cover_content_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/svg+xml"


class CoverView(View):
    def get(self, request, book_id: int):
        from .services import generate_cover_svg

        book = get_object_or_404(Book, id=book_id)
        if request.GET.get("svg"):
            data = generate_cover_svg(
                book.title_ai or book.title_user,
                book.author_ai or book.author_user,
            )
            return HttpResponse(data, content_type="image/svg+xml")
        if book.cover_blob:
            data = bytes(book.cover_blob)
            ct = _cover_content_type(data)
            # SVG covers may be old landscape format — regenerate as portrait
            if ct == "image/svg+xml":
                data = generate_cover_svg(
                    book.title_ai or book.title_user,
                    book.author_ai or book.author_user,
                )
            return HttpResponse(data, content_type=ct)
        if book.cover_url:
            return redirect(book.cover_url)
        data = generate_cover_svg(
            book.title_ai or book.title_user,
            book.author_ai or book.author_user,
        )
        return HttpResponse(data, content_type="image/svg+xml")
