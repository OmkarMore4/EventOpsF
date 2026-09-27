# EventOps — Real-Time Event Operations & Volunteer Management System

A full-stack web app for running a college/college-society event with a volunteer team:
admins configure the event, geofence and roster; volunteers check in with GPS-verified
attendance, work through assigned tasks, and report issues, all in real time.

Built as a 5th-semester B.Sc. Computer Science mini-project.

**Stack:** Flask (Python) · MongoDB · Tailwind CSS · vanilla JavaScript · Chart.js · Leaflet/OpenStreetMap

---

## Contents

1. [Features](#features)
2. [How geofenced attendance works](#how-geofenced-attendance-works)
3. [Backup QR check-in](#backup-qr-check-in)
4. [Volunteer self-registration](#volunteer-self-registration)
5. [Project structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Setup & installation](#setup--installation)
8. [Demo credentials](#demo-credentials)
9. [Running the automated tests](#running-the-automated-tests)
10. [Deploying to production](#deploying-to-production-render--vercel)
11. [MongoDB collections](#mongodb-collections)
12. [Troubleshooting](#troubleshooting)

---

## Features

### Admin
- Secure login (hashed passwords, session-based auth, rate-limited against brute-force attempts)
- Create and manage multiple events, each with its own venue, dates, volunteer domains, and geofence
- Add, edit and deactivate volunteers; assign them to a domain (Registration, Logistics, etc.)
- **Review and approve/decline volunteer self-registration requests** before they get a working login
- Create tasks, assign them to volunteers, track status and priority
- View **live** daily attendance for the whole team (auto-updates every few seconds), with GPS distance shown per check-in/out, plus a manual override for when a volunteer's GPS isn't cooperating
- Generate a **printable backup QR check-in code** per event, for volunteers whose GPS isn't working (common indoors)
- Configure each event's venue location (via an interactive map, GPS, or typed coordinates) and geofence radius
- Manage an equipment inventory (quantities, condition, who has what)
- Build and edit the event schedule
- View and resolve issues reported by volunteers, with a response visible to the reporter
- A dashboard with live stats, charts (attendance trend, task breakdown, volunteers by domain), and a live activity feed
- Export attendance and task reports as CSV, or a single polished **PDF event report**

### Volunteer
- **Self-registration** — sign up for an open event, then wait for admin approval before logging in
- Secure login
- Profile page with domain, responsibilities, and personal stats
- Mark daily attendance — GPS check-in/out, only accepted inside the event's geofence
- **Backup QR check-in** — scan the venue's printed code if GPS isn't cooperating
- View attendance history (date, times, distance from venue)
- View assigned tasks and update their status (pending → in progress → completed)
- Report event-related issues and see the admin's response
- View the event schedule and admin announcements

---

## How geofenced attendance works

1. **Admin sets the geofence.** When creating/editing an event, the admin places a marker on
   the map (click, drag, or "Use my location") and sets a radius in meters. This is stored as
   a GeoJSON point (`events.location`) plus `events.geofence_radius`.
2. **Volunteer requests a GPS fix.** On the Attendance page, tapping "Check in" calls the
   browser's [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API)
   (`navigator.geolocation.getCurrentPosition`) to read the device's current latitude/longitude.
3. **Client-side pre-check (UX only).** The page instantly estimates the distance to the venue
   in JavaScript and shows it to the volunteer — this is purely informational.
4. **Server-side check (authoritative).** The coordinates are POSTed to Flask, which computes
   the great-circle distance with the **Haversine formula** (`utils/geo.py`) and compares it to
   `geofence_radius`. The client-side estimate is never trusted for the actual decision.
   - **Inside the radius** → attendance is recorded (check-in or check-out, whichever is next).
   - **Outside the radius** → the attempt is rejected with the measured distance shown to the
     volunteer, and logged (without counting as attendance) so the admin can see it.
5. **Everything is stored.** Every accepted check-in/out saves its timestamp, latitude,
   longitude and computed distance. Rejected attempts are kept too (`rejected_attempts`), so
   there's a full audit trail even for failed tries.

Event locations are stored as proper GeoJSON `Point`s with a `2dsphere` index (`seed.py`), so
the data is ready for native MongoDB geospatial queries (`$near`, `$geoWithin`, ...) if you
extend the project — the attendance check itself just uses the direct formula, which is simpler
to reason about and doesn't depend on any particular index existing.

> **Note:** Browsers only expose the Geolocation API on secure contexts — `https://` or
> `http://localhost`. Local development (`http://localhost:5000`) works out of the box; if you
> deploy somewhere without HTTPS, location requests will be blocked by the browser. Render and
> Vercel both serve over HTTPS automatically, so this isn't a concern once deployed.

---

## Backup QR check-in

GPS can be unreliable indoors. Each event has a **Backup QR code** (Admin → Events → QR code,
or the link on the Attendance page): a printable page with a QR code that encodes a URL
containing the event's ID and a random per-event secret.

- A volunteer scans it with their phone's ordinary camera app — no in-app scanner needed.
- It opens a confirmation page in their browser; tapping "Check in"/"Check out" records
  attendance with `method: "qr"` and **no GPS check at all** — physically reaching that URL
  (i.e. having scanned a code that's only accessible by being at the printed location) is
  treated as sufficient proof of presence.
- The event date range is still enforced, same as the GPS path.
- Admins can regenerate the code at any time, instantly invalidating any previously printed copies.

This is a deliberate fallback, not a replacement for GPS — the admin Attendance page flags
QR and manual entries so they stay visually distinct from verified GPS check-ins.

---

## Volunteer self-registration

Anyone can visit `/register` (linked from the login page) and request to join an event that
hasn't ended yet. Submitting the form does **not** grant a working login — it creates a
`volunteers` document with `status: "pending"`. The username/password they chose are stored
(hashed) but no `users` account exists yet, so login attempts fail until an admin acts on it.

Pending requests show up in a queue at the top of Admin → Volunteers, where the admin can:
- **Approve** — creates the real login account and adjusts the domain if needed, or
- **Decline** — deletes the request outright.

This keeps a public sign-up form from handing out working access to anyone who fills it in.

---

## Project structure

```
EventOps/
├── app.py                   # Application factory, blueprint registration, error handlers
├── config.py                 # Config loaded from environment variables
├── extensions.py             # MongoDB connection, Flask-Login, CSRF, rate limiter
├── models.py                  # Flask-Login User wrapper
├── seed.py                    # Demo data + index creation (python seed.py)
├── build_static.py           # Vercel-only: mirrors static/ into public/ at deploy time
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt      # + pytest/mongomock, for running tests/
├── .env / .env.example        # Environment configuration
├── render.yaml                # Render Blueprint (one-click deploy config)
├── vercel.json / pyproject.toml  # Vercel deploy config
├── .github/workflows/tests.yml  # CI: runs the test suite on every push/PR
│
├── routes/
│   ├── auth.py                # /login, /logout, /register (volunteer self sign-up)
│   ├── admin.py                # Everything under /admin/... (incl. QR, PDF, live stats)
│   └── volunteer.py            # Everything under /volunteer/... (incl. QR check-in)
│
├── utils/
│   ├── geo.py                  # Haversine distance, geofence check, GeoJSON helpers
│   ├── qr.py                    # QR code generation for backup check-in
│   ├── pdf_report.py             # PDF event report generation (reportlab)
│   ├── decorators.py           # @admin_required / @volunteer_required
│   └── helpers.py              # Misc helpers + Jinja filters (badge colors, date formatting)
│
├── templates/
│   ├── base.html                # App shell: sidebar, topbar, flash messages
│   ├── login.html / register.html
│   ├── admin/                   # One template per admin page (list + _form pairs)
│   │   └── event_qr.html          # Printable backup QR code page
│   ├── volunteer/                # One template per volunteer page
│   │   └── qr_checkin.html         # Confirmation page after scanning a QR code
│   └── errors/                   # 403 / 404 / 429 / 500
│
├── static/
│   ├── css/style.css            # Custom styles supplementing Tailwind
│   └── js/
│       ├── attendance.js         # Geolocation capture + geofence map (volunteer)
│       ├── maps.js                # Editable event-location map (admin)
│       ├── charts.js              # Dashboard Chart.js setup
│       ├── live_dashboard.js       # Polls /admin/dashboard/live for auto-updates
│       └── main.js                # Sidebar toggle, flash auto-dismiss
│
└── tests/                        # Automated tests (pytest + mongomock) — 54 tests
```

---

## Prerequisites

- **Python 3.10+**
- **MongoDB** — either:
  - a local MongoDB server ([install guide](https://www.mongodb.com/docs/manual/administration/install-community/)), or
  - a free [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) cluster (no local install needed — also required if you deploy to Render/Vercel later)
- A modern browser with location permissions enabled (for the attendance feature)

---

## Setup & installation

```bash
# 1. Extract the project and move into it
cd EventOps

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Configure `.env`

A working `.env` is already included so the project runs immediately with a local MongoDB.
For your own setup, copy the template and adjust it:

```bash
cp .env.example .env
```

| Variable | Purpose | Local default |
|---|---|---|
| `SECRET_KEY` | Signs sessions & CSRF tokens | a generated random value |
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017/eventops` |
| `DB_NAME` | Database name | `eventops` |
| `DEFAULT_GEOFENCE_RADIUS_METERS` | Pre-filled radius on "new event" | `100` |
| `SESSION_COOKIE_SECURE` | HTTPS-only cookies | `False` (must stay False for local `http://`) |

To point at MongoDB Atlas instead of a local server, replace `MONGO_URI` with your Atlas
connection string (`mongodb+srv://<user>:<password>@<cluster>.mongodb.net/...`) — see
[Deploying to production](#deploying-to-production-render--vercel) for the full Atlas setup steps.

### Seed demo data

MongoDB doesn't need any manual schema setup — collections and indexes are created
automatically. Just run:

```bash
python seed.py
```

This creates an admin account, two demo events, 10 volunteers, tasks, equipment, a schedule,
issues, announcements, and a few days of attendance history (see
[Demo credentials](#demo-credentials)). It's safe to run again any time you want to reset the
demo data back to a clean state.

### Run the app

```bash
python app.py
```

Open **http://localhost:5000** and log in with one of the demo accounts below.

---

## Demo credentials

| Role | Username | Password | Domain |
|---|---|---|---|
| Admin | `admin` | `Admin@123` | — |
| Volunteer | `rahul.verma` | `Demo@123` | Registration |
| Volunteer | `sneha.iyer` | `Demo@123` | Hospitality |
| Volunteer | `arjun.mehta` | `Demo@123` | Technical Support |
| Volunteer | `priya.nair` | `Demo@123` | Logistics |
| Volunteer | `karan.singh` | `Demo@123` | Security |
| Volunteer | `divya.rao` | `Demo@123` | Media & Documentation |
| Volunteer | `aditya.kulkarni` | `Demo@123` | Technical Support |
| Volunteer | `neha.joshi` | `Demo@123` | Registration |

The seeded event ("TechFusion 2026") is always dated to span *today* (its dates are computed
relative to when you run `seed.py`), so you can test GPS attendance marking immediately —
your browser's actual location just needs to be within the geofence radius shown on the
Attendance page (or use your browser dev tools to override/simulate GPS coordinates for testing
from elsewhere).

There's also one seeded **pending** registration ("Meera Kulkarni") sitting in the admin
approval queue (Admin → Volunteers) so you can try the approve/decline flow immediately, and
`/register` is open to submit more.

---

## Running the automated tests

An optional `pytest` suite (54 tests) covers auth, self-registration and the approval queue,
every admin CRUD flow, role-based access control, PDF/CSV export, the live dashboard endpoint,
rate limiting, and — most importantly — the geofencing and QR check-in accept/reject logic
itself. It runs against [`mongomock`](https://github.com/mongomock/mongomock) (an in-memory
MongoDB stand-in), so it needs no real database:

```bash
pip install -r requirements-dev.txt
pytest
```

A GitHub Actions workflow (`.github/workflows/tests.yml`) runs this same suite automatically
on every push and pull request once you push the project to GitHub — no setup needed beyond
that. (If you want the little "passing" badge for your own README, add
`![Tests](https://github.com/<your-username>/<your-repo>/actions/workflows/tests.yml/badge.svg)`
once it's pushed.)

---

## Deploying to production (Render / Vercel)

Both platforms need a database to talk to — neither hosts MongoDB for you — so start with a
free **MongoDB Atlas** cluster either way:

1. Create a free account at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas/register)
   and create a free (M0) cluster.
2. Under **Database Access**, add a database user with a password.
3. Under **Network Access**, add `0.0.0.0/0` (allow access from anywhere) — both Render and
   Vercel connect from dynamic IPs, so a fixed IP allowlist isn't practical for a project like this.
4. Click **Connect → Drivers**, copy the connection string
   (`mongodb+srv://<user>:<password>@<cluster>.mongodb.net/...`), and fill in your real password.
5. You'll use this as `MONGO_URI` on whichever platform you deploy to. Run `python seed.py`
   once **with this Atlas URI in your local `.env`** to populate it with demo data before (or
   after) deploying.

### Render

Render runs EventOps as a standard, always-on web service — the natural fit for a Flask app.

1. Push this project to a GitHub repository (`.env` is already gitignored, so your local
   secrets won't be committed — see [render.yaml](render.yaml)).
2. In the Render dashboard: **New → Blueprint**, and point it at your repo. Render reads
   `render.yaml` and creates the web service automatically.
3. When prompted, set the `MONGO_URI` environment variable to your Atlas connection string.
   (`SECRET_KEY` is generated for you automatically by the Blueprint.)
4. Deploy. Render builds with `pip install -r requirements.txt` and starts the app with
   `gunicorn app:app --bind 0.0.0.0:$PORT`.

No Blueprint? You can configure the same thing by hand: **New → Web Service**, runtime
**Python 3**, build command `pip install -r requirements.txt`, start command
`gunicorn app:app --bind 0.0.0.0:$PORT`, and add the environment variables from `.env.example`
yourself (set `SESSION_COOKIE_SECURE=True` and `FLASK_DEBUG=False`).

### Vercel

Vercel deploys Flask apps as serverless functions. It auto-detects a Flask instance named
`app` in `app.py` — which this project already has — so no extra config is needed for the
Python side.

1. Push this project to a GitHub repository.
2. In Vercel: **Add New → Project**, import the repo, and deploy.
3. In the project's **Settings → Environment Variables**, add `SECRET_KEY`, `MONGO_URI` (your
   Atlas string), `DB_NAME`, and set `SESSION_COOKIE_SECURE=True`.
4. Redeploy after adding the variables (Vercel doesn't apply new env vars to a build already in progress).

A couple of Vercel-specific things this project already handles for you:
- **Static assets.** Vercel serves static files from a top-level `public/` folder via its CDN,
  not through Flask's own `static/` handling. `build_static.py` mirrors `static/` into
  `public/static/` automatically as part of Vercel's build step (see `pyproject.toml`), so the
  existing `/static/...` URLs in the templates keep working unchanged.
- **Cold starts.** The first request after a period of inactivity may take a couple of extra
  seconds while a fresh function instance connects to MongoDB Atlas — this is normal for
  serverless hosting and not specific to this app.

Either platform will give you a working `https://...` URL — geolocation-based attendance works
immediately there since both serve over HTTPS (see the note in
[How geofenced attendance works](#how-geofenced-attendance-works) about why that matters).

**A couple of honest limitations worth knowing about**, both fine for a mini-project demo but
worth understanding if you extend this further:
- **Login rate limiting uses in-memory storage** (see `extensions.py`), so each server
  process/worker tracks its own counts. That's irrelevant for Render's single default worker,
  but on a platform running multiple concurrent instances, an attacker could get more attempts
  than intended by hitting different instances. A shared backend (Redis) fixes this — not
  included here to keep the project's moving parts minimal.
- **The live dashboard uses polling, not WebSockets**, specifically so it behaves identically
  on Render (long-running server) and Vercel (serverless functions, which can't hold a
  persistent WebSocket connection open). It refreshes every 8 seconds, which is "live enough"
  for a volunteer check-in feed without needing a fundamentally different hosting model.

---

## MongoDB collections

| Collection | Holds |
|---|---|
| `users` | Login credentials (hashed passwords) + role (`admin`/`volunteer`) — created at approval time for self-registered volunteers, not at request time |
| `events` | Event details, GeoJSON venue location, geofence radius, volunteer domains, backup QR secret |
| `volunteers` | Volunteer profiles, linked to an event and a `users` account; `status` is `pending` / `active` / `inactive` |
| `attendance` | One document per volunteer per event per day: check-in/out time, GPS, distance, method (`gps`/`manual`/`qr`), and any rejected attempts |
| `tasks` | Tasks with domain, priority, status, and assignment |
| `issues` | Volunteer-reported issues, status, and the admin's response |
| `equipment` | Inventory items, quantities, and condition |
| `schedules` | Event agenda/schedule items |
| `notifications` | Admin announcements shown to volunteers |

---

## Troubleshooting

**"Could not reach MongoDB" warning on startup** — the app still starts, but any page that
touches the database will fail until MongoDB is reachable. Check that `mongod` is running
locally (or that your Atlas `MONGO_URI` and database user/password are correct, and that your
IP is allowed under Atlas Network Access).

**Attendance always says "outside the geofence"** — double-check the event's configured
location on the admin Event edit page actually matches where you're testing from, and that
your radius is reasonable (100–200m is typical). Browser GPS accuracy varies — indoors it can
be off by dozens of meters.

**Location permission popup never appears / attendance button does nothing** — make sure
you're on `http://localhost` or a real `https://` URL. Browsers silently block the Geolocation
API on plain `http://` for any host other than `localhost`.

**Login redirects back to itself with no error** — this usually means cookies are being
blocked. If you set `SESSION_COOKIE_SECURE=True` while running locally over plain `http://`,
the browser will refuse to store the session cookie — keep it `False` for local dev.

**Port 5000 already in use** — set `PORT=5001` (or any free port) in `.env`.

**"Too many attempts" on login** — the login form is rate-limited (10 attempts/minute,
50/hour, per IP) to slow down password guessing. Wait a minute and try again; this resets
automatically. If you're testing repeatedly during development, this is expected behavior,
not a bug.

**`ModuleNotFoundError`** — make sure your virtual environment is activated and
`pip install -r requirements.txt` completed without errors.
