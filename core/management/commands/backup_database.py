from datetime import datetime
from pathlib import Path
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Create and verify an online SQLite backup, then rotate old backups."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default=str(settings.BASE_DIR / "backups"))
        parser.add_argument("--keep", type=int, default=10)

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            raise CommandError("This project supports SQLite backups only.")
        keep = options["keep"]
        if keep < 1:
            raise CommandError("--keep must be at least 1.")
        output_dir = Path(options["output_dir"]).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = output_dir / f"cosmetics-{stamp}.sqlite3"

        connection.ensure_connection()
        with sqlite3.connect(destination) as backup_connection:
            connection.connection.backup(backup_connection)
            result = backup_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            destination.unlink(missing_ok=True)
            raise CommandError(f"Backup integrity check failed: {result}")

        backups = sorted(
            output_dir.glob("cosmetics-*.sqlite3"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[keep:]:
            if old_backup.parent == output_dir:
                old_backup.unlink()
        self.stdout.write(self.style.SUCCESS(f"Verified SQLite backup: {destination}"))
