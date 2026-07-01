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
