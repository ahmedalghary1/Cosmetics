"""Safe defaults for running the project on a local development server."""

import os


# Set these before importing the shared settings so a machine-level production
# environment cannot make Django's HTTP development server redirect to HTTPS.
os.environ["DEBUG"] = "True"
os.environ["SECURE_SSL_REDIRECT"] = "False"

from .settings import *  # noqa: E402,F401,F403


DEBUG = True
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
