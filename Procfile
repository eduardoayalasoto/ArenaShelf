web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py run_library_worker &  gunicorn bookshelf.wsgi:application --bind 0.0.0.0:$PORT
