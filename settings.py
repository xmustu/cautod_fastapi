# tortoise_config.py

TORTOISE_ORM_sqlite = {
   
   
    "connections": {
   
   "default": "sqlite://db.sqlite3"},
    "apps": {
   
   
        "models": {
   
   
            "models": ["database.models_1", "aerich.models"],
            "default_connection": "default",
        },
    },
}