# DigitalOcean production deployment

This deploys the complete torch-free FastAPI backend on one persistent Droplet.
The browser calls the original `/api/v1/*` REST contract directly; there is no
Gradio queue or ZeroGPU quota.

## 1. Create the Droplet

In DigitalOcean, first confirm the GitHub Student Pack credit appears under
**Billing**. Create a Droplet with:

- Ubuntu 24.04 LTS
- Basic, Regular SSD
- 8 GiB RAM / 4 shared vCPU
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

Set `API_DOMAIN`, `TLS_EMAIL`, `GROQ_API_KEY`, and `PROD_VERCEL_URL`. Keep the
pinned model repository and revision unchanged.

## 4. Build and start

```bash
cd /opt/digital-inspector/deploy/digitalocean
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

Port 7860 is intentionally not published to the host or public internet.

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
docker compose up -d --build
```

## 7. Retire the temporary Space

Only after the Cloudflare API URL passes text and audio tests and Vercel has been
redeployed, pause or delete the Hugging Face Space. Keep the public Hugging Face
**model repository**: Docker uses it as the artifact source during builds.
