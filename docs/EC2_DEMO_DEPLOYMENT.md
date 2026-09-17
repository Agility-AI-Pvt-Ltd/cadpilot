# Single-EC2 demo deployment

This demo uses Docker Compose on one EC2 host. It intentionally has no ECS service, autoscaling policy, load balancer, or multiple FreeCAD workers.

```text
Internet :80 → Caddy → Next.js frontend / FastAPI API
                               │
                  Redis + PostgreSQL + one Celery/FreeCAD worker
```

Only port 80 is exposed by Compose. Redis, PostgreSQL, FastAPI, and Next.js remain on the private Docker network. The worker has one Celery process and one concurrent FreeCAD job.

## EC2 prerequisites

- Ubuntu 24.04 with at least 4 vCPU, 16 GB RAM, and 50 GB free disk space.
- A security-group inbound rule for TCP 80 from the intended demo audience. Restrict SSH/TCP 22 to the operator's address.
- Docker Engine with the Docker Compose plugin.

The first image build is slow because it compiles the official FreeCAD source. Build once on the host, or build/push the worker image from CI later. Do not build FreeCAD each time a container restarts.

## Deploy

1. Copy the source to `/opt/cadpilot`, then create `/opt/cadpilot/.env` from `.env.example`.
2. Set `FREECAD_REF` to a reviewed immutable FreeCAD commit SHA. Leave `OPENAI_API_KEY` blank to use the safe deterministic planner, or set it to enable structured LLM planning.
3. Run `docker compose up -d --build`.
4. Monitor `docker compose ps` and `docker compose logs -f cad-worker` until the first source build and worker startup finish.
5. Visit `http://EC2_PUBLIC_IP/health` and then `http://EC2_PUBLIC_IP/`.

## Demo operations

```sh
cd /opt/cadpilot
docker compose ps
docker compose logs -f gateway api cad-worker
docker compose up -d --build
```

Persisted model files are in `/opt/cadpilot/storage`; PostgreSQL uses the named `postgres_data` volume. Back up both before rebuilding the host.

For automated deployments from `main`, follow [GitHub Actions deployment](GITHUB_ACTIONS_DEPLOYMENT.md). The CI workflow preserves this host's `.env` and persistent data, and only rebuilds the long-running FreeCAD worker when manually requested.
