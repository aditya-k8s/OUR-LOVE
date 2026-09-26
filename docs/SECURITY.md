# Security checklist

Items marked **[built in]** are implemented in the code and covered by tests where
practical. Items marked **[deploy]** are your responsibility when deploying.

## Secrets and configuration

- [built in] All secrets come from environment variables; nothing sensitive is in the repository.
- [built in] `.env` is listed in `.gitignore` and `.dockerignore`; `.env.example` contains no values.
- [built in] The app refuses to start with `DEBUG=False` and a missing or weak `SECRET_KEY`.
- [built in] The MongoDB URI and storage credentials are never rendered into templates or API responses.
- [deploy] Use Secrets Manager, Key Vault or platform secrets in production; rotate `SECRET_KEY` and the Atlas password if either is ever exposed.
- [deploy] Remove `ADMIN_PASSWORD` from the environment after the admin account exists.

## Authentication and authorisation

- [built in] Django password hashing (PBKDF2) with minimum length 10, common-password and similarity validators.
- [built in] The session key is rotated on login; logout is POST-only and sends `Clear-Site-Data: "cache"`.
- [built in] Brute-force protection: 5 failed attempts lock an IP and a username for 15 minutes.
- [built in] Open-redirect protection on `next=`.
- [built in] `/admin/*` and every API mutation require a staff user; viewers get 403.
- [built in] Private by default (`PUBLIC_SITE_ENABLED=false`). In public mode anonymous visitors only receive documents with `is_public: true`, and exact coordinates are hidden unless the place is public.
- [deploy] Use a long, unique admin password; consider putting `/admin/` behind a VPN or an IP allow-list at the load balancer.

## Transport and headers

- [built in] HTTPS redirect, HSTS (1 year), and secure, HttpOnly, SameSite=Lax cookies when `SECURE_HTTPS=True`.
- [built in] Content Security Policy: `script-src 'self'`, no inline scripts or styles, `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`.
- [built in] `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, `Permissions-Policy`.
- [built in] `Cache-Control: private, no-store` on all personal pages; the service worker never caches them.
- [deploy] Terminate TLS with a valid certificate (ACM, Caddy, platform-managed). Set `BEHIND_PROXY=True` only behind a proxy you control.
- [deploy] Opt into `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` only if every subdomain is HTTPS.

## Input, output and uploads

- [built in] CSRF protection on every form, upload and API mutation (session auth).
- [built in] Django auto-escaping everywhere; user content is never rendered as HTML (`linebreaks` escapes first).
- [built in] Search input is regex-escaped; ObjectIds are validated; filters are allow-listed.
- [built in] Colour settings are validated as `#RRGGBB` before being written into `/theme.css`.
- [built in] Image uploads: extension allow-list (JPG, JPEG, PNG, WEBP), size limit, Pillow verification, extension and contents must match, 60 MP decompression-bomb limit, re-encoding that strips EXIF and GPS.
- [built in] Video uploads: MP4/WebM allow-list, size limit, container signature check. External video URLs must be HTTPS.
- [built in] Import uploads: extension allow-list, size limit, PDF signature check, binary rejection, and the raw file is not stored.
- [built in] Random storage keys; path traversal is rejected in the media view.
- [built in] Rate limits on uploads and imports.

## Media privacy

- [built in] Media is served only after an access check; unknown or private keys return 404.
- [built in] S3 objects are private; access uses short-lived pre-signed URLs.
- [deploy] Enable S3 Block Public Access, default encryption and versioning.

## Search engines and sharing

- [built in] `noindex, nofollow, noarchive` meta tag and `X-Robots-Tag` header; `robots.txt` disallows everything unless the public site and indexing are both enabled.
- [built in] Open Graph and Twitter metadata are generic and contain no relationship data.

## Errors and logging

- [built in] Custom 403, 404, 429 and 500 pages; no stack traces with `DEBUG=False`.
- [built in] Passwords are marked as sensitive POST parameters and are excluded from error reports.
- [deploy] Send container logs to CloudWatch or Log Analytics; do not log request bodies.

## Data protection

- [built in] Data minimisation: imports keep only the passages under review; uploaded chat files are discarded.
- [built in] Export and restore for data portability; deletion removes files and references.
- [deploy] The story contains personal data about both partners. Keep exports encrypted, restrict dashboard access, and enable Atlas backups with encryption at rest (default on Atlas).

## Verification

```bash
python manage.py check --deploy     # with production environment variables
python -m pytest                    # includes security header, access and upload tests
```
