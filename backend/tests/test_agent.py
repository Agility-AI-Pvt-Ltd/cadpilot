from pathlib import Path

from app.agent import MAX_REPLANS, OpenAIStructuredPlanner, WorkflowServices, build_generation_graph
from app.fakes import FakeExecutor
from app.storage import LocalStorage


def initial_state() -> dict:
    return {
        "project_id": "prj_demo",
        "model_id": "prj_demo",
        "model_version": 0,
        "fixed_inputs": {
            "model_type": "plant",
            "length": 100,
            "width": 50,
            "height": 20,
            "units": "mm",
        },
        "additional_instruction": "Leave maintenance access",
    }


def test_full_graph_generates_validated_artifacts_and_updates_memory(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    stages: list[str] = []
    graph = build_generation_graph(
        services=WorkflowServices(
            storage=storage, executor=FakeExecutor(storage), on_stage=stages.append
        )
    )

    result = graph.invoke(initial_state())

    assert result["final_response"]["status"] == "completed"
    assert result["final_response"]["version"] == 1
    assert "get_model_state_via_mcp" in graph.get_graph().nodes
    assert stages == [
        "validating_request",
        "loading_memory",
        "inspecting_model_via_mcp",
        "planning",
        "validating_plan",
        "reserving_model_version",
        "executing_freecad_via_mcp",
        "validating_generated_model",
        "saving_artifacts",
        "updating_conversation_memory",
        "completed",
    ]


def test_execution_failure_returns_to_state_and_replans_without_repeating(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    graph = build_generation_graph(
        services=WorkflowServices(storage=storage, executor=FakeExecutor(storage, fail_once=True))
    )

    result = graph.invoke(initial_state())

    assert result["final_response"]["status"] == "completed"
    assert result["replan_count"] == 1
    assert [item["name"] for item in result["attempted_operations"]] == [
        "FacilityEnvelope",
        "FacilityEnvelope_retry1",
    ]


def test_repeated_execution_failures_fail_within_the_replan_budget(tmp_path: Path):
    """route_execution used to recover unconditionally on any execution error,
    so an executor that never succeeds (e.g. a dead MCP server) would loop
    between call_mcp_cad_tool and replan forever instead of ever returning a
    result. It must respect MAX_REPLANS exactly like the other three
    recovery gates (route_plan, route_plan_validation, route_model_validation).
    """
    storage = LocalStorage(tmp_path)
    graph = build_generation_graph(
        services=WorkflowServices(storage=storage, executor=FakeExecutor(storage, fail_times=10))
    )

    result = graph.invoke(initial_state())

    assert result["final_response"]["status"] == "failed"
    assert result["replan_count"] == MAX_REPLANS
    attempted_names = [item.get("name") for item in result["attempted_operations"]]
    assert len(attempted_names) == len(set(attempted_names))


def test_model_validation_failure_reinspects_state_and_replans(tmp_path: Path):
    storage = LocalStorage(tmp_path)
    stages: list[str] = []
    graph = build_generation_graph(
        services=WorkflowServices(
            storage=storage,
            executor=FakeExecutor(storage, omit_glb_once=True),
            on_stage=stages.append,
        )
    )

    result = graph.invoke(initial_state())

    assert result["final_response"]["status"] == "completed"
    assert result["replan_count"] == 1
    assert "Model validation failed: FreeCAD export missing: model.glb" in result["recovery_reason"]
    validation_index = stages.index("validating_generated_model")
    recovery_index = stages.index("recovering_and_replanning")
    assert stages[validation_index + 1 : recovery_index + 2] == [
        "recovering_and_replanning",
        "inspecting_model_via_mcp",
    ]


def test_openai_planner_requires_strict_structured_plan():
    class FakeResponses:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return type(
                "Response",
                (),
                {
                    "output_text": (
                        '{"operation":{"type":"create_box","name":"Envelope",'
                        '"dimensions":{"length":10,"width":10,"height":10},'
                        '"placement":{"x":0,"y":0,"z":0,"rotation":'
                        '{"axis_x":0,"axis_y":0,"axis_z":1,"angle":0}}},'
                        '"clarification":null}'
                    )
                },
            )()

    responses = FakeResponses()
    planner = OpenAIStructuredPlanner("test-key", "test-model")
    planner.client = type("Client", (), {"responses": responses})()

    plan = planner.plan(initial_state())

    assert plan.operation and plan.operation.name == "Envelope"
    assert responses.kwargs["text"]["format"]["strict"] is True
    assert "current_model_state" in responses.kwargs["input"]
