# Project: AI-Powered Text-to-CAD Interactive Plant Viewer

## 1. Role and objective

You are a senior full-stack AI engineer and software architect. Implement a production-oriented, modular text-to-CAD system that integrates into an existing AI application.

The system allows users to describe a 3D plant, room, equipment layout, or other CAD model through structured form inputs and natural-language instructions. An LLM agent uses LangGraph and an MCP client to inspect the current CAD model, plan operations, and invoke FreeCAD tools. FreeCAD executes the operations in an isolated worker container. The resulting model is saved in multiple formats, including a web-viewable GLB file for an interactive Three.js viewer.

The UI must be a single-page React/Next.js module that can be integrated into a larger existing application. Do not build an entire new website, dashboard, or multi-page application.

The implementation must be modular, maintainable, testable, and suitable for eventual deployment on AWS ECS using EC2 capacity.

---

# 2. Mandatory technology stack

## Frontend

- React / Next.js.
    
- TypeScript.
    
- Three.js for 3D rendering.
    
- OrbitControls for camera interaction.
    
- GLB / glTF for browser-viewable 3D models.
    
- One integrated page only.
    
- UI must be responsive and suitable for integration into a larger application.
    

## Backend

- Python.
    
- FastAPI.
    
- LangGraph for the AI agent workflow.
    
- MCP client is mandatory.
    
- Redis as the message broker and queue.
    
- Celery for background task management and worker execution.
    

## CAD engine

- FreeCAD.
    
- FreeCAD Python API for CAD operations.
    
- FreeCAD MCP server or an MCP server implemented for this application.
    
- FreeCAD worker runs in a dedicated container.
    

## Storage

Support storing multiple files associated with a CAD project and model version:

- Native FreeCAD `.FCStd` document.
    
- GLB model for browser viewing.
    
- Optional STEP export.
    
- Optional STL export.
    
- JSON metadata and textual model state.
    
- Operation history and execution logs.
    

Use a storage abstraction so the initial implementation can use local disk or mounted volumes, with a future path to object storage such as S3.

## Deployment

Initial deployment:

- One EC2 instance.
    
- Docker containers.
    
- One FreeCAD worker container initially.
    
- Redis and Celery.
    

Future deployment:

- ECS cluster using EC2 capacity.
    
- Horizontally scalable FreeCAD worker containers.
    
- Separate API and CAD worker infrastructure when required.
    

Do not implement ECS provisioning as the initial requirement. Design the application so it can be deployed there later.

---

# 3. Core architecture

Implement the following logical architecture:

User → React/Next.js UI → FastAPI → LangGraph Agent → MCP Client → FreeCAD MCP Server / FreeCAD Execution Layer → FreeCAD Worker Container → Model Storage → FastAPI → Three.js Viewer.

Redis and Celery are used for background CAD execution:

FastAPI / LangGraph → Redis broker → Celery task → FreeCAD worker container.

Important distinctions:

- Redis is the message broker that holds pending task messages.
    
- Celery manages background tasks and workers.
    
- The FreeCAD worker performs the actual CAD computation.
    
- MCP is the standardized tool interface used by the LLM agent.
    
- FreeCAD is the source of truth for actual CAD geometry and document state.
    
- LangGraph manages agent reasoning, conversation memory, and workflow transitions.
    

Do not confuse the MCP server, Celery worker, and FreeCAD engine. They are separate logical responsibilities, even if some are colocated in the initial deployment.

---

# 4. User interface requirements

Create one standalone page or page-level component that can be embedded into an existing application.

The UI should include:

## A. Project and model section

- Project name.
    
- Model ID or project ID.
    
- New model / create project action.
    
- Current model version.
    
- Model status: idle, queued, running, completed, failed.
    
- Loading and error states.
    

## B. Fixed user input form

Provide clearly labeled fixed textboxes for common CAD requirements. The exact domain can be plant design, rooms, or equipment layouts, but the form must remain extensible.

Example fields:

- Model type.
    
- Plant or facility name.
    
- Overall length.
    
- Overall width.
    
- Overall height.
    
- Units.
    
- Room or zone information.
    
- Equipment requirements.
    
- Material or construction preferences.
    
- Additional fixed domain-specific fields.
    

Use appropriate validation for numeric dimensions, units, required values, and invalid inputs.

Do not force every possible CAD requirement into fixed fields.

## C. Independent additional-instruction textbox

Provide one independent multiline input box that accepts arbitrary natural-language instructions not represented by the fixed fields.

Example:

"Create a cylindrical storage tank on the left side, add a platform around it, and leave enough space for maintenance access."

This textbox must be sent to the LangGraph agent along with all fixed form values.

The backend must not discard or overwrite additional instructions.

## D. Generate model action

The user should be able to submit the complete form and additional instructions.

The frontend sends a structured request to FastAPI. The backend creates a CAD generation job.

The UI should show:

- Job ID.
    
- Current status.
    
- Progress or stage information.
    
- Errors if execution fails.
    
- A way to refresh or poll job status.
    
- The resulting model when ready.
    

Avoid blocking the browser request while FreeCAD performs long-running work.

## E. Interactive 3D viewer

Display the generated GLB model using Three.js.

Required mouse controls:

1. Left-click + drag: Rotate the 3D model.
    
2. Mouse wheel: Zoom in and out.
    
3. Right-click + drag / middle mouse: Pan the view, depending on the configured controls.
    
4. Click an object: Select a room or piece of equipment and show its properties.
    

Use OrbitControls or an equivalent supported Three.js control.

The viewer must support:

- Model loading states.
    
- Model loading errors.
    
- Camera reset.
    
- Fit-to-model behavior.
    
- Basic lighting and a usable scene.
    
- Object selection.
    
- Selected-object highlighting.
    
- Display of selected object metadata.
    
- Model reload when a new version is generated.
    

Do not create a fake 3D model using arbitrary frontend primitives as the final implementation. The viewer should load the GLB generated by the CAD backend.

The viewer should be a reusable component that can be mounted within the single page.

## F. Textual model-state panel

Since the LLM workflow is text-based, expose a readable textual representation of the current CAD model.

Show information such as:

- Model ID.
    
- Version.
    
- Object names.
    
- Object types.
    
- Dimensions.
    
- Positions and rotations where available.
    
- Feature relationships.
    
- Operation history.
    
- Last successful operation.
    
- Validation status.
    

This panel is for user transparency and debugging. It is not a replacement for FreeCAD's authoritative document state.

---

# 5. Text-only AI interaction requirements

The LLM must reason using textual information and structured tool responses.

Do not require screenshots or image understanding for the core CAD agent workflow.

The LLM receives:

1. Fixed form fields.
    
2. Additional natural-language instruction.
    
3. Conversation history relevant to the current CAD session.
    
4. Current textual CAD model state retrieved through MCP.
    
5. Available MCP tool definitions.
    
6. Relevant previous operation results.
    
7. Validation results and errors.
    

The LLM should never assume that a model is empty or that its previous textual understanding is still current without checking the actual CAD state when necessary.

FreeCAD is the authoritative source of truth for geometry.

---

# 6. LangGraph agent design

Implement a LangGraph workflow with clear nodes and typed state.

Suggested state:

```python
class CADAgentState(TypedDict):
    messages: list
    project_id: str
    model_id: str
    model_version: int
    fixed_inputs: dict
    additional_instruction: str
    current_model_state: dict
    planned_operation: dict | None
    execution_result: dict | None
    validation_result: dict | None
    error: str | None
```

The implementation may use a more appropriate Pydantic or TypedDict structure, but it must remain explicit and typed.

## Required workflow

### Node 1: Receive user request

Read fixed inputs and additional instruction.

Validate the request structure and normalize units.

### Node 2: Load conversation memory

Retrieve relevant conversation history for the current project or thread.

Conversation memory must remember:

- What the user requested.
    
- Decisions made during the CAD session.
    
- Relevant previous instructions.
    
- Previous successful operations.
    
- Relevant failures and corrections.
    

Use a LangGraph checkpointer backed by PostgreSQL for persistent conversation state.

Use a stable thread ID for each project or conversation.

Do not send the entire conversation history to the LLM without considering relevance and token limits.

### Node 3: Retrieve current CAD state

Call the FreeCAD MCP tool that retrieves the actual current model state.

Example tool:

```text
get_model_state(model_id)
```

The returned state should include, where available:

- Object names.
    
- Object types.
    
- Parameters.
    
- Dimensions.
    
- Placement.
    
- Feature history.
    
- Parent-child relationships.
    
- Model version.
    
- Relevant metadata.
    

The MCP server must read the actual FreeCAD document or an authoritative persisted document state.

Do not rely only on stale LLM memory.

### Node 4: LLM planning

The LLM analyzes:

- Fixed user inputs.
    
- Additional instruction.
    
- Conversation memory.
    
- Current CAD state.
    
- Available MCP tools.
    

It decides whether to:

- Create a new model.
    
- Modify an existing model.
    
- Query more model information.
    
- Ask the user for clarification.
    
- Execute a supported CAD operation.
    
- Report that a requested operation is unsupported.
    

Use structured outputs or tool calling.

Do not rely on free-form text parsing for critical CAD operations.

### Node 5: Validate operation

Validate the LLM's proposed operation before execution.

Check:

- Required fields.
    
- Numeric values.
    
- Units.
    
- Object existence.
    
- Supported operation type.
    
- Allowed parameter ranges.
    
- Model consistency.
    
- Potentially destructive operations.
    

Reject malformed or unsupported operations.

### Node 6: Execute through MCP

The LangGraph agent must use the MCP client to invoke CAD tools.

Examples:

```text
create_box(...)
create_cylinder(...)
create_room(...)
create_equipment(...)
modify_object(...)
get_object_properties(...)
get_model_state(...)
save_model(...)
export_model(...)
```

These are conceptual tool names. Implement only tools that are actually supported by the MCP server.

Do not allow the LLM to execute arbitrary shell commands or unrestricted Python code.

### Node 7: Background execution

Long-running FreeCAD operations must be executed asynchronously using Celery.

The API should submit a job to Redis through Celery and return a job ID.

The Celery task invokes the FreeCAD worker execution layer.

The worker performs the operation and returns structured results.

The LangGraph workflow should be designed to handle asynchronous execution cleanly. Do not block the FastAPI event loop waiting for long CAD operations.

### Node 8: Validate resulting model

After execution:

- Check whether FreeCAD completed successfully.
    
- Check document validity.
    
- Check that expected objects exist.
    
- Check for obvious geometry or export failures.
    
- Capture errors.
    
- Update model version.
    
- Produce updated textual model state.
    

### Node 9: Save artifacts

Save the resulting model and metadata.

Required outputs:

- `.FCStd`.
    
- `.glb`.
    
- JSON textual model state.
    
- Operation history.
    
- Logs.
    

Optionally export STEP and STL.

### Node 10: Update memory and return result

Update conversation memory with:

- User request.
    
- Operation performed.
    
- Result.
    
- New model version.
    
- Relevant changes.
    
- Errors, if any.
    

Return a structured response to the frontend.

---

# 7. MCP integration requirements

The MCP client is mandatory.

Implement a dedicated MCP client abstraction in the backend.

The client must:

- Connect to the FreeCAD MCP server.
    
- Discover or use supported tools.
    
- Invoke tools with validated structured arguments.
    
- Handle connection failures.
    
- Handle timeouts.
    
- Handle malformed tool responses.
    
- Log tool calls and results safely.
    
- Avoid exposing internal credentials.
    

The MCP server must provide tools for:

## Model inspection

- `get_model_state`
    
- `list_objects`
    
- `get_object_properties`
    
- `get_feature_history`
    
- `get_model_metadata`
    

## Model creation

- Supported primitive creation tools.
    
- Room or equipment creation tools where applicable.
    
- Model initialization.
    

## Model modification

- Modify supported object parameters.
    
- Add or remove supported features.
    
- Update placements.
    
- Perform supported boolean operations.
    

## Export and persistence

- `save_model`
    
- `export_model`
    
- `get_export_status`
    

The MCP server may internally use FreeCAD Python APIs.

The LLM should see structured descriptions of tool inputs and outputs.

MCP is an interface, not the CAD engine itself.

---

# 8. FreeCAD worker container

Create a dedicated Dockerized FreeCAD worker.

The worker must:

- Have FreeCAD installed.
    
- Have the required Python dependencies.
    
- Have the MCP server or execution bridge available.
    
- Process CAD jobs.
    
- Read and write model files.
    
- Produce structured JSON results.
    
- Handle errors without crashing the entire API.
    
- Log operations and failures.
    
- Support clean shutdown where practical.
    

Initial deployment:

```text
One EC2 instance
├── FastAPI container
├── Redis container
├── Celery / FreeCAD worker container
└── Persistent model storage
```

Keep the FreeCAD execution process isolated from the main FastAPI process.

The worker should not depend on a browser or graphical desktop session for core CAD generation.

If the chosen FreeCAD integration requires a specific execution mode, document it clearly.

---

# 9. Celery and Redis requirements

Redis:

- Acts as the message broker.
    
- Holds pending background task messages.
    
- Provides the communication mechanism between the API and Celery.
    

Celery:

- Manages background tasks and workers.
    
- Executes the FreeCAD job task.
    
- Handles task state and supported retry behavior.
    
- Reports success and failure.
    

Use a dedicated CAD task queue, for example:

```text
cad_tasks
```

Do not mix unrelated application tasks into the CAD queue without a clear reason.

Implement:

- Job submission.
    
- Job ID.
    
- Status retrieval.
    
- Success result.
    
- Failure result.
    
- Task timeout policy.
    
- Safe retry policy.
    

Be careful with retries for non-idempotent CAD operations. Do not blindly repeat an operation that may create duplicate geometry.

Use idempotency keys or model-version checks where appropriate.

---

# 10. Model state and versioning

The system must maintain explicit model versions.

Example:

```text
model_id: plant_123
version: 4
```

Every successful model modification should create a new version or an explicitly documented revision.

The textual model state should include:

- Model ID.
    
- Version.
    
- Object list.
    
- Parameters.
    
- Dimensions.
    
- Placements.
    
- Feature history.
    
- Relationships.
    
- Last operation.
    
- Validation status.
    

Example:

```json
{
  "model_id": "plant_123",
  "version": 4,
  "objects": [
    {
      "name": "Tank_01",
      "type": "Part::Cylinder",
      "parameters": {
        "radius": 20,
        "height": 100
      },
      "placement": {
        "x": 0,
        "y": 0,
        "z": 0
      }
    }
  ],
  "last_operation": {
    "type": "modify_object",
    "status": "success"
  }
}
```

This is illustrative. Use a schema that matches the actual FreeCAD document.

Do not claim that a textual approximation is a complete representation of arbitrary B-Rep geometry. For precise CAD operations, the worker must inspect actual FreeCAD geometry and parameters.

---

# 11. File storage and web-viewable output

Each model project may have multiple files and versions.

Use a storage abstraction with project- and version-scoped paths.

Example:

```text
storage/
└── projects/
    └── plant_123/
        ├── versions/
        │   ├── v1/
        │   │   ├── model.FCStd
        │   │   ├── model.glb
        │   │   ├── model.step
        │   │   ├── model.stl
        │   │   ├── model_state.json
        │   │   └── operation_history.json
        │   └── v2/
        └── current.json
```

The actual implementation may use a database for metadata and a filesystem or object storage for files.

The frontend must receive a safe URL or API endpoint for the GLB file.

Do not expose arbitrary filesystem paths to the browser.

The GLB export pipeline must be documented and tested.

If FreeCAD does not natively provide the required GLB export path in the chosen setup, implement a reliable conversion pipeline using an appropriate supported method. Preserve object identity and metadata where feasible.

---

# 12. Three.js viewer and object selection

The frontend should load the GLB model generated by the backend.

Implement:

- Scene.
    
- Camera.
    
- Renderer.
    
- Lighting.
    
- OrbitControls.
    
- GLB loader.
    
- Resize handling.
    
- Model loading indicator.
    
- Error handling.
    
- Camera reset.
    
- Fit-to-model.
    

Mouse interaction:

- Left drag rotates.
    
- Wheel zooms.
    
- Right drag or middle drag pans, according to the configured controls.
    
- Clicking a mesh selects it.
    

When an object is selected:

1. Identify the selected mesh.
    
2. Resolve its associated CAD object ID or metadata.
    
3. Display its properties in a side panel or details section.
    
4. Highlight the selected object.
    
5. Allow clearing the selection.
    

The viewer must not assume that Three.js mesh names always equal FreeCAD object names. Define a stable metadata mapping during export.

For example, preserve a stable object ID in GLB node metadata or maintain a backend mapping.

---

# 13. FastAPI API design

Implement clean API routes. Suggested endpoints:

```text
POST   /api/cad/projects
GET    /api/cad/projects/{project_id}

POST   /api/cad/projects/{project_id}/generate
GET    /api/cad/jobs/{job_id}
GET    /api/cad/projects/{project_id}/state
GET    /api/cad/projects/{project_id}/versions
GET    /api/cad/projects/{project_id}/versions/{version}
GET    /api/cad/projects/{project_id}/versions/{version}/model
GET    /api/cad/projects/{project_id}/versions/{version}/metadata
```

The exact route naming can be adapted to the existing backend conventions.

Generation request example:

```json
{
  "project_id": "plant_123",
  "fixed_inputs": {
    "model_type": "plant",
    "length": 100,
    "width": 80,
    "height": 20,
    "units": "mm"
  },
  "additional_instruction": "Create a storage tank on the left side.",
  "base_version": 0
}
```

Generation response:

```json
{
  "job_id": "job_123",
  "project_id": "plant_123",
  "status": "queued"
}
```

Job result:

```json
{
  "job_id": "job_123",
  "status": "completed",
  "model_id": "plant_123",
  "version": 1,
  "artifacts": {
    "fcstd": "/api/cad/projects/plant_123/versions/1/model",
    "glb": "/api/cad/projects/plant_123/versions/1/model.glb",
    "state": "/api/cad/projects/plant_123/versions/1/metadata"
  }
}
```

Use appropriate authorization, validation, and safe file serving in the actual implementation.

---

# 14. Initial deployment on one EC2 instance

For the first working deployment, use one EC2 instance.

The initial deployment should be simple and reproducible.

Suggested services:

```text
EC2
├── FastAPI + LangGraph
├── Redis
├── Celery / FreeCAD worker
└── Persistent storage
```

Use Docker Compose for the initial setup if appropriate.

Document:

- Required EC2 instance resources.
    
- Docker installation.
    
- Environment variables.
    
- Volume mounts.
    
- Redis connectivity.
    
- Celery worker startup.
    
- FreeCAD installation.
    
- Model storage permissions.
    
- Health checks.
    
- Logs.
    
- Backup considerations.
    

Do not assume that an arbitrary low-memory EC2 instance can run FreeCAD reliably. Benchmark memory and CPU usage for the actual CAD workload.

---

# 15. Future horizontal scaling with ECS

Design the worker service so it can later run as multiple container instances.

Future architecture:

```text
ECS Cluster
├── EC2 Instance 1
│   ├── FreeCAD Worker 1
│   └── FreeCAD Worker 2
└── EC2 Instance 2
    ├── FreeCAD Worker 3
    └── FreeCAD Worker 4
```

Scaling concept:

- 1 container → 1 concurrent CAD job.
    
- 3 containers → 3 concurrent CAD jobs.
    
- 10 containers → 10 concurrent CAD jobs.
    

This assumes one worker process per container and one active CAD job per worker. Actual throughput depends on resource usage and workload characteristics.

Use horizontal scaling rather than simply increasing concurrency inside a single FreeCAD process.

The design must support:

- Shared Redis broker.
    
- Shared or accessible model storage.
    
- Job ownership and status tracking.
    
- Unique job IDs.
    
- Model version conflict detection.
    
- Idempotency.
    
- Worker health checks.
    
- Graceful task failure handling.
    
- Independent scaling of API and CAD workers.
    

Do not assume that multiple workers can safely modify the same FreeCAD document concurrently. Use project-level locking, version checks, or serialized operations for each model.

---

# 16. Security and safety

Do not execute arbitrary LLM-generated Python or shell commands directly on the host.

The MCP tool layer must expose controlled, validated CAD operations.

Requirements:

- Validate all tool arguments.
    
- Restrict file paths to approved storage directories.
    
- Prevent path traversal.
    
- Apply task timeouts.
    
- Handle worker crashes.
    
- Log tool calls without leaking secrets.
    
- Avoid exposing Redis publicly.
    
- Use authentication and authorization for project access.
    
- Separate user/project data.
    
- Ensure generated files cannot overwrite unrelated projects.
    
- Protect against concurrent conflicting edits.
    
- Use resource limits for worker containers where practical.
    

---

# 17. Testing requirements

Implement tests for:

## Backend

- Form request validation.
    
- Project creation.
    
- Job submission.
    
- Job status retrieval.
    
- Model versioning.
    
- MCP client failures.
    
- Celery task success.
    
- Celery task failure.
    
- Invalid CAD operations.
    
- Concurrent model modification handling.
    

## LangGraph

- State initialization.
    
- Conversation memory.
    
- Model state retrieval.
    
- Tool selection.
    
- Validation failures.
    
- Successful operation flow.
    
- Recovery from execution errors.
    

## FreeCAD worker

- Basic primitive creation.
    
- Parameter modification.
    
- Model saving.
    
- Model state extraction.
    
- Export pipeline.
    
- Invalid geometry handling.
    

## Frontend

- Form validation.
    
- Generate action.
    
- Job polling.
    
- Error display.
    
- GLB loading.
    
- Viewer camera controls.
    
- Object selection.
    
- Property panel.
    
- Model reload.
    

Use mocked MCP and FreeCAD execution layers for most unit tests. Use real FreeCAD integration tests for a small set of representative CAD operations.

---

# 18. Expected implementation deliverables

Produce:

1. A clean backend folder structure.
    
2. FastAPI application.
    
3. LangGraph agent workflow.
    
4. PostgreSQL-backed conversation memory integration.
    
5. MCP client abstraction.
    
6. FreeCAD MCP server or integration adapter.
    
7. Celery task definitions.
    
8. Redis configuration.
    
9. FreeCAD worker Dockerfile.
    
10. Docker Compose for initial deployment.
    
11. CAD model state schema.
    
12. Model versioning and storage abstraction.
    
13. GLB export pipeline.
    
14. Single-page React/Next.js UI.
    
15. Three.js interactive viewer.
    
16. API integration between frontend and backend.
    
17. Environment variable example file.
    
18. Tests.
    
19. README with setup and deployment instructions.
    
20. Architecture documentation.
    
21. Scaling documentation for eventual ECS deployment.
    

---

# 19. Implementation approach

Before writing extensive code:

1. Inspect the existing repository structure.
    
2. Identify the existing frontend framework and routing conventions.
    
3. Identify existing FastAPI modules and dependency management.
    
4. Identify existing authentication, database, and storage patterns.
    
5. Identify existing LLM and MCP abstractions, if present.
    
6. Avoid duplicating infrastructure already available in the project.
    
7. Propose a folder structure that integrates with the existing application.
    
8. Implement the smallest end-to-end vertical slice first.
    

The first vertical slice should demonstrate:

- User submits fixed fields and additional instruction.
    
- FastAPI creates a job.
    
- Celery receives the task through Redis.
    
- FreeCAD worker creates a simple valid model.
    
- The model is saved as FCStd and GLB.
    
- The backend returns the model artifact and textual state.
    
- The frontend displays the GLB in Three.js.
    
- The user can rotate, zoom, pan, and select objects.
    
- The selected object's properties are shown.
    

After this works, expand the CAD toolset and agent capabilities.

Do not create a multi-page UI. Keep the frontend as a single integrated module.

Do not replace MCP with direct LLM-generated Python execution. MCP client integration is a mandatory part of the design.

Do not use screenshots as a required input to the LLM. The core workflow must remain text-based and use structured CAD state retrieved through MCP.

Begin by inspecting the repository, identifying integration points, and proposing the implementation plan and folder structure. Then proceed with implementation in small, testable stages.



add ons
### What should be added to the prompt

Your diagram shows an important validation feedback loop:

```
Execute CAD operation
        ↓
   Validate model
        ↓
   Validation failed
        ↓
     LLM Agent
        ↓
  Re-plan operation
```

The agent should receive the validation error, inspect the current model state again if needed, and correct its plan. It should not blindly repeat the same failed operation.

|   |
|---|
|Validation failed → LLM Agent|

|                                                                                  |
| -------------------------------------------------------------------------------- |
| Partially — error recovery was mentioned, but the exact loop should be explicit. |
