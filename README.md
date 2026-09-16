# CadPilot

An initial, production-oriented text-to-CAD vertical slice: a single Next.js module submits a structured plant envelope request, FastAPI queues it through Redis/Celery, a LangGraph workflow validates a plan, and a FreeCAD worker calls FreeCAD through MCP to generate FCStd and GLB artifacts.

## Repository layout

- `frontend/` — one embeddable `CadStudio` page module and Three.js GLB viewer.
- `backend/` — FastAPI, typed LangGraph workflow, Celery task, MCP adapter, storage/versioning layer, and tests.
- `worker/` — dedicated FreeCAD/Celery image entrypoint.
- `docs/ARCHITECTURE.md` — boundaries, safety model, GLB pipeline, and scaling design.

## Run locally

1. Copy `.env.example` to `.env` and adjust values.
2. Set `FREECAD_REF` to the official FreeCAD commit SHA you approve. The worker builds [FreeCAD/FreeCAD](https://github.com/FreeCAD/FreeCAD) using its Pixi/CMake release build and exposes its headless `freecadcmd`; use `main` only for development.
3. The FreeCAD MCP server is started as `uvx freecad-mcp --only-text-feedback`. The initial worker uses its `execute_code_headless` path, so it does not require the GUI addon/RPC service.
4. Run `docker compose up --build`.
5. Open `http://localhost:3000`; create a project, enter dimensions, and generate a model.

The worker needs substantial RAM for FreeCAD. Start with an EC2 instance providing at least 4 vCPU and 16 GB RAM, then size it against representative documents. Keep Redis private, persist the `storage` volume, back it up, and put authentication in front of project routes before exposing the service.

## Test and validate

```sh
cd backend && uv sync --group dev && uv run pytest
cd ../frontend && npm install && npm run build
```

Most tests use the typed workflow and mocked execution boundary. Add FreeCAD integration tests to a worker-capable CI runner for primitive generation, saving, and GLB conversion.

## Tracing and evals (LangSmith)

Set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env` (see `.env.example`) to send every generation run's LangGraph trace — including replans and state re-inspections — to LangSmith; leave `LANGSMITH_TRACING=false` to keep the worker fully offline. With those same variables set, run the deterministic recovery-loop eval suite:

```sh
cd backend && uv sync --group dev --group evals && uv run python -m evals.run_evals
```

See `docs/ARCHITECTURE.md#observability-and-evals` for what each run checks.

## Current vertical-slice limits

The safe first execution operation is `create_box`. Adding tanks, rooms, equipment, booleans, and edits means adding a typed `Operation` schema, a validator, and a fixed script template—not allowing arbitrary LLM code. When `OPENAI_API_KEY` is set, the planner node uses strict structured output; otherwise it uses a deterministic local planner through the same interface.
# cadpilot
# cadpilot
