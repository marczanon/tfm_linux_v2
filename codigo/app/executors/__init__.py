"""Ejecutores deterministas del pipeline."""

from codigo.app.executors.cleaning import clean_dataset, generate_clean_signals
from codigo.app.executors.data_profiler import build_data_profile, generate_data_profile
from codigo.app.executors.dataset_manifest import build_cwru_manifest, generate_cwru_manifest
from codigo.app.executors.evaluation import evaluate_predictions, generate_evaluation_report
from codigo.app.executors.modeling import generate_model_outputs, train_anomaly_model
from codigo.app.executors.structuring import (
    build_temporal_dataset,
    generate_temporal_structure,
)

__all__ = [
    "build_cwru_manifest",
    "build_data_profile",
    "build_temporal_dataset",
    "clean_dataset",
    "evaluate_predictions",
    "generate_cwru_manifest",
    "generate_clean_signals",
    "generate_data_profile",
    "generate_evaluation_report",
    "generate_model_outputs",
    "generate_temporal_structure",
    "train_anomaly_model",
]
