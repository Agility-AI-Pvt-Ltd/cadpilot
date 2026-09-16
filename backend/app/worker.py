from contextlib import nullcontext

from celery import Celery

from app.agent import WorkflowServices, build_generation_graph
from app.cad_execution import FreeCADExecutionLayer
from app.config import get_settings
from app.repository import Repository
from app.schemas import GenerateRequest, JobStatus
from app.storage import LocalStorage


def persistent_checkpointer():
    """Use PostgreSQL LangGraph memory in deployment; retain a dependency-free local fallback."""
    if not settings.database_url.startswith("postgresql"):
        return nullcontext(None)
    from langgraph.checkpoint.postgres import PostgresSaver

    connection = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return PostgresSaver.from_conn_string(connection)


settings = get_settings()
celery_app = Celery("cadpilot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_default_queue="cad_tasks",
    task_routes={"app.worker.generate_model": {"queue": "cad_tasks"}},
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    task_soft_time_limit=270,
    task_always_eager=settings.celery_task_always_eager,
)


@celery_app.task(name="app.worker.generate_model", bind=True, autoretry_for=(), acks_late=True)
def generate_model(self, job_id: str) -> dict:
    repo = Repository()
    job = repo.get_job(job_id)
    if not job:
        raise KeyError(job_id)
    try:
        repo.update_job(job_id, status=JobStatus.RUNNING, stage="starting_agent")
        request = GenerateRequest.model_validate(job.request_json)
        services = WorkflowServices(
            repository=repo,
            storage=LocalStorage(),
            executor=FreeCADExecutionLayer(),
            on_stage=lambda stage: repo.update_job(job_id, stage=stage),
        )
        with persistent_checkpointer() as checkpointer:
            if checkpointer:
                checkpointer.setup()
            graph = build_generation_graph(services=services, checkpointer=checkpointer)
            state = graph.invoke(
                {
                    "project_id": job.project_id,
                    "model_id": job.project_id,
                    "model_version": job.base_version,
                    "fixed_inputs": request.fixed_inputs.model_dump(),
                    "additional_instruction": request.additional_instruction,
                },
                config={
                    "configurable": {"thread_id": job.project_id},
                    # Labels this run in LangSmith when LANGSMITH_TRACING is on
                    # (see app.config._configure_langsmith); harmless no-op otherwise.
                    "run_name": "cadpilot_generation",
                    "tags": ["cadpilot", "worker", f"model_type:{request.fixed_inputs.model_type}"],
                    "metadata": {
                        "project_id": job.project_id,
                        "job_id": job_id,
                        "base_version": job.base_version,
                        "model_type": request.fixed_inputs.model_type,
                    },
                },
            )
        result = state.get(
            "final_response", {"status": "failed", "error": "Workflow ended without a result"}
        )
        if result["status"] == "needs_clarification":
            repo.update_job(
                job_id,
                status=JobStatus.FAILED,
                stage="needs_clarification",
                error=result["message"],
            )
            return result
        if result["status"] != "completed":
            raise ValueError(result.get("error", "CAD generation failed"))
        repo.update_job(job_id, status=JobStatus.COMPLETED, stage="completed", result=result)
        return result
    except Exception as exc:
        repo.update_job(job_id, status=JobStatus.FAILED, stage="failed", error=str(exc))
        raise
