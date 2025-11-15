celery -A configs.celery_utils.celery worker -P eventlet -c 1 --loglevel=debug
celery -A configs.celery_utils.celery flower --port=5555 --address=0.0.0.0 --basic_auth=admin:admin