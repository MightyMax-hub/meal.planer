# Supper Club

A small Flask and SQLite recipe manager with date-range meal planning, shareable plan links, and recipe-based shopping lists.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the app with `python app.py` and open `http://127.0.0.1:5000`.

The SQLite database is created automatically in `data/`. For a public deployment, set a private `SECRET_KEY` in the environment and run behind a production WSGI server.