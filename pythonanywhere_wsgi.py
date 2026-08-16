"""Copy this file's contents into the WSGI file shown in the Web tab."""

import os
import sys
from pathlib import Path


project_home = Path.home() / "Cosmetics"
if not (project_home / "manage.py").is_file():
    raise RuntimeError(
        f"Django project not found at {project_home}. "
        "Upload/clone it there or update project_home in this WSGI file."
    )

project_path = str(project_home)
if project_path not in sys.path:
    sys.path.insert(0, project_path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_pythonanywhere")

from django.core.wsgi import get_wsgi_application


application = get_wsgi_application()
