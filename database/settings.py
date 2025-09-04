# tortoise_config.py

from config import settings

MYSQL_HOST = settings.MYSQL_HOST
MYSQL_PORT = settings.MYSQL_PORT
MYSQL_USER = settings.MYSQL_USER
MYSQL_PASSWORD = settings.MYSQL_PASSWORD
MYSQL_DATABASE = settings.MYSQL_DATABASE

TORTOISE_ORM_SQLITE = {
   
   
    "connections": {
   
   "default": "sqlite://db.sqlite3"},
    "apps": {
   
   
        "models": {
   
   
            "models": ["database.models","aerich.models"],
            "default_connection": "default",
        },
    },
}

TORTOISE_ORM_MYSQL = {
    'connections': {
        'default': {
            # 'engine': 'tortoise.backends.asyncpg',  PostgreSQL
            'engine': 'tortoise.backends.mysql',  # MySQL or Mariadb
            'credentials': {
                # 'host': "240e:3bc:266:b4d0:8ed2:275a:f1a9:7b4d",#'cautod.ssvgg.asia',
                'host': MYSQL_HOST,
                'port': MYSQL_PORT,
                'user': MYSQL_USER,
                'password':MYSQL_PASSWORD,
                'database': MYSQL_DATABASE,
                'minsize': 1,
                'maxsize': 5,
                'charset': 'utf8mb4',
                "echo": True
            }
        },
    },
    'apps': {
        'models': {
            'models': ["database.models", "aerich.models"],
            'default_connection': 'default',

        }
    },
    'use_tz': False,
    'timezone': 'Asia/Shanghai'
}