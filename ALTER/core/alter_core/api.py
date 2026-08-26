from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .models import ActionRequest, PolicyRule, Task
from .orchestrator import ApprovalMismatchError, TaskNotFoundError, TaskOrchestrator

app = FastAPI(title="ALTER Core", version="0.1.0")
orchestrator = TaskOrchestrator()


class CreateTaskBody(BaseModel):
    workspace_id: UUID
    owner_user_id: UUID
    objective: str = Field(min_length=1, max_length=10_000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=50)


class EvaluateActionBody(BaseModel):
    action: ActionRequest
    owner_rules: list[PolicyRule] = Field(default_factory=list)


class ApproveActionBody(BaseModel):
    workspace_id: UUID
    action_digest: str = Field(min_length=64, max_length=64)


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "alter-core", "status": "ok", "version": "0.1.0"}


@app.post("/tasks", response_model=Task)
def create_task(body: CreateTaskBody) -> Task:
    return orchestrator.create_task(
        workspace_id=body.workspace_id,
        owner_user_id=body.owner_user_id,
        objective=body.objective,
        acceptance_criteria=body.acceptance_criteria,
    )


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: UUID) -> Task:
    try:
        return orchestrator.store.get(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.post("/actions/evaluate", response_model=Task)
def evaluate_action(body: EvaluateActionBody) -> Task:
    try:
        return orchestrator.request_action(body.action, owner_rules=body.owner_rules)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Workspace mismatch") from exc


@app.post("/tasks/{task_id}/approve", response_model=Task)
def approve_action(task_id: UUID, body: ApproveActionBody) -> Task:
    try:
        task, _approval = orchestrator.approve_pending_action(
            task_id=task_id,
            workspace_id=body.workspace_id,
            action_digest=body.action_digest,
        )
        return task
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Workspace mismatch") from exc
    except ApprovalMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
