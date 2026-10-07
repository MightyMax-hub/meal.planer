import random
import uuid
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, send_from_directory, url_for

from config import RECIPE_IMAGE_DIR
from database.database import database


main = Blueprint("main", __name__)
IMAGE_MIME_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def image_upload_error(upload):
    if upload is None or not upload.filename:
        return None
    extension = Path(upload.filename).suffix.lower()
    if extension not in IMAGE_MIME_TYPES:
        return "Choose a PNG, JPEG, GIF, or WebP image."
    signature = upload.stream.read(12)
    upload.stream.seek(0)
    valid_signatures = {
        ".gif": signature.startswith((b"GIF87a", b"GIF89a")),
        ".jpeg": signature.startswith(b"\xff\xd8\xff"),
        ".jpg": signature.startswith(b"\xff\xd8\xff"),
        ".png": signature.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": signature.startswith(b"RIFF") and signature[8:12] == b"WEBP",
    }
    if not valid_signatures[extension]:
        return "The uploaded file is not a valid image of that type."
    return None


def save_recipe_image(upload):
    extension = Path(upload.filename).suffix.lower()
    filename = f"{uuid.uuid4().hex}{extension}"
    RECIPE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        upload.save(RECIPE_IMAGE_DIR / filename)
    except Exception:
        remove_recipe_image(filename)
        raise
    return filename


def remove_recipe_image(filename):
    if not filename or Path(filename).name != filename:
        return
    image_path = RECIPE_IMAGE_DIR / filename
    if image_path.is_file():
        image_path.unlink()


def read_ingredients(form):
    ingredients = []
    names = form.getlist("ingredient_name")
    amounts = form.getlist("ingredient_amount")
    units = form.getlist("ingredient_unit")
    for name, amount, unit in zip(names, amounts, units):
        name = name.strip()
        if not name:
            continue
        try:
            amount = float(amount)
        except ValueError:
            continue
        if amount > 0:
            ingredients.append({"name": name, "amount": amount, "unit": unit.strip()})
    return ingredients


@main.route("/")
def dashboard():
    with database() as connection:
        recipes = connection.execute(
            "SELECT id, name FROM recipes ORDER BY name COLLATE NOCASE"
        ).fetchall()
        recipe_count = len(recipes)
        featured_recipe = random.choice(recipes) if recipes else None
        upcoming = connection.execute(
            """
            SELECT p.token, p.start_date, p.end_date, COUNT(pr.recipe_id) AS meal_count
            FROM meal_plans p
            LEFT JOIN planned_recipes pr ON pr.plan_id = p.id
            WHERE p.end_date >= date('now', 'localtime')
            GROUP BY p.id
            ORDER BY p.start_date
            LIMIT 3
            """
        ).fetchall()
    return render_template(
        "dashboard.html",
        recipe_count=recipe_count,
        featured_recipe=featured_recipe,
        upcoming=upcoming,
    )


@main.route("/recipes")
def recipe_list():
    with database() as connection:
        recipes = connection.execute(
            """
            SELECT r.id, r.name, r.notes, COUNT(i.id) AS ingredient_count
            FROM recipes r LEFT JOIN ingredients i ON i.recipe_id = r.id
            GROUP BY r.id ORDER BY r.name COLLATE NOCASE
            """
        ).fetchall()
    return render_template("recipes.html", recipes=recipes)


@main.route("/recipes/new", methods=["GET", "POST"])
def new_recipe():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        ingredients = read_ingredients(request.form)
        notes = request.form.get("notes", "").strip()
        image = request.files.get("image")
        error = image_upload_error(image)
        if not name:
            error = "Give this recipe a name."
        if error:
            return render_template(
                "recipe_form.html", recipe=None, ingredients=ingredients,
                error=error,
            ), 400
        saved_image = None
        try:
            with database() as connection:
                cursor = connection.execute(
                    "INSERT INTO recipes (name, notes) VALUES (?, ?)", (name, notes)
                )
                recipe_id = cursor.lastrowid
                if image and image.filename:
                    saved_image = save_recipe_image(image)
                    connection.execute(
                        "UPDATE recipes SET image_filename = ? WHERE id = ?",
                        (saved_image, recipe_id),
                    )
                connection.executemany(
                    "INSERT INTO ingredients (recipe_id, name, amount, unit) VALUES (?, ?, ?, ?)",
                    [(recipe_id, item["name"], item["amount"], item["unit"]) for item in ingredients],
                )
        except Exception:
            remove_recipe_image(saved_image)
            raise
        return redirect(url_for("main.recipe_list"))
    return render_template("recipe_form.html", recipe=None, ingredients=[], error=None)


@main.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
def edit_recipe(recipe_id):
    with database() as connection:
        recipe = connection.execute(
            "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
        if recipe is None:
            abort(404)
        ingredients = connection.execute(
            "SELECT name, amount, unit FROM ingredients WHERE recipe_id = ? ORDER BY id",
            (recipe_id,),
        ).fetchall()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        submitted_ingredients = read_ingredients(request.form)
        image = request.files.get("image")
        error = image_upload_error(image)
        if not name:
            error = "Give this recipe a name."
        if error:
            return render_template(
                "recipe_form.html", recipe=recipe, ingredients=submitted_ingredients,
                error=error,
            ), 400
        old_image = recipe["image_filename"]
        new_image = None
        try:
            if image and image.filename:
                new_image = save_recipe_image(image)
            with database() as connection:
                connection.execute(
                    "UPDATE recipes SET name = ?, notes = ?, image_filename = ? WHERE id = ?",
                    (name, request.form.get("notes", "").strip(), new_image or old_image, recipe_id),
                )
                connection.execute("DELETE FROM ingredients WHERE recipe_id = ?", (recipe_id,))
                connection.executemany(
                    "INSERT INTO ingredients (recipe_id, name, amount, unit) VALUES (?, ?, ?, ?)",
                    [(recipe_id, item["name"], item["amount"], item["unit"]) for item in submitted_ingredients],
                )
        except Exception:
            remove_recipe_image(new_image)
            raise
        if new_image:
            remove_recipe_image(old_image)
        return redirect(url_for("main.recipe_list"))
    return render_template("recipe_form.html", recipe=recipe, ingredients=ingredients, error=None)


@main.route("/recipes/<int:recipe_id>")
def view_recipe(recipe_id):
    with database() as connection:
        recipe = connection.execute(
            "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
        if recipe is None:
            abort(404)
        ingredients = connection.execute(
            "SELECT name, amount, unit FROM ingredients WHERE recipe_id = ? ORDER BY id",
            (recipe_id,),
        ).fetchall()
    return render_template("recipe_detail.html", recipe=recipe, ingredients=ingredients)


@main.route("/recipes/<int:recipe_id>/image")
def recipe_image(recipe_id):
    with database() as connection:
        recipe = connection.execute(
            "SELECT image_filename FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
    if recipe is None or not recipe["image_filename"]:
        abort(404)
    extension = Path(recipe["image_filename"]).suffix.lower()
    response = send_from_directory(
        RECIPE_IMAGE_DIR,
        recipe["image_filename"],
        mimetype=IMAGE_MIME_TYPES.get(extension),
        conditional=True,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@main.route("/recipes/<int:recipe_id>/delete", methods=["POST"])
def delete_recipe(recipe_id):
    with database() as connection:
        recipe = connection.execute(
            "SELECT id, image_filename FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
        if recipe is None:
            abort(404)
        connection.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    remove_recipe_image(recipe["image_filename"])
    return redirect(url_for("main.recipe_list"))