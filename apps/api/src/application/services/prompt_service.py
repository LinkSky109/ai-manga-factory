from sqlalchemy.orm import Session

from src.infrastructure.db.repositories.prompt_repository import PromptRepository


class PromptService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.prompts = PromptRepository(session)

    def create_feedback(
        self,
        project_id: int | None,
        job_id: int | None,
        workflow_key: str,
        template_version: str,
        template_body: str,
        score: int,
        correction_summary: str,
        corrected_prompt: str | None,
    ):
        template = self.prompts.find_or_create_template(
            project_id=project_id,
            workflow_key=workflow_key,
            template_version=template_version,
            template_body=template_body,
        )
        feedback = self.prompts.create_feedback(
            prompt_template_id=template.id,
            job_run_id=job_id,
            score=score,
            correction_summary=correction_summary,
            corrected_prompt=corrected_prompt,
        )
        self.session.commit()
        self.session.refresh(feedback)
        return feedback

    def list_templates(self, project_id: int | None = None) -> list[dict]:
        return self.prompts.list_templates(project_id=project_id)

    def list_feedback(self, project_id: int | None = None):
        return self.prompts.list_feedback(project_id=project_id)
