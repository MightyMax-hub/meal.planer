import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "essensplaner.sqlite3"
RECIPE_IMAGE_DIR = DATA_DIR / "recipe_images"
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-key-before-deploying")