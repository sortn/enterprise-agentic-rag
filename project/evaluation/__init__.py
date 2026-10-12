"""Deterministic RAG, trajectory, reliability and regression evaluation."""

from .metrics import evaluate_records
from .regression import compare_reports

__all__ = ["evaluate_records", "compare_reports"]
