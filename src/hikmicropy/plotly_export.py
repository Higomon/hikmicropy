"""Plotly HTML export helpers for HIKMICRO thermal arrays."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def lut_to_plotly_colorscale(lut_rgb: np.ndarray) -> list[list[object]]:
    """Convert a 256x3 RGB LUT into a Plotly colorscale."""
    lut = np.asarray(lut_rgb, dtype=np.uint8)
    if lut.shape != (256, 3):
        raise ValueError(f"expected LUT shape (256, 3), got {lut.shape}")
    stops = []
    for idx in np.linspace(0, 255, 16).astype(int):
        r, g, b = [int(v) for v in lut[idx]]
        stops.append([float(idx / 255.0), f"rgb({r},{g},{b})"])
    return stops


def export_plotly_html(
    raw: np.ndarray,
    out_path: str | Path,
    temperature_c: np.ndarray | None = None,
    colorscale: list[list[object]] | str | None = None,
    title: str = "HIKMICRO thermal data",
    include_plotlyjs: str | bool = "cdn",
) -> None:
    """Write an interactive Plotly heatmap with raw/temperature hover data."""
    import plotly.graph_objects as go

    raw_f = np.asarray(raw, dtype=np.float64)
    if temperature_c is not None:
        temp_f = np.asarray(temperature_c, dtype=np.float64)
        if temp_f.shape != raw_f.shape:
            raise ValueError(f"temperature shape {temp_f.shape} != raw shape {raw_f.shape}")
        z = temp_f
        customdata = np.dstack([raw_f, temp_f])
        colorbar_title = "C"
        hovertemplate = (
            "x=%{x}<br>"
            "y=%{y}<br>"
            "raw=%{customdata[0]:.0f}<br>"
            "temp=%{customdata[1]:.2f} C"
            "<extra></extra>"
        )
    else:
        z = raw_f
        customdata = raw_f[..., None]
        colorbar_title = "raw"
        hovertemplate = (
            "x=%{x}<br>"
            "y=%{y}<br>"
            "raw=%{customdata[0]:.0f}<br>"
            "temperature=uncalibrated"
            "<extra></extra>"
        )

    if colorscale is None:
        colorscale = "Viridis"

    fig = go.Figure(
        data=[
            go.Heatmap(
                z=z,
                customdata=customdata,
                colorscale=colorscale,
                colorbar={"title": colorbar_title},
                hovertemplate=hovertemplate,
            )
        ]
    )
    fig.update_layout(
        title=title,
        xaxis_title="x [pixel]",
        yaxis_title="y [pixel]",
        yaxis={"autorange": "reversed", "scaleanchor": "x"},
        dragmode="pan",
    )
    fig.write_html(str(out_path), include_plotlyjs=include_plotlyjs)
