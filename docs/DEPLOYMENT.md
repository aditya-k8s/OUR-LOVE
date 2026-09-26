# Deployment

Every option uses the same Docker image and MongoDB Atlas. Choose one of the following:

| Option | Best for | Media storage | Users/sessions |
|--------|----------|---------------|----------------|
| A. AWS ECS Fargate + ALB + S3 + CloudFront | Production, no servers to patch | S3 (private) | RDS Postgres, or SQLite on EFS |
| B. AWS EC2 + Docker Compose + Caddy | Low cost, simple production | S3 or local volume | SQLite volume |
| C. Azure Container Apps | If you prefer Azure | Azure Files volume, or any S3-compatible bucket | Postgres Flexible Server, or SQLite on Azure Files |
| D. Render / Railway | Quick testing | S3-compatible (e.g. Cloudflare R2) | SQLite on a disk, or managed Postgres |
| E. Vercel | Serverless, deploy on every Git push | S3-compatible (required for uploads) | Postgres (required, e.g. Neon) |

Common production settings:

```env
DEBUG=False
SECRET_KEY=<50+ random characters>
ALLOWED_HOSTS=ourlove.example.com
CSRF_TRUSTED_ORIGINS=https://ourlove.example.com
BEHIND_PROXY=True            # behind ALB / Caddy / Render / Container Apps
SECURE_HTTPS=True
MONGODB_URI=<from Atlas>
MEDIA_STORAGE_PROVIDER=s3
```

Run `python manage.py check --deploy` against the production environment before going live.

---

## A. AWS: ECS Fargate, ALB, S3, CloudFront (recommended)

### 1. MongoDB Atlas

Create the cluster in the same region as ECS (for example `ap-south-1`). ECS tasks in
private subnets reach the internet through a **NAT gateway**. Add the NAT gateway's
Elastic IP to Atlas *Network Access*. For a fully private path, use Atlas **AWS PrivateLink**
(M10+).

### 2. S3 bucket for media

```bash
aws s3api create-bucket --bucket our-love-media-<unique> --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1
aws s3api put-public-access-block --bucket our-love-media-<unique> \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket our-love-media-<unique> --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket our-love-media-<unique> \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

The bucket stays private. The app issues pre-signed URLs after its own access check.

### 3. Secrets

Store `SECRET_KEY`, `MONGODB_URI` and (optionally) `ADMIN_PASSWORD` in **AWS Secrets Manager**
or **SSM Parameter Store** (SecureString), and reference them from the task definition.

### 4. Image in ECR

```bash
aws ecr create-repository --repository-name our-love
aws ecr get-login-password | docker login --username AWS --password-stdin <acct>.dkr.ecr.ap-south-1.amazonaws.com
docker build -t our-love .
docker tag our-love:latest <acct>.dkr.ecr.ap-south-1.amazonaws.com/our-love:latest
docker push <acct>.dkr.ecr.ap-south-1.amazonaws.com/our-love:latest
```

### 5. IAM task role (no access keys in the container)

Attach a policy like the following to the **task role**, and leave `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` empty. boto3 then uses the role automatically.

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    "Resource": "arn:aws:s3:::our-love-media-<unique>/*"
  }, {
    "Effect": "Allow",
    "Action": ["s3:ListBucket"],
    "Resource": "arn:aws:s3:::our-love-media-<unique>"
  }]
}
```

The **execution role** needs `secretsmanager:GetSecretValue` for the secrets above.

### 6. Users and sessions

With more than one task, use **RDS PostgreSQL** (`DATABASE_URL=postgres://...`), and for
shared rate limits either ElastiCache Redis (`REDIS_URL`) or accept per-task limits. A
single task can use SQLite on an **EFS** volume mounted at `/app/data`.

### 7. ECS service

- Fargate task: 0.5 vCPU and 1 GB are plenty; container port 8000.
- Environment: the common settings above plus `AWS_BUCKET_NAME` and `AWS_REGION`.
- Health check path: `/healthz/` (answered before host validation, so ALB probes work).
- Application Load Balancer: HTTPS listener (443) with an **ACM** certificate; HTTP (80) redirects to HTTPS. Target group on port 8000, health check `/healthz/`.
- Set `BEHIND_PROXY=True`.

### 8. CloudFront (optional but recommended)

Put CloudFront in front of the ALB for TLS at the edge, HTTP/2 and HTTP/3, and caching
of `/static/*`. Behaviours:

| Path | Cache policy | Origin request policy |
|------|--------------|-----------------------|
| `/static/*` | CachingOptimized (the files are fingerprinted) | None |
| Default (`*`) | CachingDisabled | AllViewer (forwards cookies, Host and query strings) |

Media is served through the app (access check), then redirected to S3 pre-signed URLs.
Do not cache `/media/*` at CloudFront.

### 9. DNS

Point `ourlove.example.com` at CloudFront (or the ALB) with a Route 53 alias record.

---

## B. AWS EC2 with Docker Compose and Caddy (simple production)

1. Launch an Ubuntu 24.04 `t4g.small` (or `t3.small`) with an Elastic IP. Security group: 22 (your IP only), 80, 443.
2. Install Docker: `curl -fsSL https://get.docker.com | sh`.
3. Clone the project and create `.env` with the common settings (`BEHIND_PROXY=True`).
4. Add Caddy for automatic HTTPS in `docker-compose.override.yml`:

   ```yaml
   services:
     web:
       ports: !reset []
     caddy:
       image: caddy:2
       ports: ["80:80", "443:443"]
       command: caddy reverse-proxy --from ourlove.example.com --to web:8000
       volumes: [caddy-data:/data]
       restart: unless-stopped
   volumes:
     caddy-data:
   ```

5. `docker compose up -d --build`.
6. Add the Elastic IP to the Atlas network access list.
7. Back up the `auth-data` and `media-data` volumes (or use S3 for media).

---

## C. Azure Container Apps

1. Create an **Azure Container Registry** and push the image (`az acr build -r <registry> -t our-love:latest .`).
2. Create a **Container Apps environment** and an app from the image, with ingress enabled (external, target port 8000). HTTPS is automatic.
3. Store `SECRET_KEY` and `MONGODB_URI` as Container Apps **secrets** and map them to environment variables. Set `BEHIND_PROXY=True`.
4. **Storage:** mount an **Azure Files** share at `/app/media` (`MEDIA_STORAGE_PROVIDER=local`) and another at `/app/data`, or use an S3-compatible bucket.
5. For more than one replica, use **Azure Database for PostgreSQL Flexible Server** via `DATABASE_URL`.
6. Health probe: HTTP `/healthz/` on port 8000.
7. Atlas network access: add the environment's outbound IPs (or configure a NAT gateway with a static IP).

---

## D. Render or Railway (quick testing)

1. Create a new **Web Service** from your Git repository; choose *Docker*.
2. Add the environment variables (common settings; `BEHIND_PROXY=True`).
3. Add a persistent disk mounted at `/app/data` (users and sessions). For media use Cloudflare R2 or S3 (`MEDIA_STORAGE_PROVIDER=s3`, `AWS_S3_ENDPOINT_URL` for R2).
4. Health check path `/healthz/`.
5. Atlas: these platforms do not have fixed egress IPs on free plans. For a test deployment only, allow `0.0.0.0/0` with a strong, unique database password, and remove it afterwards.

---

## E. Vercel

Vercel detects Django from `manage.py`, reads `WSGI_APPLICATION`, runs `collectstatic`
during the build and serves `/static/` from its CDN. The app detects Vercel (`VERCEL=1`)
and then automatically trusts Vercel's HTTPS proxy, adds the deployment, branch and
production domains to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, and resizes large photos
in the browser before upload.

### Limits to know about

| Limit | Effect | What to do |
|-------|--------|-----------|
| Temporary filesystem | SQLite and local media would be lost | Postgres for users and sessions; S3-compatible storage for media |
| 4.5 MB per request | Large uploads fail with 413 | Photos are resized in the browser automatically; add videos as HTTPS links; import large chat exports from your computer with `python manage.py import_chat_history <file>` (it writes to the same Atlas database) |
| No fixed outbound IP (Hobby) | Atlas cannot allow-list Vercel | Atlas *Network Access*: allow `0.0.0.0/0`, protected by a strong, unique database password |

### 1. Postgres for sign-in and sessions

In the Vercel project: *Storage > Create Database > Neon (Postgres)*, and connect it to the
project. This sets `DATABASE_URL` (the app also accepts `POSTGRES_URL`). Any Postgres
provider works.

### 2. Environment variables

*Project Settings > Environment Variables*, for **Production** and **Preview**:

| Variable | Value |
|----------|-------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `MONGODB_URI` | your Atlas connection string |
| `MONGODB_DATABASE` | `our_love` |
| `DATABASE_URL` | set by the Neon integration |
| `MEDIA_STORAGE_PROVIDER` | `s3` (uploads stay switched off until this is set) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_BUCKET_NAME`, `AWS_REGION` | your bucket; for Cloudflare R2 also `AWS_S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com` and `AWS_REGION=auto` |
| `ALLOWED_HOSTS` | only needed for a custom domain, e.g. `ourlove.example.com` (plus `CSRF_TRUSTED_ORIGINS=https://ourlove.example.com`) |

Do not set `DEBUG`. Variables apply to new deployments only, so redeploy afterwards.

### 3. Create the tables and the admin account (once)

From your computer, with `DATABASE_URL` copied into your local `.env`:

```bash
python manage.py migrate
python manage.py createadmin --username <you>
python manage.py ensure_indexes
```

Run `migrate` again only after upgrading Django.

### 4. Deploy

Push to the connected branch, or run `vercel --prod`. Then open the site and sign in.


1. Open the site and sign in with the admin account (created from `ADMIN_USERNAME` and `ADMIN_PASSWORD` by the entrypoint, or run `python manage.py createadmin` in the container).
2. Remove `ADMIN_PASSWORD` from the environment once the account exists.
3. Go to *Dashboard > Settings*: names, start date, story introduction and hero image.
4. Install the PWA on your phone (see the README).
5. Set up backups (README, *Backup*).
