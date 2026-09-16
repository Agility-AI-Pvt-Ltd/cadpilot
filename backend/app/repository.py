from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.db import JobRecord, ProjectRecord, SessionLocal
from app.schemas import GenerateRequest, JobStatus, ProjectResponse, VersionConflictError


class Repository:
    def create_project(self, name: str) -> ProjectResponse:
        project = ProjectRecord(project_id=f"prj_{uuid4().hex[:16]}", name=name)
        with SessionLocal.begin() as session:
            session.add(project)
        return ProjectResponse.model_validate(project, from_attributes=True)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with SessionLocal() as session:
            return session.get(ProjectRecord, project_id)

    def create_job(self, project_id: str, request: GenerateRequest) -> tuple[JobRecord, bool]:
        with SessionLocal.begin() as session:
            existing = session.scalar(
                select(JobRecord).where(JobRecord.idempotency_key == request.idempotency_key)
            )
            if existing:
                return existing, False
            project = session.get(ProjectRecord, project_id)
            if not project:
                raise KeyError(project_id)
            if project.current_version != request.base_version:
                raise VersionConflictError(
                    f"Expected v{request.base_version}; current model is v{project.current_version}"
                )
            job = JobRecord(
                job_id=f"job_{uuid4().hex}",
                project_id=project_id,
                idempotency_key=request.idempotency_key,
                base_version=request.base_version,
                status=JobStatus.QUEUED,
                stage="queued",
                request_json=request.model_dump(mode="json"),
            )
            session.add(job)
            return job, True

    def get_job(self, job_id: str) -> JobRecord | None:
        with SessionLocal() as session:
            return session.get(JobRecord, job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        stage: str | None = None,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        with SessionLocal.begin() as session:
            job = session.get(JobRecord, job_id)
            if not job:
                raise KeyError(job_id)
            if status is not None:
                job.status = status
            if stage is not None:
                job.stage = stage
            if result is not None:
                job.result_json = result
            if error is not None:
                job.error = error
            job.updated_at = datetime.now(UTC)

    def reserve_next_version(self, project_id: str, expected_base: int) -> int:
        with SessionLocal.begin() as session:
            project = session.get(ProjectRecord, project_id, with_for_update=True)
            if not project:
                raise KeyError(project_id)
            if project.current_version != expected_base:
                raise VersionConflictError(
                    f"Model was modified; expected v{expected_base}, found v{project.current_version}"
                )
            project.current_version += 1
            return project.current_version
