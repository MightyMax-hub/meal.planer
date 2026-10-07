import sqlite3
from contextlib import contextmanager

from config import DATA_DIR, DATABASE_PATH


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database():
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database():
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                image_filename TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS meal_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS planned_recipes (
                plan_id INTEGER NOT NULL,
                plan_date TEXT NOT NULL,
                recipe_id INTEGER NOT NULL,
                PRIMARY KEY (plan_id, plan_date, recipe_id),
                FOREIGN KEY (plan_id) REFERENCES meal_plans(id) ON DELETE CASCADE,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_ingredients_recipe
                ON ingredients(recipe_id);
            CREATE INDEX IF NOT EXISTS idx_planned_recipes_date
                ON planned_recipes(plan_id, plan_date);
            """
        )
        recipe_columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(recipes)").fetchall()
        }
        if "image_filename" not in recipe_columns:
            connection.execute("ALTER TABLE recipes ADD COLUMN image_filename TEXT")