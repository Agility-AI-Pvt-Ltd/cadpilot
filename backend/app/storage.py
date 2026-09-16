import json
import re
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings
from app.schemas import ModelState

_IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class LocalStorage:
    """Project/version-scoped storage; replace this boundary with S3 later."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_settings().cad_storage_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_id(self, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("Invalid project or artifact identifier")
        return value

    def version_dir(self, project_id: str, version: int) -> Path:
        project_id = self._safe_id(project_id)
        if version < 1:
            raise ValueError("Version must be positive")
        path = self.root / "projects" / project_id / "versions" / f"v{version}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, project_id: str, version: int, filename: str) -> Path:
        if filename not in {
            "model.FCStd",
            "model.glb",
            "model.step",
            "model.stl",
            "model_state.json",
            "operation_history.json",
            "execution.log",
        }:
            raise ValueError("Unsupported artifact")
        return self.version_dir(project_id, version) / filename

    def write_state(self, project_id: str, version: int, state: ModelState) -> Path:
        path = self.artifact_path(project_id, version, "model_state.json")
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        return path

    def read_state(self, project_id: str, version: int) -> ModelState:
        return ModelState.model_validate_json(
            self.artifact_path(project_id, version, "model_state.json").read_text()
        )

    def write_history(self, project_id: str, version: int, history: list[dict]) -> None:
        self.artifact_path(project_id, version, "operation_history.json").write_text(
            json.dumps(history, indent=2), encoding="utf-8"
        )

    def open_artifact(self, project_id: str, version: int, filename: str) -> BinaryIO:
        return self.artifact_path(project_id, version, filename).open("rb")
