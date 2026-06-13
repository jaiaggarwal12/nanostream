# Deploying NanoStream to Render (Free Tier)

Everything runs free — no credit card needed for storage:
- **Web service** — FastAPI + uvicorn (Docker) on Render
- **Redis** — Render managed Redis (free, 25 MB)
- **Backblaze B2** — HLS video storage, 10 GB free, NO card required

---

## Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/nanostream.git
git push -u origin main
```

---

## Step 2 — Deploy on Render

1. Go to https://render.com → sign up (requires card for identity, won't charge on free tier)
2. New → **Blueprint** → connect your GitHub repo
3. Render detects `render.yaml` and creates:
   - `nanostream-api` web service
   - `nanostream-redis` Redis instance
4. Click **Apply** — live in ~5 mins at `https://nanostream-api.onrender.com`

---

## Step 3 — Set up Backblaze B2 (free video storage, NO card)

1. Sign up at https://www.backblaze.com/sign-up/cloud-storage
2. **Buckets** → **Create a Bucket**
   - Bucket name: `nanostream`
   - Files in bucket: **Public**
   - Click Create Bucket
3. Open the bucket → note the **Endpoint** (e.g. `s3.us-west-004.backblazeb2.com`)
4. **Account** (top right) → **App Keys** → **Add a New Application Key**
   - Name: `nanostream`
   - Allow access to bucket: `nanostream`
   - Type of access: **Read and Write**
   - Click Create
   - **Copy both values immediately** (shown only once):
     - `keyID` → this is your `B2_KEY_ID`
     - `applicationKey` → this is your `B2_APPLICATION_KEY`
5. Work out your public URL:
   - Endpoint like `s3.us-west-004.backblazeb2.com` → region number is `004`
   - Public URL = `https://f004.backblazeb2.com/file/nanostream`

---

## Step 4 — Add B2 environment variables to Render

In Render dashboard → `nanostream-api` → **Environment**:

| Variable | Example value |
|---|---|
| `B2_KEY_ID` | `004abc123...` |
| `B2_APPLICATION_KEY` | `K004xyz...` |
| `B2_BUCKET` | `nanostream` |
| `B2_ENDPOINT` | `s3.us-west-004.backblazeb2.com` |
| `B2_PUBLIC_URL` | `https://f004.backblazeb2.com/file/nanostream` |

`REDIS_URL` is set **automatically** by Render — don't touch it.

---

## API Endpoints

| Method | URL | Description |
|---|---|---|
| GET | `/` | API info |
| GET | `/health` | Health check |
| POST | `/analyze` | Upload & analyze video |
| POST | `/encode` | Submit encoding job |
| GET | `/jobs` | List all jobs |
| GET | `/jobs/{id}` | Job status |
| GET | `/queue/stats` | Queue stats |
| POST | `/cost/compare` | Compare codec costs |
| GET | `/abr/simulation` | Simulate ABR |
| GET | `/metrics` | Prometheus metrics |

Interactive docs: `https://nanostream-api.onrender.com/docs`

---

## Free Tier Notes

- Free web service spins down after 15 min inactivity (cold start ~30s on next request)
- Free Redis: 25 MB — fine for job tracking
- No persistent disk on Render free tier — B2 handles video persistence
- No Celery worker on free tier — job queue uses JSON fallback automatically
