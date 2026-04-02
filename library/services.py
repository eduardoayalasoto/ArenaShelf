import hashlib
import html
import json
import re
import unicodedata
import zipfile
from io import BytesIO
from typing import Any

from django.conf import settings
from django.db import transaction

from .models import Book


class ValidationError(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extension_from_name(filename: str) -> str:
    lower = filename.lower().strip()
    if "." not in lower:
        return ""
    return "." + lower.rsplit(".", 1)[1]


def detect_mime(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(BytesIO(data), "r") as zf:
                if "mimetype" in zf.namelist():
                    raw = zf.read("mimetype").decode("utf-8", errors="ignore").strip()
                    if raw == "application/epub+zip":
                        return "application/epub+zip"
        except zipfile.BadZipFile:
            pass
        return "application/zip"
    return "application/octet-stream"


def validate_upload(filename: str, data: bytes) -> tuple[str, str]:
    ext = extension_from_name(filename)
    if ext in settings.BLOCKED_EXTENSIONS:
        raise ValidationError(f"Blocked extension: {ext}")
    if ext not in settings.ALLOWED_BOOK_EXTENSIONS:
        raise ValidationError("Only .pdf and .epub are allowed")

    if len(data) > settings.MAX_UPLOAD_SIZE:
        raise ValidationError(f"File exceeds max size ({settings.MAX_UPLOAD_SIZE} bytes)")

    mime = detect_mime(data)
    if ext == ".pdf" and mime != "application/pdf":
        raise ValidationError("File extension is PDF but signature is not valid PDF")
    if ext == ".epub" and mime != "application/epub+zip":
        raise ValidationError("File extension is EPUB but structure is not a valid EPUB")

    return ext, mime


def scan_with_clamav(data: bytes) -> tuple[bool, str]:
    try:
        import clamd

        client = clamd.ClamdNetworkSocket(settings.CLAMD_HOST, settings.CLAMD_PORT)
        result = client.instream(BytesIO(data))
        # result shape: {'stream': ('OK', None)} or {'stream': ('FOUND', 'Eicar-Test-Signature')}
        status, message = result.get("stream", ("ERROR", "No response"))
        if status == "OK":
            return True, "Clean"
        if status == "FOUND":
            return False, f"Malware detected: {message}"
        return False, f"Scan failed: {status} {message}"
    except Exception as exc:
        if settings.CLAMD_STRICT:
            return False, f"ClamAV unavailable and strict mode is enabled: {exc}"
        return True, f"ClamAV unavailable, skipped in non-strict mode: {exc}"


def strip_html(raw: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", no_tags).strip()


def extract_text_for_ai(ext: str, data: bytes) -> str:
    if ext == ".pdf":
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(BytesIO(data))
            chunks = []
            for page in reader.pages[:8]:
                chunks.append(page.extract_text() or "")
            return " ".join(chunks).strip()[:12000]
        except Exception:
            return ""

    if ext == ".epub":
        chunks: list[str] = []
        try:
            with zipfile.ZipFile(BytesIO(data), "r") as zf:
                for name in zf.namelist():
                    lname = name.lower()
                    if lname.endswith((".xhtml", ".html", ".htm")):
                        chunks.append(strip_html(zf.read(name).decode("utf-8", errors="ignore")))
                        if len(" ".join(chunks)) > 12000:
                            break
            return " ".join(chunks)[:12000]
        except Exception:
            return ""

    return ""


def fallback_ai_metadata(title_user: str, author_user: str) -> dict[str, Any]:
    return {
        "title_ai": title_user.strip(),
        "author_ai": author_user.strip(),
        "genre": "Unknown",
        "language": "unknown",
        "tags": ["libro", "lectura", "digital", "texto"],
        "summary": "Sinopsis no disponible.",
    }


def validate_ai_payload(payload: dict[str, Any], title_user: str, author_user: str) -> dict[str, Any]:
    try:
        title_ai = str(payload.get("title_ai", "")).strip()
        author_ai = str(payload.get("author_ai", "")).strip()
        genre = str(payload.get("genre", "")).strip()
        language = str(payload.get("language", "")).strip().lower()
        summary = str(payload.get("summary", "")).strip()
        tags_raw = payload.get("tags", [])
        tags = [str(t).strip().lower() for t in tags_raw if str(t).strip()]
    except Exception:
        return fallback_ai_metadata(title_user, author_user)

    if not title_ai:
        title_ai = title_user.strip()
    if not author_ai:
        author_ai = author_user.strip()
    if not genre:
        genre = "Unknown"
    if not language:
        language = "unknown"
    if len(tags) < 4:
        tags += ["libro", "lectura", "digital", "texto"]
    tags = tags[:8]
    if not summary:
        summary = "Sinopsis no disponible."

    return {
        "title_ai": title_ai,
        "author_ai": author_ai,
        "genre": genre,
        "language": language,
        "tags": tags,
        "summary": summary,
    }


def enrich_with_ai(text: str, title_user: str, author_user: str) -> dict[str, Any]:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY no configurada")

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
            system_instruction=(
                "Eres un analista editorial. Analiza el fragmento del libro y devuelve SOLO un objeto JSON "
                "con exactamente estas llaves: title_ai, author_ai, genre, language, tags, summary. "
                "tags debe ser un array con al menos 4 elementos en minúsculas. "
                "language debe ser el código ISO 639-1 (ej: 'es', 'en', 'fr')."
            ),
        )

        snippet = text[:6000] if text else ""
        user_content = json.dumps(
            {
                "title_user": title_user,
                "author_user": author_user,
                "book_excerpt": snippet,
            },
            ensure_ascii=False,
        )

        response = model.generate_content(user_content)
        content = response.text or "{}"
        payload = json.loads(content)
        return validate_ai_payload(payload, title_user, author_user)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Error en API de IA: {exc}") from exc


def fetch_book_metadata_from_google(title: str, author: str) -> dict[str, Any] | None:
    """Query Google Books API for canonical title, author and cover image bytes."""
    try:
        from urllib.request import Request, urlopen
        from urllib.parse import urlencode

        params = urlencode({"q": f"intitle:{title} inauthor:{author}", "maxResults": 1,
                            "fields": "items(volumeInfo/title,volumeInfo/authors,volumeInfo/imageLinks)"})
        req = Request(
            f"https://www.googleapis.com/books/v1/volumes?{params}",
            headers={"User-Agent": "ArenaShelf/1.0"},
        )
        import json as _json
        with urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())

        items = data.get("items")
        if not items:
            return None

        info = items[0].get("volumeInfo", {})
        real_title = info.get("title", "").strip()
        authors = info.get("authors") or []
        real_author = ", ".join(authors).strip()

        image_links = info.get("imageLinks", {})
        cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        cover_bytes = None
        if cover_url:
            cover_url = cover_url.replace("zoom=1", "zoom=0").replace("http://", "https://")
            try:
                cover_req = Request(cover_url, headers={"User-Agent": "ArenaShelf/1.0"})
                with urlopen(cover_req, timeout=10) as cover_resp:
                    cover_bytes = cover_resp.read()
            except Exception:
                cover_bytes = None

        if not real_title and not real_author:
            return None

        return {"title": real_title, "author": real_author, "cover_bytes": cover_bytes}
    except Exception:
        return None


def slug_piece(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9\s_-]", "", normalized)
    normalized = re.sub(r"[\s-]+", "_", normalized)
    normalized = normalized.strip("_")
    return normalized or "unknown"


def normalized_download_filename(author: str, title: str, ext: str) -> str:
    return f"{slug_piece(author)}-{slug_piece(title)}{ext}"


def generate_cover_svg(title: str, author: str) -> bytes:
    title_safe = html.escape(title[:90] or "Untitled")
    author_safe = html.escape(author[:90] or "Unknown Author")
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='900' viewBox='0 0 1200 900'>
<defs>
  <linearGradient id='bg' x1='0%' y1='0%' x2='100%' y2='100%'>
    <stop offset='0%' stop-color='#0f172a'/>
    <stop offset='50%' stop-color='#1d4ed8'/>
    <stop offset='100%' stop-color='#0ea5e9'/>
  </linearGradient>
</defs>
<rect width='1200' height='900' fill='url(#bg)'/>
<rect x='70' y='70' width='1060' height='760' rx='28' fill='rgba(255,255,255,0.10)'/>
<text x='110' y='360' fill='white' font-size='64' font-family='Georgia, serif'>{title_safe}</text>
<text x='110' y='460' fill='#e2e8f0' font-size='40' font-family='Verdana, sans-serif'>{author_safe}</text>
</svg>"""
    return svg.encode("utf-8")


@transaction.atomic
def process_book(book_id: int) -> None:
    book = Book.objects.select_for_update().get(id=book_id)
    try:
        book.status = Book.Status.VALIDATING
        book.save(update_fields=["status", "updated_at"])

        data = bytes(book.file_blob)
        ext, mime = validate_upload(book.original_filename, data)
        book.extension = ext
        book.mime_type = mime
        book.file_size = len(data)
        book.sha256 = sha256_bytes(data)

        clean, report = scan_with_clamav(data)
        book.scan_report = report
        if not clean:
            book.status = Book.Status.REJECTED
            book.save(update_fields=["status", "scan_report", "extension", "mime_type", "file_size", "sha256", "updated_at"])
            return

        book.status = Book.Status.SCANNED
        book.save(update_fields=["status", "scan_report", "extension", "mime_type", "file_size", "sha256", "updated_at"])

        text = extract_text_for_ai(ext, data)
        try:
            ai = enrich_with_ai(text, book.title_user, book.author_user)
        except RuntimeError as enrichment_error:
            ai = fallback_ai_metadata(book.title_user, book.author_user)
            book.scan_report = f"{book.scan_report}; Metadatos IA: {enrichment_error}"

        book.status = Book.Status.ENRICHED
        book.title_ai = ai["title_ai"]
        book.author_ai = ai["author_ai"]
        book.genre = ai["genre"]
        book.language = ai["language"]
        book.tags_json = ai["tags"]
        book.summary = ai["summary"]

        duplicate = (
            Book.objects.exclude(id=book.id)
            .filter(sha256=book.sha256, language=book.language)
            .exclude(status__in=[Book.Status.REJECTED, Book.Status.ERROR])
            .exists()
        )
        if duplicate:
            book.status = Book.Status.REJECTED
            book.scan_report = "Duplicate content with same language"
            book.save(
                update_fields=[
                    "status",
                    "title_ai",
                    "author_ai",
                    "genre",
                    "language",
                    "tags_json",
                    "summary",
                    "scan_report",
                    "updated_at",
                ]
            )
            return

        google_meta = fetch_book_metadata_from_google(book.title_ai, book.author_ai)
        if google_meta:
            book.title_ai = google_meta["title"] or book.title_ai
            book.author_ai = google_meta["author"] or book.author_ai
            book.cover_blob = google_meta["cover_bytes"] or generate_cover_svg(book.title_ai, book.author_ai)
        else:
            book.cover_blob = generate_cover_svg(book.title_ai, book.author_ai)

        book.normalized_filename = normalized_download_filename(book.author_ai, book.title_ai, ext)
        book.status = Book.Status.READY
        book.save(
            update_fields=[
                "status",
                "title_ai",
                "author_ai",
                "genre",
                "language",
                "tags_json",
                "summary",
                "scan_report",
                "normalized_filename",
                "cover_blob",
                "updated_at",
            ]
        )
    except ValidationError as exc:
        book.status = Book.Status.REJECTED
        book.scan_report = str(exc)
        book.save(update_fields=["status", "scan_report", "updated_at"])
    except Exception as exc:
        book.status = Book.Status.ERROR
        book.scan_report = str(exc)
        book.save(update_fields=["status", "scan_report", "updated_at"])
