
import sqlite3
from pathlib import Path

# Путь к базе данных
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "studio.db"


def initialize_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")

        # Таблица проектов
        connection.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                genre TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица коллекций
        connection.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id)
                    REFERENCES projects(id)
            )
        """)

        # Таблица предметов коллекции
        connection.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                composition_category INTEGER,
                environment TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (collection_id)
                    REFERENCES collections(id),
                UNIQUE (collection_id, position),
                CHECK (position BETWEEN 1 AND 10),
                CHECK (
                    composition_category IS NULL
                    OR composition_category BETWEEN 1 AND 4
                )
            )
        """)

        # Таблица изображений
        connection.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (card_id)
                    REFERENCES cards(id)
            )
        """)

        # Таблица промптов
        connection.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                prompt_text TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (card_id)
                    REFERENCES cards(id)
            )
        """)

        connection.commit()

    print("База данных успешно инициализирована!")
    print(f"Путь: {DB_PATH}")


if __name__ == "__main__":
    initialize_database()
