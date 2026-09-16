"""Behavioral regression dataset for the CadPilot LangGraph agent.

Every example exercises the agent's recovery contract deterministically:
bounded re-planning, forced re-inspection of authoritative FreeCAD state
before a retry, and never repeating an attempted operation. Each example
selects a scripted `FakeExecutor` behavior (see `app.fakes`) instead of a
live FreeCAD/MCP stack or a real LLM call, so the suite runs the same way
in CI, locally, and as a LangSmith experiment.

This is a graph-wiring/regression suite, not an LLM-output-quality eval:
`run_evals.py` pins `BootstrapStructuredPlanner` for every example so
results are reproducible. Once prompts for `OpenAIStructuredPlanner` are
being iterated on, add a second suite that points `target()` at it and
scores plan quality instead of graph control flow.
"""

from __future__ import annotations

from typing import Any

DATASET_NAME = "cadpilot-agent-recovery"
DATASET_DESCRIPTION = (
    "Deterministic recovery-loop scenarios for the CadPilot LangGraph agent: "
    "bounded re-planning, forced state re-inspection, and no blind repeats."
)

_BASE_FIXED_INPUTS = {
    "model_type": "plant",
    "length": 100,
    "width": 50,
    "height": 20,
    "units": "mm",
}


def _initial_state(**overrides: Any) -> dict:
    state = {
        "project_id": "eval_project",
        "model_id": "eval_project",
        "model_version": 0,
        "fixed_inputs": _BASE_FIXED_INPUTS,
        "additional_instruction": "Leave maintenance access",
    }
    state.update(overrides)
    return state


EXAMPLES: list[dict[str, Any]] = [
    {
        "inputs": {
            "scenario": "happy_path",
            "state": _initial_state(),
            "executor": {},
        },
        "outputs": {
            "expected_status": "completed",
            "max_replan_count": 0,
            "requires_state_reinspection": False,
        },
    },
    {
        "inputs": {
            "scenario": "recovers_from_execution_failure",
            "state": _initial_state(),
            "executor": {"fail_times": 1},
        },
        "outputs": {
            "expected_status": "completed",
            "max_replan_count": 1,
            "requires_state_reinspection": False,
        },
    },
    {
        "inputs": {
            "scenario": "recovers_from_model_validation_failure",
            "state": _initial_state(),
            "executor": {"omit_glb_once": True},
        },
        "outputs": {
            "expected_status": "completed",
            "max_replan_count": 1,
            "requires_state_reinspection": True,
        },
    },
    {
        "inputs": {
            "scenario": "asks_for_clarification_on_existing_model",
            "state": _initial_state(model_version=1),
            "executor": {"seed_objects": True},
        },
        "outputs": {
            "expected_status": "needs_clarification",
            "max_replan_count": 0,
            "requires_state_reinspection": False,
        },
    },
    {
        "inputs": {
            "scenario": "fails_within_budget_when_execution_never_succeeds",
            "state": _initial_state(),
            "executor": {"fail_times": 10},
        },
        "outputs": {
            "expected_status": "failed",
            "max_replan_count": 2,
            "requires_state_reinspection": False,
        },
    },
]
