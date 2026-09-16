"""Production-oriented LangGraph orchestration for validated text-to-CAD jobs.

The graph separates LLM planning from controlled CAD execution: no model output is
ever executed as FreeCAD Python or as a shell command.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from app.cad_execution import FreeCADExecutionLayer
from app.config import get_settings
from app.repository import Repository
from app.schemas import FixedInputs, ModelState, Operation, OperationType, PlanResult
from app.storage import LocalStorage

MAX_REPLANS = 2


class CADAgentState(TypedDict, total=False):
    project_id: str
    model_id: str
    model_version: int
    fixed_inputs: dict[str, Any]
    additional_instruction: str
    messages: list[dict[str, str]]
    current_model_state: dict[str, Any]
    planned_operation: dict[str, Any] | None
    clarification: str | None
    plan_validation: dict[str, Any]
    reserved_version: int | None
    execution_result: dict[str, Any]
    model_validation: dict[str, Any]
    artifacts: dict[str, str]
    final_response: dict[str, Any]
    error: str | None
    recovery_reason: str | None
    replan_count: int
    attempted_operations: list[dict[str, Any]]


class CADPlanner(Protocol):
    """Replacement seam for an LLM with strict structured output."""

    def plan(self, state: CADAgentState) -> PlanResult: ...


class BootstrapStructuredPlanner:
    """Deterministic safe baseline until a provider-specific structured planner is configured."""

    def plan(self, state: CADAgentState) -> PlanResult:
        fixed = FixedInputs.model_validate(state["fixed_inputs"])
        if (
            state.get("current_model_state", {}).get("objects")
            and state.get("replan_count", 0) == 0
        ):
            return PlanResult(
                clarification=(
                    "This initial toolset can create a new facility envelope but does not yet "
                    "support safe modification of an existing model."
                )
            )
        suffix = "" if state.get("replan_count", 0) == 0 else f"_retry{state['replan_count']}"
        return PlanResult(
            operation=Operation(
                type=OperationType.CREATE_BOX,
                name=f"FacilityEnvelope{suffix}",
                dimensions={"length": fixed.length, "width": fixed.width, "height": fixed.height},
            )
        )


class OpenAIStructuredPlanner:
    """Optional server-side planner that emits only a typed plan or clarification."""

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def plan(self, state: CADAgentState) -> PlanResult:
        response = self.client.responses.create(
            model=self.model,
            store=False,
            instructions=(
                "You are a CAD planning agent. Return only a supported structured operation or "
                "a clarification. Never return Python, shell commands, or file paths. The current "
                "FreeCAD state is authoritative. The only currently executable operation is "
                "create_box; request clarification for anything else."
            ),
            input=json.dumps(
                {
                    "fixed_inputs": state["fixed_inputs"],
                    "additional_instruction": state.get("additional_instruction", ""),
                    "current_model_state": state.get("current_model_state", {}),
                    "recent_memory": state.get("messages", [])[-12:],
                    "recovery_reason": state.get("recovery_reason"),
                    "attempted_operations": state.get("attempted_operations", []),
                }
            ),
            text={"format": _PLAN_RESPONSE_FORMAT},
        )
        return PlanResult.model_validate_json(response.output_text)


_PLAN_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "cad_operation_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": ["object", "null"],
                "properties": {
                    "type": {"type": "string", "enum": ["create_box"]},
                    "name": {"type": "string"},
                    "dimensions": {
                        "type": "object",
                        "properties": {
                            "length": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                        },
                        "required": ["length", "width", "height"],
                        "additionalProperties": False,
                    },
                    "placement": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "z": {"type": "number"},
                            "rotation": {
                                "type": "object",
                                "properties": {
                                    "axis_x": {"type": "number"},
                                    "axis_y": {"type": "number"},
                                    "axis_z": {"type": "number"},
                                    "angle": {"type": "number"},
                                },
                                "required": ["axis_x", "axis_y", "axis_z", "angle"],
                                "additionalProperties": False,
                            },
                        },
                        "required": ["x", "y", "z", "rotation"],
                        "additionalProperties": False,
                    },
                },
                "required": ["type", "name", "dimensions", "placement"],
                "additionalProperties": False,
            },
            "clarification": {"type": ["string", "null"]},
        },
        "required": ["operation", "clarification"],
        "additionalProperties": False,
    },
}


@dataclass(frozen=True)
class WorkflowServices:
    repository: Repository | None = None
    executor: FreeCADExecutionLayer | None = None
    storage: LocalStorage | None = None
    planner: CADPlanner | None = None
    on_stage: Callable[[str], None] = lambda _stage: None

    def resolved_executor(self) -> FreeCADExecutionLayer:
        return self.executor or FreeCADExecutionLayer(self.storage or LocalStorage())

    def resolved_storage(self) -> LocalStorage:
        return self.storage or LocalStorage()

    def resolved_planner(self) -> CADPlanner:
        if self.planner:
            return self.planner
        settings = get_settings()
        if settings.openai_api_key:
            return OpenAIStructuredPlanner(settings.openai_api_key, settings.openai_model)
        return BootstrapStructuredPlanner()


def _message(state: CADAgentState, role: str, content: str) -> list[dict[str, str]]:
    return [*state.get("messages", [])[-11:], {"role": role, "content": content}]


def receive_and_validate_request(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("validating_request")
    fixed = FixedInputs.model_validate(state["fixed_inputs"])
    return {
        "fixed_inputs": fixed.model_dump(),
        "additional_instruction": state.get("additional_instruction", ""),
        "replan_count": 0,
        "attempted_operations": [],
        "error": None,
        "clarification": None,
    }


def load_conversation_memory(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("loading_memory")
    # PostgresSaver retains a project thread. Only bounded relevant context reaches planning.
    return {"messages": state.get("messages", [])[-12:]}


def retrieve_current_model_state(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("inspecting_model_via_mcp")
    storage = services.resolved_storage()
    candidate = state.get("reserved_version")
    version = (
        candidate
        if candidate
        and storage.artifact_path(state["project_id"], candidate, "model.FCStd").is_file()
        else state["model_version"]
    )
    if version == 0:
        empty = ModelState(model_id=state["project_id"], version=0, validation={"status": "new"})
        return {"current_model_state": empty.model_dump(mode="json")}
    try:
        model_state = asyncio.run(
            services.resolved_executor().inspect(state["project_id"], version)
        )
        return {"current_model_state": model_state.model_dump(mode="json")}
    except Exception as exc:  # noqa: BLE001 - state failures are visible to planning/recovery
        return {
            "current_model_state": {
                "model_id": state["project_id"],
                "version": version,
                "objects": [],
            },
            "error": f"Could not inspect authoritative FreeCAD state: {exc}",
        }


def plan_cad_operation(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("planning")
    try:
        plan = services.resolved_planner().plan(state)
    except Exception as exc:  # noqa: BLE001 - provider failures enter the bounded recovery loop.
        return {"error": f"LLM planning failed: {exc}", "planned_operation": None}
    if plan.clarification:
        return {"clarification": plan.clarification, "planned_operation": None, "error": None}
    return {
        "planned_operation": plan.operation.model_dump() if plan.operation else None,
        "error": None,
    }


def route_plan(state: CADAgentState) -> str:
    if state.get("clarification"):
        return "clarify"
    if state.get("error"):
        return "recover" if state.get("replan_count", 0) < MAX_REPLANS else "failed"
    return "validate"


def validate_operation_plan(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("validating_plan")
    try:
        operation = Operation.model_validate(state.get("planned_operation"))
        if operation.type is not OperationType.CREATE_BOX:
            raise ValueError(
                f"Operation '{operation.type}' is not implemented by the FreeCAD worker"
            )
        object_ids = {
            item.get("object_id") for item in state["current_model_state"].get("objects", [])
        }
        attempted = {item.get("name") for item in state.get("attempted_operations", [])}
        if operation.name in object_ids:
            raise ValueError("A current CAD object already uses that stable ID")
        if operation.name in attempted:
            raise ValueError("Recovery cannot repeat the same operation")
        return {"plan_validation": {"valid": True}, "error": None}
    except (TypeError, ValueError) as exc:
        return {"plan_validation": {"valid": False, "error": str(exc)}, "error": str(exc)}


def route_plan_validation(state: CADAgentState) -> str:
    if state.get("plan_validation", {}).get("valid"):
        return "reserve"
    return "recover" if state.get("replan_count", 0) < MAX_REPLANS else "failed"


def reserve_model_version(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("reserving_model_version")
    if state.get("reserved_version"):
        return {}
    if not services.repository:
        return {"reserved_version": state["model_version"] + 1}
    return {
        "reserved_version": services.repository.reserve_next_version(
            state["project_id"], state["model_version"]
        )
    }


def execute_via_mcp(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("executing_freecad_via_mcp")
    try:
        operation = Operation.model_validate(state["planned_operation"])
        model_state = asyncio.run(
            services.resolved_executor().execute(
                state["project_id"], state["reserved_version"], operation
            )
        )
        return {
            "execution_result": {
                "success": True,
                "model_state": model_state.model_dump(mode="json"),
            },
            "attempted_operations": [
                *state.get("attempted_operations", []),
                operation.model_dump(mode="json"),
            ],
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - FreeCAD/MCP errors enter recovery with evidence.
        return {
            "execution_result": {"success": False, "error": str(exc)},
            "attempted_operations": [
                *state.get("attempted_operations", []),
                state.get("planned_operation", {}),
            ],
            "error": f"CAD execution failed: {exc}",
        }


def route_execution(state: CADAgentState) -> str:
    if state.get("execution_result", {}).get("success"):
        return "validate_model"
    return "recover" if state.get("replan_count", 0) < MAX_REPLANS else "failed"


def validate_resulting_model(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("validating_generated_model")
    try:
        version = state["reserved_version"]
        storage = services.resolved_storage()
        required = ["model.FCStd", "model.glb", "model.stl"]
        missing = [
            name
            for name in required
            if not storage.artifact_path(state["project_id"], version, name).is_file()
        ]
        if missing:
            raise ValueError(f"FreeCAD export missing: {', '.join(missing)}")
        authoritative = asyncio.run(
            services.resolved_executor().inspect(state["project_id"], version)
        )
        expected = Operation.model_validate(state["planned_operation"]).name
        if expected not in {obj.object_id for obj in authoritative.objects}:
            raise ValueError(
                f"Expected object '{expected}' is absent from the saved FreeCAD document"
            )
        authoritative.validation = {"status": "valid", "validated_via": "FreeCAD MCP inspection"}
        return {
            "model_validation": {
                "valid": True,
                "model_state": authoritative.model_dump(mode="json"),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - validation errors are recovery inputs.
        return {
            "model_validation": {"valid": False, "error": str(exc)},
            "error": f"Model validation failed: {exc}",
        }


def route_model_validation(state: CADAgentState) -> str:
    if state.get("model_validation", {}).get("valid"):
        return "persist"
    return "recover" if state.get("replan_count", 0) < MAX_REPLANS else "failed"


def save_model_artifacts(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("saving_artifacts")
    version = state["reserved_version"]
    model_state = ModelState.model_validate(state["model_validation"]["model_state"])
    storage = services.resolved_storage()
    storage.write_state(state["project_id"], version, model_state)
    storage.write_history(state["project_id"], version, model_state.feature_history)
    return {
        "artifacts": {
            "fcstd": f"/api/cad/projects/{state['project_id']}/versions/{version}/model",
            "glb": f"/api/cad/projects/{state['project_id']}/versions/{version}/model.glb",
            "state": f"/api/cad/projects/{state['project_id']}/versions/{version}/metadata",
        }
    }


def update_memory(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("updating_conversation_memory")
    return {
        "messages": _message(
            state,
            "assistant",
            f"Created model version {state['reserved_version']} using {state['planned_operation']['type']}.",
        )
    }


def complete(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("completed")
    return {
        "final_response": {
            "status": "completed",
            "version": state["reserved_version"],
            "artifacts": state["artifacts"],
        }
    }


def clarify(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("needs_clarification")
    return {"final_response": {"status": "needs_clarification", "message": state["clarification"]}}


def prepare_replan(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("recovering_and_replanning")
    reason = state.get("error") or "Operation could not be validated"
    return {
        "replan_count": state.get("replan_count", 0) + 1,
        "recovery_reason": reason,
        "messages": _message(state, "system", f"Recovery required. {reason}"),
        "planned_operation": None,
    }


def fail(state: CADAgentState, services: WorkflowServices) -> CADAgentState:
    services.on_stage("failed")
    return {
        "final_response": {
            "status": "failed",
            "error": state.get("error") or "CAD generation failed",
        }
    }


def build_generation_graph(
    *, services: WorkflowServices | None = None, checkpointer: Any | None = None
):
    services = services or WorkflowServices()
    graph = StateGraph(CADAgentState)
    graph.add_node("receive_request", lambda state: receive_and_validate_request(state, services))
    graph.add_node("load_memory", lambda state: load_conversation_memory(state, services))
    graph.add_node(
        "get_model_state_via_mcp", lambda state: retrieve_current_model_state(state, services)
    )
    graph.add_node("plan_cad_operation", lambda state: plan_cad_operation(state, services))
    graph.add_node("validate_plan", lambda state: validate_operation_plan(state, services))
    graph.add_node("reserve_version", lambda state: reserve_model_version(state, services))
    graph.add_node("call_mcp_cad_tool", lambda state: execute_via_mcp(state, services))
    graph.add_node("validate_model", lambda state: validate_resulting_model(state, services))
    graph.add_node("save_model", lambda state: save_model_artifacts(state, services))
    graph.add_node("update_memory", lambda state: update_memory(state, services))
    graph.add_node("return_result", lambda state: complete(state, services))
    graph.add_node("ask_clarification", lambda state: clarify(state, services))
    graph.add_node("replan", lambda state: prepare_replan(state, services))
    graph.add_node("failed", lambda state: fail(state, services))

    graph.add_edge(START, "receive_request")
    graph.add_edge("receive_request", "load_memory")
    graph.add_edge("load_memory", "get_model_state_via_mcp")
    graph.add_edge("get_model_state_via_mcp", "plan_cad_operation")
    graph.add_conditional_edges(
        "plan_cad_operation",
        route_plan,
        {
            "clarify": "ask_clarification",
            "validate": "validate_plan",
            "recover": "replan",
            "failed": "failed",
        },
    )
    graph.add_conditional_edges(
        "validate_plan",
        route_plan_validation,
        {"reserve": "reserve_version", "recover": "replan", "failed": "failed"},
    )
    graph.add_edge("reserve_version", "call_mcp_cad_tool")
    graph.add_conditional_edges(
        "call_mcp_cad_tool",
        route_execution,
        {"validate_model": "validate_model", "recover": "replan", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "validate_model",
        route_model_validation,
        {"persist": "save_model", "recover": "replan", "failed": "failed"},
    )
    graph.add_edge("save_model", "update_memory")
    graph.add_edge("update_memory", "return_result")
    graph.add_edge("return_result", END)
    graph.add_edge("ask_clarification", END)
    graph.add_edge("replan", "get_model_state_via_mcp")
    graph.add_edge("failed", END)
    return graph.compile(checkpointer=checkpointer, name="cadpilot_generation")
