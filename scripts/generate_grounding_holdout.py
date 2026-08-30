"""Create a post-fix grounding holdout from facts unused by benchmark_v1 QA."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import random

from benchmark_common import BENCHMARK_DIR, read_jsonl, write_jsonl


SEED = 20260828
OUTPUT_NAME = "grounding_holdout_v1.jsonl"
CATEGORY_COUNTS = {
    "exact_term": 8,
    "semantic_paraphrase": 8,
    "numeric_table": 8,
    "parent_context": 8,
    "version_conflict": 9,
    "rewrite_needed": 9,
}

DOMAIN_NAMES = {
    "HR": "人力资源",
    "FIN": "财务报销",
    "SEC": "信息安全",
    "PROC": "采购",
    "OPS": "运维",
    "PROD": "产品配置",
    "CS": "客户服务",
    "LEGAL": "合同合规",
    "LOG": "仓储物流",
    "RD": "研发发布",
}

PLAUSIBLE_ABSENT_SUBJECTS = [
    "海外仓冷链补贴", "跨境网络漫游费", "卫星电话租赁", "量子密钥介质押金", "无人机通勤津贴",
    "海上平台轮班补助", "极地项目保暖装备", "海外展会翻译费", "员工宠物托管补贴", "异地住房购置贷款",
    "元宇宙会议舱租赁", "脑机接口培训费", "火星差旅氧气费", "深海设备保养", "核聚变实验耗材",
    "城市空中交通票务", "私人游艇泊位费", "太空网络专线", "古籍修复津贴", "赛事门票报销",
    "海外农场承包费", "虚拟土地采购", "机器人保姆补助", "私人飞行执照培训", "数字藏品采购",
    "水下数据中心巡检", "高空飞艇广告费", "月球样品运输", "深空通信终端", "全息投影服装费",
    "自主潜艇保险", "极光观测差旅", "沙漠温室维护", "智能宠物医疗", "私人岛屿团建",
    "电竞选手签约费", "古董家具采购", "奢侈品鉴定费", "商业卫星发射", "海底光缆个人接入",
    "空中酒店住宿费", "仿生义肢美容补贴", "自动驾驶赛道租赁", "私人直升机油费", "稀有矿石收藏",
    "外星语言课程", "时光胶囊寄存", "云端婚礼服务", "海洋牧场认养", "太空电梯预约费",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def used_fact_ids() -> set[str]:
    used: set[str] = set()
    for name in ("retrieval_dev.jsonl", "retrieval_test.jsonl", "grounding_test.jsonl"):
        for row in read_jsonl(BENCHMARK_DIR / name):
            used.update(row.get("relevant_fact_ids", []))
    return used


def answerable_rows(rng: random.Random, facts: list[dict]) -> list[dict]:
    rows = []
    for category, count in CATEGORY_COUNTS.items():
        pool = [fact for fact in facts if fact["category"] == category]
        rng.shuffle(pool)
        for fact in pool[:count]:
            rows.append(
                {
                    "id": f"HOLDOUT-A-{len(rows) + 1:03d}",
                    "question": fact["question"],
                    "reference_answer": fact["reference_answer"],
                    "answer_keywords": fact["answer_keywords"],
                    "answerable": True,
                    "category": fact["category"],
                    "domain_code": fact["domain_code"],
                    "difficulty": "holdout",
                    "relevant_fact_ids": [fact["fact_id"]],
                    "relevant_clause_codes": [fact["clause_code"]],
                    "relevant_source": fact["source"],
                    "relevant_child_ids": fact["relevant_child_ids"],
                    "relevant_parent_ids": fact["relevant_parent_ids"],
                }
            )
    return rows


def unanswerable_rows() -> list[dict]:
    templates = (
        "根据{domain}制度，办理{subject}最晚需提前几个工作日提交材料？",
        "根据{domain}制度，{subject}的单笔免追加审批上限是多少元？",
        "按照{domain}规范，{subject}应当从哪个系统入口发起？",
        "公司对{subject}规定的处理时限是多少小时？",
        "{subject}需要经过哪些审批角色？",
    )
    domain_codes = list(DOMAIN_NAMES)
    rows = []
    for index, subject in enumerate(PLAUSIBLE_ABSENT_SUBJECTS, start=1):
        code = domain_codes[(index - 1) % len(domain_codes)]
        question = templates[(index - 1) % len(templates)].format(
            domain=DOMAIN_NAMES[code], subject=subject
        )
        rows.append(
            {
                "id": f"HOLDOUT-U-{index:03d}",
                "question": question,
                "reference_answer": "知识库中没有相关规定",
                "answer_keywords": [],
                "answerable": False,
                "category": "unanswerable_hard",
                "domain_code": code,
                "difficulty": "hard",
                "relevant_fact_ids": [],
                "relevant_clause_codes": [],
                "relevant_source": "",
                "relevant_child_ids": [],
                "relevant_parent_ids": [],
            }
        )
    return rows


def main() -> None:
    rng = random.Random(SEED)
    all_facts = read_jsonl(BENCHMARK_DIR / "facts.jsonl")
    used = used_fact_ids()
    unused = [fact for fact in all_facts if fact["fact_id"] not in used]
    rows = answerable_rows(rng, unused) + unanswerable_rows()
    rng.shuffle(rows)

    answerable_ids = {fact_id for row in rows for fact_id in row["relevant_fact_ids"]}
    if answerable_ids & used:
        raise AssertionError("Holdout leaked a fact used by an earlier QA split")
    corpus_text = "\n".join(fact["support_text"] for fact in all_facts)
    leaked_subjects = [subject for subject in PLAUSIBLE_ABSENT_SUBJECTS if subject in corpus_text]
    if leaked_subjects:
        raise AssertionError(f"Unanswerable subjects occur in corpus: {leaked_subjects}")

    output = BENCHMARK_DIR / OUTPUT_NAME
    write_jsonl(output, rows)
    freeze = {
        "status": "frozen_before_post_fix_holdout_run",
        "created_at": datetime.now().astimezone().isoformat(),
        "seed": SEED,
        "dataset": OUTPUT_NAME,
        "dataset_sha256": sha256(output),
        "facts_sha256": sha256(BENCHMARK_DIR / "facts.jsonl"),
        "questions": len(rows),
        "answerable": sum(row["answerable"] for row in rows),
        "unanswerable": sum(not row["answerable"] for row in rows),
        "source_fact_policy": "Answerable facts are disjoint from retrieval dev/test and grounding_test.",
        "unanswerable_policy": "Plausible absent subjects, with no explicit fake/VOID cue.",
    }
    freeze_path = BENCHMARK_DIR / "grounding_holdout_v1_frozen.json"
    freeze_path.write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(freeze, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
