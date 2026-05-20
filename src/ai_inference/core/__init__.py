"""Core functionality for Air-Gapped RAG system."""

__all__ = ["get_config", "WorkerConfig", "RAGWorker", "RAGTask"]


def __getattr__(name):
    if name in {"get_config", "WorkerConfig"}:
        from .config import WorkerConfig, get_config

        return {"get_config": get_config, "WorkerConfig": WorkerConfig}[name]
    if name in {"RAGWorker", "RAGTask"}:
        from .worker import RAGTask, RAGWorker

        return {"RAGWorker": RAGWorker, "RAGTask": RAGTask}[name]
    raise AttributeError(f"module 'ai_inference.core' has no attribute {name!r}")
