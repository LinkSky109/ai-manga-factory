from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.api.schemas.prompt_evolution import (
    PromptFeedbackCreateRequest,
    PromptFeedbackResponse,
    PromptTemplateSummaryResponse,
)
from src.application.services.prompt_service import PromptService
from src.core.dependencies import get_db_session

router = APIRouter(prefix="/prompt-evolution", tags=["prompt-evolution"])


@router.get("/templates", response_model=list[PromptTemplateSummaryResponse])
def list_templates(
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[PromptTemplateSummaryResponse]:
    service = PromptService(session)
    return [PromptTemplateSummaryResponse.model_validate(item) for item in service.list_templates(project_id=project_id)]


@router.get("/feedback", response_model=list[PromptFeedbackResponse])
def list_feedback(
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[PromptFeedbackResponse]:
    service = PromptService(session)
    return [PromptFeedbackResponse.model_validate(item) for item in service.list_feedback(project_id=project_id)]


@router.post("/feedback", response_model=PromptFeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_feedback(
    request: PromptFeedbackCreateRequest,
    session: Session = Depends(get_db_session),
) -> PromptFeedbackResponse:
    service = PromptService(session)
    feedback = service.create_feedback(
        project_id=request.project_id,
        job_id=request.job_id,
        workflow_key=request.workflow_key,
        template_version=request.template_version,
        template_body=request.template_body,
        score=request.score,
        correction_summary=request.correction_summary,
        corrected_prompt=request.corrected_prompt,
    )
    return PromptFeedbackResponse.model_validate(feedback)
