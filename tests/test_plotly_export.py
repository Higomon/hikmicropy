import numpy as np

from hikmicropy.plotly_export import export_plotly_html


def test_plotly_html_export_contains_hovertemplate(tmp_path):
    raw = np.array([[1, 2], [3, 4]], dtype=np.float64)
    temp = np.array([[10.0, 11.0], [12.0, 13.0]], dtype=np.float64)
    out = tmp_path / "thermal.html"

    export_plotly_html(raw, out, temperature_c=temp, include_plotlyjs="cdn")
    text = out.read_text(encoding="utf-8")

    assert "raw=%{customdata[0]:.0f}" in text
    assert "temp=%{customdata[1]:.2f} C" in text


def test_fusion_background_overlay_has_image_and_hover(tmp_path):
    # 実運用経路: 合成画像を背景に、透明な hover 格子で温度を出す
    raw = np.array([[4500, 4600], [4550, 4650]], dtype=np.float64)
    temp = np.array([[25.0, 26.0], [25.5, 26.5]], dtype=np.float64)
    background_rgb = np.zeros((8, 10, 3), dtype=np.uint8)
    out = tmp_path / "fusion.html"

    export_plotly_html(raw, out, temperature_c=temp, background_rgb=background_rgb)
    text = out.read_text(encoding="utf-8")

    assert '"type":"image"' in text                 # 合成画像レイヤ
    assert "rgba(0,0,0,0)" in text                   # 透明な hover 格子
    assert "raw=%{customdata[0]:.0f}" in text
    assert "temp=%{customdata[1]:.2f} C" in text
