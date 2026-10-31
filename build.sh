#!/usr/bin/env bash
# Build do Render. O JS já vem pronto em static/js (commitado), então não usa Node.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
