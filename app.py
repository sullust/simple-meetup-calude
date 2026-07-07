import sqlite3
from datetime import date
from pathlib import Path

from flask import Flask, abort, g, redirect, render_template, request, url_for

DB_PATH = Path(__file__).parent / "meetups.db"

app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
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
        CREATE TABLE IF NOT EXISTS meetups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            details TEXT,
            event_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rsvps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meetup_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meetup_id) REFERENCES meetups (id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


@app.route("/")
def index():
    db = get_db()
    # Purge meetups from before today so the table doesn't grow forever.
    db.execute("DELETE FROM meetups WHERE event_date < ?", (date.today().isoformat(),))
    db.commit()

    meetups = db.execute(
        """
        SELECT meetups.*, COUNT(rsvps.id) AS rsvp_count
        FROM meetups
        LEFT JOIN rsvps ON rsvps.meetup_id = meetups.id
        WHERE event_date >= ?
        GROUP BY meetups.id
        ORDER BY event_date ASC
        """,
        (date.today().isoformat(),),
    ).fetchall()
    return render_template("index.html", meetups=meetups)


@app.route("/new", methods=["GET", "POST"])
def new_meetup():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        details = request.form.get("details", "").strip()
        event_date = request.form.get("event_date", "").strip()

        errors = []
        if not title:
            errors.append("Title is required.")
        if not event_date:
            errors.append("Date is required.")
        else:
            try:
                date.fromisoformat(event_date)
            except ValueError:
                errors.append("Date must be a valid date.")

        if errors:
            return render_template(
                "new.html", errors=errors, title=title, details=details, event_date=event_date
            )

        db = get_db()
        db.execute(
            "INSERT INTO meetups (title, details, event_date) VALUES (?, ?, ?)",
            (title, details, event_date),
        )
        db.commit()
        return redirect(url_for("index"))

    return render_template("new.html", errors=None, title="", details="", event_date="")


@app.route("/delete/<int:meetup_id>", methods=["POST"])
def delete_meetup(meetup_id):
    db = get_db()
    db.execute("DELETE FROM meetups WHERE id = ?", (meetup_id,))
    db.commit()
    return redirect(url_for("index"))


@app.route("/meetup/<int:meetup_id>")
def meetup_detail(meetup_id):
    db = get_db()
    meetup = db.execute("SELECT * FROM meetups WHERE id = ?", (meetup_id,)).fetchone()
    if meetup is None:
        abort(404)

    rsvps = db.execute(
        "SELECT * FROM rsvps WHERE meetup_id = ? ORDER BY created_at ASC", (meetup_id,)
    ).fetchall()
    return render_template("meetup.html", meetup=meetup, rsvps=rsvps, error=None)


@app.route("/meetup/<int:meetup_id>/rsvp", methods=["POST"])
def add_rsvp(meetup_id):
    db = get_db()
    meetup = db.execute("SELECT * FROM meetups WHERE id = ?", (meetup_id,)).fetchone()
    if meetup is None:
        abort(404)

    name = request.form.get("name", "").strip()
    if not name:
        rsvps = db.execute(
            "SELECT * FROM rsvps WHERE meetup_id = ? ORDER BY created_at ASC", (meetup_id,)
        ).fetchall()
        return render_template(
            "meetup.html", meetup=meetup, rsvps=rsvps, error="Name is required."
        )

    db.execute("INSERT INTO rsvps (meetup_id, name) VALUES (?, ?)", (meetup_id, name))
    db.commit()
    return redirect(url_for("meetup_detail", meetup_id=meetup_id))


@app.route("/meetup/<int:meetup_id>/rsvp/<int:rsvp_id>/delete", methods=["POST"])
def delete_rsvp(meetup_id, rsvp_id):
    db = get_db()
    db.execute("DELETE FROM rsvps WHERE id = ? AND meetup_id = ?", (rsvp_id, meetup_id))
    db.commit()
    return redirect(url_for("meetup_detail", meetup_id=meetup_id))


init_db()

if __name__ == "__main__":
    import os

    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
