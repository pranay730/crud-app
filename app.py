import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import click
from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY"),
    ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD"),
    DATABASE=os.environ.get("EVENT_DB", str(Path(app.instance_path) / "events.sqlite3")),
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=64 * 1024,
)

CAMPUS_TIME = ZoneInfo("America/Indiana/Indianapolis")
CATEGORIES = ("Arts", "Career", "Clubs", "Food", "Sports", "Wellness", "Other")
FIELDS = ("title", "starts_at", "location", "category", "description", "source_url")


def db():
    if "db" not in g:
        path = Path(app.config["DATABASE"])
        path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                location TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_key TEXT UNIQUE,
                published INTEGER NOT NULL DEFAULT 0 CHECK (published IN (0, 1))
            )
        """)
    return g.db


@app.teardown_appcontext
def close_db(_error):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


@app.template_filter()
def campus_date(value):
    return datetime.fromisoformat(value).strftime("%a, %b %d · %I:%M %p")


def event_values(data):
    values = {}
    limits = dict(zip(FIELDS, (120, 32, 160, 30, 3000, 2048)))
    for field in FIELDS:
        value = data.get(field, "")
        if not isinstance(value, str) or len(value.strip()) > limits[field]:
            raise ValueError(f"Invalid or too long: {field.replace('_', ' ')}.")
        values[field] = value.strip()
    if not values["title"] or not values["location"]:
        raise ValueError("Enter an event title and location.")
    try:
        starts = datetime.fromisoformat(values["starts_at"])
        if starts.tzinfo is not None or "T" not in values["starts_at"]:
            raise ValueError
    except ValueError:
        raise ValueError("Enter a date and time in Purdue campus time.") from None
    values["starts_at"] = starts.isoformat(timespec="minutes")
    if values["category"] not in CATEGORIES:
        raise ValueError("Choose a category.")
    if values["source_url"]:
        try:
            source = urlsplit(values["source_url"])
            if source.scheme not in ("http", "https") or not source.hostname or source.username:
                raise ValueError
        except ValueError:
            raise ValueError("Enter a valid HTTP or HTTPS source URL.") from None
    return values


INSERT_EVENT = """
    INSERT INTO events (title, starts_at, location, category, description, source_url, source_key)
    VALUES (:title, :starts_at, :location, :category, :description, :source_url, :source_key)
"""


@app.get("/")
def index():
    now = datetime.now(CAMPUS_TIME)
    today = now.date().isoformat()
    query = request.args.get("q", "").strip()[:120]
    category = request.args.get("category", "")
    day = request.args.get("day", "")
    events = db().execute(
        "SELECT * FROM events WHERE published = 1 AND starts_at >= ? ORDER BY starts_at, id",
        (today,),
    ).fetchall()
    events = [
        event for event in events
        if (not category or event["category"] == category)
        and (day != "today" or event["starts_at"].startswith(today))
        and query.casefold() in " ".join(
            event[field] for field in ("title", "location", "description", "category")
        ).casefold()
    ]
    return render_template(
        "index.html", events=events, categories=CATEGORIES, query=query,
        category=category, day=day, campus_day=now.strftime("%A, %B %d"),
    )


@app.context_processor
def template_helpers():
    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    return {"csrf_token": csrf_token}


@app.before_request
def guard_admin():
    if not request.path.startswith("/admin"):
        return
    if not app.secret_key or not app.config["ADMIN_PASSWORD"]:
        return render_template("login.html", unavailable=True), 503
    if request.endpoint != "login" and not session.get("admin"):
        return redirect(url_for("login"), code=303)
    if request.method == "POST":
        token = session.get("csrf")
        submitted = request.form.get("csrf", "")
        if not token or not hmac.compare_digest(token.encode(), submitted.encode()):
            abort(400)


@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if hmac.compare_digest(password.encode(), app.config["ADMIN_PASSWORD"].encode()):
            session.clear()
            session["admin"] = True
            return redirect(url_for("admin"), code=303)
        return render_template("login.html", error="Incorrect password."), 401
    return render_template("login.html")


@app.post("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("index"), code=303)


@app.get("/admin")
def admin():
    events = db().execute("SELECT * FROM events ORDER BY published, starts_at, id").fetchall()
    return render_template("admin.html", events=events)


def get_event(event_id):
    event = db().execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        abort(404)
    return event


@app.route("/admin/events/new", methods=["GET", "POST"])
@app.route("/admin/events/<int:event_id>", methods=["GET", "POST"])
def edit_event(event_id=None):
    event = get_event(event_id) if event_id is not None else None
    if request.method == "POST":
        try:
            values = event_values(request.form)
        except ValueError as error:
            return render_template(
                "edit.html", event=event, values=request.form, categories=CATEGORIES, error=error,
            ), 400
        connection = db()
        with connection:
            if event is None:
                cursor = connection.execute(INSERT_EVENT, dict(values, source_key=None))
                event_id = cursor.lastrowid
            else:
                connection.execute("""
                    UPDATE events SET title=:title, starts_at=:starts_at, location=:location,
                        category=:category, description=:description, source_url=:source_url
                    WHERE id=:id
                """, dict(values, id=event_id))
        flash("Event saved.")
        return redirect(url_for("edit_event", event_id=event_id), code=303)
    return render_template(
        "edit.html", event=event, values=event or {}, categories=CATEGORIES,
    )


@app.post("/admin/events/<int:event_id>/<action>")
def change_event(event_id, action):
    get_event(event_id)
    connection = db()
    with connection:
        if action == "delete":
            connection.execute("DELETE FROM events WHERE id = ?", (event_id,))
            flash("Event deleted.")
            return redirect(url_for("admin"), code=303)
        if action not in ("publish", "unpublish"):
            abort(404)
        connection.execute(
            "UPDATE events SET published = ? WHERE id = ?", (int(action == "publish"), event_id),
        )
    flash("Event published." if action == "publish" else "Event moved back to drafts.")
    return redirect(url_for("edit_event", event_id=event_id), code=303)


@app.cli.command("import-events")
@click.argument("file", type=click.File("r", encoding="utf-8"))
def import_events(file):
    """Import a JSON list of normalized events into the review queue."""
    try:
        items = json.load(file)
        if not isinstance(items, list):
            raise ValueError("Expected a JSON list of events.")
        entries = []
        for index, item in enumerate(items, start=1):
            try:
                if not isinstance(item, dict):
                    raise ValueError("Expected an event object.")
                key = item.get("source_key")
                if not isinstance(key, str) or not key.strip() or len(key) > 300:
                    raise ValueError("Provide a stable source_key of at most 300 characters.")
                entries.append(dict(event_values(item), source_key=key.strip()))
            except ValueError as error:
                raise ValueError(f"Event {index}: {error}") from error
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    connection = db()
    with connection:
        result = connection.executemany(
            INSERT_EVENT + " ON CONFLICT(source_key) DO NOTHING", entries,
        )
    click.echo(f"Imported {result.rowcount} drafts. Skipped {len(entries) - result.rowcount} duplicates.")
