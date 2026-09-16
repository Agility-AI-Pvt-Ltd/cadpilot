"""Runs the CadPilot agent recovery-loop suite through LangSmith `evaluate()`.

Usage (from `backend/`, after `uv sync --group dev --group evals`):

    uv run python -m evals.run_evals

Requires `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env` (see
`.env.example`); the run and every eval-graded trace show up in the
`LANGSMITH_PROJECT` project. Each example runs the real compiled graph
(`app.agent.build_generation_graph`) against a scripted `FakeExecutor`
double, so this is fully offline: no live FreeCAD/MCP stack or LLM call
is needed to grade the agent's recovery behavior.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from langsmith import Client
from langsmith.evaluation import evaluate

from app.agent import BootstrapStructuredPlanner, WorkflowServices, build_generation_graph
from app.config import get_settings
from app.fakes import FakeExecutor
from app.schemas import CADObject
from app.storage import LocalStorage
from evals.dataset import DATASET_DESCRIPTION, DATASET_NAME, EXAMPLES


def _sync_dataset(client: Client) -> str:
    """Recreate the dataset from `evals/dataset.py` so LangSmith always matches the code."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        client.delete_dataset(dataset_name=DATASET_NAME)
    dataset = client.create_dataset(dataset_name=DATASET_NAME, description=DATASET_DESCRIPTION)
    client.create_examples(
        dataset_id=dataset.id,
        examples=[{"inputs": ex["inputs"], "outputs": ex["outputs"]} for ex in EXAMPLES],
    )
    return DATASET_NAME


def _build_executor(storage: LocalStorage, spec: dict[str, Any]) -> FakeExecutor:
    seed_objects = None
    if spec.get("seed_objects"):
        seed_objects = [
            CADObject(
                object_id="ExistingEnvelope",
                name="ExistingEnvelope",
                type="Part::Box",
                parameters={"length": 10, "width": 10, "height": 10},
            )
        ]
    return FakeExecutor(
        storage,
        fail_times=spec.get("fail_times", 0),
        omit_glb_once=spec.get("omit_glb_once", False),
        seed_objects=seed_objects,
    )


def target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Runs one dataset example through the real compiled graph."""
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorage(Path(tmp))
        stages: list[str] = []
        services = WorkflowServices(
            storage=storage,
            executor=_build_executor(storage, inputs.get("executor", {})),
            planner=BootstrapStructuredPlanner(),
            on_stage=stages.append,
        )
        graph = build_generation_graph(services=services)
        result = graph.invoke(inputs["state"])
        return {
            "status": result.get("final_response", {}).get("status"),
            "replan_count": result.get("replan_count", 0),
            "attempted_operation_names": [
                op.get("name") for op in result.get("attempted_operations", [])
            ],
            "stages": stages,
        }


def status_matches(outputs: dict, reference_outputs: dict) -> dict:
    expected = reference_outputs["expected_status"]
    actual = outputs.get("status")
    return {
        "key": "reaches_expected_status",
        "score": actual == expected,
        "comment": f"expected={expected!r} actual={actual!r}",
    }


def replan_budget_respected(outputs: dict, reference_outputs: dict) -> dict:
    limit = reference_outputs["max_replan_count"]
    actual = outputs.get("replan_count", 0)
    return {
        "key": "replan_budget_respected",
        "score": actual <= limit,
        "comment": f"limit={limit} actual={actual}",
    }


def never_repeats_an_attempted_operation(outputs: dict) -> dict:
    names = outputs.get("attempted_operation_names", [])
    return {
        "key": "no_blind_repeat",
        "score": len(names) == len(set(names)),
        "comment": f"attempted={names}",
    }


def reinspects_state_before_replanning(outputs: dict, reference_outputs: dict) -> dict:
    if not reference_outputs.get("requires_state_reinspection"):
        return {"key": "reinspects_state_before_replanning", "score": True}
    stages = outputs.get("stages", [])
    if "recovering_and_replanning" not in stages:
        return {
            "key": "reinspects_state_before_replanning",
            "score": False,
            "comment": "recovery never happened",
        }
    recovery_index = stages.index("recovering_and_replanning")
    reinspected = "inspecting_model_via_mcp" in stages[recovery_index + 1 :]
    return {"key": "reinspects_state_before_replanning", "score": reinspected}


def main() -> None:
    settings = get_settings()
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        raise SystemExit(
            "Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env before running evals."
        )
    client = Client()
    dataset_name = _sync_dataset(client)
    evaluate(
        target,
        data=dataset_name,
        evaluators=[
            status_matches,
            replan_budget_respected,
            never_repeats_an_attempted_operation,
            reinspects_state_before_replanning,
        ],
        experiment_prefix="cadpilot-agent-recovery",
        metadata={"planner": "BootstrapStructuredPlanner"},
        client=client,
    )


if __name__ == "__main__":
    main()
