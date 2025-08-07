# tortoise_config.py

TORTOISE_ORM_sqlite = {
   
   
    "connections": {
   
   "default": "sqlite://db.sqlite3"},
    "apps": {
   
   
        "models": {
   
   
            "models": ["database.models_1","aerich.models"],
            "default_connection": "default",
        },
    },
}

TORTOISE_ORM_mysql = {
    'connections': {
        'default': {
            # 'engine': 'tortoise.backends.asyncpg',  PostgreSQL
            'engine': 'tortoise.backends.mysql',  # MySQL or Mariadb
            'credentials': {
                # 'host': "240e:3bc:266:b4d0:8ed2:275a:f1a9:7b4d",#'cautod.ssvgg.asia',
                'host': "240e:3bc:266:b4d0:8ed2:275a:f1a9:7b4d",
                'port': '3306',
                'user': 'lwx',
                'password':'i4AIi4AI',
                'database': 'cautod',
                'minsize': 1,
                'maxsize': 5,
                'charset': 'utf8mb4',
                "echo": True
            }
        },
    },
    'apps': {
        'models': {
            'models': ["database.models_1", "aerich.models"],
            'default_connection': 'default',

        }
    },
    'use_tz': False,
    'timezone': 'Asia/Shanghai'
}