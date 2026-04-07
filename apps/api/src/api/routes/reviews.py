from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.api.schemas.review import ReviewTaskCreateRequest, ReviewTaskResponse
from src.application.services.review_service import ReviewService
from src.core.dependencies import get_db_session

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=list[ReviewTaskResponse])
def list_reviews(
    project_id: int | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[ReviewTaskResponse]:
    service = ReviewService(session)
    return [ReviewTaskResponse.model_validate(item) for item in service.list_reviews(project_id=project_id)]


@router.post("", response_model=ReviewTaskResponse, status_code=status.HTTP_201_CREATED)
def create_review(
    request: ReviewTaskCreateRequest,
    session: Session = Depends(get_db_session),
) -> ReviewTaskResponse:
    service = ReviewService(session)
    review = service.create_review(**request.model_dump())
    return ReviewTaskResponse.model_validate(review)
