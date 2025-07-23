from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "conversations" (
    "conversation_id" VARCHAR(64) NOT NULL PRIMARY KEY,
    "user_id" INT NOT NULL,
    "title" VARCHAR(255) NOT NULL DEFAULT '新会话',
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "geometry_results" (
    "geometry_id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "task_id" INT NOT NULL,
    "cad_file_path" TEXT,
    "code_file_path" TEXT,
    "preview_image_path" TEXT,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "optimization_results" (
    "optimization_id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "task_id" INT NOT NULL,
    "optimized_cad_file_path" TEXT,
    "best_params" JSON,
    "final_volume" REAL,
    "final_stress" REAL,
    "constraint_satisfied" INT,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "tasks" (
    "task_id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "conversation_id" VARCHAR(64) NOT NULL,
    "user_id" INT NOT NULL,
    "task_type" VARCHAR(10) NOT NULL,
    "status" VARCHAR(10) NOT NULL DEFAULT 'pending',
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "users" (
    "user_id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "email" VARCHAR(255) NOT NULL UNIQUE,
    "password_hash" VARCHAR(255) NOT NULL,
    "created_at" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSON NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
