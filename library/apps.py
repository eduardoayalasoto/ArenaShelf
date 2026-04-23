import sys
import threading

from django.apps import AppConfig

_SKIP_CMDS = {
    "migrate", "makemigrations", "collectstatic", "test",
    "shell", "run_library_worker", "check", "createsuperuser",
    "dbshell", "showmigrations", "sqlmigrate",
}


class LibraryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "library"

    def ready(self) -> None:
        from django.db.backends.signals import connection_created

        def _enable_wal(sender, connection, **kwargs):
            if connection.vendor == "sqlite":
                connection.cursor().execute("PRAGMA journal_mode=WAL;")
                connection.cursor().execute("PRAGMA synchronous=NORMAL;")

        connection_created.connect(_enable_wal)

        if not any(arg in _SKIP_CMDS for arg in sys.argv):
            from library.worker import run_worker_loop
            t = threading.Thread(target=run_worker_loop, daemon=True, name="library-worker")
            t.start()
