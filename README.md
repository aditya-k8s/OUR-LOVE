# Our Love

*Every moment has a story.*

A private, cinematic digital memory of a relationship: a story-first website and
installable Progressive Web App, with a premium admin dashboard for managing every
piece of content. Built with Django, MongoDB Atlas and plain HTML, CSS and JavaScript.

---

## Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [MongoDB Atlas setup](#mongodb-atlas-setup)
5. [Environment variables](#environment-variables)
6. [Local development](#local-development)
7. [Docker](#docker)
8. [Deployment](#deployment)
9. [PWA installation](#pwa-installation)
10. [Admin usage](#admin-usage)
11. [Importing ChatGPT history](#importing-chatgpt-history)
12. [Media storage](#media-storage)
13. [Security](#security)
14. [Backup](#backup)
15. [Testing](#testing)
16. [Troubleshooting](#troubleshooting)

---

## Features

**The story (public site)**

- Cinematic hero with a slow Ken Burns image or muted video, light leaks, film grain and drifting dust.
- A live "Together for" counter (years, months and days), calculated from the relationship start date in Settings.
- **How it all started**: your own introduction, written in Settings.
- **Our Firsts**: first message, call, meeting, photo, date, gift, trip, kiss, "I love you" and special memory. Anything missing shows *Not added yet*.
- **Timeline**, grouped by year and month, with categories, importance, quotes, places, tags, photos and videos. It can be filtered.
- **Memories** in a masonry grid, filterable by year, month, category, person, location, importance and tag.
- **Gallery** with a full-screen lightbox (keyboard, swipe, captions, dates, places).
- **Moments in Motion**: MP4/WebM videos, lazy-loaded, never autoplayed with sound.
- **Letters** on a paper texture; **Words I'll Never Forget** as quote cards.
- **Places**, **Little Things** (gifts) and **Our Calendar** (monthly view, recurring dates, what is coming up).
- **Things We Still Want To Do**, with an animated tick when a plan is completed.
- **Our Numbers**: every statistic is counted live from MongoDB.
- **On This Day**: memories from the same date in earlier years.
- Global search, dark mode by default with an optional light mode, optional music (never autoplays), and a hidden secret (tap the heart five times).

**The dashboard (`/admin/`)**

- Overview with KPI cards, a monthly activity chart, a getting-started checklist and recent edits.
- Add, edit, delete, publish or unpublish and mark public for every content type. Timeline and future plans can be reordered.
- Drag-and-drop photo and video uploads with preview, progress bars and validation.
- **Import history**: extract candidate memories from exported chats into *Pending memories* for review (approve, edit, reject, merge, keep both).
- Settings for the relationship, appearance, PWA, privacy, music and the hidden secret.
- **Export our story** as JSON, or as a ZIP with media.

**Principle: no fake data.** The application never invents dates, memories, quotes or statistics.
Empty sections say *Not added yet*. The optional demo seed is titled "Demo ..." and flagged `is_demo`.

## Architecture

```
Browser / PWA ──HTTPS──> Django (gunicorn + WhiteNoise)
                          ├─ apps.content    public story pages
                          ├─ apps.dashboard  /admin/ dashboard
                          ├─ apps.imports    chat history importer
                          ├─ apps.api        REST API (DRF)
                          ├─ apps.media      uploads, thumbnails, protected media
                          ├─ apps.accounts   login, logout, rate limiting
                          └─ apps.core       Mongo client, registry, settings, PWA, security
                               │                    │                      │
                         MongoDB Atlas      Local disk / S3          SQLite / Postgres
                        (all content)      (photos, videos)       (users and sessions)
```

The full design, including the MongoDB document structures, indexes and every
engineering decision, is in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Installation

Requirements: Python 3.12+, a MongoDB Atlas cluster (the free tier is enough), and optionally Docker.

```bash
git clone <your-repo-url> our-love
cd our-love
python -m venv venv
```

Activate the virtual environment:

```bash
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows (cmd / PowerShell)
```

Then:

```bash
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
# edit .env: SECRET_KEY, MONGODB_URI, ADMIN_USERNAME ...
python manage.py migrate        # creates the small auth/session database
python manage.py check_mongo    # confirms MongoDB Atlas is reachable
python manage.py ensure_indexes
python manage.py createadmin    # prompts for a password
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in. The dashboard is at http://127.0.0.1:8000/admin/.

> For local development over plain HTTP, set `DEBUG=True` (or `SECURE_HTTPS=False`) in `.env`.
> Otherwise the secure cookies and HTTPS redirect will stop you from signing in.

## MongoDB Atlas setup

1. **Create an account** at <https://www.mongodb.com/cloud/atlas/register>.
2. **Create a cluster**: *Build a Database*, then *M0 Free* (or larger). Pick the region closest to where the app will run (for AWS Mumbai: `ap-south-1`).
3. **Create a database user**: *Security > Database Access > Add New Database User*. Use password authentication, generate a strong password, and grant *Read and write to any database* (or restrict it to `our_love`).
4. **Configure network access**: *Security > Network Access > Add IP Address*. Add your development IP. For production, add your server's static egress IP (NAT gateway or Elastic IP). Avoid `0.0.0.0/0`.
5. **Get the connection string**: *Database > Connect > Drivers > Python*. Copy the `mongodb+srv://...` URI.
6. **Add it to `.env`**:
   ```env
   MONGODB_URI=mongodb+srv://ourlove_app:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   MONGODB_DATABASE=our_love
   ```
   URL-encode special characters in the password (`@` becomes `%40`).
7. **Create the database**: nothing to do. MongoDB creates `our_love` and its collections on first write.
8. **Create indexes**: `python manage.py ensure_indexes` (safe to run repeatedly; the Docker entrypoint runs it on every start).
9. **Test the connection**: `python manage.py check_mongo` should print `Connected.` The `/healthz/` endpoint reports the same.

Credentials live only in `.env` or your platform's secret store. They are never sent to the browser.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | *(required)* | Django signing key, 50+ random characters. The app refuses to start in production with a weak key. |
| `DEBUG` | `False` | Never enable in production. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` in debug | Comma-separated host names. |
| `CSRF_TRUSTED_ORIGINS` | | e.g. `https://ourlove.example.com` |
| `MONGODB_URI` | *(required)* | Atlas connection string. |
| `MONGODB_DATABASE` | `our_love` | Database name. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | | Used by `createadmin` (and the Docker entrypoint when both are set). |
| `PUBLIC_SITE_ENABLED` | `false` | `false`: sign-in required. `true`: visitors see only items marked *Public*. |
| `SECURE_HTTPS` | `True` when not debugging | Secure cookies, HSTS, HTTPS redirect. |
| `BEHIND_PROXY` | `False` | Trust `X-Forwarded-Proto` from a load balancer. |
| `SECURE_HSTS_SECONDS` / `_INCLUDE_SUBDOMAINS` / `_PRELOAD` | `31536000` / `False` / `False` | HSTS tuning. |
| `MEDIA_STORAGE_PROVIDER` | `local` | `local` or `s3`. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_BUCKET_NAME`, `AWS_REGION`, `AWS_S3_ENDPOINT_URL` | | S3-compatible storage. Leave the keys empty on AWS to use the task or instance IAM role. |
| `MEDIA_SIGNED_URL_SECONDS` | `3600` | Lifetime of pre-signed media links. |
| `MAX_IMAGE_UPLOAD_MB` / `MAX_VIDEO_UPLOAD_MB` / `MAX_IMPORT_UPLOAD_MB` | `20` / `300` / `25` | Upload limits. |
| `DATABASE_URL` | SQLite in `data/` | `postgres://...` for users and sessions (recommended when running several containers). |
| `REDIS_URL` | | Shared cache for rate limits across containers. |
| `TIME_ZONE` | `Asia/Kolkata` | Used for "today", On This Day and the calendar. |

## Local development

```bash
venv\Scripts\activate                 # or: source venv/bin/activate
pip install -r requirements-dev.txt
python manage.py runserver
python manage.py seed_data            # optional, clearly-labelled demo content
python manage.py seed_data --clear    # remove it again (also available on the dashboard)
python -m pytest                      # run the test suite
python scripts/generate_assets.py     # regenerate icons and textures after colour changes
```

## Docker

```bash
cp .env.example .env      # fill in SECRET_KEY, MONGODB_URI, ALLOWED_HOSTS ...
docker compose up --build
```

The container runs migrations, creates the MongoDB indexes, creates the admin when
`ADMIN_USERNAME` and `ADMIN_PASSWORD` are set, and serves on port 8000. For local
testing over plain HTTP, add `SECURE_HTTPS=False` to `.env`.

- Users and sessions persist in the `auth-data` volume; local media persists in `media-data`.
- No local MongoDB is needed with Atlas. For a fully offline setup:
  `docker compose --profile local-mongo up --build` with `MONGODB_URI=mongodb://mongo:27017`.
- Redis is not required.

## Deployment

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** for step-by-step guides:

- **AWS (recommended):** Docker image in ECR, ECS Fargate behind an Application Load Balancer with ACM HTTPS, MongoDB Atlas, S3 for media, CloudFront, and Secrets Manager.
- **AWS EC2:** a single instance running Docker Compose behind Caddy or Nginx with automatic HTTPS.
- **Azure:** Azure Container Apps (or App Service for Containers) with an Azure Files volume for media, or any S3-compatible bucket.
- **Simple test deployment:** Render or Railway from the Dockerfile.
- **Vercel:** zero-config serverless deployment from GitHub. It needs Postgres (e.g. Neon) for sign-in and S3-compatible storage for uploads; see *E. Vercel*.

Production checklist: `DEBUG=False`, a strong `SECRET_KEY`, correct `ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS`, `BEHIND_PROXY=True` behind a load balancer, HTTPS, the Atlas IP
allow-list, S3 media, and `python manage.py check --deploy`.

## PWA installation

The site is a full Progressive Web App: web app manifest, 192 px, 512 px and maskable
icons, `display: standalone`, and a service worker with an offline page.

- **Android Chrome:** open the site, then tap **Install** (the download icon in the header, or *More > Install Our Love*), or use Chrome's menu, *Install app*.
- **Desktop Chrome or Edge:** click the install icon in the address bar, or the one in the header.
- **iPhone or iPad (Safari):** tap *Share*, then *Add to Home Screen*. The *More* page shows this hint.

Installation needs HTTPS (or `localhost`). Offline, the app shell, styles, scripts, fonts
and icons are served from cache, together with an offline page. Private pages, the
dashboard, the API and media are never cached, and signing out clears cached pages.

## Admin usage

Go to `/admin/`, or use the settings icon in the site header when signed in as admin.

**Adding a memory in under a minute:** click *Add memory*, fill in the title and
(optionally) date, category, description and location, then drop in photos or pick
existing ones, add tags and set importance. Click *Save memory*, or *Save and add
another* to keep going.

- **Published** controls whether an item appears at all. **Public** only matters when `PUBLIC_SITE_ENABLED=true`.
- **Our Firsts:** create a timeline event and choose *Marks our first...*.
- **Photos:** upload on *Photos*. EXIF and GPS data are removed automatically. Click a photo to add a caption, date, place and tags.
- **Videos:** drag MP4/WebM files onto *Videos*, or add a video with an HTTPS link.
- **Settings:** names, start date (drives the live counter), the story introduction, hero image or video, colours, install name, music and the hidden secret.
- **Accounts:** `python manage.py createadmin --username you` (admin) or `python manage.py createadmin --viewer --username partner` (can view everything, cannot edit).

## Importing ChatGPT history

1. Export your data from ChatGPT (*Settings > Data controls > Export*). You receive `conversations.json` and `chat.html`.
2. In the dashboard, open **Import history** and upload a `.json`, `.html`, `.txt`, `.md` or text-based `.pdf` file. From the command line: `python manage.py import_chat_history path/to/file`.
3. The importer:
   - uses **only the messages you wrote**; assistant replies are ignored so AI-written details never enter your story;
   - splits the text into passages and reads dates **written in the text** (`2025-07-19`, `19 July 2025`, `July 19, 2025`, `19/07/2025` (day first));
   - suggests a category, one of your "firsts", importance, quoted words, known places and names;
   - takes titles from the text itself and never generates them;
   - assigns **Confidence: High / Medium / Low** and lists the reasons. Anything without a written date is always *Low*;
   - flags **possible duplicates** of existing memories.
4. Review each candidate under **Pending memories**: **Approve**, edit any field, change the date, category or importance, **Reject**, **Merge** into an existing memory (fills only empty fields and appends the text), or **Keep both**.

Nothing is published until you approve it. The uploaded file itself is not stored;
only the passages awaiting review are kept.

## Media storage

MongoDB stores only metadata and storage keys. Files go to the configured storage:

- **Local (default):** files are saved under `MEDIA_ROOT` and served by `/media/<key>` only after an access check.
- **S3-compatible:** set `MEDIA_STORAGE_PROVIDER=s3` and the `AWS_*` variables. The bucket stays **private**; `/media/<key>` checks access and redirects to a short-lived pre-signed URL. This works with AWS S3, Cloudflare R2, MinIO and DigitalOcean Spaces (via `AWS_S3_ENDPOINT_URL`).

Every image is validated (extension, size and actual contents), re-encoded without
EXIF or GPS, and given 480 px and 1280 px WebP thumbnails. File names are random.

## Security

Summary (the full checklist is in **[docs/SECURITY.md](docs/SECURITY.md)**):

- Private by default; admin-only mutations; signed-in viewers get read-only access.
- Django password hashing, session rotation on login, and brute-force lockout (5 attempts per 15 minutes, per IP and per username).
- CSRF on every form and upload; secure, HttpOnly, SameSite cookies; HSTS in production.
- Strict Content Security Policy (no inline scripts or styles), `X-Frame-Options: DENY`, `nosniff`, a strict referrer policy and a Permissions-Policy.
- Auto-escaped templates; user content is never rendered as HTML.
- Upload validation by content, not just extension; EXIF and GPS stripped; decompression-bomb protection.
- `noindex, nofollow` meta and `X-Robots-Tag` headers; `robots.txt` disallows everything by default.
- Secrets only in the environment; `.env` is git-ignored; no stack traces in production.

## Backup

| What | How |
|------|-----|
| **MongoDB** | Atlas M10+ has continuous cloud backups with point-in-time restore (*Cluster > Backup*). On M0/M2/M5, schedule `mongodump --uri "$MONGODB_URI" --archive=our-love-$(date +%F).gz --gzip`. |
| **Media** | S3: enable **Versioning** and a lifecycle rule; optionally Cross-Region Replication. Local: back up the `media-data` volume (`docker run --rm -v our-love_media-data:/m -v $PWD:/b alpine tar czf /b/media.tgz -C /m .`). |
| **Users** | Back up `data/auth.sqlite3` (or your Postgres database). |
| **Whole story** | Dashboard, *Export our story* (JSON, or ZIP with media), or `python manage.py export_story backup.zip --zip`. |

**Restoring:**

```bash
mongorestore --uri "$MONGODB_URI" --archive=our-love-2026-09-26.gz --gzip   # from mongodump
python manage.py restore_story backup.zip     # from an app export (data + media)
python manage.py restore_story backup.json    # data only
```

`restore_story` upserts by id, so running it twice is safe. Keep exports somewhere
private and encrypted: they contain your whole story.

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite (117 tests) uses an in-memory MongoDB (mongomock) and covers authentication,
admin authorisation, rate limiting, timeline and memory creation, visibility rules,
search, filtering, the importer, duplicate detection and merge, upload validation
(including EXIF stripping), the protected media view, the API, the PWA manifest and
service worker, security headers, export and restore, and date calculations.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `MONGODB_URI is not set` | Copy `.env.example` to `.env` and fill it in. |
| `ServerSelectionTimeoutError` | Add your IP under Atlas *Network Access*; check the user and password (URL-encode special characters). Test with `python manage.py check_mongo`. |
| `SECRET_KEY is too weak` | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(50))"`. |
| Cannot sign in locally / redirected to https | Set `DEBUG=True` or `SECURE_HTTPS=False` for plain-HTTP development. |
| CSRF failure after deploying | Add your origin to `CSRF_TRUSTED_ORIGINS`; set `BEHIND_PROXY=True` behind a load balancer. |
| "Too many attempts" | Wait 15 minutes, or restart the app (the local-memory cache resets). |
| Install button does not appear | Requires HTTPS; Chrome only offers installation once per profile. Check *DevTools > Application > Manifest*. |
| Photos return 404 | Signed out, or (in public mode) the photo is not marked Public. |
| Styles are stale after an update | The service worker updates on the next visit; reload once. |
| Upload rejected | Only JPG, PNG, WEBP (images) and MP4, WebM (videos) within the size limits; the file contents must match the extension. |
