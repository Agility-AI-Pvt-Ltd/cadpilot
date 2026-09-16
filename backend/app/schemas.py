from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationType(StrEnum):
    CREATE_BOX = "create_box"
    CREATE_CYLINDER = "create_cylinder"


class FixedInputs(BaseModel):
    model_type: str = Field(min_length=1, max_length=64)
    facility_name: str | None = Field(default=None, max_length=120)
    length: float = Field(gt=0, le=100_000)
    width: float = Field(gt=0, le=100_000)
    height: float = Field(gt=0, le=100_000)
    units: Literal["mm", "cm", "m", "in", "ft"] = "mm"
    room_or_zone: str | None = Field(default=None, max_length=240)
    equipment_requirements: str | None = Field(default=None, max_length=2_000)
    material: str | None = Field(default=None, max_length=120)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    current_version: int = 0
    created_at: datetime


class GenerateRequest(BaseModel):
    fixed_inputs: FixedInputs
    additional_instruction: str = Field(default="", max_length=5_000)
    base_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)


class GenerationJobResponse(BaseModel):
    job_id: str
    project_id: str
    status: JobStatus


class ArtifactLinks(BaseModel):
    fcstd: str
    glb: str
    state: str


class JobResponse(GenerationJobResponse):
    version: int | None = None
    stage: str | None = None
    error: str | None = None
    artifacts: ArtifactLinks | None = None


class Placement(BaseModel):
    x: float = 0
    y: float = 0
    z: float = 0
    rotation: dict[str, float] = Field(
        default_factory=lambda: {"axis_x": 0, "axis_y": 0, "axis_z": 1, "angle": 0}
    )


class CADObject(BaseModel):
    object_id: str
    name: str
    type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    placement: Placement = Field(default_factory=Placement)
    parent_id: str | None = None


class Operation(BaseModel):
    type: OperationType
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    dimensions: dict[str, float]
    placement: Placement = Field(default_factory=Placement)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "Operation":
        required = (
            {"length", "width", "height"}
            if self.type == OperationType.CREATE_BOX
            else {"radius", "height"}
        )
        if set(self.dimensions) != required or any(
            value <= 0 or value > 100_000 for value in self.dimensions.values()
        ):
            raise ValueError(f"{self.type} requires positive {sorted(required)} dimensions")
        return self


class ModelState(BaseModel):
    model_id: str
    version: int
    objects: list[CADObject] = Field(default_factory=list)
    feature_history: list[dict[str, Any]] = Field(default_factory=list)
    last_operation: dict[str, Any] | None = None
    validation: dict[str, Any] = Field(default_factory=lambda: {"status": "unknown"})


class PlanResult(BaseModel):
    operation: Operation | None = None
    clarification: str | None = None


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class VersionConflictError(Exception):
    """Raised when a project changed after a generation request was created."""
