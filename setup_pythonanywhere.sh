#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/local/bin/python3.13}"
VENV_DIR="${VENV_DIR:-${HOME}/.virtualenvs/cosmetics}"
PA_USERNAME="${PA_USERNAME:-${USER}}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Python 3.13 was not found at ${PYTHON_BIN}. Set PYTHON_BIN to the version selected for your Web app."
    exit 1
fi

"${PYTHON_BIN}" "${PROJECT_DIR}/scripts/configure_pythonanywhere.py" \
    --username "${PA_USERNAME}" \
    --project-dir "${PROJECT_DIR}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${PROJECT_DIR}/requirements.txt"

cd "${PROJECT_DIR}"
DJANGO_SETTINGS_MODULE=config.settings_pythonanywhere "${VENV_DIR}/bin/python" manage.py migrate --noinput
DJANGO_SETTINGS_MODULE=config.settings_pythonanywhere "${VENV_DIR}/bin/python" manage.py setup_roles
DJANGO_SETTINGS_MODULE=config.settings_pythonanywhere "${VENV_DIR}/bin/python" manage.py collectstatic --noinput
DJANGO_SETTINGS_MODULE=config.settings_pythonanywhere "${VENV_DIR}/bin/python" manage.py check --deploy
DJANGO_SETTINGS_MODULE=config.settings_pythonanywhere "${VENV_DIR}/bin/python" manage.py backup_database \
    --output-dir "${PROJECT_DIR}/backups" --keep 3

echo
echo "PythonAnywhere preparation completed."
echo "Virtualenv: ${VENV_DIR}"
echo "Static mapping: /static/ -> ${PROJECT_DIR}/staticfiles"
echo "Media mapping:  /media/  -> ${PROJECT_DIR}/media"
echo "Do not create a mapping for ${PROJECT_DIR}/private_media"
echo "Copy ${PROJECT_DIR}/pythonanywhere_wsgi.py into the WSGI file in the Web tab, then Reload."
