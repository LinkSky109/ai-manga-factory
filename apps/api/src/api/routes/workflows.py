from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.schemas.workflow import WorkflowCreateRequest, WorkflowResponse, WorkflowUpdateRequest
from src.application.services.workflow_service import WorkflowService
from src.core.dependencies import get_db_session

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowResponse])
def list_workflows(
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[WorkflowResponse]:
    service = WorkflowService(session)
    workflows = service.list_workflows(project_id=project_id)
    return [WorkflowResponse.model_validate(item) for item in workflows]


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(request: WorkflowCreateRequest, session: Session = Depends(get_db_session)) -> WorkflowResponse:
    service = WorkflowService(session)
    try:
        workflow = service.create_workflow(
            project_id=request.project_id,
            name=request.name,
            description=request.description,
            routing_mode=request.routing_mode,
            spec={"nodes": [node.model_dump() for node in request.nodes], "edges": [edge.model_dump() for edge in request.edges]},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return WorkflowResponse.model_validate(workflow)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: int,
    request: WorkflowUpdateRequest,
    session: Session = Depends(get_db_session),
) -> WorkflowResponse:
    service = WorkflowService(session)
    try:
        workflow = service.update_workflow(
            workflow_id=workflow_id,
            name=request.name,
            description=request.description,
            routing_mode=request.routing_mode,
            spec={"nodes": [node.model_dump() for node in request.nodes], "edges": [edge.model_dump() for edge in request.edges]},
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return WorkflowResponse.model_validate(workflow)
