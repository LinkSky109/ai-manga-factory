from sqlalchemy.orm import Session
from sqlalchemy import select

from src.infrastructure.db.models import WorkflowDefinitionModel


class WorkflowRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_workflow(
        self,
        project_id: int,
        name: str,
        description: str | None,
        routing_mode: str,
        spec: dict,
    ) -> WorkflowDefinitionModel:
        workflow = WorkflowDefinitionModel(
            project_id=project_id,
            name=name,
            description=description,
            routing_mode=routing_mode,
            spec=spec,
        )
        self.session.add(workflow)
        self.session.flush()
        return workflow

    def get_workflow(self, workflow_id: int) -> WorkflowDefinitionModel | None:
        return self.session.get(WorkflowDefinitionModel, workflow_id)

    def list_workflows(self, project_id: int | None = None) -> list[WorkflowDefinitionModel]:
        query = select(WorkflowDefinitionModel).order_by(WorkflowDefinitionModel.id.desc())
        if project_id is not None:
            query = query.where(WorkflowDefinitionModel.project_id == project_id)
        return list(self.session.scalars(query))

    def update_workflow(
        self,
        workflow_id: int,
        name: str,
        description: str | None,
        routing_mode: str,
        spec: dict,
    ) -> WorkflowDefinitionModel | None:
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            return None
        workflow.name = name
        workflow.description = description
        workflow.routing_mode = routing_mode
        workflow.spec = spec
        self.session.flush()
        return workflow
