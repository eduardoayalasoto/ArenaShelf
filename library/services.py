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
        "genre": "Desconocido",
        "language": "Desconocido",
        "tags": ["libro", "lectura", "digital", "texto"],
        "summary": "Sinopsis no disponible.",
    }


def validate_ai_payload(payload: dict[str, Any], title_user: str, author_user: str) -> dict[str, Any]:
    try:
        title_ai = str(payload.get("title_ai", "")).strip()
        author_ai = str(payload.get("author_ai", "")).strip()
        genre = str(payload.get("genre", "")).strip()
        language = str(payload.get("language", "")).strip()
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
        genre = "Desconocido"
    if not language:
        language = "Desconocido"
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
                "Reglas: "
                "language debe ser el nombre completo del idioma en español (ej: 'Inglés', 'Español', 'Francés', 'Alemán'). "
                "tags debe ser un array con al menos 4 elementos en minúsculas, en español. "
                "summary debe ser un párrafo en español que describa el contenido del libro. "
                "genre debe estar en español (ej: 'Tecnología', 'Autoayuda', 'Ficción', 'Historia')."
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
    """Query Google Books API for canonical title, author, cover URL and extra metadata."""
    try:
        from urllib.request import Request, urlopen
        from urllib.parse import urlencode
        import json as _json

        # Strip punctuation that breaks Google Books field-restricted queries
        clean_title = re.sub(r"[¡!¿?\"']", "", title).strip()
        clean_author = re.sub(r"[¡!¿?\"']", "", author).strip()

        # Try progressively looser queries until we get results
        queries = [
            f'intitle:"{clean_title}" inauthor:"{clean_author}"',
            f'"{clean_title}" "{clean_author}"',
            f'intitle:"{clean_title}"',
            f'"{clean_title}"',
        ]

        fields = (
            "items(volumeInfo/title,volumeInfo/authors,"
            "volumeInfo/imageLinks,volumeInfo/publishedDate,"
            "volumeInfo/pageCount,volumeInfo/publisher)"
        )

        data = None
        for query in queries:
            params = urlencode({"q": query, "maxResults": 3, "fields": fields})
            req = Request(
                f"https://www.googleapis.com/books/v1/volumes?{params}",
                headers={"User-Agent": "ArenaShelf/1.0"},
            )
            with urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read())
            if data.get("items"):
                break

        items = data.get("items") if data else None
        if not items:
            return None

        # Pick the first result that has a cover image, otherwise fallback to first result
        chosen = items[0]
        for item in items:
            if item.get("volumeInfo", {}).get("imageLinks"):
                chosen = item
                break

        info = chosen.get("volumeInfo", {})
        real_title = info.get("title", "").strip()
        # Do NOT append subtitle — for classic books it's often descriptive text, not a real subtitle
        authors = info.get("authors") or []
        real_author = ", ".join(authors).strip()

        image_links = info.get("imageLinks", {})
        cover_url = (
            image_links.get("extraLarge")
            or image_links.get("large")
            or image_links.get("medium")
            or image_links.get("thumbnail")
            or image_links.get("smallThumbnail")
            or ""
        )
        if cover_url:
            cover_url = (
                cover_url
                .replace("zoom=1", "zoom=6")
                .replace("&edge=curl", "")
                .replace("http://", "https://")
            )

        if not real_title and not real_author:
            return None

        return {
            "title": real_title,
            "author": real_author,
            "cover_url": cover_url,
            "published_date": info.get("publishedDate", ""),
            "page_count": info.get("pageCount"),
            "publisher": info.get("publisher", ""),
        }
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


def fetch_cover_from_openlibrary(title: str, author: str) -> str | None:
    """Query Open Library search API for a book cover URL (no API key required)."""
    try:
        from urllib.request import Request, urlopen
        from urllib.parse import urlencode
        import json as _json

        params = urlencode({"title": title, "author": author, "limit": 1, "fields": "cover_i"})
        req = Request(
            f"https://openlibrary.org/search.json?{params}",
            headers={"User-Agent": "ArenaShelf/1.0"},
        )
        with urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())

        docs = data.get("docs", [])
        if not docs:
            return None
        cover_i = docs[0].get("cover_i")
        if not cover_i:
            return None
        return f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg"
    except Exception:
        return None


def download_image(url: str) -> bytes | None:
    """Download an image from a URL and return its bytes, or None on failure."""
    try:
        from urllib.request import Request, urlopen

        req = Request(url, headers={"User-Agent": "ArenaShelf/1.0"})
        with urlopen(req, timeout=10) as resp:
            return resp.read()
    except Exception:
        return None


def generate_cover_svg(title: str, author: str) -> bytes:
    """Generate a portrait (3:4) SVG book cover with wrapped title and author."""

    def _wrap(text: str, max_chars: int, max_lines: int) -> list[str]:
        words = (text or "").split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                if len(lines) >= max_lines:
                    break
                current = word[:max_chars]
        if current and len(lines) < max_lines:
            lines.append(current)
        return lines or [""]

    title_lines = _wrap(title or "Untitled", 18, 3)
    author_lines = _wrap(author or "Unknown", 22, 2)

    title_line_h = 54
    title_y = 300
    author_y = title_y + len(title_lines) * title_line_h + 36

    title_elems = "\n".join(
        f"  <text x='40' y='{title_y + i * title_line_h}' fill='white' "
        f"font-size='42' font-family='Georgia, serif'>{html.escape(line)}</text>"
        for i, line in enumerate(title_lines)
    )
    author_elems = "\n".join(
        f"  <text x='40' y='{author_y + i * 36}' fill='#cbd5e1' "
        f"font-size='26' font-family='Verdana, sans-serif'>{html.escape(line)}</text>"
        for i, line in enumerate(author_lines)
    )

    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='600' height='800' viewBox='0 0 600 800'>
<defs>
  <linearGradient id='bg' x1='0%' y1='0%' x2='100%' y2='100%'>
    <stop offset='0%' stop-color='#0f172a'/>
    <stop offset='50%' stop-color='#1d4ed8'/>
    <stop offset='100%' stop-color='#0ea5e9'/>
  </linearGradient>
</defs>
<rect width='600' height='800' fill='url(#bg)'/>
<rect x='30' y='30' width='540' height='740' rx='16' fill='rgba(255,255,255,0.08)'/>
{title_elems}
{author_elems}
</svg>"""
    return svg.encode("utf-8")


def _epub_spine_texts(epub_data: bytes) -> tuple[str, str, list[str]]:
    """Return (title, author, ordered list of text chunks) following the OPF spine.

    Reads the OPF spine to get the correct document reading order instead of
    sorting filenames alphabetically, which breaks chapter order in most EPUBs.
    Navigation documents (nav.xhtml, toc pages) are excluded from content.
    """
    title_str = "Sin título"
    author_str = ""
    doc_texts: list[str] = []

    with zipfile.ZipFile(BytesIO(epub_data)) as zf:
        all_names = set(zf.namelist())

        # --- locate OPF ---
        opf_path: str | None = None
        try:
            container_xml = zf.read("META-INF/container.xml").decode("utf-8", errors="ignore")
            m = re.search(r'full-path="([^"]+\.opf)"', container_xml)
            if m:
                opf_path = m.group(1)
        except Exception:
            pass

        if opf_path and opf_path in all_names:
            opf_xml = zf.read(opf_path).decode("utf-8", errors="ignore")
            opf_dir = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""

            t = re.search(r"<dc:title[^>]*>([^<]+)", opf_xml)
            a = re.search(r"<dc:creator[^>]*>([^<]+)", opf_xml)
            if t:
                title_str = t.group(1).strip()
            if a:
                author_str = a.group(1).strip()

            # manifest: id → href
            manifest: dict[str, str] = {}
            for item_m in re.finditer(r"<item\b[^>]+>", opf_xml):
                tag = item_m.group(0)
                id_m = re.search(r'\bid="([^"]+)"', tag)
                href_m = re.search(r'\bhref="([^"]+)"', tag)
                if id_m and href_m:
                    manifest[id_m.group(1)] = href_m.group(1)

            # nav item ids to skip (EPUB3 navigation document)
            nav_ids: set[str] = set()
            for item_m in re.finditer(r'<item\b[^>]+\bproperties="[^"]*\bnav\b[^"]*"[^>]*>', opf_xml):
                id_m = re.search(r'\bid="([^"]+)"', item_m.group(0))
                if id_m:
                    nav_ids.add(id_m.group(1))

            # spine: ordered idrefs
            for spine_m in re.finditer(r'<itemref\b[^>]*\bidref="([^"]+)"', opf_xml):
                idref = spine_m.group(1)
                if idref in nav_ids or idref not in manifest:
                    continue
                href = manifest[idref]
                # resolve relative href against OPF directory
                full = opf_dir + href if not href.startswith("/") else href.lstrip("/")
                if full in all_names:
                    raw = zf.read(full).decode("utf-8", errors="ignore")
                    text = strip_html(raw).strip()
                    if text:
                        doc_texts.append(text)
        else:
            # Fallback when no OPF found: alphabetical order
            for name in sorted(all_names):
                if name.lower().endswith((".xhtml", ".html", ".htm")):
                    raw = zf.read(name).decode("utf-8", errors="ignore")
                    text = strip_html(raw).strip()
                    if text:
                        doc_texts.append(text)

    return title_str, author_str, doc_texts


def _epub_to_pdf(epub_data: bytes) -> bytes | None:
    """Convert EPUB bytes to PDF bytes using fpdf2. Returns None on failure."""
    try:
        from fpdf import FPDF

        def safe(s: str) -> str:
            return s.encode("latin-1", errors="replace").decode("latin-1")

        title_str, author_str, doc_texts = _epub_spine_texts(epub_data)

        if not doc_texts:
            return None

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.set_margins(20, 20, 20)

        # Title page
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 22)
        pdf.multi_cell(0, 12, safe(title_str), align="C")
        if author_str:
            pdf.ln(6)
            pdf.set_font("Helvetica", "", 14)
            pdf.multi_cell(0, 8, safe(author_str), align="C")
        pdf.ln(20)
        pdf.set_font("Helvetica", "", 11)

        for text in doc_texts:
            for para in re.split(r"(?:\r?\n){2,}", text):
                para = para.strip()
                if not para:
                    continue
                # Write full paragraph without truncation
                pdf.multi_cell(0, 6, safe(para))
                pdf.ln(3)

        return bytes(pdf.output())
    except Exception:
        return None


_PAGES_PER_CHAPTER = 10


def _pdf_to_epub(pdf_data: bytes) -> bytes | None:
    """Convert PDF bytes to EPUB using pypdf + manual zip assembly.

    Groups pages into chapters of _PAGES_PER_CHAPTER to keep the EPUB
    navigable. All pages are preserved — those with no extractable text
    get a placeholder so the chapter count matches the original PDF.
    """
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(BytesIO(pdf_data))
        total = len(reader.pages)
        if total == 0:
            return None

        all_texts = [(page.extract_text() or "").strip() for page in reader.pages]

        # Group into chapters of _PAGES_PER_CHAPTER pages each
        chapters: list[tuple[str, str]] = []  # (title, combined_text)
        for start in range(0, total, _PAGES_PER_CHAPTER):
            end = min(start + _PAGES_PER_CHAPTER, total)
            label = (
                f"Páginas {start + 1}–{end}" if end > start + 1 else f"Página {start + 1}"
            )
            combined = "\n\n".join(t for t in all_texts[start:end] if t)
            chapters.append((label, combined))

        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            # mimetype must be first and stored uncompressed
            mi = zipfile.ZipInfo("mimetype")
            mi.compress_type = zipfile.ZIP_STORED
            zf.writestr(mi, "application/epub+zip")

            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                "<rootfiles>"
                '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                "</rootfiles>"
                "</container>",
            )

            cids: list[tuple[str, str]] = []  # (id, title)
            for i, (title, text) in enumerate(chapters):
                cid = f"chap{i + 1}"
                if text:
                    lines = [html.escape(ln) for ln in text.split("\n") if ln.strip()]
                    body = "".join(f"<p>{ln}</p>" for ln in lines)
                else:
                    body = "<p><em>[Contenido no extraíble — posible imagen o font embebida]</em></p>"
                xhtml = (
                    '<?xml version="1.0" encoding="utf-8"?>'
                    "<!DOCTYPE html>"
                    '<html xmlns="http://www.w3.org/1999/xhtml">'
                    f"<head><title>{html.escape(title)}</title></head>"
                    f"<body><h2>{html.escape(title)}</h2>{body}</body>"
                    "</html>"
                )
                zf.writestr(f"OEBPS/{cid}.xhtml", xhtml)
                cids.append((cid, title))

            manifest = "\n".join(
                f'<item id="{cid}" href="{cid}.xhtml" media-type="application/xhtml+xml"/>'
                for cid, _ in cids
            )
            manifest += '\n<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            spine = "\n".join(f'<itemref idref="{cid}"/>' for cid, _ in cids)
            opf = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                f"<dc:title>Converted Book ({total} páginas)</dc:title>"
                "<dc:language>es</dc:language>"
                "</metadata>"
                f'<manifest>{manifest}</manifest>'
                f'<spine toc="ncx">{spine}</spine>'
                "</package>"
            )
            zf.writestr("OEBPS/content.opf", opf)

            nav_points = "\n".join(
                f'<navPoint id="nav{i}" playOrder="{i + 1}">'
                f"<navLabel><text>{html.escape(title)}</text></navLabel>"
                f'<content src="{cid}.xhtml"/>'
                f"</navPoint>"
                for i, (cid, title) in enumerate(cids)
            )
            ncx = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
                '<head><meta name="dtb:uid" content="converted"/></head>'
                "<docTitle><text>Converted Book</text></docTitle>"
                f"<navMap>{nav_points}</navMap>"
                "</ncx>"
            )
            zf.writestr("OEBPS/toc.ncx", ncx)

        return output.getvalue()
    except Exception:
        return None


def convert_format(ext: str, data: bytes) -> tuple[bytes, str] | tuple[None, None]:
    """Convert epub→pdf or pdf→epub. Returns (bytes, new_ext) or (None, None) on failure."""
    if ext == ".epub":
        result = _epub_to_pdf(data)
        return (result, ".pdf") if result else (None, None)
    if ext == ".pdf":
        result = _pdf_to_epub(data)
        return (result, ".epub") if result else (None, None)
    return None, None


def process_book(book_id: int) -> None:
    """Process a book through validation, scanning, AI enrichment, and metadata lookup.

    Uses short targeted transactions instead of one long atomic block so that
    SQLite is never locked during external I/O (ClamAV, Gemini, Google Books,
    image downloads). This prevents concurrent uploads from getting a 500 error
    while a book is being processed.
    """
    try:
        _do_process_book(book_id)
    except Book.DoesNotExist:
        pass  # book was deleted during processing — nothing to update
    except Exception as exc:
        with transaction.atomic():
            Book.objects.filter(id=book_id).update(
                status=Book.Status.ERROR,
                scan_report=str(exc),
            )


def _do_process_book(book_id: int) -> None:
    # --- Step 1: read initial data and mark as VALIDATING (short transaction) ---
    with transaction.atomic():
        book = Book.objects.get(id=book_id)
        title_user = book.title_user
        author_user = book.author_user
        original_filename = book.original_filename
        file_data = bytes(book.file_blob)
        book.status = Book.Status.VALIDATING
        book.save(update_fields=["status", "updated_at"])

    scan_report = ""

    # --- Step 2: validate file format (CPU only, no DB lock needed) ---
    try:
        ext, mime = validate_upload(original_filename, file_data)
    except ValidationError as exc:
        with transaction.atomic():
            Book.objects.filter(id=book_id).update(
                status=Book.Status.REJECTED,
                scan_report=str(exc),
            )
        return

    sha256 = sha256_bytes(file_data)
    file_size = len(file_data)

    # --- Step 3: ClamAV scan (external process, no DB lock needed) ---
    try:
        clean, scan_report = scan_with_clamav(file_data)
    except Exception as exc:
        clean, scan_report = True, f"ClamAV unavailable: {exc}"

    with transaction.atomic():
        if not clean:
            Book.objects.filter(id=book_id).update(
                status=Book.Status.REJECTED,
                scan_report=scan_report,
                extension=ext,
                mime_type=mime,
                file_size=file_size,
                sha256=sha256,
            )
            return
        Book.objects.filter(id=book_id).update(
            status=Book.Status.SCANNED,
            scan_report=scan_report,
            extension=ext,
            mime_type=mime,
            file_size=file_size,
            sha256=sha256,
        )

    # --- Step 4: AI enrichment (external API, no DB lock needed) ---
    text = extract_text_for_ai(ext, file_data)
    try:
        ai = enrich_with_ai(text, title_user, author_user)
    except RuntimeError as enrichment_error:
        ai = fallback_ai_metadata(title_user, author_user)
        scan_report = f"{scan_report}; Metadatos IA: {enrichment_error}"

    title_ai = ai["title_ai"]
    author_ai = ai["author_ai"]

    # --- Step 5: duplicate check + save ENRICHED (short transaction) ---
    with transaction.atomic():
        is_duplicate = (
            Book.objects.exclude(id=book_id)
            .filter(sha256=sha256, language=ai["language"])
            .exclude(status__in=[Book.Status.REJECTED, Book.Status.ERROR])
            .exists()
        )
        if is_duplicate:
            Book.objects.filter(id=book_id).update(
                status=Book.Status.REJECTED,
                title_ai=title_ai,
                author_ai=author_ai,
                genre=ai["genre"],
                language=ai["language"],
                tags_json=ai["tags"],
                summary=ai["summary"],
                scan_report="Duplicate content with same language",
            )
            return
        Book.objects.filter(id=book_id).update(
            status=Book.Status.ENRICHED,
            title_ai=title_ai,
            author_ai=author_ai,
            genre=ai["genre"],
            language=ai["language"],
            tags_json=ai["tags"],
            summary=ai["summary"],
            scan_report=scan_report,
        )

    # --- Step 6: external metadata + cover (network I/O, no DB lock needed) ---
    published_date = ""
    page_count = None
    publisher = ""
    cover_blob = None
    cover_url = ""

    google_meta = fetch_book_metadata_from_google(title_ai, author_ai)
    if google_meta:
        title_ai = google_meta["title"] or title_ai
        author_ai = google_meta["author"] or author_ai
        published_date = google_meta.get("published_date") or ""
        page_count = google_meta.get("page_count")
        publisher = google_meta.get("publisher") or ""
        if google_meta.get("cover_url"):
            img_data = download_image(google_meta["cover_url"])
            if img_data:
                cover_blob = img_data
            else:
                cover_url = google_meta["cover_url"]

    if not cover_blob and not cover_url:
        ol_cover_url = fetch_cover_from_openlibrary(title_ai, author_ai)
        if ol_cover_url:
            img_data = download_image(ol_cover_url)
            if img_data:
                cover_blob = img_data
            else:
                cover_url = ol_cover_url

    if not cover_blob:
        cover_blob = generate_cover_svg(title_ai, author_ai)

    normalized_filename = normalized_download_filename(author_ai, title_ai, ext)

    # --- Step 7: final save as READY (short transaction) ---
    with transaction.atomic():
        book = Book.objects.get(id=book_id)
        book.status = Book.Status.READY
        book.title_ai = title_ai
        book.author_ai = author_ai
        book.published_date = published_date
        book.page_count = page_count
        book.publisher = publisher
        book.cover_blob = cover_blob
        book.cover_url = cover_url
        book.normalized_filename = normalized_filename
        book.scan_report = scan_report
        book.save(
            update_fields=[
                "status",
                "title_ai",
                "author_ai",
                "published_date",
                "page_count",
                "publisher",
                "cover_blob",
                "cover_url",
                "normalized_filename",
                "scan_report",
                "updated_at",
            ]
        )

    # --- Step 8: format conversion (CPU-intensive, outside transaction) ---
    # Failure here is non-fatal: book is already READY without the alt format.
    alt_data, alt_ext = convert_format(ext, file_data)
    if alt_data and alt_ext:
        with transaction.atomic():
            Book.objects.filter(id=book_id).update(
                alt_blob=alt_data,
                alt_extension=alt_ext,
            )
