from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.infrastructure.db.models import PromptFeedbackModel, PromptTemplateModel


class PromptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_or_create_template(
        self,
        project_id: int | None,
        workflow_key: str,
        template_version: str,
        template_body: str,
    ) -> PromptTemplateModel:
        template = self.session.scalars(
            select(PromptTemplateModel).where(
                PromptTemplateModel.project_id == project_id,
                PromptTemplateModel.workflow_key == workflow_key,
                PromptTemplateModel.template_version == template_version,
            )
        ).first()
        if template is None:
            template = PromptTemplateModel(
                project_id=project_id,
                workflow_key=workflow_key,
                template_version=template_version,
                template_body=template_body,
            )
            self.session.add(template)
            self.session.flush()
            return template

        template.template_body = template_body
        self.session.flush()
        return template

    def create_feedback(
        self,
        prompt_template_id: int,
        job_run_id: int | None,
        score: int,
        correction_summary: str,
        corrected_prompt: str | None,
    ) -> PromptFeedbackModel:
        feedback = PromptFeedbackModel(
            prompt_template_id=prompt_template_id,
            job_run_id=job_run_id,
            score=score,
            correction_summary=correction_summary,
            corrected_prompt=corrected_prompt,
        )
        self.session.add(feedback)
        self.session.flush()
        return feedback

    def list_templates(self, project_id: int | None = None) -> list[dict]:
        query = select(PromptTemplateModel).order_by(PromptTemplateModel.id.desc())
        if project_id is not None:
            query = query.where(PromptTemplateModel.project_id == project_id)
        templates = list(self.session.scalars(query))
        items: list[dict] = []
        for template in templates:
            feedback_rows = list(
                self.session.scalars(
                    select(PromptFeedbackModel)
                    .where(PromptFeedbackModel.prompt_template_id == template.id)
                    .order_by(PromptFeedbackModel.id.desc())
                )
            )
            items.append(
                {
                    "id": template.id,
                    "project_id": template.project_id,
                    "workflow_key": template.workflow_key,
                    "template_version": template.template_version,
                    "template_body": template.template_body,
                    "feedback_count": len(feedback_rows),
                    "latest_score": feedback_rows[0].score if feedback_rows else None,
                    "created_at": template.created_at,
                    "updated_at": template.updated_at,
                }
            )
        return items

    def list_feedback(self, project_id: int | None = None) -> list[PromptFeedbackModel]:
        query = select(PromptFeedbackModel).join(
            PromptTemplateModel,
            PromptTemplateModel.id == PromptFeedbackModel.prompt_template_id,
        )
        if project_id is not None:
            query = query.where(PromptTemplateModel.project_id == project_id)
        query = query.order_by(PromptFeedbackModel.id.desc())
        return list(self.session.scalars(query))
