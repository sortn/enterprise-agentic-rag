"""Batch-ingest files or directories through the production pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

from core.rag_system import RAGSystem  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="批量解析并写入企业知识库")
    parser.add_argument("paths", nargs="+", type=Path, help="文件或目录")
    parser.add_argument("--replace", action="store_true", help="重新写入已存在的同名文档")
    parser.add_argument("--recursive", action="store_true", help="递归扫描目录")
    return parser.parse_args()


def collect_files(paths: list[Path], recursive: bool, extensions: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
            continue
        if not path.is_dir():
            raise FileNotFoundError(path)
        iterator = path.rglob("*") if recursive else path.glob("*")
        files.extend(candidate for candidate in iterator if candidate.is_file())
    return sorted({path.resolve() for path in files if path.suffix.lower() in extensions})


def main() -> None:
    args = parse_args()
    system = RAGSystem().initialize()
    files = collect_files(args.paths, args.recursive, system.settings.allowed_extensions)
    if not files:
        raise SystemExit("没有找到支持的文档")

    failures = 0
    for path in files:
        try:
            result = system.ingestion.ingest(path, replace=args.replace)
            print(json.dumps(result.__dict__, ensure_ascii=False))
        except Exception as exc:
            failures += 1
            print(
                json.dumps(
                    {"source": str(path), "status": "failed", "error": str(exc)},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
    if failures:
        raise SystemExit(f"{failures} 个文档入库失败")


if __name__ == "__main__":
    main()
