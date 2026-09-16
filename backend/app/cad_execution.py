import asyncio
import json
from pathlib import Path

from app.mcp_client import CadScriptCompiler, FreeCADMCPClient
from app.schemas import CADObject, ModelState, Operation, OperationType
from app.storage import LocalStorage


class FreeCADExecutionLayer:
    """Worker-side execution adapter. Geometry remains authored by FreeCAD."""

    def __init__(
        self, storage: LocalStorage | None = None, mcp: FreeCADMCPClient | None = None
    ) -> None:
        self.storage = storage or LocalStorage()
        self.mcp = mcp or FreeCADMCPClient()

    async def execute(self, project_id: str, version: int, operation: Operation) -> ModelState:
        fcstd = self.storage.artifact_path(project_id, version, "model.FCStd")
        stl = self.storage.artifact_path(project_id, version, "model.stl")
        if operation.type is not OperationType.CREATE_BOX:
            raise ValueError(f"Vertical slice does not support {operation.type}")
        script = CadScriptCompiler.create_box(
            name=operation.name,
            **operation.dimensions,
            x=operation.placement.x,
            y=operation.placement.y,
            z=operation.placement.z,
            fcstd_path=str(fcstd),
            stl_path=str(stl),
        )
        result = await self.mcp.execute_headless(script)
        if not result.success:
            raise RuntimeError(result.error or "FreeCAD MCP headless execution failed")
        payload = self._extract_result(result.data["content"])
        await asyncio.to_thread(
            self._convert_stl_to_glb,
            stl,
            self.storage.artifact_path(project_id, version, "model.glb"),
            payload,
        )
        objects = [CADObject.model_validate(item) for item in payload["objects"]]
        return ModelState(
            model_id=project_id,
            version=version,
            objects=objects,
            feature_history=[operation.model_dump()],
            last_operation={"type": operation.type, "status": "success"},
            validation={"status": "valid"},
        )

    async def inspect(self, project_id: str, version: int) -> ModelState:
        """Inspect the saved FCStd through MCP/FreeCAD, never an LLM-side approximation."""
        fcstd = self.storage.artifact_path(project_id, version, "model.FCStd")
        if not fcstd.is_file():
            raise FileNotFoundError(f"No FreeCAD document for {project_id} v{version}")
        result = await self.mcp.execute_headless(CadScriptCompiler.inspect_document(str(fcstd)))
        if not result.success:
            raise RuntimeError(result.error or "FreeCAD MCP inspection failed")
        payload = self._extract_marker(result.data["content"], "CADPILOT_STATE=")
        return ModelState(
            model_id=project_id,
            version=version,
            objects=[CADObject.model_validate(item) for item in payload["objects"]],
            feature_history=payload.get("feature_history", []),
            last_operation=payload.get("last_operation"),
            validation={"status": "inspected"},
        )

    @staticmethod
    def _extract_result(output: str) -> dict:
        return FreeCADExecutionLayer._extract_marker(output, "CADPILOT_RESULT=")

    @staticmethod
    def _extract_marker(output: str, marker: str) -> dict:
        for line in output.splitlines():
            if line.startswith(marker):
                return json.loads(line.removeprefix(marker))
        raise RuntimeError(f"FreeCAD completed without structured output ({marker})")

    @staticmethod
    def _convert_stl_to_glb(stl: Path, glb: Path, payload: dict) -> None:
        import trimesh

        mesh = trimesh.load_mesh(stl, force="mesh")
        mesh.metadata["cad_objects"] = payload["objects"]
        mesh.export(glb, file_type="glb")
