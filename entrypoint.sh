#!/bin/sh
set -e

# Wait for PostgreSQL to be ready if configured
if [ "$POSTGRES_HOST" ]; then
    echo "Waiting for PostgreSQL at $POSTGRES_HOST:$POSTGRES_PORT..."
    while ! nc -z "$POSTGRES_HOST" "${POSTGRES_PORT:-5432}" 2>/dev/null && ! python -c "import socket; s = socket.socket(); s.connect(('$POSTGRES_HOST', int('${POSTGRES_PORT:-5432}'))); s.close()" 2>/dev/null; do
        sleep 1
    done
    echo "PostgreSQL is ready!"
fi

# Run database migrations
echo "Applying database schema migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static assets..."
python manage.py collectstatic --noinput --clear || true

exec "$@"
