"""hikmicropy: HIKMICRO Pocket2 放射温度JPEG の抽出・フュージョン・温度解析.

主な公開API:
  - HikmicroExtractor: JPEG 末尾の HDRI ブロックから生ラジオメトリ(256x192 uint16)を抽出。
  - to_celsius(t_min, t_max): スケールバー2点による per-image 線形較正（唯一の較正法）。
  - process(...): VIS を IR 画角に整列し arctic フュージョン画像 + 温度凡例 + metadata を出力。
  - export_plotly_html(...): raw/温度を hover できる Plotly HTML を出力。

温度較正の要点:
  raw→℃ は「各画像の焼き込みスケールバー min/max と raw min/max を結ぶ per-image 2点線形」で行う。
  全画像共通の1本式は成立しない（撮影ごとに raw ベースラインがドリフトする）。詳細は README を参照。
"""

from __future__ import annotations

from .extractor import HikThermal, HikmicroExtractor
from .fusion import (
    process,
    read_datetime_original,
    read_scale_temperatures_from_overlay,
    read_scale_temperatures_with_confidence,
)
from .plotly_export import export_plotly_html, lut_to_plotly_colorscale

__version__ = "0.1.0"

__all__ = [
    "HikThermal",
    "HikmicroExtractor",
    "process",
    "read_datetime_original",
    "read_scale_temperatures_from_overlay",
    "read_scale_temperatures_with_confidence",
    "export_plotly_html",
    "lut_to_plotly_colorscale",
    "__version__",
]
