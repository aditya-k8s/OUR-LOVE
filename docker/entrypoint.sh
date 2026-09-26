#!/bin/sh
# Prepare the database and indexes, then hand over to the main process.
set -e

python manage.py migrate --noinput
python manage.py ensure_indexes || echo "Warning: could not create MongoDB indexes (check MONGODB_URI and Atlas network access)."

if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python manage.py createadmin --no-input
fi

exec "$@"
