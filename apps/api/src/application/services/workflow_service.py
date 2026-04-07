from sqlalchemy.orm import Session

from src.domain.workflow.specs import WorkflowDefinitionSpec
from src.infrastructure.db.repositories.workflow_repository import WorkflowRepository


class WorkflowService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.workflows = WorkflowRepository(session)

    def create_workflow(self, project_id: int, name: str, description: str | None, routing_mode: str, spec: dict):
        parsed_spec = WorkflowDefinitionSpec.model_validate(spec)
        parsed_spec.validate_graph()
        workflow = self.workflows.create_workflow(
            project_id=project_id,
            name=name,
            description=description,
            routing_mode=routing_mode,
            spec=parsed_spec.model_dump(),
        )
        self.session.commit()
        self.session.refresh(workflow)
        return workflow

    def list_workflows(self, project_id: int | None = None):
        return self.workflows.list_workflows(project_id=project_id)

    def update_workflow(self, workflow_id: int, name: str, description: str | None, routing_mode: str, spec: dict):
        parsed_spec = WorkflowDefinitionSpec.model_validate(spec)
        parsed_spec.validate_graph()
        workflow = self.workflows.update_workflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            routing_mode=routing_mode,
            spec=parsed_spec.model_dump(),
        )
        if workflow is None:
            raise LookupError("Workflow not found.")
        self.session.commit()
        self.session.refresh(workflow)
        return workflow
