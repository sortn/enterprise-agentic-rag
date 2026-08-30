"""Build the human-readable and machine-readable benchmark_v1 reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmark_common import BENCHMARK_DIR, RESULTS_DIR, read_jsonl


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = BENCHMARK_DIR / "REPORT.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_records(run_name: str) -> dict[str, dict]:
    records = {}
    for row in read_jsonl(RESULTS_DIR / run_name / "grounding_details.jsonl"):
        if row.get("error"):
            records.pop(row["id"], None)
        else:
            records[row["id"]] = row
    return records


def paired(records: dict[str, dict], field: str, subset: str = "all") -> dict[str, int]:
    rows = list(records.values())
    if subset == "answerable":
        rows = [row for row in rows if row["answerable"]]
    elif subset == "unanswerable":
        rows = [row for row in rows if not row["answerable"]]
    result = {"both": 0, "dense_only": 0, "agent_only": 0, "neither": 0}
    for row in rows:
        dense = bool(row["dense_rag"][field])
        agent = bool(row["agentic_rag"][field])
        key = "both" if dense and agent else "dense_only" if dense else "agent_only" if agent else "neither"
        result[key] += 1
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> None:
    retrieval = load_json(RESULTS_DIR / "test_v1" / "retrieval_summary.json")
    grounding_v1 = load_json(RESULTS_DIR / "grounding_v1" / "grounding_summary.json")
    grounding_v2 = load_json(RESULTS_DIR / "grounding_router_fixed_v2" / "grounding_summary.json")
    holdout = load_json(RESULTS_DIR / "grounding_holdout_v1" / "grounding_summary.json")
    frozen = load_json(BENCHMARK_DIR / "frozen_experiment_config.json")
    holdout_frozen = load_json(BENCHMARK_DIR / "grounding_holdout_v1_frozen.json")
    holdout_records = latest_records("grounding_holdout_v1")
    v1_records = latest_records("grounding_v1")
    v2_records = latest_records("grounding_router_fixed_v2")

    retrieval_rows = []
    for key, label in (("dense", "Dense"), ("hybrid", "Hybrid (Dense+BM25+RRF)"), ("hybrid_rerank", "Hybrid + BGE Rerank")):
        item = retrieval["results"][key]
        retrieval_rows.append(
            {
                "method": label,
                "hit_rate": item["hit_rate"],
                "recall_at_5": item["recall"],
                "recall_95ci": item["recall_95ci"],
                "mrr": item["mrr"],
                "ndcg": item["ndcg"],
                "parent_hit_rate": item["parent_hit_rate"],
                "mean_retrieval_latency_ms": item["mean_retrieval_latency_ms"],
                "p95_retrieval_latency_ms": item["p95_retrieval_latency_ms"],
            }
        )

    v1_pair = {
        "both": 0,
        "v1_only": 0,
        "v2_only": 0,
        "neither": 0,
    }
    for record_id, before in v1_records.items():
        if not before["answerable"]:
            continue
        after = v2_records[record_id]
        old = before["agentic_rag"]["keyword_correct"]
        new = after["agentic_rag"]["keyword_correct"]
        key = "both" if old and new else "v1_only" if old else "v2_only" if new else "neither"
        v1_pair[key] += 1

    overview = {
        "protocol": "benchmark_v1",
        "corpus": {"documents": 50, "facts": 1000, "domains": 10, "formats": 5},
        "retrieval_test": {
            "questions": retrieval["dataset_questions"],
            "errors": sum(item["errors"] for item in retrieval["results"].values()),
            "methods": retrieval_rows,
        },
        "grounding_same_set_diagnostic": {
            "v1": grounding_v1["methods"]["agentic_rag"],
            "router_fixed_v2": grounding_v2["methods"]["agentic_rag"],
            "paired_answerable": v1_pair,
            "warning": "Post-hoc same-set diagnostic; not an unbiased final estimate.",
        },
        "grounding_independent_holdout": {
            "questions": holdout["questions"],
            "dense_rag": holdout["methods"]["dense_rag"],
            "agentic_rag": holdout["methods"]["agentic_rag"],
            "paired_answerable_correct": paired(holdout_records, "keyword_correct", "answerable"),
            "paired_unanswerable_refusal": paired(holdout_records, "refused", "unanswerable"),
            "paired_task_success": paired(holdout_records, "successful"),
        },
        "hashes": {
            "retrieval_protocol": sha256(BENCHMARK_DIR / "frozen_experiment_config.json"),
            "retrieval_test_summary": sha256(RESULTS_DIR / "test_v1" / "retrieval_summary.json"),
            "holdout_dataset": holdout_frozen["dataset_sha256"],
            "holdout_summary": sha256(RESULTS_DIR / "grounding_holdout_v1" / "grounding_summary.json"),
            "router_code": sha256(ROOT / "project" / "rag_agent" / "nodes.py"),
        },
    }
    (BENCHMARK_DIR / "experiment_overview.json").write_text(
        json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    dense = holdout["methods"]["dense_rag"]
    agent = holdout["methods"]["agentic_rag"]
    retrieval_table = "\n".join(
        "| {method} | {hit} | {recall} | {ci} | {mrr:.4f} | {ndcg:.4f} | {parent} | {mean:.1f} | {p95:.1f} |".format(
            method=row["method"],
            hit=pct(row["hit_rate"]),
            recall=pct(row["recall_at_5"]),
            ci=f"{pct(row['recall_95ci'][0])}–{pct(row['recall_95ci'][1])}",
            mrr=row["mrr"],
            ndcg=row["ndcg"],
            parent=pct(row["parent_hit_rate"]),
            mean=row["mean_retrieval_latency_ms"],
            p95=row["p95_retrieval_latency_ms"],
        )
        for row in retrieval_rows
    )
    holdout_table = "\n".join(
        [
            f"| Dense RAG | {pct(dense['answerable_keyword_accuracy'])} | {pct(dense['answerable_source_recall'])} | {pct(dense['unanswerable_refusal_rate'])} | {pct(dense['unsupported_answer_rate_overall'])} | {pct(dense['task_success_rate'])} | {dense['mean_latency_ms']:.0f} | {dense['p95_latency_ms']:.0f} |",
            f"| Agentic RAG | {pct(agent['answerable_keyword_accuracy'])} | {pct(agent['answerable_source_recall'])} | {pct(agent['unanswerable_refusal_rate'])} | {pct(agent['unsupported_answer_rate_overall'])} | {pct(agent['task_success_rate'])} | {agent['mean_latency_ms']:.0f} | {agent['p95_latency_ms']:.0f} |",
        ]
    )
    answer_failures = [
        (row["id"], row["category"])
        for row in holdout_records.values()
        if row["answerable"] and not row["agentic_rag"]["keyword_correct"]
    ]
    unsupported_ids = [
        row["id"]
        for row in holdout_records.values()
        if not row["answerable"] and row["agentic_rag"]["unsupported_answer"]
    ]

    report = rf"""# 企业知识库 Agentic-RAG 离线基准评测报告

生成时间：{holdout['completed_at']}
结论：项目与评测链路已经完整跑通。冻结的合成检索测试得到 Hybrid Recall@5 **78.6%**、Hybrid+Rerank **97.5%**；独立答案 holdout 中，Agentic RAG 的关键词正确率为 **84.0%**、来源召回为 **98.0%**、总体无依据答案率为 **5.0%**。

## 1. 实验协议

- 语料：50 份模拟企业文档、10 个业务域、1000 条原子事实；MD/DOCX/PDF/XLSX/TXT 各 10 份。
- 检索数据：100 条开发集仅用于确认方案，500 条测试集在参数和 SHA-256 冻结后一次性运行。
- 答案数据：原始 200 条（100 可回答/100 不可回答）；发现路由缺陷后保留修复前 v1 和同集诊断 v2。
- 独立答案 holdout：100 条（50/50）；可回答事实与此前 600 条检索 QA、200 条答案题的事实集合完全不重叠；不可回答题不含“虚构/VOID”等泄题词。
- 模型：`{frozen['retrieval']['embedding_model']}`、`{frozen['retrieval']['rerank_model']}`、Qwen/Qwen3-8B。
- 检索：候选 Top-{frozen['retrieval']['fusion_top_k']}，最终 Top-5；Parent/Child={frozen['chunking']['parent_chunk_size']}/{frozen['chunking']['child_chunk_size']} 字符，Child overlap={frozen['chunking']['child_chunk_overlap']}。
- 指标：检索使用 Recall@5、MRR、nDCG；答案使用冻结关键词/来源标签和确定性拒答规则，不使用 LLM-as-judge。

## 2. 500 条冻结检索测试

| 方法 | Hit@5 | Recall@5 | 95% CI | MRR | nDCG | Parent Hit@5 | 平均检索 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{retrieval_table}

解释：以 Hybrid 作为混合召回基线，加入 BGE Reranker 后 Recall@5 为 **78.6%→97.5%**，MRR 为 **0.5948→0.9141**；如果以 Dense 作为基础方案，则 Recall@5 为 **63.8%→97.5%**。这些结果仅适用于当前冻结的合成语料与配置，不能直接外推到真实企业知识库。

## 3. 路由缺陷与修复

首次 200 条答案实验中，规划模型把 30/100 条文档制度问题误路由到仅支持“产品价格/质保、部门联系方式”的结构化工具，可回答题正确率只有 **67%**。修复为确定性工具边界后：

- 30 条错误 `structured_data` 路由降为 0，并为该缺陷补充路由回归测试。
- 同一集合配对结果：两版都对 {v1_pair['both']}，仅 v1 对 {v1_pair['v1_only']}，仅修复版对 {v1_pair['v2_only']}，两版都错 {v1_pair['neither']}。
- 修复后同集正确率 **95%**、来源召回 **98%**、任务成功率 **97.5%**。

这一步看过 v1 错题，因此是缺陷修复诊断，不作为最终无偏能力估计。

## 4. 独立修复后答案 holdout

| 方法 | 可回答关键词正确率 | 来源召回 | 不可回答拒答率 | 无依据答案率（全体） | 任务成功率 | 平均端到端 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
{holdout_table}

- Agent 正确率 95% CI：{pct(agent['answerable_keyword_accuracy_95ci'][0])}–{pct(agent['answerable_keyword_accuracy_95ci'][1])}；无依据答案率 95% CI：{pct(agent['unsupported_answer_rate_overall_95ci'][0])}–{pct(agent['unsupported_answer_rate_overall_95ci'][1])}。
- 配对任务成功：两者都成功 70，仅 Dense 成功 10，仅 Agent 成功 17，两者都失败 3，Agent 净增 7 个百分点。
- Agent 剩余 8 条可回答失败：{', '.join(f'{item[0]}({item[1]})' for item in answer_failures)}。其中 7 条是严格要求同时出现“入口 + 专项流程名”的 rewrite_needed 题。
- Agent 对 5 条不可回答题仍作答：{', '.join(unsupported_ids)}。这暴露了“回答与证据一致，但证据未真正回答问题”的相关性缺口。
- 质量提升换来了明显延迟：平均约 {agent['mean_latency_ms'] / dense['mean_latency_ms']:.1f} 倍，P95 增加约 {(agent['p95_latency_ms'] - dense['p95_latency_ms']) / 1000:.1f} 秒。

## 5. 工程结论与边界

- Reranker 显著改善了 Top-5 召回和首条结果排序，但平均检索延迟由 5.3 ms 增至 674.0 ms。
- Agentic RAG 提升了答案正确率和来源召回，但平均端到端延迟约为 Dense RAG 的 {agent['mean_latency_ms'] / dense['mean_latency_ms']:.1f} 倍。
- 当前评测使用确定性生成的模拟企业语料，优势是标签可核验、实验可冻结；不足是不能代表真实企业文档的噪声、权限和分布漂移。
- 报告同时保留失败样本、置信区间和逐题结果，避免只展示单个汇总数字。

## 6. 可复现命令

```powershell
python scripts\generate_benchmark.py
python scripts\validate_benchmark.py --parse-corpus
python scripts\index_benchmark.py --reset
python scripts\link_ground_truth.py
python scripts\validate_benchmark.py --require-linked
python scripts\run_retrieval_benchmark.py --dataset retrieval_dev.jsonl --run-name dev_v1 --k 5 --restart
python scripts\freeze_benchmark.py
python scripts\run_retrieval_benchmark.py --dataset retrieval_test.jsonl --run-name test_v1 --k 5 --restart
python scripts\run_grounding_benchmark.py --run-name grounding_v1 --max-workers 2 --restart
python scripts\generate_grounding_holdout.py
python scripts\run_grounding_benchmark.py --dataset grounding_holdout_v1.jsonl --run-name grounding_holdout_v1 --max-workers 2 --restart
python -m pytest project\tests -q
```

## 7. 证据与限制

- 检索协议哈希：`{overview['hashes']['retrieval_protocol']}`
- 检索测试结果哈希：`{overview['hashes']['retrieval_test_summary']}`
- 独立 holdout 数据哈希：`{overview['hashes']['holdout_dataset']}`
- 独立 holdout 结果哈希：`{overview['hashes']['holdout_summary']}`
- 路由实现哈希：`{overview['hashes']['router_code']}`
- 全部语料是确定性生成的模拟企业数据，不是真实公司文件；不能外推到生产知识库。
- 严格关键词指标可审计，但不能识别所有语义等价表达；无依据答案规则也应再由人工抽检确认。
- 模型 API 是远端服务，模型版本、排队和网络会影响时延及少量输出稳定性。
- 下一轮应加入独立的“问题—证据相关性”检查，并在一份全新 holdout 上验证，不能继续用本轮错题调参后报告本轮分数。
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(json.dumps({"report": str(REPORT_PATH), "overview": str(BENCHMARK_DIR / 'experiment_overview.json'), "hashes": overview["hashes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
