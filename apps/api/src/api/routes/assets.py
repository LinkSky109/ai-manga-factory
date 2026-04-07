from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.schemas.asset import (
    ArtifactResponse,
    ArtifactSyncRunCreateRequest,
    ArtifactSyncRunListResponse,
    ArtifactSyncRunResponse,
    CharacterProfileCreateRequest,
    CharacterProfileResponse,
    SceneProfileCreateRequest,
    SceneProfileResponse,
    VoiceProfileCreateRequest,
    VoiceProfileResponse,
)
from src.application.queries.artifacts import ArtifactQueryService
from src.application.services.artifact_service import ArtifactService
from src.application.services.asset_service import AssetService
from src.core.dependencies import get_db_session

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/characters", response_model=list[CharacterProfileResponse])
def list_characters(
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[CharacterProfileResponse]:
    service = AssetService(session)
    return [CharacterProfileResponse.model_validate(item) for item in service.list_characters(project_id=project_id)]


@router.post("/characters", response_model=CharacterProfileResponse, status_code=status.HTTP_201_CREATED)
def create_character(
    request: CharacterProfileCreateRequest,
    session: Session = Depends(get_db_session),
) -> CharacterProfileResponse:
    service = AssetService(session)
    character = service.create_character(
        project_id=request.project_id,
        name=request.name,
        appearance=request.appearance,
        personality=request.personality,
        lora_path=request.lora_path,
        reference_images=[item.model_dump() for item in request.reference_images],
    )
    return CharacterProfileResponse.model_validate(character)


@router.get("/voices", response_model=list[VoiceProfileResponse])
def list_voices(
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[VoiceProfileResponse]:
    service = AssetService(session)
    return [VoiceProfileResponse.model_validate(item) for item in service.list_voices(project_id=project_id)]


@router.post("/voices", response_model=VoiceProfileResponse, status_code=status.HTTP_201_CREATED)
def create_voice(
    request: VoiceProfileCreateRequest,
    session: Session = Depends(get_db_session),
) -> VoiceProfileResponse:
    service = AssetService(session)
    voice = service.create_voice(**request.model_dump())
    return VoiceProfileResponse.model_validate(voice)


@router.get("/scenes", response_model=list[SceneProfileResponse])
def list_scenes(
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[SceneProfileResponse]:
    service = AssetService(session)
    return [SceneProfileResponse.model_validate(item) for item in service.list_scenes(project_id=project_id)]


@router.post("/scenes", response_model=SceneProfileResponse, status_code=status.HTTP_201_CREATED)
def create_scene(
    request: SceneProfileCreateRequest,
    session: Session = Depends(get_db_session),
) -> SceneProfileResponse:
    service = AssetService(session)
    scene = service.create_scene(**request.model_dump())
    return SceneProfileResponse.model_validate(scene)


@router.get("/artifacts", response_model=list[ArtifactResponse])
def list_artifacts(
    project_id: int = Query(...),
    session: Session = Depends(get_db_session),
) -> list[ArtifactResponse]:
    items = ArtifactQueryService(session).list_project_artifacts(project_id)
    return [ArtifactResponse.model_validate(item) for item in items]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
def get_artifact(
    artifact_id: int,
    session: Session = Depends(get_db_session),
) -> ArtifactResponse:
    item = ArtifactQueryService(session).get_artifact(artifact_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return ArtifactResponse.model_validate(item)


@router.post("/artifacts/{artifact_id}/archives/sync", response_model=ArtifactResponse)
def sync_artifact_archives(
    artifact_id: int,
    session: Session = Depends(get_db_session),
) -> ArtifactResponse:
    service = ArtifactService(session)
    try:
        artifact = service.sync_artifact_archives(artifact_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    item = ArtifactQueryService(session).get_artifact(artifact.id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return ArtifactResponse.model_validate(item)


@router.get("/artifacts/{artifact_id}/archive-sync-runs", response_model=ArtifactSyncRunListResponse)
def list_artifact_sync_runs(
    artifact_id: int,
    session: Session = Depends(get_db_session),
) -> ArtifactSyncRunListResponse:
    service = ArtifactService(session)
    try:
        runs = service.list_artifact_sync_runs(artifact_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ArtifactSyncRunListResponse(
        items=[ArtifactSyncRunResponse.model_validate(run) for run in runs]
    )


@router.post(
    "/artifacts/{artifact_id}/archive-sync-runs",
    response_model=ArtifactSyncRunListResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_artifact_sync_runs(
    artifact_id: int,
    request: ArtifactSyncRunCreateRequest,
    session: Session = Depends(get_db_session),
) -> ArtifactSyncRunListResponse:
    service = ArtifactService(session)
    try:
        runs = service.enqueue_artifact_sync_runs(
            artifact_id=artifact_id,
            archive_types=request.archive_types,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ArtifactSyncRunListResponse(
        items=[ArtifactSyncRunResponse.model_validate(run) for run in runs]
    )
