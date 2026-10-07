import secrets
from datetime import date, timedelta

from flask import Blueprint, abort, redirect, render_template, request, url_for

from database.database import database


plans = Blueprint("plans", __name__)


def date_range(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def load_recipes(connection):
    return connection.execute(
        "SELECT id, name FROM recipes ORDER BY name COLLATE NOCASE"
    ).fetchall()


def shopping_items(connection, quantities):
    recipe_ids = list(quantities)
    if not recipe_ids:
        return []
    placeholders = ",".join("?" for _ in recipe_ids)
    rows = connection.execute(
        f"""
        SELECT i.name, i.amount, i.unit, r.name AS recipe_name, r.id AS recipe_id
        FROM ingredients i JOIN recipes r ON r.id = i.recipe_id
        WHERE i.recipe_id IN ({placeholders})
        ORDER BY i.name COLLATE NOCASE
        """,
        recipe_ids,
    ).fetchall()
    grouped = {}
    for item in rows:
        key_name = item["name"].strip().casefold()
        if key_name.endswith("ies") and len(key_name) > 4:
            key_name = key_name[:-3] + "y"
        elif key_name.endswith(("ches", "shes", "xes", "zes", "oes")):
            key_name = key_name[:-2]
        elif key_name.endswith("s") and not key_name.endswith("ss"):
            key_name = key_name[:-1]
        key = (key_name, item["unit"].strip().casefold())
        if key not in grouped:
            grouped[key] = {
                "name": item["name"].strip(), "amount": 0.0,
                "unit": item["unit"].strip(), "recipes": [],
            }
        grouped[key]["amount"] += item["amount"] * quantities[item["recipe_id"]]
        if item["recipe_name"] not in grouped[key]["recipes"]:
            grouped[key]["recipes"].append(item["recipe_name"])
    return sorted(grouped.values(), key=lambda item: item["name"].casefold())


@plans.route("/plans/new", methods=["GET", "POST"])
def new_plan():
    today = date.today()
    error = None
    if request.method == "POST":
        try:
            start_date = date.fromisoformat(request.form["start_date"])
            end_date = date.fromisoformat(request.form["end_date"])
            if end_date < start_date:
                raise ValueError
            if (end_date - start_date).days > 59:
                error = "Choose a period of 60 days or fewer."
            else:
                token = secrets.token_urlsafe(6)
                with database() as connection:
                    connection.execute(
                        "INSERT INTO meal_plans (token, start_date, end_date) VALUES (?, ?, ?)",
                        (token, start_date.isoformat(), end_date.isoformat()),
                    )
                return redirect(url_for("plans.edit_plan", token=token))
        except (KeyError, ValueError):
            error = "Enter a valid start and end date."
    with database() as connection:
        recipe_count = connection.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
        existing_plans = connection.execute(
            """
            SELECT p.token, p.start_date, p.end_date, COUNT(pr.recipe_id) AS meal_count
            FROM meal_plans p
            LEFT JOIN planned_recipes pr ON pr.plan_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC, p.id DESC
            """
        ).fetchall()
    return render_template(
        "plan_form.html", today=today.isoformat(), tomorrow=(today + timedelta(days=6)).isoformat(),
        recipe_count=recipe_count, existing_plans=existing_plans, error=error,
    )


@plans.route("/p/<token>")
def view_plan(token):
    return render_plan(token, editable=False)


@plans.route("/p/<token>/edit", methods=["GET", "POST"])
def edit_plan(token):
    return render_plan(token, editable=True)


def render_plan(token, editable):
    with database() as connection:
        plan = connection.execute(
            "SELECT * FROM meal_plans WHERE token = ?", (token,)
        ).fetchone()
        if plan is None:
            abort(404)
        start_date = date.fromisoformat(plan["start_date"])
        end_date = date.fromisoformat(plan["end_date"])
        days = list(date_range(start_date, end_date))
        if editable and request.method == "POST":
            connection.execute("DELETE FROM planned_recipes WHERE plan_id = ?", (plan["id"],))
            valid_ids = {str(recipe["id"]) for recipe in load_recipes(connection)}
            assignments = []
            for meal_day in days:
                field_name = f"recipes_{meal_day.isoformat()}"
                for recipe_id in request.form.getlist(field_name):
                    if recipe_id in valid_ids:
                        assignments.append((plan["id"], meal_day.isoformat(), int(recipe_id)))
            connection.executemany(
                "INSERT OR IGNORE INTO planned_recipes (plan_id, plan_date, recipe_id) VALUES (?, ?, ?)",
                assignments,
            )
            return redirect(url_for("plans.view_plan", token=token))

        recipes = load_recipes(connection)
        assignments = connection.execute(
            """
            SELECT pr.plan_date, r.id, r.name
            FROM planned_recipes pr JOIN recipes r ON r.id = pr.recipe_id
            WHERE pr.plan_id = ? ORDER BY r.name COLLATE NOCASE
            """,
            (plan["id"],),
        ).fetchall()
        recipes_by_day = {}
        for assignment in assignments:
            recipes_by_day.setdefault(assignment["plan_date"], []).append(assignment)
        day_rows = [
            {"date": meal_day, "recipes": recipes_by_day.get(meal_day.isoformat(), [])}
            for meal_day in days
        ]
    return render_template(
        "plan_detail.html", plan=plan, days=day_rows, recipes=recipes, editable=editable
    )


@plans.route("/p/<token>/delete", methods=["POST"])
def delete_plan(token):
    with database() as connection:
        plan = connection.execute(
            "SELECT id FROM meal_plans WHERE token = ?", (token,)
        ).fetchone()
        if plan is None:
            abort(404)
        connection.execute("DELETE FROM meal_plans WHERE token = ?", (token,))
    return redirect(url_for("main.dashboard"))


@plans.route("/shopping", methods=["GET", "POST"])
def shopping_list():
    selected = []
    items = []
    with database() as connection:
        recipes = load_recipes(connection)
        if request.method == "POST":
            recipe_ids = request.form.getlist("recipe_id")
            multipliers = request.form.getlist("multiplier")
            quantities = {}
            valid_ids = {str(recipe["id"]) for recipe in recipes}
            for recipe_id, multiplier in zip(recipe_ids, multipliers):
                if recipe_id not in valid_ids:
                    continue
                try:
                    multiplier = float(multiplier)
                except ValueError:
                    continue
                if 0 < multiplier <= 100:
                    recipe_id = int(recipe_id)
                    quantities[recipe_id] = quantities.get(recipe_id, 0) + multiplier
                    selected.append({"id": recipe_id, "multiplier": multiplier})
            items = shopping_items(connection, quantities)
    return render_template("shopping_list.html", recipes=recipes, selected=selected, items=items)


@plans.route("/p/<token>/shopping")
def plan_shopping_list(token):
    with database() as connection:
        plan = connection.execute("SELECT * FROM meal_plans WHERE token = ?", (token,)).fetchone()
        if plan is None:
            abort(404)
        recipe_ids = connection.execute(
            "SELECT recipe_id FROM planned_recipes WHERE plan_id = ?", (plan["id"],)
        ).fetchall()
        quantities = {}
        for row in recipe_ids:
            quantities[row["recipe_id"]] = quantities.get(row["recipe_id"], 0) + 1
        items = shopping_items(connection, quantities)
    return render_template("plan_shopping.html", plan=plan, items=items)