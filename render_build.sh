#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Run migrations and collect static files
python manage.py collectstatic --no-input
python manage.py migrate --no-input
