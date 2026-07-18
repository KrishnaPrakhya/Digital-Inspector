# DigitalOcean production deployment

This deploys the complete torch-free FastAPI backend on one persistent Droplet.
The browser calls the original `/api/v1/*` REST contract directly; there is no
Gradio queue or ZeroGPU quota.

The stack is three containers on one private compose network:

| Service | Role | Exposure |
| ------- | ---- | -------- |
| `api` | FastAPI + ONNX models, `mem_limit: 3.2g` | internal only, port 7860 |
| `db` | Postgres 16 for the Scam Pulse feed, `mem_limit: 512m` | **internal only, no published port** |
| `caddy` | TLS termination and reverse proxy, `mem_limit: 128m` | 80 / 443 |

Postgres deliberately publishes no port, so it is reachable only by `api`. The
`pulse_data` volume holds the aggregate feed and `caddy_data` holds the
Let's Encrypt certificates — never prune volumes on this host.

## 1. Create the Droplet

In DigitalOcean, first confirm the GitHub Student Pack credit appears under
**Billing**. Create a Droplet with:

- Ubuntu 24.04 LTS
- Basic, Regular SSD
- 4 GiB RAM / 2 shared vCPU is sufficient: the API holds about 2.2 GiB with all
  three ONNX models resident, and `mem_limit: 3.2g` is sized for that box. 8 GiB
  / 4 vCPU roughly halves analysis latency if the credit allows it.
- the closest available region (Bangalore is preferred for Indian users)
- SSH key authentication
- backups off unless you intentionally want the paid add-on
- monitoring on

Copy the public IPv4 address after creation.

## 2. Create the Cloudflare DNS record

Create this record in the domain's Cloudflare DNS page:

| Type | Name  | Content          | Proxy status           |
| ---- | ----- | ---------------- | ---------------------- |
| A    | `api` | the Droplet IPv4 | **DNS only** initially |

DNS-only avoids Cloudflare's 120-second proxy read timeout for a worst-case local
audio transcription. Caddy still provides normal public HTTPS. After measuring
audio P95 below 120 seconds, the record can be proxied if desired.

Wait until `nslookup api.example.com` returns the Droplet IP.

## 3. Provision the server

Connect from the local machine:

```bash
ssh root@DROPLET_IP
```

Install the runtime and firewall:

```bash
apt-get update
apt-get install -y ca-certificates curl git ufw docker.io docker-compose-v2 unattended-upgrades
systemctl enable --now docker
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
```

Clone and configure the application:

```bash
git clone https://github.com/KrishnaPrakhya/Digital-Inspector.git /opt/digital-inspector
cd /opt/digital-inspector/deploy/digitalocean
cp .env.example .env
nano .env
```

Set `API_DOMAIN`, `TLS_EMAIL`, `GROQ_API_KEY`, `PROD_VERCEL_URL`, and
`POSTGRES_PASSWORD` (any long random string — it never leaves the compose
network). Keep the pinned model repository and revision unchanged.

`.env` is intentionally untracked, so `git pull` never delivers new variables.
When a release adds one — `POSTGRES_PASSWORD` did — add it by hand before
rebuilding, or the affected service will not start.

If the Droplet has no swap, add 2 GB before the first build. A 4 GB box running
the models has little headroom, and swap lets the kernel apply pressure instead
of invoking the OOM killer:

```bash
free -h && swapon --show
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl vm.swappiness=10
echo 'vm.swappiness=10' > /etc/sysctl.d/99-digital-inspector.conf
```

## 4. Build and start

```bash
cd /opt/digital-inspector/deploy/digitalocean
export GIT_SHA="$(git -C /opt/digital-inspector rev-parse --short HEAD)"
docker compose up -d --build
docker compose ps
docker compose logs -f api
```

The first build downloads the pinned ONNX artifacts and the pinned local Whisper
fallback into the image. It can take several minutes. Wait until the API container
becomes healthy, then press `Ctrl+C` to leave the log view without stopping the
containers.

Verify inside the API container and through the public hostname:

```bash
docker compose exec -T api /app/backend/.venv/bin/python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:7860/health').read().decode())"
curl -fsS https://api.example.com/health
```

A healthy response reports every model `true`, `groq_configured: true`,
`pulse: true`, and the deployed Git SHA. `pulse: false` means the API could not
reach Postgres — analyses still work, but the feed is disabled; check that
`POSTGRES_PASSWORD` is set in `.env` and that `docker compose ps` shows `db`
healthy.

Port 7860 and Postgres are intentionally not published to the host or public
internet.

Test inference:

```bash
curl -fsS https://api.example.com/api/v1/analyze/text
  -H 'Content-Type: application/json'
  -d '{"text":"This is CBI. Transfer Rs 50000 to safeaccount@ybl immediately or you will be arrested."}'
```

## 5. Point Vercel to the Droplet

In the Vercel project, set:

```text
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
```

Redeploy the production frontend. `PROD_VERCEL_URL` on the server must exactly
match the production Vercel origin, without a trailing slash. Preview deployments
continue to work through the existing `*.vercel.app` CORS rule.

## 6. Monitoring

Monitor `https://api.example.com/health` every five minutes with UptimeRobot or
cron-job.org. Alert on non-200 responses. The Droplet does not sleep; this is an
availability alert, not a keep-alive workaround.

Useful commands:

```bash
cd /opt/digital-inspector/deploy/digitalocean
docker compose ps
docker compose logs --tail=200 api
docker stats --no-stream
docker compose restart api
git pull --ff-only
export GIT_SHA="$(git -C /opt/digital-inspector rev-parse --short HEAD)"
docker compose up -d --build
```

### Shipping a code change

The Dockerfile copies `backend/` into the image, so the container runs the code
that was baked in at build time. `git pull` alone changes nothing the running
service sees — `--build` is what applies it:

```bash
cd /opt/digital-inspector && git pull --ff-only
cd deploy/digitalocean
export GIT_SHA="$(git -C /opt/digital-inspector rev-parse --short HEAD)"
docker compose up -d --build
```

Layer caching keeps this quick: a backend-only change reuses the dependency
layer and the pinned 1.6 GB model download, so only the `COPY backend` layer
onward is rebuilt. Bumping `MODEL_REVISION` re-downloads the artifacts.

### Reclaiming disk

Old images are not removed automatically; each rebuild leaves the previous one
untagged. Safe to run at any time:

```bash
docker system df           # see what is reclaimable
docker image prune -f      # dangling images only
docker builder prune -f    # build cache only
```

Never use `--volumes` or `docker volume prune` here: they destroy `caddy_data`
(the Let's Encrypt certificates, whose reissue is rate limited) and `pulse_data`
(the threat feed). Avoid `docker system prune -a`, which evicts the cached model
layer and forces a fresh 1.6 GB download.

## 7. Retire the temporary Space

Only after the Cloudflare API URL passes text and audio tests and Vercel has been
redeployed, pause or delete the Hugging Face Space. Keep the public Hugging Face
**model repository**: Docker uses it as the artifact source during builds.
