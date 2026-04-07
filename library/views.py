import re

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.http import Http404, HttpResponse, JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

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
            books = books.filter(Q(title_ai__icontains=q) | Q(author_ai__icontains=q))
        if genre:
            books = books.filter(genre__iexact=genre)
        if language:
            books = books.filter(language__iexact=language)
        books = list(books)
        if tag:
            books = [b for b in books if tag in [t.lower() for t in b.tags_json]]

        genres = Book.objects.exclude(genre="").values_list("genre", flat=True).distinct()
        languages = Book.objects.exclude(language="").values_list("language", flat=True).distinct()

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
        book = Book.objects.create(
            title_user=form.cleaned_data["title"],
            author_user=form.cleaned_data["author"],
            original_filename=f.name,
            file_blob=data,
            file_size=len(data),
            status=Book.Status.PENDING,
        )
        ProcessingJob.objects.create(book=book, status=ProcessingJob.JobStatus.PENDING)
        messages.success(request, "Libro subido. El procesamiento se ejecuta en segundo plano.")
        return redirect("book-detail", book_id=book.id)


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


class CoverView(View):
    def get(self, request, book_id: int):
        book = get_object_or_404(Book, id=book_id)
        if book.cover_blob:
            return HttpResponse(bytes(book.cover_blob), content_type="image/svg+xml")
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='900'>"
            "<rect width='1200' height='900' fill='#334155'/></svg>"
        )
        return HttpResponse(svg, content_type="image/svg+xml")


def _send_email(recipient: str, subject: str, body: str, attachment_name: str, file_data: bytes, mime: str) -> None:
    """Send an email with a file attachment.

    Uses Resend if RESEND_API_KEY is configured, otherwise falls back to SMTP.
    Raises on failure so the caller can return an appropriate HTTP response.
    """
    from_addr = settings.EMAIL_FROM

    if settings.RESEND_API_KEY:
        import base64
        import resend  # type: ignore

        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            "from": from_addr or "ArenaShelf <onboarding@resend.dev>",
            "to": [recipient],
            "subject": subject,
            "text": body,
            "attachments": [{
                "filename": attachment_name,
                "content": base64.b64encode(file_data).decode(),
            }],
        })
    else:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_addr or settings.EMAIL_HOST_USER,
            to=[recipient],
        )
        msg.attach(attachment_name, file_data, mime)
        msg.send(fail_silently=False)


class EmailBookView(View):
    def post(self, request, book_id: int):
        if not settings.RESEND_API_KEY and not settings.EMAIL_HOST_USER:
            return JsonResponse(
                {"error": "El envío por correo no está configurado en el servidor."},
                status=503,
            )

        book = get_object_or_404(Book, id=book_id)
        if book.status != Book.Status.READY:
            return JsonResponse({"error": "El libro aún no está listo."}, status=400)

        recipient = request.POST.get("email", "").strip()
        if not _EMAIL_RE.match(recipient):
            return JsonResponse({"error": "Dirección de correo inválida."}, status=400)

        # Prefer EPUB; fall back to whatever format was uploaded
        if book.extension == ".epub":
            file_data = bytes(book.file_blob)
            mime = "application/epub+zip"
            ext = ".epub"
        else:
            file_data = bytes(book.file_blob)
            mime = book.mime_type or "application/octet-stream"
            ext = book.extension or ""

        title = book.title_ai or book.title_user
        author = book.author_ai or book.author_user
        attachment_name = f"{title} - {author}{ext}"
        body = f"Hola,\n\nAquí está tu libro: {title} de {author}.\n\nEnviado desde ArenaShelf."

        try:
            _send_email(recipient, title, body, attachment_name, file_data, mime)
            return JsonResponse({"ok": True})
        except Exception as exc:
            return JsonResponse({"error": f"Error al enviar: {exc}"}, status=500)
