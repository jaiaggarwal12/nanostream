# Deploying NanoStream to Render (Free Tier)

Everything runs free on Render:
- **Web service** — FastAPI + uvicorn (Docker)
- **Redis** — Render managed Redis (free plan, 25 MB)
- **Cloudflare R2** — HLS video storage, 10 GB free + zero egress fees

---

## Step 1 — Push to GitHub

```bash
# From the nanostream folder
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/nanostream.git
git push -u origin main
```

> Make sure `.env` is in `.gitignore` (it is) — never push secrets.

---

## Step 2 — Create Render account

Go to https://render.com and sign up (free, no credit card required).

---

## Step 3 — Deploy with render.yaml (Blueprint)

1. In Render dashboard → **New** → **Blueprint**
2. Connect your GitHub repo
3. Render will detect `render.yaml` and create:
   - `nanostream-api` (web service)
   - `nanostream-redis` (Redis instance)
4. Click **Apply**

That's it — your app will be live at:
`https://nanostream-api.onrender.com`

---

## Step 4 — Set optional environment variables

In Render dashboard → `nanostream-api` → **Environment**:

| Variable | Value | Purpose |
|---|---|---|
| `R2_ACCOUNT_ID` | from Cloudflare | Required for video CDN delivery |
| `R2_ACCESS_KEY_ID` | from Cloudflare | R2 API key |
| `R2_SECRET_ACCESS_KEY` | from Cloudflare | R2 API secret |
| `R2_BUCKET` | `nanostream` | R2 bucket name |
| `R2_PUBLIC_URL` | `https://pub-xxxx.r2.dev` | CDN URL from R2 public access |

`REDIS_URL` is set **automatically** by Render from the Redis service — don't set it manually.

---

## Step 5 — Set up Cloudflare R2 (free video CDN)

1. Go to https://dash.cloudflare.com → **R2**
2. Create bucket named `nanostream`
3. Enable **Public Access** on the bucket → copy the public URL
4. Go to **Manage R2 API Tokens** → Create token with "Object Read & Write"
5. Copy Account ID, Access Key, Secret Key
6. Paste into Render environment variables (Step 4)

---

## API Endpoints

| Method | URL | Description |
|---|---|---|
| GET | `/` | API info |
| GET | `/health` | Health check |
| POST | `/analyze` | Upload and analyze video |
| POST | `/encode` | Submit encoding job |
| GET | `/jobs` | List all jobs |
| GET | `/jobs/{id}` | Get job status |
| GET | `/queue/stats` | Queue statistics |
| POST | `/cost/compare` | Compare codec costs |
| GET | `/abr/simulation` | Simulate ABR behavior |
| GET | `/metrics` | Prometheus metrics |

Interactive docs at: `https://nanostream-api.onrender.com/docs`

---

## Notes on Free Tier Limits

- Free web service **spins down after 15 min of inactivity** (cold start ~30s)
- Free Redis: 25 MB max — fine for job tracking, not video storage
- No persistent disk on free tier — uploaded videos are ephemeral
  - Use the `/analyze` endpoint with small test files
  - Large video storage → Cloudflare R2
- No Celery worker on free tier → job queue uses the built-in JSON fallback automatically

## Upgrading

To run Celery workers (parallel encoding), add a worker service to `render.yaml`:
```yaml
  - type: worker
    name: nanostream-worker
    runtime: docker
    dockerfilePath: ./Dockerfile
    dockerCommand: celery -A job_queue worker --loglevel=info --concurrency=2
    plan: starter  # $7/month
    envVars:
      - key: REDIS_URL
        fromService:
          type: redis
          name: nanostream-redis
          property: connectionString
```
