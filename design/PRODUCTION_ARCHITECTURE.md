# 企业知识库 Agentic RAG 面向生产架构设计

> 文档状态：Proposed（待实现）
> 版本：v1.0
> 更新日期：2026-08-09
> 适用仓库：`enterprise-agentic-rag`
> 目标读者：开发者、架构评审者、后续维护者

## 1. 文档定位

本文档定义当前企业知识库 Agentic RAG 原型的工业化目标架构、数据模型、核心流程、失败恢复、安全边界、评测体系和分阶段实施顺序。本文档不代表这些能力已经实现；只有代码、测试、运行数据和故障演练全部满足验收条件后，对应能力才可标记为已交付。

项目保留以下业务目标：

- 支持 PDF、DOCX、XLSX、Markdown、TXT 等企业文档入库。
- 使用 BGE-M3 Dense、Milvus BM25、RRF 和 BGE Reranker 构建混合检索。
- 使用 LangGraph 编排查询分析、改写、检索、工具调用、生成、校验和拒答。
- 使用 FastAPI 提供管理 API、问答 API 和 SSE 流式事件。
- 使用模拟企业数据完成可复现实验，不上传真实企业机密数据。
- 模型能力通过供应商无关的 Provider Adapter 接入，可按合规、SLA、成本和部署要求选择托管模型或企业自托管模型。

### 1.1 “工业级”的判定

工业级不是组件数量多，也不是代码看起来复杂，而是系统具备并经过验证的以下性质：

1. 正确性：数据不会因为重试、并发或部分失败而产生错误版本。
2. 可恢复性：进程、网络或依赖故障后可以继续执行或安全回滚。
3. 安全性：身份、权限、租户、工具和模型输入输出均有明确边界。
4. 可观测性：能够定位一次请求或入库任务在哪一步失败、消耗多少资源。
5. 可扩展性：API、入库 Worker 和检索服务可以分别扩容。
6. 可验证性：功能、性能、检索质量和故障恢复都有自动化测试及指标。

因此，本设计实现后更准确的表述是“面向生产设计并完成本地验证的企业知识库系统”。在没有真实业务流量、长期运行和灾难恢复演练之前，不声称已经完成大规模生产验证。

## 2. 目标与非目标

### 2.1 目标

- 文档上传接口快速返回任务 ID，不在 HTTP 请求中同步完成全部入库。
- 入库任务支持幂等、有限重试、断点恢复、取消、进度查询和失败审计。
- 原文件、元数据、父块、子块和向量索引各自有明确的权威存储。
- 新文档版本验证成功后才对查询可见，失败版本不影响当前线上版本。
- 检索前执行权限过滤，检索后再次校验，禁止跨租户、跨知识库泄露。
- 实现真正的 Parent-Child Retrieval：子块负责召回，父块负责提供上下文。
- 切块按文档结构优先，并使用 tokenizer 控制模型输入上限。
- 模型调用具备超时、退避重试、限流、熔断、降级、调用审计和成本统计。
- LangGraph 对话状态持久化，服务重启后可恢复。
- 建立离线评测、集成测试、安全测试、性能测试和故障演练。
- 同一业务逻辑支持单机 Docker Compose 和生产分布式部署。

### 2.2 非目标

- 不在第一阶段训练或微调基础大模型、Embedding 模型与 Reranker。
- 不假设任何单一模型供应商天然满足企业 SLA、隐私和合规要求；供应商必须经过正式评估并支持替换。
- 不允许模型直接执行任意 SQL、系统命令或未经审批的有副作用操作。
- 不以 Gradio 作为最终生产前端；Gradio 仅作为本地管理与功能演示界面。
- 不在第一阶段支持任意规模和任意格式文档，格式能力按测试矩阵逐步开放。

## 3. 设计原则

1. PostgreSQL 是控制面与业务状态的唯一权威来源。
2. Milvus 是可重建的检索索引，不承担文档版本和任务状态的权威职责。
3. MinIO/S3 保存不可变原文件和大体积处理产物。
4. Redis 只承担缓存、限流和 Celery Broker；不能作为永久业务事实来源。
5. 所有异步任务按“至少一次执行”设计，因此任务必须幂等。
6. 所有外部调用必须有超时、有限重试和可追踪的错误分类。
7. 所有检索都必须带服务端生成的租户和知识库过滤条件。
8. 文档内容和用户输入都视为不可信数据，不能当作系统指令。
9. 先建立可测的基线，再通过实验决定块大小、Top-K、阈值和重试次数。
10. 本地开发形态可以降配，但不能改变核心数据状态和安全语义。

## 4. 质量目标

以下是实施后的初始设计目标，不是当前已取得的测量结果：

| 类别 | 初始目标 | 验证方式 |
|---|---:|---|
| 权限隔离 | 越权检索测试泄露数为 0 | 自动化安全测试 |
| 发布一致性 | 失败版本对查询不可见 | 故障注入测试 |
| 入库幂等 | 同一幂等键重复提交只产生一个有效版本 | 并发集成测试 |
| API 可用性 | 初始月度目标 99.9%，最终以业务 SLO 为准 | 服务监控 |
| 检索延迟 | 服务端检索阶段 P95 小于 1 秒，不含外部模型网络波动 | 压力测试 |
| 首 Token | 标准问题 P95 小于 4 秒，作为调优目标 | SSE 指标 |
| 完整回答 | 标准问题 P95 小于 15 秒，作为调优目标 | 端到端测试 |
| 恢复目标 | 初始 RPO 15 分钟、RTO 2 小时 | 恢复演练 |
| 检索质量 | 在有区分度评测集上报告 Recall@K、MRR、nDCG | 离线评测 |
| 回答质量 | 报告引用正确率、忠实度、拒答精度，不虚构提升 | 离线评测 |

外部模型供应商的排队、配额和服务中断会直接影响端到端指标，必须单独记录供应商延迟和系统内部延迟；自托管模型也必须单独记录推理队列和资源饱和度。

## 5. 总体架构

### 5.1 逻辑组件图

```mermaid
flowchart LR
    User[用户或管理员] --> Gateway[反向代理/API Gateway]
    Gateway --> Auth[OIDC/JWT 鉴权]
    Auth --> API[FastAPI API Service]

    API --> PG[(PostgreSQL<br/>权威元数据/任务/权限)]
    API --> Object[(MinIO/S3<br/>原文件与处理产物)]
    API --> Redis[(Redis<br/>Broker/缓存/限流)]
    Redis --> Worker[Celery Ingestion Worker]

    Worker --> Object
    Worker --> PG
    Worker --> ModelAPI[Model Provider Gateway<br/>Embedding/Reranker/LLM]
    Worker --> Milvus[(Milvus<br/>Dense + BM25 索引)]

    API --> Query[Query Service]
    Query --> Graph[LangGraph Workflow]
    Graph --> Milvus
    Graph --> PG
    Graph --> Redis
    Graph --> ModelAPI
    Graph --> Tools[受控 Tool Gateway]

    API --> Stream[SSE Event Stream]
    Stream --> User

    API --> Obs[OpenTelemetry/结构化日志]
    Worker --> Obs
    Graph --> Obs
    Milvus --> Metrics[Prometheus/Grafana]
    Obs --> Metrics
```

### 5.2 组件职责

| 组件 | 权威职责 | 不承担的职责 |
|---|---|---|
| FastAPI | 鉴权、参数校验、任务创建、查询编排、SSE | 长时间同步入库 |
| PostgreSQL | 租户、权限、文档版本、任务状态、父块、审计、LangGraph Checkpoint | 向量近邻检索 |
| MinIO/S3 | 原始文件、解析产物、可选 OCR 产物、评测报告 | 文档是否在线的最终判断 |
| Redis | Celery Broker、短期缓存、限流计数、分布式互斥辅助 | 永久文档状态 |
| Celery Worker | 解析、切块、Embedding、索引、验证、补偿 | 用户身份判定 |
| Milvus | Dense、BM25、标量过滤、候选召回 | 任务状态与完整业务事务 |
| LangGraph | 显式问答状态机、重试边界、工具路由、人工中断 | 绕过权限直接访问数据 |
| Model Provider Gateway | LLM、Embedding、Reranker 的统一调用、路由、限流和审计接口 | 保存业务真相 |
| Gradio | 本地管理和演示 | 正式企业门户 |

### 5.3 两种部署形态

#### 开发与集成测试形态

- Docker Compose 启动 PostgreSQL、Redis、MinIO、Milvus、API 和单个 Worker。
- Worker 并发和容器资源通过环境配置调整，不写死具体硬件假设。
- 模型可连接测试供应商、Mock Server 或专用测试推理服务，业务代码不感知具体供应商。
- OCR 作为独立能力开关和 Worker 队列，是否启动由测试范围决定。
- 所有功能语义与生产形态一致，只降低副本数和吞吐量。

#### 生产参考形态

- API、Query Worker、Ingestion Worker 分别横向扩容。
- PostgreSQL 使用主从、自动备份和连接池。
- Redis 使用高可用部署；需要更强消息语义时可替换为 RabbitMQ。
- Milvus 使用分布式模式、独立对象存储和监控。
- 通过 Kubernetes Secret 或密钥管理服务注入凭据。
- 使用 Ingress、TLS、OIDC、NetworkPolicy 和集中日志平台。

## 6. 数据模型

### 6.1 核心实体关系

```mermaid
erDiagram
    TENANT ||--o{ USER_MEMBERSHIP : contains
    USER ||--o{ USER_MEMBERSHIP : joins
    TENANT ||--o{ KNOWLEDGE_BASE : owns
    KNOWLEDGE_BASE ||--o{ DOCUMENT : contains
    DOCUMENT ||--o{ DOCUMENT_VERSION : versions
    DOCUMENT_VERSION ||--o{ INGESTION_JOB : processed_by
    DOCUMENT_VERSION ||--o{ PARENT_CHUNK : contains
    PARENT_CHUNK ||--o{ CHILD_CHUNK_MANIFEST : contains
    USER ||--o{ CONVERSATION : starts
    CONVERSATION ||--o{ MESSAGE : contains
    TENANT ||--o{ AUDIT_EVENT : produces

    TENANT {
        uuid id PK
        string name
        string status
    }
    KNOWLEDGE_BASE {
        uuid id PK
        uuid tenant_id FK
        string name
        string status
    }
    DOCUMENT {
        uuid id PK
        uuid knowledge_base_id FK
        string canonical_name
        uuid active_version_id
        string status
    }
    DOCUMENT_VERSION {
        uuid id PK
        uuid document_id FK
        string content_sha256
        string object_key
        string pipeline_signature
        string status
        int version_no
    }
    INGESTION_JOB {
        uuid id PK
        uuid document_version_id FK
        string state
        int attempt
        int progress
        string error_code
        datetime lease_expires_at
    }
    PARENT_CHUNK {
        uuid id PK
        uuid document_version_id FK
        int ordinal
        text content
        jsonb locator
        int token_count
    }
    CHILD_CHUNK_MANIFEST {
        string id PK
        uuid parent_id FK
        int ordinal
        string content_hash
        int token_count
        string index_status
    }
```

### 6.2 PostgreSQL 表职责

#### `tenants/users/user_memberships`

- 保存用户与租户关系、角色和状态。
- 角色初始定义为 `tenant_admin`、`kb_editor`、`kb_viewer`、`auditor`。
- API 从认证身份和 membership 计算权限，不接受模型或客户端直接指定角色。

#### `knowledge_bases`

- 作为权限、检索和数据生命周期的主要边界。
- 保存默认检索配置、语言、保留策略和当前配置版本。

#### `documents`

- 表示业务意义上的一份文档，不再用文件名充当文档身份。
- `active_version_id` 指向当前对查询可见的版本。
- 删除操作先进入 `DELETING`，完成所有存储清理后进入 `DELETED`。

#### `document_versions`

- 每次内容变化或解析流水线变化都产生新版本。
- 唯一约束建议包含 `document_id + content_sha256 + pipeline_signature`。
- 状态包括 `DRAFT`、`PROCESSING`、`READY`、`ACTIVE`、`RETIRED`、`FAILED`、`DELETED`。

#### `ingestion_jobs`

- 保存任务当前步骤、进度、尝试次数、心跳、租约、错误码和时间指标。
- 任务状态是用户看到的唯一进度来源，不能只依赖 Celery result backend。
- 同一个 `document_version_id + pipeline_signature` 最多存在一个非终态任务。

#### `parent_chunks/child_chunk_manifests`

- `parent_chunks` 保存完整父块文本，实现真正的 Small2Big/Parent-Child Retrieval。
- `child_chunk_manifests` 保存索引清单和校验信息，向量与可搜索子块正文存入 Milvus。
- 通过 manifest 对比预期块数量与 Milvus 实际数量。

#### `conversations/messages/checkpoints`

- 会话与消息保存业务展示所需内容。
- LangGraph 使用 PostgreSQL Checkpointer 保存节点状态和恢复点。
- 长期记忆与线程 checkpoint 分开管理，并设置 TTL 或归档策略。

#### `audit_events/outbox_events`

- `audit_events` 记录上传、发布、删除、权限变更、工具调用和管理员操作。
- `outbox_events` 与业务事务一起提交，再由发布器投递 Celery，解决“数据库已提交但消息未发送”的间隙。

### 6.3 对象存储路径

```text
rag-documents/
└── {tenant_id}/
    └── {knowledge_base_id}/
        └── {document_id}/
            └── {version_id}/
                ├── original/{safe_filename}
                ├── parsed/document.json
                ├── ocr/page-0001.json
                ├── artifacts/tables.json
                └── reports/ingestion-report.json
```

对象默认不可变。数据库中只保存 object key、哈希、大小、MIME、版本和状态，不保存本机绝对路径。

### 6.4 Milvus Collection Schema

推荐初始字段：

| 字段 | 类型/用途 |
|---|---|
| `child_id` | 主键，内容与流水线版本共同决定 |
| `tenant_id` | 必须过滤的租户字段 |
| `knowledge_base_id` | 必须过滤的知识库字段 |
| `document_id` | 文档过滤和删除 |
| `document_version_id` | 版本可见性校验 |
| `parent_id` | 父块批量回取 |
| `ordinal` | 子块顺序和邻居扩展 |
| `source` | 展示文件名 |
| `heading_path` | 标题路径 |
| `locator` | 页码、表格、工作表、行号等展示定位 |
| `text` | 子块正文，BM25 输入和 Reranker 输入 |
| `dense_vector` | BGE-M3 稠密向量，维度与模型配置绑定 |
| `sparse_vector` | Milvus BM25 Function 产生或显式写入 |
| `is_active` | 索引侧快速过滤，不能作为唯一版本真相 |
| `pipeline_signature` | 支持索引迁移与问题定位 |

租户、知识库和版本是高频过滤字段，应使用独立标量字段；动态 JSON metadata 只用于扩展展示和低频过滤，不能承担权限控制。

### 6.5 多租户策略

本项目首先面向“单企业、多知识库”场景：共享 collection，并使用 `tenant_id + knowledge_base_id` 强制过滤。若演进为 SaaS：

- 强隔离或受监管租户：优先 database-per-tenant 或 collection-per-tenant。
- 大量小租户：可以评估 partition key，但必须接受较弱隔离且应用层仍需鉴权。
- 策略选择必须经过规模、隔离、RBAC 和性能测试，不能只按租户数量决定。

## 7. 文档上传与异步入库

### 7.1 上传时序

```mermaid
sequenceDiagram
    actor U as 用户
    participant A as FastAPI
    participant P as PostgreSQL
    participant O as MinIO/S3
    participant Q as Redis/Celery
    participant W as Ingestion Worker

    U->>A: POST /documents + Idempotency-Key
    A->>A: 鉴权/权限/扩展名/MIME/大小校验
    A->>P: 查询或创建 document/version
    A->>O: 流式上传不可变原文件
    A->>P: 事务写 version、job、outbox
    A-->>U: 202 Accepted + document_id/version_id/job_id
    P->>Q: Outbox Publisher 投递任务
    Q->>W: 至少一次交付 job_id
    W->>P: 获取任务租约并更新心跳
    W->>O: 读取原文件
    W->>W: 解析/切块/Embedding/索引/验证
    W->>P: 发布新版本并完成任务
    U->>A: GET /ingestion-jobs/{job_id}
    A->>P: 查询权威任务状态
    A-->>U: 当前阶段、进度、错误或完成结果
```

上传接口返回 `202 Accepted`，并不表示文档已经可检索；只有任务进入 `PUBLISHED` 且文档版本进入 `ACTIVE` 后才可查询。

### 7.2 入库状态机

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> VALIDATING: Worker取得租约
    VALIDATING --> QUARANTINED: 安全检查失败
    VALIDATING --> PARSING: 文件合法
    PARSING --> CHUNKING: 解析成功
    CHUNKING --> EMBEDDING: 生成父子块
    EMBEDDING --> INDEXING: 向量批次完成
    INDEXING --> VERIFYING: Milvus写入完成
    VERIFYING --> PUBLISHING: 数量/维度/抽样检索通过
    PUBLISHING --> PUBLISHED: 原子切换有效版本

    VALIDATING --> RETRY_WAIT: 瞬时依赖错误
    PARSING --> RETRY_WAIT: 可重试错误
    EMBEDDING --> RETRY_WAIT: 限流/超时
    INDEXING --> RETRY_WAIT: Milvus暂时不可用
    VERIFYING --> RETRY_WAIT: 可恢复校验错误
    RETRY_WAIT --> PENDING: 退避到期

    VALIDATING --> FAILED: 永久错误或重试耗尽
    PARSING --> FAILED: 永久错误或重试耗尽
    CHUNKING --> FAILED: 配置或数据错误
    EMBEDDING --> FAILED: 重试耗尽
    INDEXING --> FAILED: 重试耗尽
    VERIFYING --> FAILED: 数据不一致
    PENDING --> CANCELLED: 用户取消
    RETRY_WAIT --> CANCELLED: 用户取消

    PUBLISHED --> [*]
    FAILED --> [*]
    QUARANTINED --> [*]
    CANCELLED --> [*]
```

状态转换必须通过带版本号的条件更新，例如 `WHERE id=? AND state=? AND row_version=?`，防止两个 Worker 同时推进一个任务。

### 7.3 详细处理流程

```mermaid
flowchart TD
    Start[读取 job/version/object key] --> Lease{租约有效且任务可执行?}
    Lease -->|否| Exit[安全退出]
    Lease -->|是| Validate[文件签名/MIME/大小/压缩比/恶意文件扫描]
    Validate -->|永久失败| Quarantine[隔离或 FAILED]
    Validate --> Parse[格式插件解析为 Document AST]
    Parse --> Normalize[结构化清洗与元数据标准化]
    Normalize --> Parent[按标题/段落/表格构造 ParentChunk]
    Parent --> Child[按 Token 上限生成重叠 ChildChunk]
    Child --> Cache{Embedding缓存命中?}
    Cache -->|是| Cached[读取 content_hash + model_version 向量]
    Cache -->|否| Embed[限流批量调用 BGE-M3]
    Cached --> Stage
    Embed --> Stage[写入 staging manifest]
    Stage --> Index[批量写入 Milvus is_active=false]
    Index --> Flush[Flush并等待可查询]
    Flush --> Verify[核对块数/维度/哈希/抽样搜索]
    Verify -->|失败| Compensate[记录失败并清理 staging 数据]
    Verify -->|通过| Publish[发布新版本]
    Publish --> Active[查询可见]
    Active --> Cleanup[异步清理旧版本和过期产物]
```

### 7.4 文件校验与安全处理

1. 客户端文件名只用于展示，存储 key 使用服务端 UUID。
2. 同时检查扩展名、MIME 和文件魔数，禁止仅根据扩展名判断格式。
3. 对 DOCX/XLSX 检查 ZIP 成员数、压缩比和解压后总大小。
4. 设置最大文件大小、最大页数、最大工作表数、最大行列数和解析超时。
5. 加密文档、损坏文档和不支持特性返回稳定错误码，不直接暴露堆栈。
6. 可疑文件进入隔离区，不进入解析 Worker。
7. 原文件哈希在流式上传过程中计算，避免再次读取整份文件。

### 7.5 格式解析策略

| 格式 | 结构单元 | 首选能力 | 回退与边界 |
|---|---|---|---|
| PDF | 页、版面块、标题、表格 | 文本层 + 版面顺序 | 无文本层时可选 OCR；复杂表格记录置信度 |
| DOCX | 按原始顺序的段落、标题、表格 | XML block 顺序遍历 | 视觉标题识别为增强项 |
| XLSX | 工作表、表头、数据区域 | 流式读取、表头探测 | 公式缓存状态和合并单元格显式记录 |
| Markdown | AST 节点 | 标题、代码块、表格感知 | 不使用单行正则模拟完整语法 |
| TXT | 段落与行号区间 | 编码检测、流式读取 | 无结构时保留行号 locator |

解析输出改为统一的 Document AST/Block 模型，至少包含：

```text
Document
├── document/version/source/language
└── blocks[]
    ├── block_id/type/order
    ├── heading_path
    ├── text
    ├── locator
    ├── structural_metadata
    └── extraction_confidence
```

### 7.6 Token 与结构感知切块

```mermaid
flowchart LR
    Blocks[同一标题下的连续 Block] --> Merge[按结构合并父块]
    Merge --> ParentLimit{父块是否超过 Token 上限?}
    ParentLimit -->|否| Parent[保存 ParentChunk全文]
    ParentLimit -->|是| Sentence[按段落/句子边界拆分]
    Sentence --> Parent
    Parent --> ChildSplit[使用 Embedding Tokenizer 切子块]
    ChildSplit --> Overlap[在句子边界构造 10%-20% 重叠]
    Overlap --> Context[为 Embedding 拼接受控标题上下文]
    Context --> Children[ChildChunk列表]
```

原则：

- 父块是完整业务语义容器，优先按标题、条款、段落或表格区域划分，不机械重叠。
- 子块用于召回，长度由 BGE-M3 tokenizer 计算，并保留受控重叠。
- 新子块的起点尽量落在句子或段落边界，不从任意字符中间开始。
- 表格使用行组切分并重复表头，但不能把表头计为业务重复内容。
- `heading_path` 可拼接到 embedding 输入，但原文与增强文本分别保存，避免引用污染。
- 块大小不是固定真理，必须通过不同文档类型的 Recall、MRR、延迟和成本实验确定。

### 7.7 Embedding 与索引

- 按模型允许的批量大小和供应商限流动态分批。
- 缓存键包含 `normalized_content_hash + embedding_model + model_revision + preprocessing_version`。
- 每批记录开始时间、结束时间、文本数、token 数、重试次数和供应商 request ID。
- 只对明确的瞬时错误重试；参数错误、超长输入和鉴权错误直接失败。
- 重试使用指数退避与 jitter，并设置任务级最大时间预算。
- 每个向量写入前校验维度、有限值和子块映射关系。
- Milvus 插入使用稳定主键；相同任务重复执行时写入结果一致或安全 upsert。
- 写入完成后执行 flush、数量核对和少量已知文本的抽样搜索。

### 7.8 幂等与发布协议

```mermaid
sequenceDiagram
    participant W as Worker
    participant P as PostgreSQL
    participant M as Milvus
    participant C as Redis Cache

    W->>P: 创建/恢复 version 与 manifest
    W->>M: 幂等写入新版本，is_active=false
    W->>M: flush + count + sample search
    M-->>W: 校验通过
    W->>M: 新版本 is_active=true，旧版本暂时保持 true
    W->>M: 验证新版本在 active 过滤下可搜索
    W->>P: 事务锁定 document
    W->>P: 新版本 READY→ACTIVE，旧版本 ACTIVE→RETIRED
    W->>P: 更新 document.active_version_id
    W->>P: 写 outbox version_published
    W->>P: 提交事务
    P-->>C: Outbox消费者刷新 active-version 缓存
    W->>M: 将旧版本 is_active=false
    W->>P: 标记索引侧同步完成
```

跨 PostgreSQL 与 Milvus 无法获得传统单库 ACID，因此采用 Saga/可补偿发布：

- PostgreSQL 的 `active_version_id` 是最终业务真相。
- Milvus 的 `is_active` 用于快速预过滤。
- 查询结果返回前，再根据缓存或 PostgreSQL 活跃版本清单进行防御性校验。
- 切换前让新旧版本同时满足 Milvus active 过滤，切换点前由 PostgreSQL 清单只接受旧版本，切换点后只接受新版本，从而避免无结果窗口。
- 如果 PostgreSQL 发布事务失败，新版本虽然暂时在 Milvus 标记为 active，也会被旧的权威版本清单拒绝，并由 Reconciler 清理。
- Reconciler 定期对比 PostgreSQL manifest 和 Milvus，修复缺块、错误 active 标记和孤儿数据。
- 新版本验证失败时不切换 `active_version_id`，旧版本持续服务。
- 全量 Schema/Embedding 迁移采用 blue-green collection + alias 切换，保留快速回滚窗口。

### 7.9 删除流程

```text
DELETE 请求
→ PostgreSQL 标记 DELETING 并立即阻止新查询
→ 创建 purge job
→ 删除/停用 Milvus 子块
→ 删除父块与 manifest
→ 按保留策略删除或归档对象存储文件
→ 清理缓存
→ 写不可篡改审计事件
→ 标记 DELETED
```

删除任务同样幂等；任一步失败都可从记录的 step 继续执行。

## 8. 查询与 Agentic RAG

### 8.1 查询主流程

```mermaid
sequenceDiagram
    actor U as 用户
    participant A as FastAPI
    participant P as Policy Service
    participant G as LangGraph
    participant E as Embedding API
    participant M as Milvus
    participant R as Reranker API
    participant DB as PostgreSQL/Parent Store
    participant L as LLM API

    U->>A: POST /chat/stream
    A->>A: JWT、限流、输入长度、trace_id
    A->>P: 解析用户允许访问的 tenant/kb/tool
    P-->>A: 服务端权限上下文
    A->>G: question + policy_context + thread_id
    G->>G: 意图识别/是否需要澄清
    G->>E: 查询向量
    G->>M: tenant/kb/version过滤下 Dense + BM25
    M-->>G: RRF融合候选
    G->>G: 丢弃非活跃版本并去重
    G->>R: 批量重排候选
    R-->>G: 相关性排序
    G->>DB: 根据 parent_id 批量读取父块/邻居
    DB-->>G: 授权后的完整上下文
    G->>G: 去重、引用编号、Token预算组装
    G->>L: 系统指令 + 问题 + 不可信证据
    L-->>G: 结构化答案与引用
    G->>G: 引用存在性/权限/事实一致性检查
    G-->>A: 节点事件与最终结果
    A-->>U: SSE
```

### 8.2 LangGraph 状态

状态中只保存可序列化、可审计的数据，不保存数据库连接和客户端对象。建议字段：

```text
request_id / trace_id / thread_id
user_id / tenant_id / allowed_kb_ids
question / normalized_question / rewritten_queries
intent / route / clarification_reason
retrieval_attempt / retrieval_mode
candidate_child_ids / authorized_hits
selected_parent_ids / context_blocks / citations
tool_call / tool_result / approval_state
answer_draft / final_answer / grounded
error_code / fallback_path / latency_breakdown
```

LangGraph 使用 PostgreSQL Checkpointer。对话线程、用户和租户 namespace 必须绑定，不能只凭客户端提供的 `thread_id` 读取状态。

### 8.3 查询路由

```mermaid
flowchart TD
    Analyze[analyze_query] --> Route{意图与信息是否充分?}
    Route -->|闲聊| Chitchat[chitchat]
    Route -->|缺少必要参数| Clarify[clarification]
    Route -->|文档知识| Retrieve[retrieve]
    Route -->|结构化/实时业务| ToolGate[tool_policy_check]
    Route -->|越权或危险请求| Refuse[refuse]

    Retrieve --> Relevant{相关性是否达标?}
    Relevant -->|否且未重试| Rewrite[rewrite_search]
    Rewrite --> Retrieve
    Relevant -->|否且已重试| Refuse
    Relevant -->|是| Expand[parent_expand/context_build]
    Expand --> Generate[generate_answer]

    ToolGate -->|允许| RunTool[run_tool]
    ToolGate -->|需审批| Interrupt[human_approval]
    ToolGate -->|拒绝| Refuse
    Interrupt -->|批准| RunTool
    Interrupt -->|拒绝| Refuse
    RunTool --> Generate

    Generate --> Validate[citation_and_fact_check]
    Validate -->|通过| Finish[finish]
    Validate -->|可修正| Revise[revise_answer]
    Validate -->|无证据| Refuse
```

### 8.4 混合检索

1. 查询标准化：只做可解释的空白、语言和 Unicode 处理，不删除型号、数字和符号。
2. Query Rewrite：保留原始查询，同时生成数量受限的改写；所有改写继承相同权限过滤。
3. Dense：BGE-M3 处理语义改写、同义表达和跨语言相似性。
4. BM25：处理型号、制度编号、价格、缩写和精确关键词。
5. RRF：仅基于排名融合不同分数空间，不直接相加 Dense 与 BM25 原始分数。
6. Oversampling：融合后获取多于最终数量的候选，为权限校验、版本过滤和去重留余量。
7. Reranker：对授权后的有限候选进行 Cross-Encoder 重排。
8. Parent Expansion：根据命中子块读取父块，必要时加入相邻子块或相邻父块。
9. Context Builder：按 token 预算、文档多样性、引用完整性和去重规则选择证据。

### 8.5 Parent-Child Retrieval

```text
用户问题
→ 对 ChildChunk 搜索，获得精确命中
→ 对命中结果按 parent_id 分组
→ 每个父块保留最高分子块
→ 批量读取 ParentChunk 全文
→ 根据命中位置选择父块或局部邻居窗口
→ 去除父块之间重复文本
→ 加入 source/heading/locator/citation_id
→ 在上下文预算内交给 LLM
```

父块默认不机械重叠，因为它应是完整结构单元；若语料是长篇叙述，应通过评测选择父块 overlap 或邻居扩展。子块 overlap 只在同一父块内部发生。

### 8.6 降级与错误路径

```mermaid
flowchart LR
    Query[查询请求] --> Embed{Embedding可用?}
    Embed -->|是| Hybrid[Dense + BM25]
    Embed -->|否| Sparse[降级为BM25并标记fallback]
    Hybrid --> Rerank{Reranker可用?}
    Sparse --> Rerank
    Rerank -->|是| Ranked[重排结果]
    Rerank -->|否| RRF[RRF顺序]
    Ranked --> Evidence{证据充分?}
    RRF --> Evidence
    Evidence -->|否| Refuse[明确拒答/建议澄清]
    Evidence -->|是| Generate{LLM可用?}
    Generate -->|是| Answer[生成并校验]
    Generate -->|否| Error[返回可重试错误，不伪造答案]
```

降级必须在响应和指标中显式记录，不能让用户或评测脚本误以为完整链路正常运行。

## 9. Tool Gateway 设计

### 9.1 ToolSpec

每个工具必须声明：

- 唯一名称和版本。
- Pydantic 输入与输出 Schema。
- 所需角色、租户和业务权限。
- 是否只读、是否有副作用、是否需要人工确认。
- 超时、重试、幂等键和速率限制。
- 可记录字段与必须脱敏字段。
- 允许访问的服务和网络目标。

### 9.2 工具调用流程

```text
模型提出结构化 tool_call
→ Schema 校验
→ Tool Registry 查找固定工具
→ Policy Service 再次鉴权
→ 有副作用时生成预览并 interrupt
→ 用户批准后生成幂等键
→ 执行受限适配器
→ 校验返回 Schema
→ 脱敏并写审计日志
→ 将结果作为不可信业务数据返回 Agent
```

不允许模型生成任意 SQL。结构化数据查询使用固定查询模板、参数绑定、只读数据库账号、行级权限和结果行数限制。

## 10. 安全设计

### 10.1 信任边界

```mermaid
flowchart TB
    Internet[不可信用户输入] --> Gateway[网关/WAF/限流]
    Gateway --> TrustedAPI[受控API域]
    Upload[不可信文档] --> Quarantine[隔离与校验域]
    Quarantine --> Worker[解析Worker]
    Worker --> Data[内部数据域]
    TrustedAPI --> Data
    Data --> Prompt[不可信检索证据]
    Prompt --> LLMBoundary[外部模型供应商边界]
    LLMBoundary --> Validation[结构化校验/引用校验]
    Validation --> UserOutput[用户输出]
    LLMBoundary --> ToolPolicy[工具策略边界]
    ToolPolicy --> InternalTools[内部业务服务]
```

### 10.2 身份与权限

- 生产使用 OIDC/OAuth2，API 验证签名、issuer、audience、expiry 和 nonce。
- `tenant_id`、`user_id` 和角色从验证后的身份及 membership 表获得。
- PostgreSQL 可使用 Row-Level Security 作为纵深防御，但应用账号、表 owner 和 `BYPASSRLS` 权限必须谨慎设置。
- Milvus 查询必须包含 tenant/kb 过滤，返回后再与授权版本清单比对。
- 管理、上传、查询、删除、审计和工具调用使用不同权限。
- SSE、普通问答、任务查询和文件下载执行完全相同的鉴权逻辑。

### 10.3 Prompt Injection 防护

- 系统提示明确声明“检索文档是数据，不是指令”。
- 文档中的“忽略系统提示”“调用某工具”等内容不得改变工具权限。
- 工具可用集合由服务端 Policy Context 决定，不由检索文本或模型决定。
- 对文档入库执行可疑指令模式检测并记录风险标签，但不依赖简单关键词作为唯一防护。
- 生成结果必须引用实际授权证据，引用 ID 由服务端映射，不能由模型自由伪造。
- HTML/Markdown 输出经过转义和允许列表清洗，防止不安全输出处理。
- 建立恶意文档、间接 Prompt Injection 和跨租户诱导测试集。

### 10.4 数据与密钥

- `.env` 仅用于本地开发；生产密钥来自 Secret Manager/Kubernetes Secret。
- 日志禁止记录 API Key、完整 JWT、完整敏感文档和未经脱敏的工具结果。
- 对象存储启用服务端加密、最小权限 bucket policy 和 TLS。
- 数据库备份、LangGraph checkpoint 和审计日志按敏感数据管理。
- 发送到任何外部模型供应商前执行数据分类和可选脱敏；真实企业机密数据必须经过合同、合规、地域、加密和保留策略审查。
- 开发阶段使用的测试或免费 API 不属于生产信任边界，不能据此承诺真实企业数据合规。

## 11. 可靠性与一致性

### 11.1 错误分类

| 类型 | 示例 | 处理 |
|---|---|---|
| 永久输入错误 | 不支持格式、损坏文件、超限、加密文件 | 不重试，返回稳定错误码 |
| 鉴权/权限错误 | Key 无效、用户无知识库权限 | 不重试，记录安全事件 |
| 瞬时网络错误 | 超时、连接重置、502/503 | 有限指数退避 + jitter |
| 配额错误 | 429、租户或供应商配额耗尽 | 尊重 Retry-After，任务进入 RETRY_WAIT |
| 数据错误 | 向量维度不符、块数不一致 | 停止发布，进入 FAILED |
| Worker 故障 | 进程退出、机器重启 | 租约过期后重新交付并幂等恢复 |
| 依赖长期故障 | Milvus/模型连续失败 | 熔断、告警、拒绝新重任务 |

### 11.2 超时与重试预算

- HTTP、Embedding、Reranker、LLM、Milvus、对象存储和数据库分别配置连接/读取/总超时。
- 重试次数不是各层无限叠加；一次请求有统一 deadline，各组件只使用剩余预算。
- 只重试幂等调用或带幂等键的操作。
- 使用 jitter 防止依赖恢复时所有任务同时重试。
- Circuit Breaker 打开后快速失败或进入队列等待，避免线程被耗尽。

Celery Worker 在任务实现幂等后启用 late acknowledgement，并设置有限重试、soft/hard time limit、Worker 心跳和合理的 prefetch。Worker 崩溃可能导致同一任务再次执行，因此所有步骤都通过稳定主键、唯一约束、条件状态更新和 manifest checkpoint 消除重复副作用；不能依赖“任务正常只执行一次”的假设。

### 11.3 Reconciler

定时一致性任务负责：

- 找出 PostgreSQL 为 ACTIVE 但 Milvus 块数不足的版本。
- 找出 Milvus 中没有 manifest 的孤儿块。
- 修复错误的 `is_active` 标记。
- 清理超过回滚保留期的 RETIRED 版本。
- 检查对象存储原文件、解析产物和数据库记录是否一致。
- 输出修复报告，不在没有审计的情况下静默删除大量数据。

### 11.4 备份与恢复

- PostgreSQL：定期全量备份 + WAL/PITR，恢复演练必须验证权限和 active version。
- MinIO/S3：开启版本化与生命周期策略，Milvus 内部 bucket 与业务文件 bucket 分离凭据。
- Milvus：使用与版本匹配的备份工具，并记录 collection schema、index 参数和模型版本。
- Redis：Broker 配置持久化和高可用；缓存内容允许重建。
- 恢复顺序：PostgreSQL → 对象存储 → Milvus → Reconciler → API/Worker。

## 12. 可观测性

### 12.1 统一关联标识

每条链路至少携带：

```text
trace_id
request_id
tenant_id
user_id（日志中可哈希）
knowledge_base_id
document_id / version_id / job_id
thread_id
model_provider / model / model_revision
pipeline_signature / prompt_version
```

### 12.2 指标

#### API

- 请求量、4xx/5xx、P50/P95/P99。
- SSE 首事件、首 Token、完整响应和断开率。
- 每租户限流、并发和超时数量。

#### 入库

- 各状态任务数、队列深度、任务年龄、成功率和重试率。
- 每格式解析耗时、页数、块数、token 数和失败码。
- Embedding 批次数、429、供应商延迟和缓存命中率。
- 发布失败、Reconciler 差异和孤儿数据数量。

#### 检索与 Agent

- Dense/BM25/RRF/Reranker 各阶段延迟。
- 候选数、去重数、权限过滤数、父块扩展数。
- 查询重写比例、二次检索比例、拒答率、降级率。
- 每节点 LLM token、调用成本、错误率和事实校验失败率。

#### 基础设施

- PostgreSQL 连接池、慢查询、锁等待、磁盘和复制延迟。
- Redis 队列、内存和 evictions。
- Milvus 查询延迟、segment、index、compaction、内存和磁盘。
- Worker CPU、内存、任务租约过期和 OOM。

### 12.3 日志与追踪

- 使用 JSON 结构化日志，错误包含稳定 `error_code`，详细堆栈只在服务端。
- OpenTelemetry 贯穿 API、Celery header、模型请求、Milvus 和 PostgreSQL。
- Langfuse 可用于模型与 Prompt 观测，但必须脱敏并可关闭。
- 不把完整文档和完整提示默认写入日志；调试采样需经过授权和保留期控制。

## 13. 评测体系

### 13.1 数据集分层

1. `smoke`：少量简单问题，用于确认链路可运行。
2. `retrieval_hard`：同义改写、型号、数字、跨段信息和相似干扰文档。
3. `unanswerable`：知识库没有答案，测试拒答。
4. `citation`：答案与页码、标题、表格行严格对应。
5. `permission`：不同用户只能召回被授权文档。
6. `versioning`：旧版本内容发布后不再被回答。
7. `prompt_injection`：恶意文档和恶意用户提示不能扩大权限或触发工具。
8. `failure`：模型、Milvus、Redis、PostgreSQL 和 Worker 故障路径。

### 13.2 指标

#### 检索指标

- Recall@K
- MRR
- nDCG@K
- Precision@K
- Parent Recall@K
- 权限过滤正确率
- 版本可见性正确率

#### 生成指标

- Answer Correctness
- Faithfulness/Groundedness
- Citation Precision/Recall
- 无答案场景拒答 Precision/Recall
- 工具选择和参数正确率
- 人工评分及错误类型分布

#### 系统指标

- P50/P95/P99 延迟
- 首 Token 时间
- 429/重试/降级率
- 每问题 token 与 API 成本
- 入库吞吐、峰值内存和恢复时间

### 13.3 对照实验

固定同一数据集和索引版本，对比：

```text
BM25 only
Dense only
Dense + BM25 + RRF
Hybrid + Reranker
Hybrid + Reranker + Parent Expansion
不同 chunk token/overlap 参数
有无 query rewrite
```

每次实验记录 Git commit、数据集版本、模型、Prompt、pipeline signature、Milvus index 参数和运行环境。简单数据集全部满分时，不声称某方案提升准确率，而应增加难例后重新比较。

## 14. 测试策略

```mermaid
flowchart TB
    Unit[单元测试<br/>解析/切块/路由/策略] --> Contract[契约测试<br/>模型/对象存储/工具]
    Contract --> Integration[集成测试<br/>Postgres/Redis/MinIO/Milvus]
    Integration --> E2E[端到端测试<br/>上传到引用回答]
    E2E --> Security[安全测试<br/>越权/注入/恶意文件]
    Security --> Load[性能测试<br/>并发/大文档/队列]
    Load --> Chaos[故障注入<br/>断网/重启/部分失败]
    Chaos --> Release[发布门禁]
```

最低发布门禁：

- 单元和集成测试全部通过。
- 数据库迁移可以升级和回滚。
- 同一任务重复投递不会产生两个活跃版本。
- Worker 在每个关键步骤退出后均可恢复。
- 权限测试和 Prompt Injection 测试无高危失败。
- 检索质量不低于上一稳定版本设定的阈值。
- P95 延迟、峰值内存和错误率在目标范围。
- 备份能够在干净环境完成恢复。

## 15. API 设计

### 15.1 文档管理

```text
POST   /api/v1/knowledge-bases/{kb_id}/documents
GET    /api/v1/knowledge-bases/{kb_id}/documents
GET    /api/v1/documents/{document_id}
GET    /api/v1/documents/{document_id}/versions
POST   /api/v1/documents/{document_id}/versions
DELETE /api/v1/documents/{document_id}
POST   /api/v1/documents/{document_id}/reindex
```

上传要求 `Idempotency-Key`，返回：

```json
{
  "document_id": "uuid",
  "version_id": "uuid",
  "job_id": "uuid",
  "status": "PENDING"
}
```

### 15.2 任务

```text
GET  /api/v1/ingestion-jobs/{job_id}
POST /api/v1/ingestion-jobs/{job_id}/cancel
POST /api/v1/ingestion-jobs/{job_id}/retry
GET  /api/v1/ingestion-jobs/{job_id}/events
```

### 15.3 问答

```text
POST /api/v1/chat
POST /api/v1/chat/stream
GET  /api/v1/conversations/{thread_id}
POST /api/v1/answers/{answer_id}/feedback
```

请求中的 `kb_ids` 只是用户期望范围，服务端必须与实际授权范围取交集。

### 15.4 错误格式

统一使用 Problem Details 风格：

```json
{
  "type": "https://errors.example/ingestion/unsupported-format",
  "title": "Unsupported document format",
  "status": 422,
  "code": "INGEST_UNSUPPORTED_FORMAT",
  "detail": "该文件格式尚未开放",
  "request_id": "uuid",
  "retryable": false
}
```

## 16. 配置与版本治理

### 16.1 Pipeline Signature

```text
pipeline_signature = SHA256(
    parser_name + parser_version
    + normalization_version
    + chunker_version + chunk_parameters
    + embedding_model + embedding_revision + dimension
    + milvus_schema_version
)
```

Pipeline Signature 改变时，不允许直接把新旧向量混在一起而不记录版本。模型、Prompt、Reranker 和检索参数同样需要版本化。

### 16.2 配置分类

- 启动时固定：数据库、Milvus、模型名称、维度、Schema 版本。
- 可热更新：Top-K、阈值、超时、租户限流，但需要配置版本和审计。
- 密钥：只从密钥管理系统或本地 `.env` 获取，禁止写入设计文档和数据库普通字段。
- 功能开关：OCR、Reranker、Query Rewrite、Langfuse 必须可关闭并记录实际启用状态。

## 17. 部署架构

### 17.1 本地 Docker Compose

```mermaid
flowchart LR
    Browser[浏览器] --> App[FastAPI + Gradio]
    App --> Postgres[(PostgreSQL)]
    App --> Redis[(Redis)]
    Redis --> Worker[Celery Worker x1]
    Worker --> Postgres
    Worker --> MinIO[(MinIO App Bucket)]
    Worker --> Milvus[(Milvus Standalone)]
    Milvus --> Etcd[(etcd)]
    Milvus --> MilvusMinIO[(MinIO Milvus Bucket)]
    App --> Provider[测试 Model Provider]
    Worker --> Provider
```

本地仍然使用容器模拟服务边界。业务文件 bucket 与 Milvus 内部 bucket 分离，禁止共用管理员凭据。

### 17.2 生产参考部署

```mermaid
flowchart TB
    Client[企业用户] --> LB[WAF/Ingress/TLS]
    LB --> API1[API Pod]
    LB --> API2[API Pod]
    API1 --> PgBouncer[PgBouncer]
    API2 --> PgBouncer
    PgBouncer --> PG[(PostgreSQL HA)]
    API1 --> Redis[(Redis HA)]
    API2 --> Redis
    Redis --> IW[Ingestion Worker Pool]
    Redis --> QW[Query/Utility Worker Pool]
    IW --> Object[(S3/MinIO HA)]
    IW --> Milvus[(Milvus Distributed)]
    API1 --> Milvus
    API2 --> Milvus
    API1 --> Provider[Approved Model Provider]
    API2 --> Provider
    IW --> Provider
    API1 --> OTEL[OTel Collector]
    API2 --> OTEL
    IW --> OTEL
    Milvus --> Prom[Prometheus/Grafana/Alerting]
    OTEL --> Prom
```

### 17.3 CI/CD

```text
提交代码
→ 格式、静态检查、单元测试
→ 构建不可变镜像并生成 SBOM
→ 依赖和镜像漏洞扫描
→ 启动临时依赖执行集成测试
→ 运行数据库迁移验证
→ 运行小型检索回归集
→ 部署 Staging
→ E2E、安全和故障测试
→ 人工批准
→ 灰度/滚动发布
→ 指标异常自动停止或回滚
```

数据库迁移与应用版本需要兼容滚动升级；先扩展 Schema，再部署新代码，最后清理旧字段。

## 18. 目标代码结构

```text
project/
├── api/                       HTTP/SSE、认证依赖、错误映射
├── application/
│   ├── commands/              上传、发布、删除、重建索引
│   ├── queries/               文档、任务、会话查询
│   └── services/              应用编排，不含基础设施细节
├── domain/
│   ├── documents/             文档、版本、任务状态机
│   ├── retrieval/             Chunk、Citation、RetrievalResult
│   └── agents/                ToolPolicy、Conversation
├── adapters/
│   ├── postgres/              Repository、事务、Outbox
│   ├── milvus/                Schema、索引、搜索适配器
│   ├── object_store/          MinIO/S3
│   ├── model_provider/        SiliconFlow及后续供应商
│   └── tools/                 企业服务适配器
├── ingestion/
│   ├── parsers/               按格式插件化
│   ├── normalization/
│   ├── chunking/
│   └── tasks/                 Celery任务与幂等步骤
├── rag_agent/                 LangGraph State/Nodes/Edges
├── security/                  Policy、脱敏、输出清洗
├── observability/             日志、指标、Tracing
├── migrations/                PostgreSQL迁移
├── evaluation/                数据集、Runner、报告
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    ├── e2e/
    ├── security/
    └── load/
```

领域层不能直接 import FastAPI、Celery、MilvusClient 或具体模型 SDK。基础设施通过 Protocol/Interface 注入，避免当前 `RAGSystem` 成为全局大对象。

## 19. 从当前代码迁移

| 当前模块 | 处理方式 | 目标 |
|---|---|---|
| `ingestion/models.py` | 重构 | 增加 DocumentVersion、Block、ParentChunk、ChildChunk、稳定类型 |
| `ingestion/parsers.py` | 保留接口并插件化重写 | 格式感知、安全限制、流式解析、结构置信度 |
| `ingestion/chunker.py` | 重写 | Token + 结构切块，保存父块，配置可评测 |
| `ingestion/pipeline.py` | 拆分 | Command Service + Celery Job State Machine + Publisher |
| `retrieval/milvus_store.py` | 重构 | 租户过滤、批处理、版本发布、Schema migration |
| `retrieval/hybrid_retriever.py` | 扩展 | ACL、版本防御校验、Parent Expansion、deadline/fallback |
| `core/rag_system.py` | 移除全局大容器 | FastAPI lifespan + 显式依赖注入 |
| `InMemorySaver` | 替换 | PostgreSQL Checkpointer，支持恢复和多实例 |
| `rag_agent/tools.py` | 重构 | Tool Registry + Policy + Audit + Idempotency/HITL |
| `api/main.py` | 拆分路由 | 管理、任务、问答、健康、审计分别维护 |
| `ui/gradio_app.py` | 保留演示定位 | 不承担生产权限与核心业务逻辑 |
| `scripts/evaluate_retrieval.py` | 扩展 | 版本化数据集、生成质量、安全和性能评测 |

## 20. 分阶段实施与验收

### 阶段 0：设计冻结与基线

- 冻结当前数据集、评测结果和 Git commit。
- 建立 ADR、错误码、状态机和 Pipeline Signature。
- 将当前运行结果作为迁移前基线。

验收：当前 Demo 可重复运行，所有已知不足都有编号和目标阶段。

### 阶段 1：控制面与异步任务

- 加入 PostgreSQL、Redis、Celery、MinIO 业务 bucket。
- 实现 tenant/kb/document/version/job/outbox 基础表。
- 上传返回 202 + job_id，任务状态可查询。
- 实现租约、幂等键、有限重试和 Worker 重启恢复。

验收：同一文件并发提交不产生两个有效版本；在关键步骤杀死 Worker 后任务可恢复。

### 阶段 2：工业化解析与切块

- 引入 Document AST、格式插件、安全限制和流式处理。
- 实现 Token + 结构感知切块。
- 持久化 ParentChunk 和 Child Manifest。
- 修复当前不足清单中 parser/chunker 的 P0/P1。

验收：格式测试矩阵、大文件内存测试、恶意压缩包测试和 locator 正确率测试通过。

### 阶段 3：可靠索引与版本发布

- 实现批量 embedding、缓存、限流和断点。
- 实现 staging、验证、发布、补偿和 Reconciler。
- 实现 active version 双重校验和旧版本回滚。

验收：Milvus 在删除、插入、flush、发布各阶段故障时，旧版本持续可用或系统明确拒绝，不出现半发布结果。

### 阶段 4：检索和 Agent

- 完成 ACL-aware Hybrid Retrieval 和 Parent Expansion。
- 使用 PostgreSQL Checkpointer。
- 实现 Tool Policy、HITL、引用校验和降级路径。
- 设置统一请求 deadline 和供应商熔断。

验收：跨租户测试无泄露；服务重启后会话可恢复；模型或 Reranker 故障时按设计降级。

### 阶段 5：可观测性与质量体系

- 加入结构化日志、OpenTelemetry、Prometheus/Grafana。
- 建立难例、拒答、权限、版本和 Prompt Injection 数据集。
- 完成集成、E2E、安全、负载和故障测试。

验收：每次发布自动生成质量、延迟、成本和安全报告；未达到门禁不得发布。

### 阶段 6：部署与恢复

- 完善本地 Compose，增加健康检查、非 root、资源限制和独立凭据。
- 准备生产参考部署和 CI/CD。
- 完成 PostgreSQL、对象存储和 Milvus 备份恢复演练。

验收：在干净环境按文档完成恢复，并验证权限、版本和抽样问答。

## 21. 交付证据矩阵

只有验收完成后才更新能力状态：

| 能力声明 | 必须具备的证据 |
|---|---|
| 多格式文档入库 | 格式测试矩阵、解析报告、失败样例 |
| 标题层级与滑动窗口 | Token/结构切块代码、参数实验、块可视化 |
| BM25 + BGE + RRF + Reranker | 相同数据集的对照评测报告 |
| 低置信度二次检索 | LangGraph Trace、最大循环测试、失败路径 |
| 超时重试与异常回退 | 故障注入测试和降级指标 |
| 状态恢复 | PostgreSQL Checkpoint 和重启恢复测试 |
| 工程化部署 | Compose/Kubernetes 配置、健康检查、恢复文档 |
| 工业化入库 | 幂等、版本发布、补偿、任务队列和一致性测试 |

当前实现没有使用 PostgreSQL、Redis 和 Celery。只有对应实现与测试完成后，才能将它们列入已交付技术栈；设计文档本身不能作为实现证据。

## 22. 关键架构决策摘要

### ADR-001：PostgreSQL 作为权威状态库

原因：需要事务、唯一约束、版本状态、审计、权限和 LangGraph 持久化。Milvus 不适合承担这些职责。

### ADR-002：Redis + Celery 执行入库任务

原因：入库属于耗时、可重试、可跨进程执行的工作。任务按至少一次投递设计，权威状态仍在 PostgreSQL。

### ADR-003：MinIO/S3 保存不可变原文件

原因：本地路径不适合多实例；对象存储便于版本、生命周期、校验和恢复。

### ADR-004：Milvus 仅作为可重建索引

原因：向量检索和 BM25 是其优势；文档版本与任务事务由 PostgreSQL 管理。

### ADR-005：结构优先、Token 约束的 Parent-Child Chunking

原因：子块提高召回精度，父块提供完整上下文；Token 计数匹配模型限制，结构边界减少语义破坏。

### ADR-006：模型能力通过 Provider Adapter/Gateway 接入

原因：避免业务层与单一供应商 SDK、具体模型部署方式或个人硬件耦合。开发环境可以使用硅基流动适配器，生产环境根据合规、SLA、成本和数据边界选择经过批准的托管或自托管 Provider。

### ADR-007：PostgreSQL Checkpointer 替换 InMemorySaver

原因：内存状态不支持多实例、重启恢复和可靠审计；持久化 checkpoint 是会话恢复与 HITL 的基础。

## 23. 官方参考资料

- [FastAPI Background Tasks：重计算建议使用 Celery 等多进程工具](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [Celery Tasks：任务幂等、确认、重试与至少一次执行语义](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [LangGraph Persistence：Checkpoint、故障恢复和生产持久化后端](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Milvus Multi-tenancy：Database、Collection、Partition 与 Partition Key 策略](https://milvus.io/docs/v2.6.x/multi_tenancy.md)
- [Milvus Monitoring：Prometheus 与 Grafana 监控框架](https://milvus.io/docs/v2.6.x/monitor_overview.md)
- [Milvus Backup：备份与恢复工具](https://milvus.io/docs/v2.6.x/milvus_backup_overview.md)
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Azure AI Search 文档切块：字符、Token、结构与 overlap 的取舍](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents)
- [OWASP Top 10 for LLM Applications：Prompt Injection 等风险](https://owasp.org/www-project-top-10-for-large-language-model-applications/)

## 24. 最终验收定义

只有同时满足以下条件，项目才从 Demo 进入“面向生产验证完成”状态：

1. 核心状态不再依赖进程内存和本地临时文件。
2. 入库异步化，具备任务状态、幂等、版本、重试、补偿和恢复。
3. 子块、父块和文档版本形成可验证、可回滚的数据链路。
4. 所有查询执行租户、知识库、文档版本和工具权限校验。
5. LangGraph 状态持久化并通过重启恢复测试。
6. 关键依赖故障时能够降级、拒绝或恢复，而不是返回错误答案。
7. 指标、日志和 Trace 能定位一次请求的完整路径。
8. 难例、安全、版本、权限、性能和故障测试达到发布门禁。
9. 备份可以在干净环境恢复并通过抽样验证。
10. 每一项对外能力声明都有代码、测试、报告或运行截图作为证据。
