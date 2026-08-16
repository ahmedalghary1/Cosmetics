#!/usr/bin/env python3
"""Create an idempotent, private .env and persistent folders for PythonAnywhere."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import secrets
import sqlite3
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_KEYS = (
    "DJANGO_SECRET_KEY",
    "DEBUG",
    "PYTHONANYWHERE_USERNAME",
    "ALLOWED_HOSTS",
    "CSRF_TRUSTED_ORIGINS",
    "PYTHONANYWHERE_DATA_ROOT",
    "SQLITE_PATH",
    "SQLITE_TIMEOUT",
    "SQLITE_ENABLE_WAL",
    "STATIC_ROOT",
    "MEDIA_ROOT",
    "PRIVATE_MEDIA_ROOT",
    "CACHE_BACKEND",
    "CACHE_LOCATION",
    "SECURE_SSL_REDIRECT",
    "SECURE_HSTS_SECONDS",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_HSTS_PRELOAD",
    "LOG_LEVEL",
    "EMAIL_BACKEND",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_USE_TLS",
    "EMAIL_TIMEOUT",
    "DEFAULT_FROM_EMAIL",
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def safe_secret(current: str) -> str:
    insecure_markers = ("replace", "development-only", "django-insecure")
    if len(current) >= 50 and not any(marker in current.lower() for marker in insecure_markers):
        return current
    return secrets.token_urlsafe(64)


def sqlite_backup(source: Path, destination: Path) -> None:
    temporary = destination.with_suffix(".sqlite3.tmp")
    if temporary.exists():
        temporary.unlink()
    with sqlite3.connect(source) as source_connection:
        with sqlite3.connect(temporary) as destination_connection:
            source_connection.backup(destination_connection)
            result = destination_connection.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        temporary.unlink(missing_ok=True)
        raise RuntimeError("The copied SQLite database failed integrity_check.")
    temporary.replace(destination)
    destination.chmod(0o600)


def write_env(path: Path, values: dict[str, str]) -> None:
    extra_keys = sorted(key for key in values if key not in ENV_KEYS)
    lines = [
        "# Generated for PythonAnywhere. Keep this file private and out of Git.",
        *[f"{key}={values.get(key, '')}" for key in ENV_KEYS],
        *[f"{key}={values[key]}" for key in extra_keys],
        "",
    ]
    temporary = path.with_suffix(".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.getenv("USER") or getpass.getuser())
    parser.add_argument("--project-dir", type=Path, default=PROJECT_DIR)
    args = parser.parse_args()

    username = args.username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", username):
        raise SystemExit("PythonAnywhere username must contain only letters, numbers, and underscores.")

    project_dir = args.project_dir.expanduser().resolve()
    if not (project_dir / "manage.py").is_file():
        raise SystemExit(f"manage.py was not found in {project_dir}")

    data_root = project_dir / "data"
    static_root = project_dir / "staticfiles"
    media_root = project_dir / "media"
    private_media_root = project_dir / "private_media"
    backup_root = project_dir / "backups"
    for directory in (
        data_root,
        data_root / "cache",
        static_root,
        media_root,
        private_media_root,
        backup_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    target_database = data_root / "db.sqlite3"
    legacy_database = project_dir / "db.sqlite3"
    if legacy_database.is_file() and not target_database.exists():
        sqlite_backup(legacy_database, target_database)
        print(f"Copied the existing SQLite database safely to {target_database}")

    env_path = project_dir / ".env"
    values = read_env(env_path)
    host = f"{username}.pythonanywhere.com"
    values.update(
        {
            "DJANGO_SECRET_KEY": safe_secret(values.get("DJANGO_SECRET_KEY", "")),
            "DEBUG": "False",
            "PYTHONANYWHERE_USERNAME": username,
            "ALLOWED_HOSTS": host,
            "CSRF_TRUSTED_ORIGINS": f"https://{host}",
            "PYTHONANYWHERE_DATA_ROOT": str(data_root),
            "SQLITE_PATH": str(target_database),
            "SQLITE_TIMEOUT": "20",
            # PythonAnywhere's filesystem and the single free worker are safer
            # with the default rollback journal than with WAL.
            "SQLITE_ENABLE_WAL": "False",
            "STATIC_ROOT": str(static_root),
            "MEDIA_ROOT": str(media_root),
            "PRIVATE_MEDIA_ROOT": str(private_media_root),
            "CACHE_BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "CACHE_LOCATION": str(data_root / "cache"),
            "SECURE_SSL_REDIRECT": "True",
            "SECURE_HSTS_SECONDS": values.get("SECURE_HSTS_SECONDS", "3600"),
            "SECURE_HSTS_INCLUDE_SUBDOMAINS": "False",
            "SECURE_HSTS_PRELOAD": "False",
            "LOG_LEVEL": values.get("LOG_LEVEL", "WARNING"),
        }
    )
    values.setdefault("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
    values.setdefault("EMAIL_HOST", "")
    values.setdefault("EMAIL_PORT", "587")
    values.setdefault("EMAIL_HOST_USER", "")
    values.setdefault("EMAIL_HOST_PASSWORD", "")
    values.setdefault("EMAIL_USE_TLS", "True")
    values.setdefault("EMAIL_TIMEOUT", "10")
    values.setdefault("DEFAULT_FROM_EMAIL", f"noreply@{host}")
    write_env(env_path, values)
    print(f"Configured {env_path} for https://{host} (secret value not displayed).")


if __name__ == "__main__":
    main()
