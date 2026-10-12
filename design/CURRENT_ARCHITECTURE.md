# 当前实现架构

## 请求链路

```text
Gradio / API Client
  → RequestContextMiddleware（request_id、耗时、结构化日志）
  → JWTAuthenticationMiddleware（RS256、kid、iss、aud、exp）
  → FastAPI Router（Pydantic + Depends 权限）
  → Service（业务规则与事务边界）
  → Repository（AsyncSession）
  → PostgreSQL
```

聊天请求在Service中创建Conversation、Message和AgentRun，随后把阻塞型LangGraph/模型调用放入线程池。执行结束后保存回答、引用、路由、改写、重试、检索/精排/LLM/总耗时、Token、状态和Usage。

## 存储职责

| 组件 | 当前职责 |
|---|---|
| PostgreSQL | 租户、用户、RBAC、知识库成员、文档与版本、对话、消息、Agent Run、Usage、审计 |
| Redis | Refresh Token、最近对话缓存、租户知识库范围内的检索缓存 |
| Milvus | 带`tenant_id + knowledge_base_id`过滤的Child向量和BM25索引 |
| 本地Parent Store | 以租户作用域文档ID保存Parent正文 |
| 本地文件目录 | 按租户和知识库保存不可变内容版本文件 |
| PostgreSQL企业工具表 | 产品、部门、库存和服务状态的白名单查询数据 |

## RAG链路

```text
Query Analysis
  → Dense + BM25
  → RRF
  → BGE Reranker
  → Parent Expansion
  → Context Budget
  → Answer
  → Fact Check
  → Retry / Refuse / Finish
```

Milvus V2 Schema包含`tenant_id`、`knowledge_base_id`和`document_version`。企业请求遇到旧版无作用域Collection时会直接失败，不会降级为无过滤检索。

## 代码边界

```text
api/             HTTP、SSE、Schema、Depends、错误映射
auth/            密码、JWT/JWKS、Refresh Token、RBAC
services/        Chat、Document、KnowledgeBase、Conversation、Audit业务规则
repositories/    SQLAlchemy查询与持久化
database/        ORM模型、Engine、AsyncSession
core/            容器、RAGSystem、缓存、可观测性
evaluation/      确定性指标与回归比较
migrations/      Alembic Schema版本
```

## 当前部署

Docker Compose包含PostgreSQL、Redis、Milvus、etcd、MinIO和应用。应用容器启动时先执行`alembic upgrade head`，迁移成功后再启动Uvicorn。

耗时较长的文档解析、Embedding和Milvus发布目前仍在API进程的线程池中执行。Celery Worker、对象存储业务Bucket、Outbox补偿发布以及PostgreSQL LangGraph Checkpointer保留在生产架构的下一阶段。
