from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.db.models import ReviewTaskModel


class ReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_review(
        self,
        project_id: int | None,
        chapter_id: int | None,
        review_stage: str,
        review_type: str,
        assigned_agents: list[str],
        checklist: list[str],
        findings_summary: str | None,
        result_payload: dict,
    ) -> ReviewTaskModel:
        review = ReviewTaskModel(
            project_id=project_id,
            chapter_id=chapter_id,
            review_stage=review_stage,
            review_type=review_type,
            assigned_agents=assigned_agents,
            checklist=checklist,
            findings_summary=findings_summary,
            result_payload=result_payload,
        )
        self.session.add(review)
        self.session.flush()
        return review

    def list_reviews(self, project_id: int | None = None) -> list[ReviewTaskModel]:
        query = select(ReviewTaskModel).order_by(ReviewTaskModel.id.desc())
        if project_id is not None:
            query = query.where(ReviewTaskModel.project_id == project_id)
        return list(self.session.scalars(query))
