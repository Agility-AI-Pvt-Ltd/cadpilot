"""Deterministic FreeCAD execution double.

Shared by the unit tests (`tests/test_agent.py`) and the offline LangSmith
eval suite (`evals/`) so both exercise the exact same recovery-loop
semantics without a live FreeCAD/MCP stack. Never imported by production
code paths (`app.worker`, `app.main`).
"""

from app.schemas import CADObject, ModelState, Operation
from app.storage import LocalStorage


class FakeExecutor:
    """Stands in for `FreeCADExecutionLayer` with scriptable failure modes.

    - `fail_times` / `fail_once`: the next N `execute()` calls raise instead
      of producing artifacts, simulating a FreeCAD/MCP execution failure.
    - `omit_glb_once`: the next successful `execute()` writes every artifact
      except `model.glb`, simulating a partially generated model that fails
      post-execution validation.
    - `seed_objects`: objects `inspect()` reports before any operation has
      run in this fake, simulating a project that already has a model on
      disk (used to exercise the "existing model" clarification path).
    """

    def __init__(
        self,
        storage: LocalStorage,
        *,
        fail_once: bool = False,
        fail_times: int | None = None,
        omit_glb_once: bool = False,
        seed_objects: list[CADObject] | None = None,
    ) -> None:
        self.storage = storage
        self.remaining_failures = fail_times if fail_times is not None else (1 if fail_once else 0)
        self.omit_glb_once = omit_glb_once
        self.seed_objects = seed_objects
        self.last_operation: Operation | None = None

    async def inspect(self, project_id: str, version: int) -> ModelState:
        if self.last_operation:
            objects = [
                CADObject(
                    object_id=self.last_operation.name,
                    name=self.last_operation.name,
                    type="Part::Box",
                    parameters=self.last_operation.dimensions,
                )
            ]
        else:
            objects = self.seed_objects or []
        return ModelState(model_id=project_id, version=version, objects=objects)

    async def execute(self, project_id: str, version: int, operation: Operation) -> ModelState:
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise RuntimeError("simulated FreeCAD failure")
        self.last_operation = operation
        artifacts = ["model.FCStd", "model.glb", "model.stl"]
        if self.omit_glb_once:
            artifacts.remove("model.glb")
            self.omit_glb_once = False
        for artifact in artifacts:
            self.storage.artifact_path(project_id, version, artifact).write_bytes(b"artifact")
        return await self.inspect(project_id, version)
