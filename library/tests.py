from unittest.mock import patch

from django.test import TestCase

from .models import Book
from .services import normalized_download_filename, process_book, validate_ai_payload, validate_upload


class ServiceTests(TestCase):
    def test_normalized_download_filename(self):
        name = normalized_download_filename("Gabriel García Márquez", "Cien Años de Soledad", ".pdf")
        self.assertEqual(name, "gabriel_garcia_marquez-cien_anos_de_soledad.pdf")

    def test_validate_upload_rejects_zip(self):
        with self.assertRaises(Exception):
            validate_upload("malicious.zip", b"PK\x03\x04foo")

    def test_validate_upload_accepts_pdf_signature(self):
        ext, mime = validate_upload("book.pdf", b"%PDF-1.5\nabc")
        self.assertEqual(ext, ".pdf")
        self.assertEqual(mime, "application/pdf")

    def test_validate_ai_payload_fills_defaults(self):
        payload = {"title_ai": "", "author_ai": "", "tags": []}
        data = validate_ai_payload(payload, "Title", "Author")
        self.assertEqual(data["title_ai"], "Title")
        self.assertEqual(data["author_ai"], "Author")
        self.assertGreaterEqual(len(data["tags"]), 4)


class ProcessingTests(TestCase):
    @patch("library.services.enrich_with_ai")
    @patch("library.services.extract_text_for_ai")
    @patch("library.services.scan_with_clamav")
    def test_duplicate_rule_same_hash_language_is_rejected(self, mock_scan, mock_extract, mock_ai):
        mock_scan.return_value = (True, "Clean")
        mock_extract.return_value = "text"
        mock_ai.return_value = {
            "title_ai": "Book",
            "author_ai": "Author",
            "genre": "Novel",
            "language": "es",
            "tags": ["a", "b", "c", "d"],
            "summary": "Summary",
        }
        data = b"%PDF-1.4\nfake"

        first = Book.objects.create(
            title_user="Book",
            author_user="Author",
            original_filename="first.pdf",
            file_blob=data,
            file_size=len(data),
        )
        process_book(first.id)
        first.refresh_from_db()
        self.assertEqual(first.status, Book.Status.READY)

        second = Book.objects.create(
            title_user="Book copy",
            author_user="Author",
            original_filename="second.pdf",
            file_blob=data,
            file_size=len(data),
        )
        process_book(second.id)
        second.refresh_from_db()
        self.assertEqual(second.status, Book.Status.REJECTED)

    @patch("library.services.enrich_with_ai")
    @patch("library.services.extract_text_for_ai")
    @patch("library.services.scan_with_clamav")
    def test_duplicate_rule_allows_same_hash_if_language_differs(self, mock_scan, mock_extract, mock_ai):
        mock_scan.return_value = (True, "Clean")
        mock_extract.return_value = "text"
        data = b"%PDF-1.4\nfake"

        mock_ai.return_value = {
            "title_ai": "Book",
            "author_ai": "Author",
            "genre": "Novel",
            "language": "es",
            "tags": ["a", "b", "c", "d"],
            "summary": "Summary",
        }
        first = Book.objects.create(
            title_user="Book",
            author_user="Author",
            original_filename="first.pdf",
            file_blob=data,
            file_size=len(data),
        )
        process_book(first.id)

        mock_ai.return_value = {
            "title_ai": "Book",
            "author_ai": "Author",
            "genre": "Novel",
            "language": "en",
            "tags": ["a", "b", "c", "d"],
            "summary": "Summary",
        }
        second = Book.objects.create(
            title_user="Book",
            author_user="Author",
            original_filename="second.pdf",
            file_blob=data,
            file_size=len(data),
        )
        process_book(second.id)
        second.refresh_from_db()
        self.assertEqual(second.status, Book.Status.READY)
