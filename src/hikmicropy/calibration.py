"""Validate HIKMICRO raw-to-temperature calibration against Analyzer CSV.

Compares the raw HDRI array extracted from a HIKMICRO JPEG with a per-pixel
temperature CSV exported by HIKMICRO Analyzer, and reports fit metrics for the
linear and two-point calibrations. This is a validation/inspection tool; the
runtime calibration is the per-image two-point linear model in ``extractor``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .extractor import HikmicroExtractor


@dataclass
class FitMetrics:
    rmse: float
    mae: float
    max_abs_error: float
    mean_error: float
    n: int


@dataclass
class LinearCalibration:
    model_type: str
    slope: float
    intercept: float


def _parse_numeric_token(token: str) -> float | None:
    cleaned = token.strip().strip('"').strip("'")
    cleaned = cleaned.replace("degC", "").replace("C", "").replace("℃", "")
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    if "," in cleaned and "." not in cleaned:
        cleaned = cleaned.replace(",", ".")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
        return None
    return float(cleaned)


def _detect_delimiter(lines: list[str]) -> str:
    sample = "\n".join(lines[:10])
    counts = {
        ";": sample.count(";"),
        "\t": sample.count("\t"),
        ",": sample.count(","),
    }
    delimiter, count = max(counts.items(), key=lambda item: item[1])
    return delimiter if count > 0 else ","


def read_analyzer_csv(path: str | Path) -> np.ndarray:
    """Read a HIKMICRO Analyzer temperature CSV into a 2D float64 array."""
    csv_path = Path(path)
    lines = [line.strip() for line in csv_path.read_text(encoding="utf-8-sig").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise ValueError(f"empty CSV: {csv_path}")

    delimiter = _detect_delimiter(lines)
    rows: list[list[float]] = []
    for line in lines:
        values = []
        for token in line.split(delimiter):
            value = _parse_numeric_token(token)
            if value is not None:
                values.append(value)
        if values:
            rows.append(values)

    if not rows:
        raise ValueError(f"no numeric rows in CSV: {csv_path}")

    width_counts: dict[int, int] = {}
    for row in rows:
        width_counts[len(row)] = width_counts.get(len(row), 0) + 1
    expected_width = max(width_counts.items(), key=lambda item: item[1])[0]
    filtered = [row for row in rows if len(row) == expected_width]
    if not filtered:
        raise ValueError(f"could not find consistent numeric row width in: {csv_path}")

    return np.asarray(filtered, dtype=np.float64)


def fit_linear_calibration(raw: np.ndarray, temp_c: np.ndarray) -> LinearCalibration:
    raw_flat = raw.astype(np.float64).ravel()
    temp_flat = temp_c.astype(np.float64).ravel()
    if raw_flat.shape != temp_flat.shape:
        raise ValueError(f"shape mismatch after flatten: raw={raw.shape}, temp={temp_c.shape}")
    slope, intercept = np.polyfit(raw_flat, temp_flat, 1)
    return LinearCalibration("linear", float(slope), float(intercept))


def apply_linear_calibration(raw: np.ndarray, model: LinearCalibration) -> np.ndarray:
    return raw.astype(np.float64) * model.slope + model.intercept


def two_point_calibration(raw: np.ndarray, t_min: float, t_max: float) -> np.ndarray:
    raw_f = raw.astype(np.float64)
    rmin = float(raw_f.min())
    rmax = float(raw_f.max())
    if rmax == rmin:
        return np.full_like(raw_f, (t_min + t_max) / 2.0)
    return t_min + (raw_f - rmin) / (rmax - rmin) * (t_max - t_min)


def compute_metrics(pred: np.ndarray, ref: np.ndarray) -> FitMetrics:
    diff = pred.astype(np.float64) - ref.astype(np.float64)
    return FitMetrics(
        rmse=float(math.sqrt(np.mean(diff**2))),
        mae=float(np.mean(np.abs(diff))),
        max_abs_error=float(np.max(np.abs(diff))),
        mean_error=float(np.mean(diff)),
        n=int(diff.size),
    )


def align_raw_to_temperature_shape(raw: np.ndarray, temp_c: np.ndarray) -> np.ndarray:
    """Return raw array aligned to the Analyzer CSV shape.

    If Analyzer exports display-size data, resize raw to that shape using cubic
    interpolation. If shapes already match, return raw unchanged.
    """
    if raw.shape == temp_c.shape:
        return raw
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - dependency error path
        raise RuntimeError("OpenCV is required when CSV shape differs from raw shape") from exc

    target_h, target_w = temp_c.shape
    resized = cv2.resize(raw.astype(np.float32), (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    return resized.astype(np.float64)


def write_scatter_html(raw: np.ndarray, temp_c: np.ndarray, out_path: str | Path) -> None:
    """Write a raw-vs-temperature scatter plot for visual model inspection."""
    try:
        import plotly.graph_objects as go
    except Exception:
        return

    raw_flat = raw.ravel()
    temp_flat = temp_c.ravel()
    if raw_flat.size > 20000:
        idx = np.linspace(0, raw_flat.size - 1, 20000).astype(int)
        raw_flat = raw_flat[idx]
        temp_flat = temp_flat[idx]

    fig = go.Figure(
        data=[
            go.Scattergl(
                x=raw_flat,
                y=temp_flat,
                mode="markers",
                marker={"size": 3, "opacity": 0.35},
            )
        ]
    )
    fig.update_layout(
        title="Analyzer temperature vs extracted raw value",
        xaxis_title="Extracted raw value",
        yaxis_title="Analyzer temperature [C]",
    )
    fig.write_html(str(out_path), include_plotlyjs="cdn")


def run_probe(
    image_path: str | Path,
    csv_path: str | Path,
    out_dir: str | Path,
    t_min: float | None = None,
    t_max: float | None = None,
) -> dict:
    image_path = Path(image_path)
    csv_path = Path(csv_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    extractor = HikmicroExtractor(str(image_path))
    thermal = extractor.process_image()
    raw = thermal.raw.astype(np.float64)
    temp_c = read_analyzer_csv(csv_path)
    raw_aligned = align_raw_to_temperature_shape(raw, temp_c)

    linear_model = fit_linear_calibration(raw_aligned, temp_c)
    linear_pred = apply_linear_calibration(raw_aligned, linear_model)
    linear_metrics = compute_metrics(linear_pred, temp_c)

    result = {
        "image_path": str(image_path),
        "csv_path": str(csv_path),
        "raw_shape": list(raw.shape),
        "analyzer_shape": list(temp_c.shape),
        "aligned_raw_shape": list(raw_aligned.shape),
        "linear_model": asdict(linear_model),
        "linear_metrics": asdict(linear_metrics),
    }

    if t_min is not None and t_max is not None:
        two_point_pred = two_point_calibration(raw_aligned, t_min, t_max)
        result["two_point"] = {
            "t_min": float(t_min),
            "t_max": float(t_max),
            "metrics": asdict(compute_metrics(two_point_pred, temp_c)),
        }

    stem = image_path.stem
    json_path = out_dir / f"{stem}_calibration_probe.json"
    report_path = out_dir / f"{stem}_calibration_report.md"
    scatter_path = out_dir / f"{stem}_raw_vs_temp.html"

    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_scatter_html(raw_aligned, temp_c, scatter_path)

    lines = [
        f"# Calibration Probe: {image_path.name}",
        "",
        f"- Image: `{image_path}`",
        f"- Analyzer CSV: `{csv_path}`",
        f"- Raw shape: `{raw.shape}`",
        f"- Analyzer shape: `{temp_c.shape}`",
        f"- Linear model: `T = {linear_model.slope:.10f} * raw + {linear_model.intercept:.10f}`",
        f"- Linear RMSE: `{linear_metrics.rmse:.6f}` C",
        f"- Linear MAE: `{linear_metrics.mae:.6f}` C",
        f"- Linear max abs error: `{linear_metrics.max_abs_error:.6f}` C",
    ]
    if "two_point" in result:
        metrics = result["two_point"]["metrics"]
        lines.extend(
            [
                "",
                "## Two-point calibration",
                "",
                f"- t_min: `{t_min}` C",
                f"- t_max: `{t_max}` C",
                f"- RMSE: `{metrics['rmse']:.6f}` C",
                f"- MAE: `{metrics['mae']:.6f}` C",
                f"- Max abs error: `{metrics['max_abs_error']:.6f}` C",
            ]
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result["outputs"] = {
        "json": str(json_path),
        "report": str(report_path),
        "scatter_html": str(scatter_path),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fit extracted HIKMICRO raw values to Analyzer CSV temperatures.")
    parser.add_argument("image", help="HIKMICRO radiometric JPEG")
    parser.add_argument("csv", help="HIKMICRO Analyzer per-pixel temperature CSV")
    parser.add_argument("--out-dir", default="calibration/output", help="Output directory for reports")
    parser.add_argument("--tmin", type=float, default=None, help="Scale-bar minimum temperature [C]")
    parser.add_argument("--tmax", type=float, default=None, help="Scale-bar maximum temperature [C]")
    args = parser.parse_args(argv)

    result = run_probe(args.image, args.csv, args.out_dir, args.tmin, args.tmax)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
