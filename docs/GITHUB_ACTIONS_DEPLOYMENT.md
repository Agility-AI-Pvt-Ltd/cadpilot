# GitHub Actions deployment

The workflow in `.github/workflows/ci-cd.yml` runs backend lint/tests, a Next.js production build, and Docker Compose validation for every pull request and push. A successful push to `main` then deploys the API, frontend, and Caddy gateway to the single EC2 demo host.

It deliberately does **not** rebuild the FreeCAD worker on every push. The worker compiles official FreeCAD source and can take a long time on the demo VM. Use **Actions → CI and EC2 demo deployment → Run workflow**, then enable **Rebuild and restart the FreeCAD worker**, only when `worker/`, FreeCAD build settings, or backend code used by the worker has changed.

## Repository secrets

Create these under **Settings → Secrets and variables → Actions**. Use an environment named `production` as referenced by the workflow if you want approval gates or environment-scoped secrets.

| Secret | Value |
| --- | --- |
| `EC2_HOST` | The EC2 DNS name or public IP, for example `ec2-18-212-99-22.compute-1.amazonaws.com`. |
| `EC2_USER` | `ubuntu` for the current host. |
| `EC2_SSH_PRIVATE_KEY` | The complete contents of the deployment private key, including its BEGIN/END lines. Use a dedicated deploy key rather than a personal key when possible. |
| `EC2_SSH_KNOWN_HOSTS` | A pinned `known_hosts` entry for the host. This prevents accepting an unexpected SSH host key during deployment. |

Generate the host-key secret from a trusted operator machine, review its fingerprint against the EC2 console or a known-good connection, then save the output as `EC2_SSH_KNOWN_HOSTS`:

```sh
ssh-keyscan -H ec2-18-212-99-22.compute-1.amazonaws.com
```

Never commit `.env`, private keys, or `known_hosts` entries that expose internal host details. The workflow copies source with `rsync` but explicitly preserves the remote `/opt/cadpilot/.env`, `.env` backups, `storage/`, PostgreSQL volume data, and worker build logs.

## What a normal deployment does

1. GitHub Actions validates the backend, frontend, and Compose configuration.
2. It syncs the repository to `/opt/cadpilot/` on EC2.
3. It rebuilds/restarts `api`, `web`, and `gateway` only.
4. It checks `http://localhost/health` on EC2.

The remote `.env` is authoritative. Change deployment configuration or provider credentials directly on the host (or by a separate secrets-management process), then recreate the affected service. For example, after changing `OPENAI_BASE_URL`, `OPENAI_API_KEY`, or `OPENAI_MODEL`:

```sh
cd /opt/cadpilot
docker compose up -d api
```
