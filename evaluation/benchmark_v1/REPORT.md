# 企业知识库 Agentic-RAG 离线基准评测报告

> 本报告记录当前代码与冻结合成数据上的真实实验结果。语料、问题和标签均由确定性脚本生成，不包含真实企业数据，结果不能直接外推到生产环境。

## 1. 实验协议

- 语料规模：50份模拟企业文档、10个业务域、1000条原子事实，覆盖MD、DOCX、PDF、XLSX和TXT。
- 检索数据：100条开发集用于确认方案；500条测试集在配置和SHA-256冻结后运行。
- 答案数据：100条独立holdout，其中50条可回答、50条不可回答；可回答事实与此前检索及答案题事实集合不重叠。
- 模型：`BAAI/bge-m3`、`BAAI/bge-reranker-v2-m3`、`Qwen/Qwen3-8B`。
- 检索配置：候选Top-24、最终Top-5，Parent/Child为1800/700字符，Child overlap为120字符。
- 评测方法：检索使用Recall@5、MRR、nDCG；答案使用冻结关键词、来源标签和确定性拒答规则，不使用LLM-as-judge。

生成语料未提交到仓库，需要评测时运行生成脚本即可恢复。

## 2. 500条冻结检索测试

| 方法 | Hit@5 | Recall@5 | 95% CI | MRR | nDCG | 平均检索 | P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dense | 64.0% | 63.8% | 59.3%–68.1% | 0.4886 | 0.5247 | 4.8 ms | 6.0 ms |
| Hybrid（Dense+BM25+RRF） | 79.0% | 78.6% | 75.0%–81.9% | 0.5948 | 0.6401 | 5.3 ms | 7.0 ms |
| Hybrid+BGE Rerank | 97.6% | 97.5% | 96.2%–98.8% | 0.9141 | 0.9297 | 674.0 ms | 1876.6 ms |

以Hybrid作为混合召回基线，加入BGE Reranker后，Recall@5由 **78.6%提升至97.5%**，MRR由 **0.5948提升至0.9141**。精度提升伴随明显延迟成本，因此生产环境应根据查询类型决定是否执行精排。

## 3. 100条独立答案holdout

| 方法 | 可回答关键词正确率 | 来源召回 | 不可回答拒答率 | 总体无依据回答率 | 任务成功率 | 平均端到端 | P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dense RAG | 72.0% | 82.0% | 88.0% | 6.0% | 80.0% | 1995 ms | 3255 ms |
| Agentic RAG | 84.0% | 98.0% | 90.0% | 5.0% | 87.0% | 10654 ms | 20945 ms |

- Agentic RAG的关键词正确率95%置信区间为74.0%–94.0%，总体无依据答案率95%置信区间为1.0%–9.0%。
- Agentic RAG提升了答案正确率、来源召回和任务成功率，但平均延迟约为Dense RAG的5.3倍。
- 剩余错误主要集中在需要同时命中“入口+专项流程名”的改写问题，以及“答案与片段一致、但片段没有真正回答问题”的相关性缺口。

## 4. 可复现命令

```powershell
python scripts\generate_benchmark.py
python scripts\validate_benchmark.py --parse-corpus
python scripts\index_benchmark.py --reset
python scripts\link_ground_truth.py
python scripts\validate_benchmark.py --require-linked
python scripts\run_retrieval_benchmark.py --dataset retrieval_dev.jsonl --run-name dev_v1 --k 5 --restart
python scripts\freeze_benchmark.py
python scripts\run_retrieval_benchmark.py --dataset retrieval_test.jsonl --run-name test_v1 --k 5 --restart
python scripts\generate_grounding_holdout.py
python scripts\run_grounding_benchmark.py --dataset grounding_holdout_v1.jsonl --run-name grounding_holdout_v1 --max-workers 2 --restart
python -m pytest project\tests -q
```

完整检索和回答结果位于`evaluation/benchmark_v1/results/`。其中查询Embedding属于可重新生成的缓存，不提交到Git。

## 5. 限制

- 全部语料是模拟企业数据，无法覆盖真实文档中的OCR噪声、历史版本冲突和权限边界。
- 关键词指标可核验，但无法识别所有语义等价表达，仍需人工抽检。
- 模型API版本、服务排队和网络状态会影响延迟及少量输出稳定性。
- 当前事实校验更擅长检查“回答是否得到证据支持”，还需加强“证据是否真正回答了问题”的相关性判断。
