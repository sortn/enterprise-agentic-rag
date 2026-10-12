# 评测体系学习指南

这套评测把“检索到了什么”“答案是否正确”“Agent 是否走对流程”和“系统代价”分开记录。这样调整 Chunk、Embedding、Reranker 或 Prompt 后，可以定位具体是哪一层发生变化。

## 1. 两套冻结数据

### 检索集

`evaluation/benchmark_v1/retrieval_test.jsonl`有500条问题。每条问题带有正确的 Child ID、Parent ID、来源、业务类别和难度，用来回答：

- 正确片段是否进入 Top K；
- 正确片段排在第几位；
- Dense、BM25、RRF 和 Reranker 分别带来什么变化；
- 效果提升增加了多少延迟。

### 答案集

`evaluation/benchmark_v1/grounding_holdout_v1.jsonl`有100条独立问题，包含可回答和不可回答样本。它与检索测试的事实集合隔离，用来回答：

- 最终答案是否包含必要事实；
- 引用是否命中正确来源；
- 没有依据时是否拒答；
- 检索、改写、生成和事实校验组合后的任务成功率。

## 2. 检索评测

运行：

```powershell
python scripts\run_retrieval_benchmark.py `
  --dataset retrieval_test.jsonl `
  --run-name test_v2 `
  --k 5 `
  --restart
```

一次运行比较四条链路：

```text
BM25 Only
Dense Only
Dense + BM25 + RRF
Dense + BM25 + RRF + BGE Reranker
```

Parent Expansion不会改变Child候选的排序，所以检索报告使用`parent_hit/parent_recall`检查Parent覆盖，并在答案集上通过ON/OFF消融衡量完整上下文对正确率、忠实度和延迟的影响；不会把相同排序复制成一个虚假的第五组检索结果。

主要指标：

- `Hit@K`：Top K 中是否至少出现一个正确片段。
- `Recall@K`：Top K 覆盖了多少标注相关片段。
- `MRR`：第一个正确片段排名的倒数；越靠前越高。
- `nDCG`：同时考虑多个相关片段和排名位置。
- `parent_recall`：命中的 Child 是否覆盖正确 Parent。
- `latency`：检索与精排带来的时间代价。

结果写入：

```text
evaluation/benchmark_v1/results/{run_name}/
├── retrieval_details.jsonl
├── retrieval_details.csv
└── retrieval_summary.json
```

当前报告中的78.6%、97.5%等数字来自已有冻结运行。新增的BM25 Only需要重新执行实验后再写入报告，不在代码中预设结果。

## 3. 答案与拒答评测

运行：

```powershell
python scripts\run_grounding_benchmark.py `
  --dataset grounding_holdout_v1.jsonl `
  --run-name grounding_v2 `
  --max-workers 2 `
  --restart
```

主要指标：

- `answerable_keyword_accuracy`：可回答问题是否覆盖冻结答案关键词。
- `answerable_source_recall`：是否引用正确来源。
- `unanswerable_refusal_rate`：不可回答问题是否正确拒答。
- `unsupported_answer_rate_overall`：系统在无依据问题上仍尝试回答的比例。
- `task_success_rate`：可回答时答对、不可回答时拒答的整体比例。

关键词规则用于稳定回归，不等价于完整语义评分。逐题记录仍应保留，便于人工检查表达等价但关键词不同的答案。

## 4. 消融实验

查询改写 OFF：

```powershell
python scripts\run_grounding_benchmark.py `
  --dataset grounding_holdout_v1.jsonl `
  --run-name rewrite_off `
  --rewrite-off `
  --restart
```

Parent Expansion OFF：

```powershell
python scripts\run_grounding_benchmark.py `
  --dataset grounding_holdout_v1.jsonl `
  --run-name parent_off `
  --parent-expansion-off `
  --restart
```

实验时每次只改变一个变量，并保持数据集、模型、Top K、并发数和其他参数不变。比较效果的同时必须比较延迟和 Token。

## 5. Agent 轨迹与系统指标

运行时会在PostgreSQL中保存：

```text
request_id
run_id
conversation_id
route
rewrite_triggered
retrieve_count
rerank_count
retry_count
retrieval_latency_ms
reranker_latency_ms
llm_latency_ms
total_latency_ms
prompt_tokens
completion_tokens
final_status
state_json
```

`project/evaluation/metrics.py`可以对标准化Trace计算：

- Rewrite Decision Accuracy；
- Route Accuracy；
- 最大循环约束；
- Citation Precision / Recall；
- Answer Correctness / Faithfulness；
- Refusal Correctness；
- Error / Timeout Rate；
- 重复运行成功率与全部通过率；
- 按标签拆分的指标。

确定性规则先评估ID、路由、引用、拒答、循环和延迟。语义正确性以后可以接入LLM Judge，但不应替代可确定判断的指标。

## 6. 回归比较

标准Trace聚合：

```powershell
Push-Location project
python -m evaluation.run `
  --dataset ..\evaluation\traces\candidate.jsonl `
  --experiment hybrid_reranker_v4 `
  --output-dir ..\evaluation\results
Pop-Location
```

比较两个报告：

```powershell
python scripts\compare_evaluation.py `
  evaluation\results\baseline\evaluation_report.json `
  evaluation\results\candidate\evaluation_report.json `
  --output evaluation\results\regression.json
```

比较器默认规则：质量指标下降超过0.01判定回归；延迟、错误、超时、重试和Token增加超过10%判定回归。退出码为2表示存在回归，可直接接入CI。

将失败Trace整理成人工复核队列：

```powershell
python scripts\promote_failure_cases.py `
  evaluation\traces\production_failures.jsonl `
  evaluation\review_queue\failure_cases.jsonl
```

脚本只生成带有`review_required=true`的候选样本，不会把未经确认的线上问题直接写进冻结数据集。

## 7. 推荐学习顺序

1. 阅读一条检索样本的Gold Child和Gold Parent。
2. 手算一次Recall@5和MRR。
3. 对照逐题结果观察RRF前后排名。
4. 查看Reranker提高了哪些专有名词或语义改写问题。
5. 阅读不可回答样本，理解拒答率和无依据回答率的区别。
6. 分别运行Rewrite和Parent Expansion消融。
7. 最后学习Agent Trace、重复运行稳定性和Regression Gate。
