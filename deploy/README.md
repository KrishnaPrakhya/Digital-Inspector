# Production deployment

The production backend runs as the original Docker/FastAPI service on one
DigitalOcean Droplet. Hugging Face is used only as a public artifact registry for
the pinned ONNX files during the Docker build; it is not in the request path.

See [`digitalocean/DEPLOY.md`](digitalocean/DEPLOY.md) for the complete setup.

