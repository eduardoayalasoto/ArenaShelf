from django.urls import path

from .api import BookListApiView
from .views import CoverView, DeleteView, DetailView, DownloadAltView, DownloadView, EmailBookView, IndexView, UploadView

urlpatterns = [
    path("", IndexView.as_view(), name="home"),
    path("upload", UploadView.as_view(), name="upload"),
    path("books/<int:book_id>", DetailView.as_view(), name="book-detail"),
    path("books/<int:book_id>/delete", DeleteView.as_view(), name="book-delete"),
    path("books/<int:book_id>/download", DownloadView.as_view(), name="book-download"),
    path("books/<int:book_id>/download/alt", DownloadAltView.as_view(), name="book-download-alt"),
    path("books/<int:book_id>/email", EmailBookView.as_view(), name="book-email"),
    path("books/<int:book_id>/cover", CoverView.as_view(), name="book-cover"),
    path("api/books", BookListApiView.as_view(), name="api-books"),
]
