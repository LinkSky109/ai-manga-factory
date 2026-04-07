from sqlalchemy.orm import Session

from src.infrastructure.db.repositories.memory_repository import MemoryRepository


class MemoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.memories = MemoryRepository(session)

    def create_memory(self, **payload):
        memory = self.memories.create_memory(**payload)
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def list_memories(self, project_id: int | None = None):
        return self.memories.list_memories(project_id=project_id)
