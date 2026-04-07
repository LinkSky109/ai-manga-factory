from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.db.models import SharedMemoryModel


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_memory(
        self,
        project_id: int | None,
        scope_type: str,
        scope_key: str,
        memory_type: str,
        content: dict,
    ) -> SharedMemoryModel:
        memory = SharedMemoryModel(
            project_id=project_id,
            scope_type=scope_type,
            scope_key=scope_key,
            memory_type=memory_type,
            content=content,
        )
        self.session.add(memory)
        self.session.flush()
        return memory

    def upsert_memory(
        self,
        project_id: int | None,
        scope_type: str,
        scope_key: str,
        memory_type: str,
        content: dict,
    ) -> SharedMemoryModel:
        query = select(SharedMemoryModel).where(
            SharedMemoryModel.project_id == project_id,
            SharedMemoryModel.scope_type == scope_type,
            SharedMemoryModel.scope_key == scope_key,
            SharedMemoryModel.memory_type == memory_type,
        )
        memory = self.session.scalar(query)
        if memory is None:
            return self.create_memory(
                project_id=project_id,
                scope_type=scope_type,
                scope_key=scope_key,
                memory_type=memory_type,
                content=content,
            )
        memory.content = content
        self.session.flush()
        return memory

    def list_memories(self, project_id: int | None = None) -> list[SharedMemoryModel]:
        query = select(SharedMemoryModel).order_by(SharedMemoryModel.id.desc())
        if project_id is not None:
            query = query.where(SharedMemoryModel.project_id == project_id)
        return list(self.session.scalars(query))
