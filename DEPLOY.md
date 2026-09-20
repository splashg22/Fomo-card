# Getting a real URL up for testers

The repo now has a `Dockerfile`, so any of these work with almost no setup. Pick one — Railway is
the fastest if you want a single click.

## Option A — Railway (fastest, ~10 minutes)

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** →
   pick this repo. Railway detects the `Dockerfile` automatically.
2. Add a database: **New** → **Database** → **Add MongoDB**. Railway wires up its connection
   string for you automatically as `MONGO_URL` if you reference it, or copy it manually into your
   web service's variables.
3. In the web service's **Variables** tab, set `MONGO_URL` (from step 2) and `DB_NAME=socialcash`.
   Everything else in `.env.example` is optional — leave unset for demo mode.
4. Railway builds and deploys automatically. Under **Settings → Networking**, click **Generate
   Domain** for a public `*.up.railway.app` URL.

## Option B — Render + MongoDB Atlas (both free forever)

1. [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas) → create a free **M0** cluster →
   **Connect** → **Drivers** → copy the connection string. That's your `MONGO_URL`.
2. [render.com](https://render.com) → **New** → **Web Service** → connect this GitHub repo. Render
   detects the `Dockerfile`.
3. Under **Environment**, add `MONGO_URL` (the Atlas string) and `DB_NAME=socialcash`.
4. Deploy. You'll get a `*.onrender.com` URL. Free tier spins down after inactivity, so the first
   request after a quiet period takes a few extra seconds — fine for testers, not for production.

## Option C — Fly.io

1. Install `flyctl`, then from the repo root: `fly launch` (it finds the `Dockerfile` and asks a
   few questions — say no to a Postgres database, you don't need one).
2. Set `MONGO_URL`/`DB_NAME` with `fly secrets set MONGO_URL=... DB_NAME=socialcash` (point it at
   an Atlas free cluster, same as Option B, step 1 — Fly doesn't offer managed Mongo).
3. `fly deploy`. You get a `*.fly.dev` URL.

## Whichever you pick

- Every variable in `.env.example` is optional. With none of them set beyond `MONGO_URL`/`DB_NAME`,
  the app runs in full demo mode — see [TESTING.md](TESTING.md) for what that means.
- The `serverSelectionTimeoutMS` change means if `MONGO_URL` is wrong, the app fails fast (~4s)
  with a clear error naming the problem, both at startup and in your host's logs.
- None of these need a credit card for the free tiers described above, at the scale a handful of
  testers will produce.
