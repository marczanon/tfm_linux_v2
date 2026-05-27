"""Diagnostico no supervisado de degradacion para features NASA IMS."""

from __future__ import annotations

import argparse
import json

from codigo.app.services.degradation_diagnostics import (
    generate_degradation_diagnostics,
)


def main() -> None:
    args = _parse_args()
    summary = generate_degradation_diagnostics(
        args.features_path,
        args.output_dir,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--features-path",
        default=(
            "codigo/data/tensors/nasa_ims_bearing/"
            "nasa-ims-qwen-smoke-fase3-qwen/windows_features.csv"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=(
            "codigo/reports/nasa_ims_bearing/"
            "nasa-ims-qwen-smoke-fase3-qwen/degradation"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
