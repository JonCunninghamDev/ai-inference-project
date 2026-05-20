"""
Air-Gapped RAG System

Enterprise-grade secure AI infrastructure for air-gapped environments.

Imports are intentionally kept light at package import time so platform modules
like routing can be tested without requiring optional runtime integrations such
as CloudWatch logging handlers.
"""

__version__ = "1.0.0"
__author__ = "Air-Gapped RAG Team"

__all__ = [
    "get_config",
    "WorkerConfig",
    "RAGWorker",
    "RAGTask",
]


def __getattr__(name):
    if name in {"get_config", "WorkerConfig"}:
        from .core.config import WorkerConfig, get_config

        return {"get_config": get_config, "WorkerConfig": WorkerConfig}[name]
    if name in {"RAGWorker", "RAGTask"}:
        from .core.worker import RAGTask, RAGWorker

        return {"RAGWorker": RAGWorker, "RAGTask": RAGTask}[name]
    raise AttributeError(f"module 'ai_inference' has no attribute {name!r}")
