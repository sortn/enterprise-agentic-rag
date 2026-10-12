# 企业知识库 Agentic RAG

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1.x-0B1727)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-5EE7A6)
[![CI](https://github.com/sortn/enterprise-agentic-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/sortn/enterprise-agentic-rag/actions/workflows/ci.yml)

> 完整离线基准已跑通：500条冻结检索测试与100条独立答案holdout的协议、结果和限制见[评测报告](evaluation/benchmark_v1/REPORT.md)。

面向企业制度、技术文档和产品手册问答的可运行 Agentic RAG 应用：使用 PostgreSQL 保存用户、权限、知识库、文档版本、对话、Agent Run、用量和审计记录，Redis 管理 Refresh Token、短期对话与检索缓存；检索侧使用 Milvus 完成 BGE Dense + BM25 双路召回、RRF 融合和 BGE Reranker 重排序，再由 LangGraph 编排查询改写、工具调用、二次检索、回答生成与事实校验。

<p align="center">
  <img src="assets/ui-preview.png" alt="企业知识库 Agentic RAG 前端" width="100%">
</p>

> 我使用确定性脚本生成可复现的演示文档与评测集。仓库保留生成脚本、冻结配置和评测结果，文档由使用者按需生成。

## 实验摘要

| 对比 | Recall@5 | MRR | 说明 |
|---|---:|---:|---|
| Hybrid（Dense+BM25+RRF） | 78.6% | 0.5948 | 混合召回基线 |
| Hybrid+BGE Rerank | **97.5%** | **0.9141** | 精排后结果 |

独立100条答案holdout中，Agentic RAG取得84%关键词正确率、98%来源召回率和5%总体无依据回答率；对应代价是更高的端到端延迟。完整实验协议、置信区间、逐题结果与失败样本见[评测报告](evaluation/benchmark_v1/REPORT.md)。

## 核心能力

- 企业认证：Argon2id 密码哈希、RS256 Access Token、Redis Refresh Token 轮换、JWKS 和统一 JWT Middleware。
- 权限控制：`admin/user` 两类角色与可扩展 RBAC 表；聊天、文档读取和文档管理使用独立权限边界。
- 业务持久化：SQLAlchemy 2.x AsyncSession + PostgreSQL，使用 Alembic 管理 Schema 迁移。
- 租户隔离：知识库成员关系由 PostgreSQL 管理，Milvus 查询强制携带 `tenant_id + knowledge_base_id` 过滤条件。
- 运行审计：每次 Agent 请求保存 `request_id/run_id`、路由、改写、重试、分段耗时、Token 和最终状态。
- 多格式入库：PDF / DOCX / XLSX / Markdown / TXT，保留页码、工作表和标题路径。
- Parent-Child 切分：父块全文持久化到 `data/parents/`，仅对子块生成向量；命中子块后按 `parent_id` 还原父块。
- 混合检索：`BAAI/bge-m3` Dense 召回 + Milvus BM25，使用 RRF 融合。
- 精排：`BAAI/bge-reranker-v2-m3` 对融合候选执行 Cross-Encoder 重排序。
- Agentic RAG：低相关度或事实校验失败时自动改写查询并进行第二次检索，最多两轮。
- 企业工具：Pydantic 校验的结构化数据库查询和演示业务接口；数据库只允许参数化白名单查询。
- 可靠回答：只依据文档/工具证据回答，输出来源位置，并在末端执行事实一致性检查。
- 工程接口：FastAPI 普通接口、经过事实校验后发送的 SSE 分片、Gradio 网页、Docker Compose。
- 离线评测：检索对照实验覆盖 Recall@K/MRR/延迟，回答评测覆盖引用召回、错误拒答和无依据回答率。

## 系统架构

```mermaid
flowchart LR
    U[企业用户] --> AUTH[登录 / RS256 JWT / RBAC]
    AUTH --> PG[(PostgreSQL<br/>用户 / 知识库 / 对话 / 审计)]
    AUTH --> Q[用户问题]
    D[PDF / Word / Excel] --> P[多格式解析]
    P --> C[Parent-Child 切分]
    C --> PS[(本地 Parent Store)]
    C --> E[Child BGE-M3 Embedding]
    E --> M[(Milvus)]
    C --> M

    Q --> A[意图识别 / 查询改写]
    A -->|文档问题| H[Dense + BM25]
    H --> R[RRF + BGE Reranker]
    R --> G{相关性足够?}
    G -->|否，首次| W[二次改写]
    W --> H
    G -->|是| X[按 parent_id 还原父块 / Token Budget]
    X --> L[答案生成]
    A -->|结构化数据/实时业务数据| S[(PostgreSQL 企业工具表)]
    A -->|实时业务| B[演示业务 API]
    S --> L
    B --> L
    L --> F{事实校验}
    F -->|失败且未达上限| W
    F -->|通过或安全拒答| API[FastAPI SSE]
    API --> UI[Gradio 网页]
    API --> REDIS[(Redis<br/>会话 / 检索缓存)]
```

LangGraph 的显式节点和路由在 `project/rag_agent/graph.py`，不会把关键流程藏在一个超长 Agent Prompt 中。

## 代码结构

```text
project/
├── api/                 拆分后的认证、知识库、文档、对话、聊天和审计 Router
├── auth/                用户、RBAC、JWT/JWKS、Refresh Token 与 Middleware
├── core/                应用容器、请求追踪、Redis 运行时缓存
├── database/            SQLAlchemy 模型与 AsyncSession 生命周期
├── db/                  父块本地持久化
├── evaluation/          Agent/轨迹/系统指标与回归比较
├── ingestion/           多格式解析、切分、入库流水线
├── rag_agent/           LangGraph 状态、节点、边和企业工具
├── retrieval/           Milvus Schema、Dense/BM25/RRF/Reranker
├── repositories/        PostgreSQL 数据访问层
├── services/            业务规则、RAG 编排、模型和演示业务服务
├── tests/               不依赖真实模型的单元测试
├── ui/                  Gradio 企业工作台与自定义主题
├── config.py            唯一配置入口
└── app.py               启动入口

project/migrations/      Alembic 版本迁移

scripts/
├── generate_sample_documents.py
├── ingest_documents.py
├── generate_benchmark.py
├── run_retrieval_benchmark.py
└── run_grounding_benchmark.py

evaluation/benchmark_v1/
docker-compose.yml
```

## 快速开始

### 1. 环境准备

建议使用 Python 3.11。Milvus Standalone 需要 Docker Desktop、WSL 2 后端和 Docker Compose V2。

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

Linux/macOS将前两行替换为`python3.11 -m venv .venv`和`source .venv/bin/activate`即可。
如需与已验证环境完全一致，可将安装命令替换为`pip install -r requirements-lock.txt`。

### 2. 配置模型 API

复制示例文件：

```powershell
Copy-Item project\.env.example project\.env
```

Linux/macOS使用`cp project/.env.example project/.env`。

至少填写 `SILICONFLOW_API_KEY`。默认模型名不带 `Pro/` 前缀：

```dotenv
LLM_MODEL=Qwen/Qwen3-8B
EMBEDDING_MODEL=BAAI/bge-m3
RERANK_MODEL=BAAI/bge-reranker-v2-m3
```

我将模型密钥保存在本地 `project/.env`；根目录 `.gitignore` 已忽略所有 `.env`。

### 3. 生成演示企业文档

```powershell
python scripts\generate_sample_documents.py
```

命令会生成四份DOCX、PDF、XLSX和Markdown演示文档，统一写入`sample_data/generated/`。

### 4. 启动 PostgreSQL、Milvus 与 Redis

```powershell
docker compose up -d postgres etcd minio milvus redis
docker compose ps
```

容器健康后即可启动应用服务。

### 5. 启动后端和网页

```powershell
Push-Location project
alembic -c alembic.ini upgrade head
Pop-Location
python project\app.py
```

启动后可使用 Gradio 工作台、FastAPI 交互文档以及 live/ready 健康探针。

首次注册的账号会成为默认租户管理员，后续注册账号为普通用户。管理员可在“知识库管理”页上传 `sample_data/generated/` 下的四份文件，所有已登录用户均可进入“智能问答”。如由企业身份系统预置管理员，可将 `AUTH_FIRST_USER_ADMIN` 设置为 `false`。

也可以使用批量入库命令：

```powershell
python scripts\ingest_documents.py sample_data\generated
```

### 6. 全容器部署

```powershell
docker compose up -d --build
```

应用容器会先执行 Alembic 迁移，再和 PostgreSQL、Milvus、etcd、MinIO、Redis 一起启动。业务数据库、RSA 密钥和 Redis 数据分别持久化到 Compose Volume 与本地运行目录。

> Compose 默认将管理端口绑定到本机回环地址。公网部署时应在入口层启用 HTTPS，并通过密钥挂载或密钥管理服务提供 RSA 私钥。

## API 示例

认证接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册并签发 Token Pair |
| POST | `/api/v1/auth/login` | 用户名/邮箱登录 |
| POST | `/api/v1/auth/refresh` | 原子消费并轮换 Refresh Token |
| POST | `/api/v1/auth/logout` | 撤销 Refresh Token |
| GET | `/api/v1/auth/me` | 查询当前用户、角色与权限 |
| GET | `/.well-known/jwks.json` | 获取 RS256 公钥参数与 `kid` |
| GET/POST | `/api/v1/knowledge-bases` | 查询或创建知识库 |
| POST | `/api/v1/knowledge-bases/{id}/members` | 分配知识库成员权限 |
| GET | `/api/v1/conversations` | 查询当前用户的对话 |
| GET | `/api/v1/conversations/{id}` | 查询对话和最近消息 |
| GET | `/api/v1/audit-logs` | 管理员查询租户审计记录 |
| GET | `/api/v1/evaluation/runs` | 管理员导出 Agent 运行 Trace |

登录响应同时返回短生命周期 Access Token 和随机 Refresh Token。访问业务接口时统一携带：

```http
Authorization: Bearer <access_token>
```

普通回答接口为 `POST /api/v1/chat`，请求体示例：

```json
{
  "question": "住宿费超标后怎么办？"
}
```

SSE 流式接口为 `POST /api/v1/chat/stream`，依次返回 `start`、`token`、`final` 事件。为防止未经校验的幻觉内容提前泄露，`token` 是 Fact-Check 完成后对最终答案进行的安全分片。最终结果分别使用 `grounded` 表示回答得到证据支持、`refused` 表示系统因证据不足而拒答。

## 离线评测

仓库保留冻结配置、问题集、标签、汇总结果与逐题证据。完整复现时先通过脚本生成50份评测文档：

```powershell
python scripts\generate_benchmark.py
python scripts\validate_benchmark.py --parse-corpus
python scripts\index_benchmark.py --reset
python scripts\link_ground_truth.py
python scripts\validate_benchmark.py --require-linked
```

运行冻结的500条检索测试：

```powershell
python scripts\run_retrieval_benchmark.py --dataset retrieval_test.jsonl --run-name test_v1 --k 5 --restart
```

运行独立答案holdout：

```powershell
python scripts\generate_grounding_holdout.py
python scripts\run_grounding_benchmark.py --dataset grounding_holdout_v1.jsonl --run-name grounding_holdout_v1 --max-workers 2 --restart
```

查询改写和 Parent Expansion 消融实验分别使用：

```powershell
python scripts\run_grounding_benchmark.py --dataset grounding_holdout_v1.jsonl --run-name rewrite_off --rewrite-off --restart
python scripts\run_grounding_benchmark.py --dataset grounding_holdout_v1.jsonl --run-name parent_off --parent-expansion-off --restart
```

`project/evaluation/`提供独立于模型供应商的确定性指标聚合与回归比较，可计算检索、答案、引用、拒答、轨迹、分段延迟、Token、重复运行稳定性和按标签结果。比较两个报告：

```powershell
python scripts\compare_evaluation.py baseline.json candidate.json --output regression.json
```

实验协议、置信区间、延迟代价、失败样本和数据哈希见[离线基准评测报告](evaluation/benchmark_v1/REPORT.md)，指标和消融实验的学习顺序见[评测体系学习指南](docs/EVALUATION_GUIDE.md)。

## 测试

```powershell
python -m pytest project\tests -q
```

单元测试通过可控替身覆盖 Argon2id、RS256/JWKS、Refresh Token 轮换、RBAC Middleware、异步 SQLAlchemy Repository、评测与回归指标，以及解析、父子分块、LangGraph 路由、降级检索和 SSE 分片。GitHub Actions 会在 push 和 pull request 时自动执行同一套测试并构建应用镜像。

## 可靠性设计

- Access Token 仅使用 RS256 并校验 `kid/iss/aud/exp/iat`；验证侧只加载公钥。
- Refresh Token 只保存于 Redis，使用 TTL 管理过期时间，刷新时原子消费旧 Token，退出时立即撤销。
- 密码采用 Argon2id 加盐哈希；用户名和邮箱按租户建立唯一约束，角色与权限通过关联表扩展。
- Middleware 统一注入用户、角色、租户和权限上下文；管理员与普通用户的文档管理边界由后端强制执行。
- PostgreSQL 是用户、知识库、文档版本、对话、运行与审计的权威来源；Redis 内容可过期并可重建。
- 每次 Milvus 检索同时校验租户和知识库，旧版无隔离字段的 Collection 不允许承载企业查询。
- 模型、Embedding、Reranker 请求均有超时和指数退避重试。
- 查询改写最多触发一次，整个检索最多两轮，避免 Agent 无限循环。
- 工具参数由 Pydantic 验证；结构化数据库不接受模型生成的任意 SQL。
- 子块只负责召回，生成前去重并还原父块全文，再按近似 token budget 裁剪上下文。
- Milvus Hybrid、Dense、BM25 或 Reranker 单项故障时执行可用单路降级；全部不可用才安全拒答。
- 检索不足时拒答；生成后再做证据一致性检查，不通过会在上限内二次检索，仍失败则拒答。
- 上传文件限制扩展名、大小，并使用安全文件名。
- 回答保留文件名和页码/工作表/标题路径，便于人工复核。

## 项目来源与独立改造

我以 Giovanni Pasqualino 的 MIT 项目 [agentic-rag-for-dummies](https://github.com/GiovanniPasq/agentic-rag-for-dummies) 作为早期 LangGraph 学习参考，并围绕企业知识问答重构了多格式解析、Milvus Schema、BGE API、BM25/RRF/Reranker、企业工具、可靠性工作流、FastAPI SSE、评测体系和 Docker Compose。

| 改造领域 | 当前仓库中的可核验实现 |
|---|---|
| 文档入库 | 多格式解析、Parent-Child 切分、父块持久化与批量入库脚本 |
| 身份与权限 | 用户注册登录、Argon2id、RS256/JWKS、Redis Token 轮换与 RBAC |
| 检索链路 | Milvus Dense/BM25、RRF、BGE Reranker及单路故障降级 |
| Agent 工作流 | 显式 LangGraph 节点、有限重试、企业工具、证据校验与安全拒答 |
| 服务与交互 | FastAPI、校验后 SSE、文档管理 API 和 Gradio 工作台 |
| 实验验证 | 冻结评测数据、逐题结果、置信区间和失败样本 |
| 工程交付 | Docker Compose、依赖锁定、单元测试、CI 与可复现实验报告 |

本项目继续采用MIT License，我在[NOTICE](NOTICE.md)中记录了基础归属与独立改造范围。

问题进来
   │
   ▼
analyze_query（意图识别 + 查询改写）
   │
   ├── 说不清 → clarification（反问用户）→ 结束
   ├── 闲聊   → chitchat（固定话术）→ 结束
   ├── 查文档 → retrieve ──相关性不够──→ rewrite_search ──→ retrieve（最多2次）
   │              │                            │
   │              ▼                            └── 还不行 → refuse（拒答）
   │        build_context（子块→父块扩展，token 预算控制）
   │              │
   ├── 查工具 → run_tool（结构化数据/业务API）
   │              │
   ▼              ▼
generate_answer（基于证据生成）
   │
   ▼
fact_check（回答和证据一致性校验）
   │
   ├── 通过 → finish → 结束
   └── 不通过 → rewrite_search 重试 或 refuse
