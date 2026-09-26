# Our Love — Architecture

This document records the architecture and the engineering decisions taken where
the specification was ambiguous. It is the Phase 1 deliverable and is kept up to
date as the application evolves.

---

## 1. Overview

```
 Browser / installed PWA
        │  HTTPS (session cookie, CSRF token)
        ▼
 ┌──────────────────────────── Django (gunicorn + WhiteNoise) ───────────────────────────┐
 │  Middleware: security headers + CSP · access control (private/public) · cache policy  │
 │                                                                                        │
 │  apps.content    public story pages (templates)      apps.api        REST (DRF)        │
 │  apps.dashboard  premium admin at /admin/            apps.imports    chat importer     │
 │  apps.accounts   login / logout / rate limiting      apps.media      storage + uploads │
 │  apps.core       Mongo client, repositories, registry, settings, PWA, errors          │
 └───────────────┬───────────────────────────────┬─────────────────────────┬──────────────┘
                 │ PyMongo                       │ Django storage API       │ Django ORM
                 ▼                               ▼                          ▼
          MongoDB Atlas                 Local disk or S3-compatible     SQLite / Postgres
     (all story content + metadata)     (photos, videos, thumbnails)    (auth users, sessions)
```

* **Server-rendered** Django templates, hand-written CSS and vanilla JavaScript.
  No Node build step, no React. The site is fast, easy to deploy and easy to maintain.
* **MongoDB Atlas** holds every piece of story content and all media metadata.
* **Media binaries** never go into MongoDB. They go through Django's storage API to
  either local disk (development) or any S3-compatible bucket (production).
* **Django authentication** handles users, password hashing and sessions.

## 2. Key decisions

| # | Decision | Reason |
|---|----------|--------|
| D1 | Content in MongoDB via **PyMongo** with a thin repository layer (not MongoEngine, not an ORM adapter). | PyMongo is the official, maintained driver. A small repository keeps queries explicit, testable (mongomock) and index-aware. |
| D2 | **Users and sessions stay in Django's SQL database** (SQLite by default, `DATABASE_URL` for Postgres). | Django auth provides battle-tested password hashing, session rotation, CSRF integration and `is_staff` authorisation. Re-implementing it on MongoDB would add risk for no benefit. This is also why `python manage.py migrate` is part of setup. |
| D3 | A **content-type registry** (`apps/core/registry.py`) describes each collection's fields once. Admin forms, validation, list views, API serialisation and export are all generated from it. | Twelve near-identical CRUD apps would be repetitive. The registry keeps things DRY while each public page still has its own purpose-built view and template. |
| D4 | Django apps are grouped by responsibility (core, accounts, content, media, imports, dashboard, api) rather than one app per collection. | Same reason as D3; the specification allowed structure changes. |
| D5 | **"Our Firsts"** are timeline events carrying a `first_key` (e.g. `first_call`), not a separate collection. | One fact, one place. A first is always also a timeline moment. Missing firsts render as "Not added yet". |
| D6 | **Meetings, milestones and favourites** are categories / flags on timeline events and memories (`category: "meeting"`, `is_favorite: true`) rather than separate collections. | Avoids duplicating the same moment in several collections. |
| D7 | **Relationship statistics are computed live**, never stored. | The specification forbids fabricated numbers; computed values cannot go stale. |
| D8 | **Relationship profile, appearance, PWA, privacy, music and easter-egg settings** live in one `settings` document (`_id: "site"`). | Single read per request (cached briefly), single admin screen. |
| D9 | The admin dashboard is mounted at **`/admin/`**. The stock Django admin is **not** installed. | The specification asks for a separate premium dashboard at that URL. |
| D10 | **Search uses escaped, case-insensitive regular expressions** across a curated field list per collection. | Personal datasets are small; regex search supports partial words ("Bhagal") and works identically in tests (mongomock). Title indexes are still created. |
| D11 | **Chat import uses deterministic, rule-based extraction** (dates, keywords, quotes, known places). Only the author's own messages are mined from ChatGPT exports; assistant replies are ignored. | Assistant text was written by an AI and could introduce invented details. Nothing is published automatically — every candidate goes to *Pending Memories* with a confidence level. |
| D12 | **Titles suggested by the importer are taken from the source text** (first sentence, trimmed), never generated. | "Never invent" rule. The admin can rewrite them. |
| D13 | **Images are re-encoded on upload**: EXIF (including GPS) is stripped and WebP thumbnails (480 px, 1280 px) are generated. | Privacy (no hidden coordinates) and performance. Originals are kept, also without EXIF. |
| D14 | **Private media is never publicly addressable.** Local media is served through an authorised view; S3 media uses short-lived pre-signed URLs. | A guessable or leaked URL must not expose private photos. |
| D15 | **No inline scripts.** All JavaScript is in static files so the Content Security Policy can forbid inline script. The accent colour is served from a small dynamic stylesheet (`/theme.css`). | Strong XSS protection. |
| D16 | **Service worker caches only the app shell** (CSS, JS, fonts, icons, offline page). HTML pages are cached only when the server marks them cacheable (public mode, anonymous, public content). Admin, API and media responses are never cached. Logout clears the cache. | Offline support without storing private data on the device. |
| D17 | The product name is rendered as **"Our Love"** with an SVG heart mark instead of an emoji. | Emoji rendering differs between platforms; the SVG mark is consistent and matches the cinematic style. |
| D18 | Tailwind is **not** used. | A hand-written design system (custom properties, ~1 stylesheet) gives full control over the cinematic look without a build step. |
| D19 | Maps: when a place has coordinates **and** is marked public (or the viewer is signed in), an "Open map" link to OpenStreetMap is shown. No third-party map scripts are embedded. | Keeps the CSP strict and avoids leaking locations to tile providers. |
| D20 | Redis is **not** required. Rate limiting and settings caching use Django's cache (local memory by default, `REDIS_URL` optional). | The specification asks to add Redis only if needed. |

## 3. MongoDB collections

All documents carry `created_at`, `updated_at` (UTC datetimes) and, where visible
on the site, `is_public` (default `false`) and `is_published` (default `true`).
Dates of events are stored as ISO strings `YYYY-MM-DD` (a calendar date has no
time zone), which sort and range-query correctly.

| Collection | Purpose | Main fields |
|------------|---------|-------------|
| `settings` | Site configuration (single document `_id: "site"`) | `relationship{person_one, person_two, start_date, first_meeting_date, anniversary_date, description, story_intro}`, `appearance{accent_color, hero_title, hero_subtitle, hero_photo_id, final_quote}`, `pwa{app_name, short_name, theme_color, background_color}`, `privacy{allow_search_indexing}`, `music{enabled, url, title}`, `easter_egg{enabled, message}` |
| `timeline_events` | The main timeline and "Our Firsts" | `title, date, end_date, category, first_key, description, quote, location{name, city, country}, place_id, photo_ids[], video_ids[], tags[], people[], importance, order, is_favorite` |
| `memories` | Memory journal | `title, date, category, description, location{…}, place_id, photo_ids[], video_ids[], people[], tags[], mood, importance, is_favorite` |
| `photos` | Photo metadata | `storage_key, thumb_key, medium_key, original_name, content_type, size, width, height, caption, date, location{…}, tags[]` |
| `videos` | Video metadata | `storage_key` **or** `external_url`, `poster_photo_id, title, caption, date, location{…}, tags[], content_type, size` |
| `letters` | Love letters | `title, date, recipient, author, content, photo_id` |
| `messages` | "Words I'll never forget" | `message, date, sender, context, category` |
| `places` | Places that became memories | `name, city, country, date, description, latitude, longitude, photo_ids[], memory_ids[]` |
| `gifts` | "Little things" | `gift, date, given_by, given_to, occasion, description, photo_id, memory_id` |
| `important_dates` | "Our calendar" | `title, date, kind, recurring_yearly, description` |
| `future_plans` | "Things we still want to do" | `title, description, target_date, completed, completion_date, completion_photo_id, order` |
| `import_jobs` | One uploaded chat file | `filename, file_type, status, stats{segments, candidates}, error, created_by` |
| `pending_memories` | Extracted candidates awaiting review | `job_id, status (pending/approved/rejected/merged), target_collection, suggested{title, date, category, description, location, people, importance, quote}, confidence, reasons[], source_excerpt, possible_duplicates[{collection, id, title, date, score}], resolved_ref` |

### Indexes (created by `python manage.py ensure_indexes`)

* `date`, `category`, `tags`, `title`, `location.city`, `created_at`, `is_public`
  on `timeline_events` and `memories` (plus `first_key` on timeline).
* `date`, `tags`, `created_at` on `photos` and `videos`; `storage_key` unique (sparse) on `photos`/`videos`.
* `date` on `letters`, `messages`, `gifts`, `important_dates`; `name`, `city` on `places`.
* `job_id + status` and `created_at` on `pending_memories`.

## 4. Application structure

```
our-love/
├── manage.py
├── config/                 settings, urls, wsgi, asgi
├── apps/
│   ├── core/               Mongo client, repository, registry, site settings,
│   │                       middleware, context processors, PWA views, error pages,
│   │                       dates/duration helpers, management commands
│   ├── accounts/           login, logout, rate limiting, createadmin command
│   ├── content/            public story pages (home, story, memories, gallery, …)
│   ├── media/              storage abstraction, upload validation, thumbnails, media view
│   ├── imports/            parsers, extractor, duplicate detection, review workflow
│   ├── dashboard/          /admin/: dashboard, generic CRUD, uploads, settings, export
│   └── api/                /api/: read endpoints + admin-only mutations (DRF)
├── templates/              base, public pages, dashboard, errors, partials
├── static/                 css, js, icons, images
├── tests/                  pytest suite (mongomock)
├── docs/                   architecture, deployment, security checklist
├── Dockerfile, docker-compose.yml, .dockerignore
├── requirements.txt, requirements-dev.txt, pytest.ini
└── .env.example, .gitignore, README.md
```

## 5. Frontend architecture

* `templates/base.html` — shell with header, mobile bottom navigation, music toggle,
  theme toggle, install button, film grain and light-leak layers.
* `static/css/ourlove.css` — design tokens (custom properties), dark default and light
  theme, typography (Cormorant Garamond for display, Inter for UI), components.
* `static/css/dashboard.css` — the admin design system (same tokens, denser layout).
* `static/js/theme-init.js` — tiny, loaded in `<head>` to apply the saved theme before paint.
* `static/js/ourlove.js` — reveal-on-scroll, hero parallax, dust particles, live
  duration counter, lightbox (keyboard + swipe), music, easter egg, install prompt,
  service-worker registration. Every animation is disabled under `prefers-reduced-motion`.
* `static/js/dashboard.js` — drag-and-drop uploads with progress, confirmations,
  reordering, import review helpers.

## 6. PWA architecture

* `/manifest.webmanifest` — rendered from settings (name, short name, colours),
  icons 192, 512 and maskable 512, `display: standalone`, `start_url: /?source=pwa`.
* `/service-worker.js` — served from the site root so its scope is `/`. It is rendered
  with the hashed static URLs, versioned by a build hash, and:
  * pre-caches the app shell and `/offline/`;
  * cache-first for static assets; network-first for pages;
  * caches a page only if the response is not `private`/`no-store`;
  * never touches `/admin/`, `/api/`, `/media/`, `/accounts/`.
* Install button appears on `beforeinstallprompt`; iOS users get an "Add to Home Screen" hint.

## 7. Media storage architecture

* `MEDIA_STORAGE_PROVIDER=local` (default) → `FileSystemStorage` under `MEDIA_ROOT`,
  served by `/media/<key>` after an access check.
* `MEDIA_STORAGE_PROVIDER=s3` → `django-storages` S3 backend (AWS S3, Cloudflare R2,
  MinIO, DigitalOcean Spaces via `AWS_S3_ENDPOINT_URL`). The bucket is private;
  `/media/<key>` performs the same access check and redirects to a pre-signed URL
  (default lifetime 1 hour). CloudFront can sit in front for performance.
* Keys are random (`photos/2026/09/<uuid>.webp`) — never derived from the upload name.

## 8. Security architecture

* Authentication: Django sessions, PBKDF2/Argon2-ready hashing, session key rotated on login.
* Authorisation: `staff_required` for every `/admin/` view and API mutation.
* Access modes: `PUBLIC_SITE_ENABLED=false` (default) — every page except login, PWA
  assets and static requires sign-in. `true` — anonymous visitors see **only** documents
  with `is_public: true`; places hide coordinates unless public.
* CSRF on all forms and AJAX (token from cookie-less meta tag).
* XSS: template auto-escaping, no user HTML is ever rendered, strict CSP without inline script.
* Headers: HSTS (production), `X-Content-Type-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `X-Frame-Options: DENY`.
* Rate limiting: login (per IP and per username), uploads and imports.
* Uploads: extension allow-list, size limits, content sniffing (Pillow verification for
  images, container signatures for MP4/WebM), randomised names, EXIF removal.
* Secrets only from environment; `.env` is git-ignored; `DEBUG=False` by default;
  the app refuses to start in production with an unsafe `SECRET_KEY`.
* `noindex, nofollow` on every page and `X-Robots-Tag` header unless indexing is
  explicitly allowed in settings; `robots.txt` disallows everything by default.

## 9. Implementation roadmap

| Phase | Scope |
|-------|-------|
| 1 | Architecture (this document), project skeleton, settings, environment |
| 2 | MongoDB client, repositories, registry, indexes, site settings |
| 3 | Authentication, access control, rate limiting |
| 4 | Admin dashboard shell, generic CRUD |
| 5–8 | Timeline, memories, gallery/videos, letters/messages, places, gifts, dates, future |
| 9 | Search and filtering |
| 10 | Chat history importer, review workflow, duplicate detection |
| 11 | Cinematic frontend |
| 12 | PWA (manifest, service worker, install, offline) |
| 13 | Security hardening |
| 14 | Tests |
| 15 | Docker |
| 16 | Deployment and backup documentation, export |
