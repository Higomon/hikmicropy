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
    background_rgb: np.ndarray | None = None,
) -> None:
    """Write an interactive Plotly heatmap with raw/temperature hover data.

    If ``background_rgb`` (an H×W×3 RGB image, e.g. the detail-fused ``*_fusion.png``)
    is supplied, it is drawn as the visible layer and a transparent, hover-only grid
    carrying the per-pixel raw / temperature values is overlaid on top. This keeps the
    fused structural edges visible while every pixel still reports its temperature on
    hover. Without it, a colour-mapped heatmap is written (legacy behaviour).
    """
    import plotly.graph_objects as go

    raw_f = np.asarray(raw, dtype=np.float64)

    if background_rgb is not None:
        _write_fusion_overlay_html(
            raw_f, background_rgb, temperature_c, title, include_plotlyjs, out_path, go
        )
        return

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


def _write_fusion_overlay_html(
    raw_f: np.ndarray,
    background_rgb: np.ndarray,
    temperature_c: np.ndarray | None,
    title: str,
    include_plotlyjs: str | bool,
    out_path: str | Path,
    go,
) -> None:
    """Fused image as the visible layer + a transparent hover grid on top."""
    bg = np.asarray(background_rgb)
    if bg.ndim != 3 or bg.shape[2] != 3:
        raise ValueError(f"background_rgb must be H×W×3 RGB, got {bg.shape}")
    bh, bw = bg.shape[:2]
    h, w = raw_f.shape
    # 生データ格子(w×h)を合成画像(bw×bh)の全面に重ねる（セル中心を等間隔配置）。
    dx, dy = bw / w, bh / h

    if temperature_c is not None:
        temp_f = np.asarray(temperature_c, dtype=np.float64)
        if temp_f.shape != raw_f.shape:
            raise ValueError(f"temperature shape {temp_f.shape} != raw shape {raw_f.shape}")
        customdata = np.dstack([raw_f, temp_f])
        hovertemplate = (
            "raw=%{customdata[0]:.0f}<br>"
            "temp=%{customdata[1]:.2f} C"
            "<extra></extra>"
        )
    else:
        customdata = raw_f[..., None]
        hovertemplate = (
            "raw=%{customdata[0]:.0f}<br>"
            "temperature=uncalibrated"
            "<extra></extra>"
        )

    hover = go.Heatmap(
        z=np.zeros((h, w)),
        x0=dx / 2.0 - 0.5, dx=dx,
        y0=dy / 2.0 - 0.5, dy=dy,
        customdata=customdata,
        colorscale=[[0.0, "rgba(0,0,0,0)"], [1.0, "rgba(0,0,0,0)"]],
        showscale=False,
        hoverongaps=False,
    )
    hover.update(hovertemplate=hovertemplate)

    # go.Image は自前の hover を出さない（hoverinfo=skip）。上に重ねた透明格子が
    # 最近傍セルの温度を表示する（hovermode=closest）。
    fig = go.Figure(data=[go.Image(z=bg, hoverinfo="skip"), hover])
    fig.update_layout(
        title=title,
        dragmode="pan",
        hovermode="closest",
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        xaxis={"visible": False, "range": [-0.5, bw - 0.5], "constrain": "domain"},
        yaxis={"visible": False, "range": [bh - 0.5, -0.5], "scaleanchor": "x"},
    )
    fig.write_html(str(out_path), include_plotlyjs=include_plotlyjs)
