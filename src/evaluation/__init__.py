"""
Package đánh giá Retrieval và Citation cho Multi-agent Financial Report Writer.
"""
from src.evaluation.metrics import (
    precision_at_k,
    context_precision_at_k,
    recall_at_k,
    mrr,
    evaluate_retrieval_query,
    CitationEvaluator,
)
