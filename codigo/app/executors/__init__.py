"""Ejecutores deterministas del pipeline."""

from codigo.app.executors.dataset_manifest import build_cwru_manifest, generate_cwru_manifest

__all__ = ["build_cwru_manifest", "generate_cwru_manifest"]
