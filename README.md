# Boiler Bulletin

A Purdue West Lafayette event directory and an editorial desk for the person curating it. Students can browse and filter approved events without signing in. The event desk accepts manual submissions through a reusable HTML form and supports editing, publishing, unpublishing, and deleting events. Each saved event also has an editable caption to copy into Instagram.

## Run locally

Requires Python 3.9 or newer.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -c 'import secrets; print(secrets.token_urlsafe(18))'
export ADMIN_PASSWORD='paste the generated password here'
flask --app app run
```

Open http://127.0.0.1:5000 for the student feed and http://127.0.0.1:5000/admin for the event desk. To try the full workflow, sign in, create a future event, save it as a draft, then publish the saved event. The SQLite file is created under `instance/`. Set `EVENT_DB` to use another file.

## Import drafts

Source integrations can submit normalized event records through the CLI. Instagram and Facebook collection and automatic posting are outside this first build.

```sh
flask --app app import-events path/to/events.json
```

The file is an array of records, for example:

```json
[
  {
    "source_key": "campus-calendar:example-event",
    "title": "Student organization fair",
    "starts_at": "2027-01-15T16:00",
    "location": "Purdue Memorial Union",
    "category": "Clubs",
    "description": "An example event for testing the review workflow.",
    "source_url": ""
  }
]
```

Use campus-local time and a stable, source-qualified key. Reimporting an existing key preserves the editor's saved changes. Imports start as drafts and go through the same review workflow as manually entered events.

## Architecture

Flask renders Jinja templates and stores events in SQLite. The student feed only queries published events. The password-gated event desk uses signed sessions and checks CSRF tokens for every form submission. Both the HTML form and the importer use the same validation rules. The single-admin setup is intended for local development. A hosted release needs production authentication, HTTPS, and persistent database storage.

Feature branches target `develop`. The release PR targets `main` once the integrated app is ready.

## Try a fictional social event

With the app configured, run `flask --app app import-events examples/mock-social-event.json`.
The fixture simulates a normalized Instagram result. Open the event desk and find
**[Demo] Study Break and Board Games** under **Drafts to review**. Verify the public
feed omits it, then select **Publish saved event** and search the student feed for
**Study Break**. The listing uses the same HTML card as manually entered events.
The event is fictional. If its date has passed, set a future date in the editor
before publishing. Use **Unpublish** to return the event to the review queue.
