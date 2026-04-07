from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas.job import JobCreateRequest, JobResponse, JobResumeRequest
from src.application.services.job_service import JobService
from src.core.dependencies import get_db_session

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(request: JobCreateRequest, session: Session = Depends(get_db_session)) -> JobResponse:
    service = JobService(session)
    try:
        job = service.create_job(
            project_id=request.project_id,
            chapter_id=request.chapter_id,
            workflow_id=request.workflow_id,
            execution_mode=request.execution_mode,
            input_payload=request.input,
            routing_mode=request.routing_mode,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, session: Session = Depends(get_db_session)) -> JobResponse:
    service = JobService(session)
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JobResponse.model_validate(job)


@router.post("/{job_id}/resume", response_model=JobResponse)
def resume_job(
    job_id: int,
    request: JobResumeRequest,
    session: Session = Depends(get_db_session),
) -> JobResponse:
    service = JobService(session)
    try:
        job = service.resume_job(job_id=job_id, override_input=request.override_input)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return JobResponse.model_validate(job)
