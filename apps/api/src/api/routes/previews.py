from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.dependencies import get_db_session
from src.infrastructure.db.repositories.artifact_repository import ArtifactRepository

router = APIRouter(prefix="/previews", tags=["previews"])


@router.get("/artifacts/{artifact_id}")
def stream_artifact_preview(artifact_id: int, session: Session = Depends(get_db_session)) -> FileResponse:
    artifact = ArtifactRepository(session).get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    preview_file = get_settings().preview_root / artifact.preview_path
    if not preview_file.exists():
        raise HTTPException(status_code=404, detail="Preview file not found.")

    return FileResponse(
        preview_file,
        media_type=artifact.mime_type.split(";")[0],
        filename=preview_file.name,
    )
