"""OCR 温度アンカーの信頼度・妥当性ロジックのテスト.

アンカー値（t_min/t_max）を 1 つ読み違えると画像全体がバイアスするため、
`read_scale_temperatures_with_confidence` が「一致率」「妥当性」を正しく返し、
非妥当な読み（スパン非正・不完全）を弾くことを確認する。tesseract 非依存
（OCR 候補生成を差し替えて検証する）。
"""

import numpy as np
import pytest

import hikmicropy.fusion as fusion


@pytest.fixture()
def hf(monkeypatch):
    # cv2.imread を差し替え、実画像なしでも「読めた」ことにする
    monkeypatch.setattr(fusion.cv2, "imread", lambda *a, **k: np.zeros((480, 640, 3), np.uint8))
    return fusion


def _patch_candidates(hf, monkeypatch, min_vals, max_vals):
    def fake(img, boxes, variants, psms):
        # min_boxes は y0>=380 の箱で判別
        return min_vals if boxes and boxes[0][1] >= 380 else max_vals

    monkeypatch.setattr(hf, "_ocr_temperature_candidates", fake)


def test_good_read_is_plausible_with_full_confidence(hf, monkeypatch):
    _patch_candidates(hf, monkeypatch, [31.4, 31.4, 31.4], [33.8, 33.8, 33.8])
    r = hf.read_scale_temperatures_with_confidence("dummy.jpg")
    assert (r["t_min"], r["t_max"]) == (31.4, 33.8)
    assert r["min_conf"] == 1.0 and r["max_conf"] == 1.0
    assert r["plausible"] is True and r["note"] == ""


def test_disagreement_lowers_confidence(hf, monkeypatch):
    # max 側が 3 候補中 1 票 → conf ~0.33、ただし最頻値自体は妥当
    _patch_candidates(hf, monkeypatch, [31.4, 31.4], [38.4, 33.4, 88.0])
    r = hf.read_scale_temperatures_with_confidence("dummy.jpg")
    assert r["max_conf"] < 0.5
    assert r["plausible"] is True


def test_nonpositive_span_is_rejected(hf, monkeypatch):
    # min 箱と max 箱が同じ値 → スパン 0（到達可能な不整合）を弾く
    _patch_candidates(hf, monkeypatch, [31.4, 31.4], [31.4, 31.4])
    r = hf.read_scale_temperatures_with_confidence("dummy.jpg")
    assert r["plausible"] is False and r["note"] == "nonpositive_span"


def test_swapped_order_is_corrected(hf, monkeypatch):
    # min 箱に大きい値、max 箱に小さい値が来ても t_min<t_max に整列される
    _patch_candidates(hf, monkeypatch, [33.8, 33.8], [31.4, 31.4])
    r = hf.read_scale_temperatures_with_confidence("dummy.jpg")
    assert r["t_min"] == 31.4 and r["t_max"] == 33.8
    assert r["plausible"] is True


def test_empty_read_is_incomplete(hf, monkeypatch):
    _patch_candidates(hf, monkeypatch, [], [])
    r = hf.read_scale_temperatures_with_confidence("dummy.jpg")
    assert r["t_min"] is None and r["t_max"] is None
    assert r["plausible"] is False and r["note"] == "ocr_incomplete"


def test_backward_compatible_tuple(hf, monkeypatch):
    _patch_candidates(hf, monkeypatch, [31.4], [33.8])
    assert hf.read_scale_temperatures_from_overlay("dummy.jpg") == (31.4, 33.8)
