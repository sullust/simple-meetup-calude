import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, url_for

DB_PATH = Path(__file__).parent / "moods.db"

app = Flask(__name__)

MOODS = [
    {"key": "very_sad", "emoji": "😢", "label": "Very sad"},
    {"key": "kinda_sad", "emoji": "🙁", "label": "Kinda sad"},
    {"key": "neutral", "emoji": "😐", "label": "Neutral"},
    {"key": "kinda_happy", "emoji": "🙂", "label": "Kinda happy"},
    {"key": "very_happy", "emoji": "😄", "label": "Very happy"},
]
MOODS_BY_KEY = {m["key"]: m for m in MOODS}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity TEXT NOT NULL,
            mood TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


@app.template_filter("mood_info")
def mood_info(mood_key):
    return MOODS_BY_KEY.get(mood_key, {"emoji": "?", "label": mood_key})


@app.template_filter("format_dt")
def format_dt(iso_string):
    return datetime.fromisoformat(iso_string).strftime("%b %d, %Y %I:%M %p")


@app.route("/")
def index():
    db = get_db()
    entries = db.execute(
        "SELECT * FROM entries ORDER BY created_at DESC, id DESC"
    ).fetchall()
    saved = request.args.get("saved") == "1"
    return render_template("index.html", entries=entries, moods=MOODS, saved=saved)


@app.route("/log", methods=["POST"])
def log_entry():
    activity = request.form.get("activity", "").strip()
    mood = request.form.get("mood", "").strip()

    if mood not in MOODS_BY_KEY:
        return redirect(url_for("index"))

    db = get_db()
    db.execute(
        "INSERT INTO entries (activity, mood, created_at) VALUES (?, ?, ?)",
        (activity, mood, datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    return redirect(url_for("index", saved=1))


@app.route("/delete/<int:entry_id>", methods=["POST"])
def delete_entry(entry_id):
    db = get_db()
    db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    db.commit()
    return redirect(url_for("index"))


init_db()

if __name__ == "__main__":
    import os

    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
