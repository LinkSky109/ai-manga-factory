from pydantic import BaseModel, Field


class WorkflowNodeSpec(BaseModel):
    key: str
    title: str
    provider_type: str
    checkpointable: bool = True


class WorkflowEdgeSpec(BaseModel):
    source: str
    target: str


class WorkflowDefinitionSpec(BaseModel):
    nodes: list[WorkflowNodeSpec] = Field(default_factory=list)
    edges: list[WorkflowEdgeSpec] = Field(default_factory=list)

    def validate_graph(self) -> None:
        node_keys = {node.key for node in self.nodes}
        if len(node_keys) != len(self.nodes):
            raise ValueError("Workflow node keys must be unique.")
        for edge in self.edges:
            if edge.source not in node_keys or edge.target not in node_keys:
                raise ValueError("Workflow edges must reference existing nodes.")
