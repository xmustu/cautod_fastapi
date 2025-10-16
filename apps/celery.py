from celery import Celery
from configs.celery_config import settings

# def create_celery():
#     celery_app = Celery("cautod",broker_url = 'pyamqp://admin:admin@localhost:5672//',result_backend = 'redis://')
#     # 1. 先从 settings（config/celery_config.py）加载配置
#     celery_app.config_from_object(settings, namespace='CELERY')
#     # 2. 再从 celeryconfig.py（根目录或config目录）加载配置，允许覆盖
#     celery_app.config_from_object("configs.celeryconfig", namespace=None, silent=True)
#     return celery_app

# celery_app = create_celery()
# print("Celery configured:", celery_app.conf)

celery_app = Celery("cautod",broker_url = 'pyamqp://admin:admin@localhost:5672//',result_backend = 'redis://')