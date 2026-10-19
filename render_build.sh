#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Run migrations and collect static files
python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Optionally seed realistic organization sample data (set SEED_DEMO_DATA=1 in environment)
if [ "$SEED_DEMO_DATA" = "1" ] || [ "$SEED_DEMO_DATA" = "true" ]; then
  echo "Seeding sample data..."
  python manage.py seed_sample_data
fi

