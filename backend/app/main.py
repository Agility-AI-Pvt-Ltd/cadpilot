from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.db import init_db
from app.repository import Repository
from app.schemas import (
    GenerateRequest,
    GenerationJobResponse,
    JobResponse,
    JobStatus,
    ProjectCreateRequest,
    ProjectResponse,
    VersionConflictError,
)
from app.storage import LocalStorage
from app.worker import generate_model


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="CadPilot API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_project(project_id: str):
    project = Repository().get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/cad/projects", response_model=ProjectResponse, status_code=201)
def create_project(request: ProjectCreateRequest) -> ProjectResponse:
    return Repository().create_project(request.name)


@app.get("/api/cad/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str) -> ProjectResponse:
    project = require_project(project_id)
    return ProjectResponse.model_validate(project, from_attributes=True)


@app.post(
    "/api/cad/projects/{project_id}/generate", response_model=GenerationJobResponse, status_code=202
)
def generate(project_id: str, request: GenerateRequest) -> GenerationJobResponse:
    require_project(project_id)
    try:
        job, created = Repository().create_job(project_id, request)
    except VersionConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    if created:
        generate_model.delay(job.job_id)
    return GenerationJobResponse(
        job_id=job.job_id, project_id=project_id, status=JobStatus(job.status)
    )


@app.get("/api/cad/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = Repository().get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    payload = job.result_json or {}
    return JobResponse(
        job_id=job.job_id,
        project_id=job.project_id,
        status=JobStatus(job.status),
        stage=job.stage,
        error=job.error,
        version=payload.get("version"),
        artifacts=payload.get("artifacts"),
    )


@app.get("/api/cad/projects/{project_id}/state")
def get_current_state(project_id: str):
    project = require_project(project_id)
    if project.current_version == 0:
        return {"model_id": project_id, "version": 0, "objects": []}
    return LocalStorage().read_state(project_id, project.current_version)


@app.get("/api/cad/projects/{project_id}/versions")
def list_versions(project_id: str) -> dict[str, list[int]]:
    project = require_project(project_id)
    return {"versions": list(range(1, project.current_version + 1))}


@app.get("/api/cad/projects/{project_id}/versions/{version}/metadata")
def get_metadata(project_id: str, version: int):
    require_project(project_id)
    try:
        return LocalStorage().read_state(project_id, version)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Version not found") from exc


@app.get("/api/cad/projects/{project_id}/versions/{version}/model")
def get_fcstd(project_id: str, version: int):
    require_project(project_id)
    return artifact_response(project_id, version, "model.FCStd", "application/octet-stream")


@app.get("/api/cad/projects/{project_id}/versions/{version}/model.glb")
def get_glb(project_id: str, version: int):
    require_project(project_id)
    return artifact_response(project_id, version, "model.glb", "model/gltf-binary")


def artifact_response(
    project_id: str, version: int, filename: str, media_type: str
) -> FileResponse:
    try:
        path = LocalStorage().artifact_path(project_id, version, filename)
    except ValueError as exc:
        raise HTTPException(404, "Version not found") from exc
    if not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path, media_type=media_type, filename=filename)
