# Production deployment

The production backend runs as the original Docker/FastAPI service on one
DigitalOcean Droplet. Hugging Face is used only as a public artifact registry for
the pinned ONNX files during the Docker build; it is not in the request path.

Compose brings up three containers: `api` (FastAPI and the ONNX models), `db`
(Postgres, backing the anonymous Scam Pulse feed and reachable only over the
private compose network), and `caddy` (TLS termination). Postgres is optional to
the product — if it is down, analyses continue and `/health` reports
`pulse: false`.

See [`digitalocean/DEPLOY.md`](digitalocean/DEPLOY.md) for the complete setup.

