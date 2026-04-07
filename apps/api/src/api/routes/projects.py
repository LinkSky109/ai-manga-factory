from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.schemas.project import (
    ChapterCreateRequest,
    ChapterDetailResponse,
    ChapterResponse,
    ProjectInitializationRequest,
    ProjectInitializationResponse,
    ProjectCreateRequest,
    ProjectOverviewResponse,
    ProjectResponse,
)
from src.application.services.project_service import ProjectService
from src.application.services.job_service import JobService
from src.application.services.artifact_service import ArtifactService
from src.application.queries.preview import PreviewQueryService
from src.api.schemas.job import JobResponse, ProjectPreviewItemResponse, ProjectPreviewListResponse
from src.api.schemas.storage import ArtifactArchiveBatchSyncResponse
from src.core.dependencies import get_db_session

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(request: ProjectCreateRequest, session: Session = Depends(get_db_session)) -> ProjectResponse:
    service = ProjectService(session)
    project = service.create_project(name=request.name, description=request.description)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=list[ProjectResponse])
def list_projects(session: Session = Depends(get_db_session)) -> list[ProjectResponse]:
    service = ProjectService(session)
    return [ProjectResponse.model_validate(project) for project in service.list_projects()]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, session: Session = Depends(get_db_session)) -> ProjectResponse:
    service = ProjectService(session)
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return ProjectResponse.model_validate(project)


@router.post("/{project_id}/chapters", response_model=ChapterResponse, status_code=status.HTTP_201_CREATED)
def create_chapter(
    project_id: int,
    request: ChapterCreateRequest,
    session: Session = Depends(get_db_session),
) -> ChapterResponse:
    service = ProjectService(session)
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    chapter = service.create_chapter(
        project_id=project_id,
        chapter_number=request.chapter_number,
        title=request.title,
        summary=request.summary,
    )
    return ChapterResponse.model_validate(chapter)


@router.get("/{project_id}/chapters", response_model=list[ChapterDetailResponse])
def list_chapters(project_id: int, session: Session = Depends(get_db_session)) -> list[ChapterDetailResponse]:
    service = ProjectService(session)
    project = service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return [ChapterDetailResponse.model_validate(chapter) for chapter in service.list_chapters(project_id)]


@router.get("/{project_id}/overview", response_model=ProjectOverviewResponse)
def project_overview(project_id: int, session: Session = Depends(get_db_session)) -> ProjectOverviewResponse:
    service = ProjectService(session)
    try:
        overview = service.build_overview(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProjectOverviewResponse.model_validate(overview)


@router.post(
    "/{project_id}/initialize",
    response_model=ProjectInitializationResponse,
    status_code=status.HTTP_201_CREATED,
)
def initialize_project(
    project_id: int,
    request: ProjectInitializationRequest,
    session: Session = Depends(get_db_session),
) -> ProjectInitializationResponse:
    service = ProjectService(session)
    try:
        snapshot = service.initialize_project(
            project_id=project_id,
            source_title=request.source_title,
            source_type=request.source_type,
            source_text=request.source_text,
            overwrite_assets=request.overwrite_assets,
            routing_mode=request.routing_mode,
            manual_provider=request.manual_provider,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProjectInitializationResponse.model_validate(snapshot)


@router.get("/{project_id}/initialization", response_model=ProjectInitializationResponse)
def get_project_initialization(
    project_id: int,
    session: Session = Depends(get_db_session),
) -> ProjectInitializationResponse:
    service = ProjectService(session)
    try:
        snapshot = service.get_initialization_snapshot(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProjectInitializationResponse.model_validate(snapshot)


@router.get("/{project_id}/jobs", response_model=list[JobResponse])
def list_project_jobs(project_id: int, session: Session = Depends(get_db_session)) -> list[JobResponse]:
    project_service = ProjectService(session)
    if project_service.get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    jobs = JobService(session).list_jobs_by_project(project_id)
    return [JobResponse.model_validate(job) for job in jobs]


@router.get("/{project_id}/previews", response_model=ProjectPreviewListResponse)
def list_project_previews(project_id: int, session: Session = Depends(get_db_session)) -> ProjectPreviewListResponse:
    project_service = ProjectService(session)
    if project_service.get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    items = [ProjectPreviewItemResponse.model_validate(item) for item in PreviewQueryService(session).list_project_previews(project_id)]
    return ProjectPreviewListResponse(items=items)


@router.post("/{project_id}/artifacts/archives/sync", response_model=ArtifactArchiveBatchSyncResponse)
def sync_project_artifact_archives(
    project_id: int,
    session: Session = Depends(get_db_session),
) -> ArtifactArchiveBatchSyncResponse:
    project_service = ProjectService(session)
    if project_service.get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    result = ArtifactService(session).sync_project_artifact_archives(project_id)
    return ArtifactArchiveBatchSyncResponse.model_validate(result)
