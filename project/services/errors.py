class DomainError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ResourceNotFound(DomainError):
    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__(404, "resource_not_found", message)


class AccessDenied(DomainError):
    def __init__(self, message: str = "无权访问该资源") -> None:
        super().__init__(403, "access_denied", message)


class DocumentProcessingError(DomainError):
    def __init__(self, message: str = "文档处理失败") -> None:
        super().__init__(422, "document_processing_failed", message)


class AgentExecutionError(DomainError):
    def __init__(self, message: str = "Agent 执行失败，请稍后重试") -> None:
        super().__init__(503, "agent_execution_failed", message)


class DatabaseError(DomainError):
    def __init__(self, message: str = "数据库服务暂时不可用") -> None:
        super().__init__(503, "database_unavailable", message)


class VectorStoreError(DomainError):
    def __init__(self, message: str = "向量检索服务暂时不可用") -> None:
        super().__init__(503, "vector_store_unavailable", message)
