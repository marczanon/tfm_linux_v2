"""Modelado determinista de anomalias sobre features temporales."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from codigo.app.schemas.executor_results import ModelingResult
from codigo.app.schemas.state import ArtifactRef, ModelingConfig, PipelineError


DEFAULT_MODELING_CONFIG = ModelingConfig(
    model_name="isolation_forest",
    random_state=42,
    hyperparameters={
        "n_estimators": 200,
        "max_samples": "auto",
        "contamination": "auto",
        "max_features": 1.0,
        "bootstrap": False,
        "n_jobs": 1,
        "threshold_quantile": 0.99,
    },
)

DEFAULT_PCA_MODELING_CONFIG = ModelingConfig(
    model_name="pca_reconstruction_error",
    random_state=42,
    hyperparameters={
        "n_components": 0.95,
        "svd_solver": "full",
        "whiten": False,
        "threshold_quantile": 0.99,
    },
)

DEFAULT_OCSVM_MODELING_CONFIG = ModelingConfig(
    model_name="one_class_svm",
    random_state=42,
    hyperparameters={
        "kernel": "rbf",
        "nu": 0.05,
        "gamma": "scale",
        "shrinking": True,
        "tol": 0.001,
        "max_iter": -1,
        "threshold_quantile": 0.99,
    },
)

DEFAULT_AUTOENCODER_DENSE_CONFIG = ModelingConfig(
    model_name="autoencoder_dense",
    random_state=42,
    hyperparameters={
        "hidden_layers": "32,16",
        "latent_dim": 8,
        "learning_rate": 0.001,
        "batch_size": 32,
        "max_epochs": 100,
        "patience": 12,
        "weight_decay": 0.0001,
        "threshold_quantile": 0.99,
        "device": "cpu",
    },
)

METADATA_COLUMNS = {
    "window_id",
    "file_id",
    "source_path",
    "condition_id",
    "asset_id",
    "run_id",
    "label_source",
    "label_granularity",
    "window_index",
    "start",
    "end",
    "timestamp_start",
    "timestamp_end",
    "time_since_start_seconds",
    "time_to_failure_seconds",
    "relative_life",
    "split",
    "label",
    "target",
    "fault_type",
    "sample_rate_hz",
    "channel",
}

PREDICTION_FIELDS = [
    "window_id",
    "file_id",
    "condition_id",
    "asset_id",
    "run_id",
    "label_source",
    "label_granularity",
    "window_index",
    "timestamp_start",
    "timestamp_end",
    "time_since_start_seconds",
    "time_to_failure_seconds",
    "relative_life",
    "split",
    "label",
    "target",
    "fault_type",
    "anomaly_score",
    "threshold",
    "predicted_anomaly",
]

SKLEARN_IFOREST_PARAMS = {
    "n_estimators",
    "max_samples",
    "contamination",
    "max_features",
    "bootstrap",
    "n_jobs",
}

SKLEARN_PCA_PARAMS = {
    "n_components",
    "svd_solver",
    "whiten",
}

SKLEARN_OCSVM_PARAMS = {
    "kernel",
    "degree",
    "gamma",
    "coef0",
    "tol",
    "nu",
    "shrinking",
    "cache_size",
    "max_iter",
}

AUTOENCODER_DENSE_PARAMS = {
    "hidden_layers",
    "latent_dim",
    "learning_rate",
    "batch_size",
    "max_epochs",
    "patience",
    "weight_decay",
    "threshold_quantile",
    "device",
}


def generate_model_outputs(
    features_path: str | Path = "codigo/data/tensors/cwru_bearing/windows_features.csv",
    output_dir: str | Path = "codigo/models/cwru_bearing",
    config: ModelingConfig | None = None,
) -> ModelingResult:
    """Entrena un modelo base y devuelve un resultado estructurado."""

    started_at = datetime.now(UTC)
    output = Path(output_dir)
    cfg = config or DEFAULT_MODELING_CONFIG
    model_path = _model_output_path(output, cfg.model_name)
    predictions_path = output / "predictions.csv"
    try:
        summary = train_anomaly_model(features_path, output, cfg)
        artifacts = [
            ArtifactRef(
                name=f"{summary['model_name']}_model",
                artifact_type="model",
                path=summary["model_path"],
                producer="modeling_executor",
                metadata={
                    "model_name": summary["model_name"],
                    "n_train_windows": summary["n_train_windows"],
                    "n_features": len(summary["feature_columns"]),
                },
            ),
            ArtifactRef(
                name="model_predictions",
                artifact_type="predictions",
                path=summary["predictions_path"],
                producer="modeling_executor",
                metadata={"n_predictions": summary["n_predictions"]},
            ),
            ArtifactRef(
                name="modeling_summary",
                artifact_type="log",
                path=summary["summary_path"],
                producer="modeling_executor",
                metadata={"threshold": summary["threshold"]},
            ),
        ]
        if summary.get("preprocessor_path"):
            artifacts.append(
                ArtifactRef(
                    name=f"{summary['model_name']}_preprocessor",
                    artifact_type="model",
                    path=summary["preprocessor_path"],
                    producer="modeling_executor",
                    metadata={"model_name": summary["model_name"]},
                )
            )
        if summary.get("training_curve_path"):
            artifacts.append(
                ArtifactRef(
                    name=f"{summary['model_name']}_training_curve",
                    artifact_type="log",
                    path=summary["training_curve_path"],
                    producer="modeling_executor",
                    metadata={
                        "model_name": summary["model_name"],
                        "n_epochs": summary.get("n_epochs_trained"),
                    },
                )
            )
        return ModelingResult(
            executor_name="modeling",
            status="success",
            message="Anomaly model generated.",
            artifacts=artifacts,
            errors=[],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            model_path=summary["model_path"],
            predictions_path=summary["predictions_path"],
        )
    except Exception as exc:
        error = PipelineError(
            stage="modeling",
            node="modeling_executor",
            message=str(exc),
            recoverable=True,
        )
        return ModelingResult(
            executor_name="modeling",
            status="failed",
            message="Anomaly modeling failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            model_path=str(model_path),
            predictions_path=str(predictions_path),
        )


def train_anomaly_model(
    features_path: str | Path,
    output_dir: str | Path,
    config: ModelingConfig = DEFAULT_MODELING_CONFIG,
) -> dict[str, Any]:
    """Entrena un detector de anomalias soportado con ventanas normales."""

    if config.model_name not in {
        "isolation_forest",
        "one_class_svm",
        "pca_reconstruction_error",
        "autoencoder_dense",
    }:
        raise ValueError(f"unsupported model_name for MVP: {config.model_name}")

    data = pd.read_csv(features_path)
    feature_columns = _feature_columns(data)
    train = data[(data["split"] == "train") & (data["label"] == "normal")]
    if train.empty:
        raise ValueError("training requires normal windows in split=train")

    model_bundle, scores, threshold_quantile = _fit_and_score(
        config,
        train,
        data,
        feature_columns,
    )
    threshold = _threshold(scores, data["split"].to_numpy(), threshold_quantile)
    predictions = _prediction_rows(data, scores, threshold)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    model_path = _model_output_path(output, config.model_name)
    predictions_path = output / "predictions.csv"
    summary_path = output / "modeling_summary.json"
    model_bundle.update(
        {
            "feature_columns": feature_columns,
            "threshold": threshold,
            "config": config.model_dump(mode="json"),
        }
    )
    extra_summary = _persist_model_bundle(model_bundle, model_path, output)
    _write_predictions(predictions_path, predictions)
    summary = _summary(
        config,
        feature_columns,
        train,
        data,
        predictions,
        model_path,
        predictions_path,
        summary_path,
        threshold,
        threshold_quantile,
    )
    summary.update(extra_summary)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _model_output_path(output_dir: Path, model_name: str) -> Path:
    suffix = ".pt" if model_name == "autoencoder_dense" else ".joblib"
    return output_dir / f"{model_name}{suffix}"


def _feature_columns(data: pd.DataFrame) -> list[str]:
    columns = [column for column in data.columns if column not in METADATA_COLUMNS]
    if not columns:
        raise ValueError("no feature columns found")
    return columns


def _isolation_forest_params(config: ModelingConfig) -> tuple[dict[str, Any], float]:
    unsupported = set(config.hyperparameters) - SKLEARN_IFOREST_PARAMS - {"threshold_quantile"}
    if unsupported:
        raise ValueError(f"unsupported isolation_forest hyperparameters: {', '.join(sorted(unsupported))}")
    threshold_quantile = float(config.hyperparameters.get("threshold_quantile", 0.99))
    if not 0.0 < threshold_quantile <= 1.0:
        raise ValueError("threshold_quantile must be in (0, 1]")
    params = {
        key: value
        for key, value in config.hyperparameters.items()
        if key in SKLEARN_IFOREST_PARAMS
    }
    return params, threshold_quantile


def _pca_params(config: ModelingConfig) -> tuple[dict[str, Any], float]:
    unsupported = set(config.hyperparameters) - SKLEARN_PCA_PARAMS - {"threshold_quantile"}
    if unsupported:
        raise ValueError(
            f"unsupported pca_reconstruction_error hyperparameters: {', '.join(sorted(unsupported))}"
        )
    threshold_quantile = float(config.hyperparameters.get("threshold_quantile", 0.99))
    if not 0.0 < threshold_quantile <= 1.0:
        raise ValueError("threshold_quantile must be in (0, 1]")
    params = {
        key: value
        for key, value in config.hyperparameters.items()
        if key in SKLEARN_PCA_PARAMS
    }
    n_components = params.get("n_components")
    if n_components is not None:
        if isinstance(n_components, bool):
            raise ValueError("n_components must be numeric")
        if isinstance(n_components, int):
            if n_components < 1:
                raise ValueError("n_components integer must be >= 1")
        elif isinstance(n_components, float):
            if not 0.0 < n_components <= 1.0:
                raise ValueError("n_components float must be in (0, 1]")
        else:
            raise ValueError("n_components must be numeric")
    return params, threshold_quantile


def _one_class_svm_params(config: ModelingConfig) -> tuple[dict[str, Any], float]:
    unsupported = set(config.hyperparameters) - SKLEARN_OCSVM_PARAMS - {
        "threshold_quantile"
    }
    if unsupported:
        raise ValueError(
            "unsupported one_class_svm hyperparameters: "
            + ", ".join(sorted(unsupported))
        )
    threshold_quantile = float(config.hyperparameters.get("threshold_quantile", 0.99))
    if not 0.0 < threshold_quantile <= 1.0:
        raise ValueError("threshold_quantile must be in (0, 1]")
    params = {
        key: value
        for key, value in config.hyperparameters.items()
        if key in SKLEARN_OCSVM_PARAMS
    }
    _validate_one_class_svm_params(params)
    return params, threshold_quantile


def _fit_and_score(
    config: ModelingConfig,
    train: pd.DataFrame,
    data: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[dict[str, Any], np.ndarray, float]:
    if config.model_name == "isolation_forest":
        params, threshold_quantile = _isolation_forest_params(config)
        model = IsolationForest(random_state=config.random_state, **params)
        model.fit(train[feature_columns].to_numpy(dtype=float))
        scores = -model.score_samples(data[feature_columns].to_numpy(dtype=float))
        return {"model": model, "model_family": "sklearn_isolation_forest"}, scores, threshold_quantile

    if config.model_name == "one_class_svm":
        params, threshold_quantile = _one_class_svm_params(config)
        scaler = StandardScaler()
        train_matrix = scaler.fit_transform(train[feature_columns].to_numpy(dtype=float))
        all_matrix = scaler.transform(data[feature_columns].to_numpy(dtype=float))
        model = OneClassSVM(**params)
        model.fit(train_matrix)
        scores = -model.decision_function(all_matrix)
        return {
            "model": model,
            "scaler": scaler,
            "model_family": "sklearn_one_class_svm",
        }, scores, threshold_quantile

    if config.model_name == "autoencoder_dense":
        return _fit_autoencoder_dense(config, train, data, feature_columns)

    params, threshold_quantile = _pca_params(config)
    scaler = StandardScaler()
    train_matrix = scaler.fit_transform(train[feature_columns].to_numpy(dtype=float))
    all_matrix = scaler.transform(data[feature_columns].to_numpy(dtype=float))
    model = PCA(random_state=config.random_state, **params)
    model.fit(train_matrix)
    reconstructed = model.inverse_transform(model.transform(all_matrix))
    scores = np.mean((all_matrix - reconstructed) ** 2, axis=1)
    return {
        "model": model,
        "scaler": scaler,
        "model_family": "pca_reconstruction_error",
    }, scores, threshold_quantile


def _autoencoder_dense_params(
    config: ModelingConfig,
    *,
    input_dim: int,
) -> tuple[dict[str, Any], float]:
    unsupported = set(config.hyperparameters) - AUTOENCODER_DENSE_PARAMS
    if unsupported:
        raise ValueError(
            "unsupported autoencoder_dense hyperparameters: "
            + ", ".join(sorted(unsupported))
        )

    threshold_quantile = float(config.hyperparameters.get("threshold_quantile", 0.99))
    if not 0.0 < threshold_quantile <= 1.0:
        raise ValueError("threshold_quantile must be in (0, 1]")

    hidden_layers = _parse_autoencoder_hidden_layers(
        config.hyperparameters.get("hidden_layers"),
        input_dim=input_dim,
    )
    latent_dim = _positive_int_hyperparameter(
        config.hyperparameters.get("latent_dim"),
        name="latent_dim",
        default=max(1, min(8, input_dim // 2 or 1)),
    )
    if not 1 <= latent_dim <= min(hidden_layers[-1], input_dim, 64):
        raise ValueError(
            "autoencoder_dense latent_dim must be between 1 and "
            "min(last hidden layer, input_dim, 64)"
        )

    learning_rate = _float_hyperparameter(
        config.hyperparameters.get("learning_rate"),
        name="learning_rate",
        default=0.001,
    )
    if not 1e-5 <= learning_rate <= 1e-2:
        raise ValueError("autoencoder_dense learning_rate must be between 1e-5 and 1e-2")

    batch_size = _positive_int_hyperparameter(
        config.hyperparameters.get("batch_size"),
        name="batch_size",
        default=32,
    )
    if not 4 <= batch_size <= 512:
        raise ValueError("autoencoder_dense batch_size must be between 4 and 512")

    max_epochs = _positive_int_hyperparameter(
        config.hyperparameters.get("max_epochs"),
        name="max_epochs",
        default=100,
    )
    if not 1 <= max_epochs <= 500:
        raise ValueError("autoencoder_dense max_epochs must be between 1 and 500")

    patience = _non_negative_int_hyperparameter(
        config.hyperparameters.get("patience"),
        name="patience",
        default=12,
    )
    if patience > max_epochs:
        raise ValueError("autoencoder_dense patience cannot exceed max_epochs")

    weight_decay = _float_hyperparameter(
        config.hyperparameters.get("weight_decay"),
        name="weight_decay",
        default=0.0001,
    )
    if not 0.0 <= weight_decay <= 1e-2:
        raise ValueError("autoencoder_dense weight_decay must be between 0 and 1e-2")

    device = str(config.hyperparameters.get("device", "cpu")).lower()
    if device != "cpu":
        raise ValueError("autoencoder_dense device must be cpu for local reproducibility")

    return {
        "hidden_layers": hidden_layers,
        "latent_dim": latent_dim,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "max_epochs": max_epochs,
        "patience": patience,
        "weight_decay": weight_decay,
        "device": device,
    }, threshold_quantile


def _parse_autoencoder_hidden_layers(value: Any, *, input_dim: int) -> list[int]:
    if value is None:
        return [max(4, min(64, input_dim * 2))]
    if isinstance(value, bool):
        raise ValueError("autoencoder_dense hidden_layers must be an integer or csv string")
    if isinstance(value, int):
        layers = [value]
    elif isinstance(value, str):
        try:
            layers = [int(part.strip()) for part in value.split(",") if part.strip()]
        except ValueError as exc:
            raise ValueError(
                "autoencoder_dense hidden_layers must contain integers"
            ) from exc
    else:
        raise ValueError("autoencoder_dense hidden_layers must be an integer or csv string")
    if not 1 <= len(layers) <= 3:
        raise ValueError("autoencoder_dense hidden_layers must define 1 to 3 layers")
    if any(layer < 2 or layer > 256 for layer in layers):
        raise ValueError("autoencoder_dense hidden_layers values must be in [2, 256]")
    return layers


def _positive_int_hyperparameter(value: Any, *, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"autoencoder_dense {name} must be an integer")
    return value


def _non_negative_int_hyperparameter(value: Any, *, name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"autoencoder_dense {name} must be an integer")
    if value < 0:
        raise ValueError(f"autoencoder_dense {name} must be >= 0")
    return value


def _float_hyperparameter(value: Any, *, name: str, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"autoencoder_dense {name} must be numeric")
    return float(value)


def _fit_autoencoder_dense(
    config: ModelingConfig,
    train: pd.DataFrame,
    data: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[dict[str, Any], np.ndarray, float]:
    params, threshold_quantile = _autoencoder_dense_params(
        config,
        input_dim=len(feature_columns),
    )
    torch, nn = _torch_modules()

    seed = 42 if config.random_state is None else int(config.random_state)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)

    scaler = StandardScaler()
    train_matrix = scaler.fit_transform(train[feature_columns].to_numpy(dtype=float))
    all_matrix = scaler.transform(data[feature_columns].to_numpy(dtype=float))
    if not np.isfinite(train_matrix).all() or not np.isfinite(all_matrix).all():
        raise ValueError("autoencoder_dense requires finite numeric feature values")

    validation = data[(data["split"] == "validation") & (data["label"] == "normal")]
    validation_matrix = (
        scaler.transform(validation[feature_columns].to_numpy(dtype=float))
        if not validation.empty
        else train_matrix
    )

    model = _build_autoencoder_model(
        nn,
        input_dim=len(feature_columns),
        hidden_layers=params["hidden_layers"],
        latent_dim=params["latent_dim"],
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=params["learning_rate"],
        weight_decay=params["weight_decay"],
    )
    loss_fn = nn.MSELoss()
    train_tensor = torch.tensor(train_matrix, dtype=torch.float32)
    validation_tensor = torch.tensor(validation_matrix, dtype=torch.float32)

    history, best_state = _train_autoencoder_loop(
        torch=torch,
        model=model,
        optimizer=optimizer,
        loss_fn=loss_fn,
        train_tensor=train_tensor,
        validation_tensor=validation_tensor,
        batch_size=params["batch_size"],
        max_epochs=params["max_epochs"],
        patience=params["patience"],
    )
    model.load_state_dict(best_state)
    model.eval()
    all_tensor = torch.tensor(all_matrix, dtype=torch.float32)
    with torch.no_grad():
        reconstructed = model(all_tensor).detach().cpu().numpy()
    scores = np.mean((all_matrix - reconstructed) ** 2, axis=1)

    return {
        "model": model,
        "scaler": scaler,
        "model_family": "torch_autoencoder_dense",
        "autoencoder_params": params,
        "training_history": history,
        "model_state_dict": {
            key: value.detach().cpu()
            for key, value in model.state_dict().items()
        },
    }, scores, threshold_quantile


def _torch_modules() -> tuple[Any, Any]:
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required for autoencoder_dense. Install project "
            "dependencies with torch>=2.3 before selecting this model."
        ) from exc
    return torch, nn


def _build_autoencoder_model(
    nn: Any,
    *,
    input_dim: int,
    hidden_layers: list[int],
    latent_dim: int,
) -> Any:
    encoder_layers: list[Any] = []
    previous = input_dim
    for hidden_dim in hidden_layers:
        encoder_layers.extend([nn.Linear(previous, hidden_dim), nn.ReLU()])
        previous = hidden_dim
    encoder_layers.append(nn.Linear(previous, latent_dim))

    decoder_layers: list[Any] = []
    previous = latent_dim
    for hidden_dim in reversed(hidden_layers):
        decoder_layers.extend([nn.Linear(previous, hidden_dim), nn.ReLU()])
        previous = hidden_dim
    decoder_layers.append(nn.Linear(previous, input_dim))

    return nn.Sequential(
        nn.Sequential(*encoder_layers),
        nn.Sequential(*decoder_layers),
    )


def _train_autoencoder_loop(
    *,
    torch: Any,
    model: Any,
    optimizer: Any,
    loss_fn: Any,
    train_tensor: Any,
    validation_tensor: Any,
    batch_size: int,
    max_epochs: int,
    patience: int,
) -> tuple[list[dict[str, float | int]], dict[str, Any]]:
    best_state = {
        key: value.detach().cpu().clone()
        for key, value in model.state_dict().items()
    }
    best_validation_loss = float("inf")
    epochs_without_improvement = 0
    history: list[dict[str, float | int]] = []

    for epoch in range(1, max_epochs + 1):
        model.train()
        permutation = torch.randperm(train_tensor.shape[0])
        batch_losses: list[float] = []
        for start in range(0, train_tensor.shape[0], batch_size):
            indices = permutation[start : start + batch_size]
            batch = train_tensor[indices]
            optimizer.zero_grad()
            reconstructed = model(batch)
            loss = loss_fn(reconstructed, batch)
            loss.backward()
            optimizer.step()
            batch_losses.append(float(loss.detach().cpu().item()))

        model.eval()
        with torch.no_grad():
            validation_loss = float(
                loss_fn(model(validation_tensor), validation_tensor)
                .detach()
                .cpu()
                .item()
            )
        train_loss = float(np.mean(batch_losses)) if batch_losses else validation_loss
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "validation_loss": validation_loss,
            }
        )

        if validation_loss < best_validation_loss - 1e-8:
            best_validation_loss = validation_loss
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.state_dict().items()
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if patience > 0 and epochs_without_improvement >= patience:
                break

    return history, best_state


def _persist_model_bundle(
    model_bundle: dict[str, Any],
    model_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if model_bundle.get("model_family") != "torch_autoencoder_dense":
        joblib.dump(model_bundle, model_path)
        return {"model_family": model_bundle.get("model_family")}

    torch, _ = _torch_modules()
    preprocessor_path = output_dir / "autoencoder_dense_scaler.joblib"
    training_curve_path = output_dir / "autoencoder_dense_training_curve.json"
    checkpoint = {
        "model_family": model_bundle["model_family"],
        "feature_columns": model_bundle["feature_columns"],
        "threshold": model_bundle["threshold"],
        "config": model_bundle["config"],
        "autoencoder_params": model_bundle["autoencoder_params"],
        "model_state_dict": model_bundle["model_state_dict"],
        "scaler_path": str(preprocessor_path),
    }
    torch.save(checkpoint, model_path)
    joblib.dump(model_bundle["scaler"], preprocessor_path)
    training_curve_path.write_text(
        json.dumps(model_bundle["training_history"], indent=2),
        encoding="utf-8",
    )
    return {
        "model_family": model_bundle["model_family"],
        "preprocessor_path": str(preprocessor_path),
        "training_curve_path": str(training_curve_path),
        "n_epochs_trained": len(model_bundle["training_history"]),
        "best_validation_loss": min(
            row["validation_loss"] for row in model_bundle["training_history"]
        ),
    }


def _validate_one_class_svm_params(params: dict[str, Any]) -> None:
    kernel = params.get("kernel", "rbf")
    if kernel not in {"linear", "poly", "rbf", "sigmoid"}:
        raise ValueError("one_class_svm kernel must be linear, poly, rbf or sigmoid")

    nu = params.get("nu", 0.5)
    if isinstance(nu, bool) or not isinstance(nu, int | float):
        raise ValueError("one_class_svm nu must be numeric")
    if not 0.0 < float(nu) <= 1.0:
        raise ValueError("one_class_svm nu must be in (0, 1]")

    gamma = params.get("gamma", "scale")
    if isinstance(gamma, str):
        if gamma not in {"scale", "auto"}:
            raise ValueError("one_class_svm gamma must be scale, auto or positive")
    elif isinstance(gamma, bool) or not isinstance(gamma, int | float):
        raise ValueError("one_class_svm gamma must be scale, auto or positive")
    elif float(gamma) <= 0.0:
        raise ValueError("one_class_svm gamma must be positive")

    degree = params.get("degree")
    if degree is not None:
        if isinstance(degree, bool) or not isinstance(degree, int):
            raise ValueError("one_class_svm degree must be an integer")
        if not 2 <= degree <= 6:
            raise ValueError("one_class_svm degree must be between 2 and 6")

    coef0 = params.get("coef0")
    if coef0 is not None:
        if isinstance(coef0, bool) or not isinstance(coef0, int | float):
            raise ValueError("one_class_svm coef0 must be numeric")
        if not -10.0 <= float(coef0) <= 10.0:
            raise ValueError("one_class_svm coef0 must be between -10 and 10")

    tol = params.get("tol")
    if tol is not None:
        if isinstance(tol, bool) or not isinstance(tol, int | float):
            raise ValueError("one_class_svm tol must be numeric")
        if not 1e-6 <= float(tol) <= 1e-1:
            raise ValueError("one_class_svm tol must be between 1e-6 and 1e-1")

    shrinking = params.get("shrinking")
    if shrinking is not None and not isinstance(shrinking, bool):
        raise ValueError("one_class_svm shrinking must be boolean")

    cache_size = params.get("cache_size")
    if cache_size is not None:
        if isinstance(cache_size, bool) or not isinstance(cache_size, int | float):
            raise ValueError("one_class_svm cache_size must be numeric")
        if not 50 <= float(cache_size) <= 1000:
            raise ValueError("one_class_svm cache_size must be between 50 and 1000")

    max_iter = params.get("max_iter")
    if max_iter is not None:
        if isinstance(max_iter, bool) or not isinstance(max_iter, int):
            raise ValueError("one_class_svm max_iter must be an integer")
        if max_iter != -1 and not 100 <= max_iter <= 100000:
            raise ValueError("one_class_svm max_iter must be -1 or between 100 and 100000")


def _threshold(scores: np.ndarray, splits: np.ndarray, quantile: float) -> float:
    validation_scores = scores[splits == "validation"]
    source = validation_scores if validation_scores.size else scores[splits == "train"]
    return float(np.quantile(source, quantile))


def _prediction_rows(
    data: pd.DataFrame,
    scores: np.ndarray,
    threshold: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row, score in zip(data.to_dict("records"), scores, strict=True):
        rows.append(
            {
                "window_id": row["window_id"],
                "file_id": row["file_id"],
                "condition_id": _optional_text(row.get("condition_id", "")),
                "asset_id": _optional_text(row.get("asset_id", "")),
                "run_id": _optional_text(row.get("run_id", "")),
                "label_source": _optional_text(row.get("label_source", "")),
                "label_granularity": _optional_text(
                    row.get("label_granularity", "")
                ),
                "window_index": _optional_value(row.get("window_index", "")),
                "timestamp_start": _optional_text(row.get("timestamp_start", "")),
                "timestamp_end": _optional_text(row.get("timestamp_end", "")),
                "time_since_start_seconds": _optional_value(
                    row.get("time_since_start_seconds", "")
                ),
                "time_to_failure_seconds": _optional_value(
                    row.get("time_to_failure_seconds", "")
                ),
                "relative_life": _optional_value(row.get("relative_life", "")),
                "split": row["split"],
                "label": row["label"],
                "target": row["target"],
                "fault_type": _optional_text(row.get("fault_type", "")),
                "anomaly_score": float(score),
                "threshold": threshold,
                "predicted_anomaly": int(score > threshold),
            }
        )
    return rows


def _optional_text(value: Any) -> str:
    return "" if pd.isna(value) else str(value)


def _optional_value(value: Any) -> Any:
    return "" if pd.isna(value) else value


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=PREDICTION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _summary(
    config: ModelingConfig,
    feature_columns: list[str],
    train: pd.DataFrame,
    data: pd.DataFrame,
    predictions: list[dict[str, Any]],
    model_path: Path,
    predictions_path: Path,
    summary_path: Path,
    threshold: float,
    threshold_quantile: float,
) -> dict[str, Any]:
    prediction_counts = Counter(row["predicted_anomaly"] for row in predictions)
    return {
        "model_name": config.model_name,
        "model_path": str(model_path),
        "predictions_path": str(predictions_path),
        "summary_path": str(summary_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "config": config.model_dump(mode="json"),
        "feature_columns": feature_columns,
        "threshold": threshold,
        "threshold_quantile": threshold_quantile,
        "n_train_windows": int(len(train)),
        "n_predictions": int(len(predictions)),
        "split_counts": dict(Counter(data["split"])),
        "label_counts": dict(Counter(data["label"])),
        "predicted_anomaly_counts": {str(key): value for key, value in prediction_counts.items()},
    }
