"""HIKMICRO Pocket2: 可視光(VIS)をIRフレームに合わせてクロップ＋自前合成.

背景:
  Pocket2 は 熱(256x192→表示640x480) と 可視光(1600x1200) の2眼。可視光の方が
  画角が広く、IR は可視光の中央付近を写す。メーカー製の合成JPEG(HM*.jpeg)は
  ロゴ・スケールバー・日時が焼き込まれていて邪魔。

このモジュールは:
  1) 生ラジオメトリからロゴ無しのクリーンな熱カラー画像を作る
  2) VIS を IR の画角に合わせてクロップ／位置合わせ（VISの方が広画角なので"切り出し"）
  3) 自前合成（熱カラー＋VISの高周波ディテール）を作る

位置合わせ手法:
  IR合成画像の輪郭 = カメラが整列済みの可視光エッジ。VISエッジを IR合成エッジに
  マルチスケール・テンプレートマッチ（相似変換=クロップ＋拡大）で粗く合わせ、
  UIをマスクした ECC(affine) で精密化する。視差は深度依存なので単一変換では
  完全には消えないが、実用十分な精度で一致する。
"""
from __future__ import annotations

from collections import Counter
import json
import os
import re

import numpy as np
import cv2

from .extractor import HikmicroExtractor


# ---------------------------------------------------------------- #
# 補助
# ---------------------------------------------------------------- #
def _grad(gray: np.ndarray) -> np.ndarray:
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    m = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, 3),
                      cv2.Sobel(g, cv2.CV_32F, 0, 1, 3))
    return cv2.normalize(m, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


# ---------------------------------------------------------------- #
# カラーパレット（FLIR風LUT）
#   FLIR公式記事の実例画像にある温度バーをサンプリングし、制御点化したもの。
#   雨漏り診断では冷たい湿潤部を青〜水色で拾える arctic を既定にする。
#   cv2内蔵(JET/INFERNO等)は色の山が不自然なので使わない。
# ---------------------------------------------------------------- #
def _lut_from_points(points) -> np.ndarray:
    """points=[(pos0..1,(r,g,b)),...] → (256,3) uint8 RGB を線形補間で生成."""
    xs = np.array([p for p, _ in points], float)
    cols = np.array([c for _, c in points], float)
    lut = np.zeros((256, 3), np.uint8)
    g = np.linspace(0, 1, 256)
    for ch in range(3):
        lut[:, ch] = np.clip(np.interp(g, xs, cols[:, ch]), 0, 255)
    return lut


# 制御点（冷→熱, RGB）
_ARCTIC = [(0.0000, (0, 1, 154)), (0.0625, (1, 0, 224)),
           (0.1250, (2, 30, 253)), (0.1875, (12, 117, 245)),
           (0.2500, (33, 186, 253)), (0.3125, (49, 245, 244)),
           (0.3750, (69, 215, 212)), (0.4375, (88, 178, 176)),
           (0.5000, (94, 124, 126)), (0.5625, (109, 101, 88)),
           (0.6250, (149, 100, 70)), (0.6875, (185, 100, 33)),
           (0.7500, (233, 100, 7)), (0.8125, (253, 123, 3)),
           (0.8750, (252, 162, 4)), (0.9375, (243, 216, 3)),
           (1.0000, (253, 228, 73))]
_IRONBOW = [(0.0000, (1, 14, 31)), (0.0625, (15, 3, 105)),
            (0.1250, (71, 0, 132)), (0.1875, (105, 3, 151)),
            (0.2500, (134, 8, 154)), (0.3125, (172, 10, 155)),
            (0.3750, (197, 30, 135)), (0.4375, (216, 49, 101)),
            (0.5000, (232, 71, 76)), (0.5625, (246, 95, 48)),
            (0.6250, (251, 123, 13)), (0.6875, (253, 149, 2)),
            (0.7500, (245, 180, 0)), (0.8125, (253, 199, 2)),
            (0.8750, (255, 218, 26)), (0.9375, (252, 237, 74)),
            (1.0000, (248, 247, 165))]
_LAVA = [(0.0000, (9, 10, 31)), (0.0625, (31, 56, 148)),
         (0.1250, (10, 88, 171)), (0.1875, (0, 111, 164)),
         (0.2500, (0, 126, 148)), (0.3125, (0, 135, 135)),
         (0.3750, (37, 110, 125)), (0.4375, (126, 46, 117)),
         (0.5000, (163, 30, 83)), (0.5625, (180, 30, 57)),
         (0.6250, (207, 27, 39)), (0.6875, (235, 51, 41)),
         (0.7500, (251, 76, 19)), (0.8125, (251, 108, 6)),
         (0.8750, (251, 161, 3)), (0.9375, (254, 192, 9)),
         (1.0000, (254, 228, 89))]
_RAINBOW_HC = [(0.0000, (15, 1, 18)), (0.0625, (138, 0, 137)),
               (0.1250, (218, 5, 221)), (0.1875, (113, 2, 185)),
               (0.2500, (1, 3, 150)), (0.3125, (3, 107, 196)),
               (0.3750, (6, 217, 228)), (0.4375, (0, 161, 120)),
               (0.5000, (4, 85, 16)), (0.5625, (85, 134, 6)),
               (0.6250, (191, 206, 3)), (0.6875, (196, 164, 1)),
               (0.7500, (162, 62, 2)), (0.8125, (144, 4, 13)),
               (0.8750, (176, 31, 34)), (0.9375, (212, 67, 62)),
               (1.0000, (242, 150, 161))]

_LUTS = {name: _lut_from_points(pts) for name, pts in {
    "arctic": _ARCTIC, "ironbow": _IRONBOW, "lava": _LAVA,
    "rainbow_hc": _RAINBOW_HC}.items()}

# CLI/選択用の一覧
PALETTES = ["arctic", "ironbow", "lava", "rainbow_hc",
            "whitehot", "blackhot", "isotherm"]


def apply_palette(u8: np.ndarray, palette: str = "arctic",
                  iso_cold_pct: float = 10.0, iso_hot_pct: float = 95.0) -> np.ndarray:
    """8bitグレー→カラーBGR. palette は PALETTES のいずれか."""
    if palette == "whitehot":
        return cv2.cvtColor(u8, cv2.COLOR_GRAY2BGR)              # 白=高温
    if palette == "blackhot":
        return cv2.cvtColor(255 - u8, cv2.COLOR_GRAY2BGR)       # 黒=高温
    if palette == "isotherm":
        # グレー地に、冷点(=雨漏り湿潤候補)を水色・熱点を赤橙で強調
        out = cv2.cvtColor(u8, cv2.COLOR_GRAY2BGR)
        out[u8 <= np.percentile(u8, iso_cold_pct)] = (255, 210, 0)  # 水色(BGR)
        out[u8 >= np.percentile(u8, iso_hot_pct)] = (35, 60, 245)   # 赤橙(BGR)
        return out
    lut = _LUTS.get(palette, _LUTS["arctic"])
    return cv2.cvtColor(lut[u8], cv2.COLOR_RGB2BGR)


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _parse_datetime_display(value: str | None) -> str | None:
    if not value:
        return None
    m = re.match(r"(\d{4}):(\d{2}):(\d{2})\s+(\d{2}):(\d{2})", value)
    if m:
        y, mo, d, h, mi = m.groups()
        return f"{y}/{mo}/{d} {h}:{mi}"
    m = re.match(r"HM(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", value)
    if m:
        y, mo, d, h, mi = m.groups()
        return f"{y}/{mo}/{d} {h}:{mi}"
    return value


def read_datetime_original(image_path: str) -> str | None:
    """Read EXIF DateTimeOriginal and format it for overlay."""
    try:
        from PIL import Image, ExifTags

        with Image.open(image_path) as im:
            exif = im.getexif()
        tag_names = {v: k for k, v in ExifTags.TAGS.items()}
        for name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            tag = tag_names.get(name)
            if tag is not None and tag in exif:
                return _parse_datetime_display(str(exif[tag]))
    except Exception:
        pass

    import os
    return _parse_datetime_display(os.path.basename(image_path))


def _ocr_temperature_candidates(img: np.ndarray, boxes, variants, psms) -> list[float]:
    try:
        import pytesseract
    except Exception:
        return []

    values: list[float] = []
    for x0, y0, x1, y1 in boxes:
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        up = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        images = []
        if "gray" in variants:
            images.append(up)
        if "otsu" in variants:
            images.append(cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
        if "inv" in variants:
            images.append(cv2.threshold(up, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1])
        if "bright" in variants:
            images.append(cv2.threshold(up, 120, 255, cv2.THRESH_BINARY)[1])

        for image in images:
            for psm in psms:
                config = f"--psm {psm} -c tessedit_char_whitelist=0123456789.Max"
                text = pytesseract.image_to_string(image, config=config).strip()
                for hit in re.findall(r"\d{1,3}\.\d", text):
                    value = round(float(hit), 1)
                    if 0.0 <= value <= 100.0:
                        values.append(value)
    return values


def _value_and_confidence(values: list[float]) -> tuple[float | None, float, int]:
    """OCR 候補値から最頻値と信頼度を返す.

    アンカー値（t_min/t_max）を 1 つ読み違えると画像全体がバイアスするため、
    「何個中何個がその値で一致したか」を confidence（一致率 0..1）として残す。
    戻り: (最頻値 or None, agreement=一致率, n=候補総数)
    """
    if not values:
        return None, 0.0, 0
    value, count = Counter(values).most_common(1)[0]
    return value, count / len(values), len(values)


def read_scale_temperatures_with_confidence(image_path: str) -> dict:
    """スケールバー min/max を OCR し、値と信頼度・妥当性を dict で返す.

    戻り dict:
      t_min, t_max            : 読み取り値（妥当性 NG や失敗時は None）
      min_conf, max_conf      : 各側の OCR 一致率 (0..1)
      min_n, max_n            : 各側の候補総数
      plausible               : t_min<t_max かつ妥当域内で読めたか
      note                    : 妥当性を欠いた理由（あれば）
    """
    fail = {"t_min": None, "t_max": None, "min_conf": 0.0, "max_conf": 0.0,
            "min_n": 0, "max_n": 0, "plausible": False, "note": "image_unreadable"}
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return fail

    max_boxes = [(0, 0, 180, 60), (8, 8, 160, 52)]
    min_boxes = [(8, 388, 92, 424), (0, 385, 105, 430),
                 (10, 390, 90, 422), (0, 380, 110, 430)]

    t_max, max_conf, max_n = _value_and_confidence(
        _ocr_temperature_candidates(img, max_boxes, ("gray", "otsu"), (7, 6))
    )
    t_min, min_conf, min_n = _value_and_confidence(
        _ocr_temperature_candidates(img, min_boxes, ("otsu", "inv", "gray"), (7, 6, 8))
    )
    if t_min is not None and t_max is not None and t_min > t_max:
        t_min, t_max = t_max, t_min
        min_conf, max_conf = max_conf, min_conf
        min_n, max_n = max_n, min_n

    # 値域は候補生成側で 0..100℃ にクランプ済みなので、ここでは到達可能な
    # 不整合（読み欠け・スパン非正）だけを弾く。誤読の実質的な検知は confidence が担う。
    note = ""
    plausible = t_min is not None and t_max is not None
    if not plausible:
        note = "ocr_incomplete"
    elif t_max - t_min <= 0.0:
        plausible, note = False, "nonpositive_span"

    return {"t_min": t_min, "t_max": t_max, "min_conf": min_conf, "max_conf": max_conf,
            "min_n": min_n, "max_n": max_n, "plausible": plausible, "note": note}


def read_scale_temperatures_from_overlay(image_path: str) -> tuple[float | None, float | None]:
    """OCR the camera-rendered min/max scale labels (backward-compatible tuple)."""
    r = read_scale_temperatures_with_confidence(image_path)
    return r["t_min"], r["t_max"]


def _draw_text_box(img: np.ndarray, text: str, x: int, y: int,
                   scale: float = 0.62, thickness: int = 1) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    pad = 6
    x2 = min(img.shape[1] - 1, x + tw + 2 * pad)
    y2 = min(img.shape[0] - 1, y + th + baseline + 2 * pad)
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x2, y2), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)
    cv2.putText(img, text, (x + pad, y + pad + th), font, scale,
                (255, 255, 255), thickness, cv2.LINE_AA)


def draw_temperature_legend(
    image: np.ndarray,
    palette: str,
    t_min: float | None,
    t_max: float | None,
    raw_min: float,
    raw_max: float,
) -> np.ndarray:
    """Draw a FLIR-style temperature color bar on a fusion image."""
    out = image.copy()
    h, w = out.shape[:2]
    x = 14
    bar_w = 18
    bar_h = min(250, h - 180)
    bar_y = 108

    if t_min is not None and t_max is not None:
        top_label = f"Max {t_max:.1f} C"
        bottom_label = f"{t_min:.1f}"
    else:
        top_label = f"Raw max {int(raw_max)}"
        bottom_label = f"{int(raw_min)}"

    _draw_text_box(out, top_label, 10, 10, scale=0.62, thickness=1)

    grad = np.linspace(255, 0, 256, dtype=np.uint8).reshape(256, 1)
    bar = apply_palette(grad, palette)
    bar = cv2.resize(bar, (bar_w, bar_h), interpolation=cv2.INTER_LINEAR)
    out[bar_y:bar_y + bar_h, x:x + bar_w] = bar
    cv2.rectangle(out, (x, bar_y), (x + bar_w, bar_y + bar_h),
                  (255, 255, 255), 1)
    _draw_text_box(out, bottom_label, 10, min(h - 44, bar_y + bar_h + 10),
                   scale=0.62, thickness=1)
    return out


def draw_datetime(image: np.ndarray, datetime_original: str | None) -> np.ndarray:
    if not datetime_original:
        return image
    out = image.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.62
    thickness = 1
    (tw, th), _ = cv2.getTextSize(datetime_original, font, scale, thickness)
    x = max(8, out.shape[1] - tw - 18)
    y = out.shape[0] - 18
    cv2.putText(out, datetime_original, (x + 1, y + 1), font, scale,
                (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(out, datetime_original, (x, y), font, scale,
                (255, 255, 255), thickness, cv2.LINE_AA)
    return out


def write_metadata_json(metadata_path: str, metadata: dict) -> None:
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(_jsonable(metadata), f, ensure_ascii=False, indent=2)


def thermal_gray(raw: np.ndarray, out_size, denoise: int = 35,
                 contrast=(2.0, 98.0)) -> np.ndarray:
    """生ラジオメトリ→表示用グレー(8bit, デノイズ＋拡大)."""
    r = raw.astype(np.float32)
    lo, hi = np.percentile(r, contrast[0]), np.percentile(r, contrast[1])
    u8 = (np.clip((r - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)
    if denoise and denoise > 0:
        u8 = cv2.fastNlMeansDenoising(u8, None, float(denoise), 7, 21)
    return cv2.resize(u8, out_size, interpolation=cv2.INTER_CUBIC)


def thermal_colormap(raw: np.ndarray, out_size, palette="arctic",
                     denoise: int = 35, contrast=(2.0, 98.0)) -> np.ndarray:
    """生ラジオメトリ(H,W)→クリーンな熱カラーBGR画像（UI無し, out_size に拡大）.

    palette  : PALETTES のいずれか（arctic/ironbow/lava/rainbow_hc/whitehot/blackhot/isotherm）
    denoise  : SuperIR風の空間デノイズ強度(=NLMのh, 0で無効, 35前後が目安).
               ※表示用のみ。解析は生配列(get_thermal_np)/to_celsius を使う。
    contrast : 表示コントラストのパーセンタイル (下, 上)
    """
    return apply_palette(thermal_gray(raw, out_size, denoise, contrast), palette)


# ---------------------------------------------------------------- #
# 位置合わせ本体
#   注: 生サーモの2.5倍拡大は メーカー合成の熱層と恒等（実測: 位相相関で shift≈0,
#   scale≈1.000, 回転なし）。よって熱側の補正変換は不要で、VIS を合成に合わせるだけ。
#   同一機体の2カメラ間は スケール＋平行移動のみ（回転・せん断は物理的に無い）。
# ---------------------------------------------------------------- #
def register_vis_to_ir(ir_gray: np.ndarray, vis_gray: np.ndarray,
                       refine: bool = True):
    """VIS を IR フレームへ写す変換を推定.

    戻り値: dict(
        Wm      : 相似変換(2x3, IRフレーム座標->VIS座標, WARP_INVERSE_MAP用),
        warp    : ECC精密化(2x3, vis_coarse->ir),
        scale   : IR->VIS 倍率,
        crop    : VIS内クロップ矩形 (x0,y0,x1,y1),
        model   : "affine" or "similarity",
    )
    """
    H, W = ir_gray.shape
    irg, visg = _grad(ir_gray), _grad(vis_gray)

    # UIを避けて中央領域をテンプレートに
    tx0, ty0, tx1, ty1 = 90, 60, W - 40, H - 50
    tmpl = irg[ty0:ty1, tx0:tx1]

    best = None
    for s in np.linspace(1.0, 2.6, 65):
        tw, th = int(tmpl.shape[1] * s), int(tmpl.shape[0] * s)
        if tw >= vis_gray.shape[1] or th >= vis_gray.shape[0]:
            continue
        res = cv2.matchTemplate(
            visg, cv2.resize(tmpl, (tw, th), interpolation=cv2.INTER_AREA),
            cv2.TM_CCOEFF_NORMED)
        _, mx, _, mxloc = cv2.minMaxLoc(res)
        if best is None or mx > best[0]:
            best = (mx, s, mxloc)
    score, s, loc = best
    tvx, tvy = loc[0] - s * tx0, loc[1] - s * ty0
    Wm = np.array([[s, 0, tvx], [0, s, tvy]], np.float32)
    crop = (tvx, tvy, tvx + s * W, tvy + s * H)

    warp = np.eye(2, 3, dtype=np.float32)
    model = "similarity"
    if refine:
        vis_coarse = cv2.warpAffine(vis_gray, Wm, (W, H),
                                    flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        # UIマスク（1=使う）
        mask = np.ones((H, W), np.uint8)
        mask[:48, :] = 0
        mask[H - 42:, :] = 0
        mask[:, :80] = 0
        mask[:60, W - 170:] = 0
        valid = cv2.warpAffine(np.full(vis_gray.shape, 255, np.uint8), Wm, (W, H),
                               flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP)
        mask[valid == 0] = 0
        try:
            # 精密化は平行移動のみ（回転・せん断は物理的に無いので許さない）
            crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 500, 1e-7)
            _, warp = cv2.findTransformECC(irg, _grad(vis_coarse), warp,
                                           cv2.MOTION_TRANSLATION, crit, mask, 5)
            model = "similarity+shift"
        except cv2.error:
            warp = np.eye(2, 3, dtype=np.float32)
    return {"Wm": Wm, "warp": warp, "scale": float(s), "crop": crop,
            "score": float(score), "model": model, "size": (W, H)}


def warp_vis(vis_color: np.ndarray, reg: dict) -> np.ndarray:
    """カラーVISを IRフレーム(640x480)へ切り出し＋整列."""
    W, H = reg["size"]
    coarse = cv2.warpAffine(vis_color, reg["Wm"], (W, H),
                            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    fine = cv2.warpAffine(coarse, reg["warp"], (W, H),
                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    return fine


# ---------------------------------------------------------------- #
# 合成
# ---------------------------------------------------------------- #
def fusion_detail(thermal_color: np.ndarray, vis_aligned: np.ndarray,
                  amount: float = 0.7) -> np.ndarray:
    """熱カラーにVISの『高周波ディテール(陰影・質感)』だけを重ねる MSX風.

    VIS輝度をそのまま混ぜると（強い反射・影で）濁るので、高周波成分のみを
    抽出して熱カラーの明度(V)に加算する。色相・彩度は熱のまま＝温度情報を保持。
    """
    g = cv2.cvtColor(vis_aligned, cv2.COLOR_BGR2GRAY).astype(np.float32)
    detail = g - cv2.GaussianBlur(g, (0, 0), 4)      # 高周波(平均≒0)
    hsv = cv2.cvtColor(thermal_color, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 2] = np.clip(hsv[..., 2] + amount * detail, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


# ---------------------------------------------------------------- #
# 一括処理
# ---------------------------------------------------------------- #
def process(ir_jpeg: str, vis_jpeg: str, out_prefix: str,
            t_min: float | None = None, t_max: float | None = None,
            palette: str = "arctic", denoise: int = 35,
            html: bool = False, html_embed_js: bool = False) -> dict:
    """IR_jpeg(メーカー合成) と VIS_jpeg から, VISクロップ/合成画像を出力."""
    ir_gray = cv2.imread(ir_jpeg, cv2.IMREAD_GRAYSCALE)
    vis_color = cv2.imread(vis_jpeg, cv2.IMREAD_COLOR)
    vis_gray = cv2.cvtColor(vis_color, cv2.COLOR_BGR2GRAY)
    H, W = ir_gray.shape

    # 生ラジオメトリ → 表示用グレー（SuperIR風デノイズ＋2.5倍拡大）。
    # 生の2.5倍拡大はメーカー合成の熱層と恒等（実測: shift≈0, scale≈1.000, 回転なし）
    # なので余計な変換はかけない。VIS を合成に合わせれば熱と整合する。
    ext = HikmicroExtractor(ir_jpeg)
    ext.process_image()
    raw = ext.get_thermal_np()
    base = thermal_gray(raw, (W, H), denoise=denoise)
    thermal_color = apply_palette(base, palette)

    temperature_source = "raw_only"
    ocr_confidence: dict | None = None
    if t_min is not None and t_max is not None:
        temperature_source = "manual"
    else:
        ocr = read_scale_temperatures_with_confidence(ir_jpeg)
        if ocr["plausible"]:
            t_min, t_max = ocr["t_min"], ocr["t_max"]
            temperature_source = "ocr"
            ocr_confidence = {k: ocr[k] for k in
                              ("min_conf", "max_conf", "min_n", "max_n")}
            # アンカー誤読は画像全体をバイアスするため、弱い読みは黙って通さない
            if min(ocr["min_conf"], ocr["max_conf"]) < 0.5 or min(ocr["min_n"], ocr["max_n"]) < 2:
                print(f"[警告] OCR 温度アンカーの信頼度が低い: {os.path.basename(ir_jpeg)} "
                      f"min={t_min}(conf {ocr['min_conf']:.2f}/n{ocr['min_n']}) "
                      f"max={t_max}(conf {ocr['max_conf']:.2f}/n{ocr['max_n']}) "
                      f"→ --tmin/--tmax の手入力を検討")
        elif ocr["note"] not in ("ocr_incomplete", "image_unreadable"):
            print(f"[警告] OCR 温度アンカーが非妥当({ocr['note']}): "
                  f"{os.path.basename(ir_jpeg)} min={ocr['t_min']} max={ocr['t_max']} "
                  f"→ 較正なし(raw_only)で出力。手入力を検討")

    datetime_original = read_datetime_original(ir_jpeg)

    # 位置合わせ（VIS→合成画像=IRクロップ）。スケール＋平行移動のみ（回転・せん断なし）。
    reg = register_vis_to_ir(ir_gray, vis_gray, refine=True)
    vis_aligned = warp_vis(vis_color, reg)

    # 出力: 通常用途では可視光と合成画像の2枚だけで十分。
    outs = {}
    outs["visible"] = out_prefix + "_visible.png"
    outs["fusion"] = out_prefix + "_fusion.png"
    outs["metadata"] = out_prefix + "_metadata.json"
    if html:
        outs["thermal_html"] = out_prefix + "_thermal.html"
    cv2.imwrite(outs["visible"], vis_aligned)
    fused = fusion_detail(thermal_color, vis_aligned)
    fused = draw_temperature_legend(
        fused, palette, t_min, t_max, float(raw.min()), float(raw.max())
    )
    fused = draw_datetime(fused, datetime_original)
    cv2.imwrite(outs["fusion"], fused)

    if html:
        from .plotly_export import export_plotly_html

        temperature_c = None
        if t_min is not None and t_max is not None:
            temperature_c = ext.to_celsius(t_min, t_max)
        # HTML の背景は合成画像（外形エッジ重畳済み）。その上に透明な hover 格子を
        # 重ね、各画素の raw/温度をマウスオーバーで読めるようにする。
        export_plotly_html(
            raw,
            outs["thermal_html"],
            temperature_c=temperature_c,
            background_rgb=cv2.cvtColor(fused, cv2.COLOR_BGR2RGB),
            title=f"{palette} fusion (hover for temperature)",
            include_plotlyjs=True if html_embed_js else "cdn",
        )

    reg_report = {k: reg[k] for k in ("scale", "score", "model", "crop")}
    metadata = {
        "image_path": ir_jpeg,
        "visible_path": vis_jpeg,
        "outputs": outs,
        "raw_min": int(raw.min()),
        "raw_max": int(raw.max()),
        "t_min": t_min,
        "t_max": t_max,
        "temperature_source": temperature_source,
        "ocr_confidence": ocr_confidence,
        "calibration_model": "linear" if t_min is not None and t_max is not None else "raw_only",
        "datetime_original": datetime_original,
        "palette": palette,
        "denoise": denoise,
        "html": html,
        "registration": reg_report,
        "raw_shape": raw.shape,
    }
    write_metadata_json(outs["metadata"], metadata)
    return {"outputs": outs, "reg": reg_report, "raw_shape": raw.shape}


def process_all_palettes(ir_jpeg: str, vis_jpeg: str, out_dir: str,
                         denoise: int = 35) -> list:
    """全パレットで合成画像を出力（試し比較用）。out_dir に <画像名>_<palette>.png."""
    import os
    os.makedirs(out_dir, exist_ok=True)
    ir_gray = cv2.imread(ir_jpeg, cv2.IMREAD_GRAYSCALE)
    vis_color = cv2.imread(vis_jpeg, cv2.IMREAD_COLOR)
    vis_gray = cv2.cvtColor(vis_color, cv2.COLOR_BGR2GRAY)
    H, W = ir_gray.shape
    ext = HikmicroExtractor(ir_jpeg); ext.process_image()
    base = thermal_gray(ext.get_thermal_np(), (W, H), denoise=denoise)
    vis_aligned = warp_vis(vis_color, register_vis_to_ir(ir_gray, vis_gray))
    name = os.path.splitext(os.path.basename(ir_jpeg))[0]
    paths = []
    for pal in PALETTES:
        fd = fusion_detail(apply_palette(base, pal), vis_aligned)
        fp = os.path.join(out_dir, f"{name}_{pal}.png")
        cv2.imwrite(fp, fd)
        paths.append(fp)
    return paths


if __name__ == "__main__":
    import argparse, os
    p = argparse.ArgumentParser(description="VIS を IR にクロップ整列して自前合成")
    p.add_argument("ir", help="メーカー合成 IR JPEG (HM*.jpeg)")
    p.add_argument("vis", help="可視光 JPEG (HM*.VIS.jpeg)")
    p.add_argument("-o", "--out", default=None,
                   help="出力プレフィックス（省略時は hikmicro_extractor/output/ 直下）")
    p.add_argument("--palette", default="arctic",
                   choices=PALETTES, help="カラーマップ(FLIR風)")
    p.add_argument("--denoise", type=int, default=35,
                   help="SuperIR風デノイズ強度(0で無効, 35前後が目安)")
    p.add_argument("--tmin", type=float, default=None,
                   help="温度凡例の下端[degC]。未指定時は元JPEGの焼き込み表示をOCR")
    p.add_argument("--tmax", type=float, default=None,
                   help="温度凡例の上端[degC]。未指定時は元JPEGの焼き込み表示をOCR")
    p.add_argument("--html", action="store_true",
                   help="raw/温度をhover表示できる Plotly HTML も出力")
    p.add_argument("--html-embed-js", action="store_true",
                   help="Plotly JSをHTMLに埋め込む（ファイルは大きくなる）")
    p.add_argument("--showcase", action="store_true",
                   help="全パレットの一覧画像も出力")
    p.add_argument("--all-palettes", action="store_true",
                   help="全パレットで合成画像を output/palettes/ に個別出力")
    args = p.parse_args()
    module_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

    if args.all_palettes:
        pdir = os.path.join(module_out, "palettes")
        paths = process_all_palettes(args.ir, args.vis, pdir, denoise=args.denoise)
        for fp in paths:
            print(f"[出力] {fp}")
        raise SystemExit(0)

    # 生成物はソース画像フォルダを汚さず、モジュール直下の output/ に集約する
    if args.out:
        prefix = args.out
    else:
        os.makedirs(module_out, exist_ok=True)
        prefix = os.path.join(module_out, os.path.splitext(os.path.basename(args.ir))[0])
    r = process(args.ir, args.vis, prefix, t_min=args.tmin, t_max=args.tmax,
                palette=args.palette, denoise=args.denoise,
                html=args.html, html_embed_js=args.html_embed_js)
    print(f"[設定] palette={args.palette} denoise={args.denoise}")
    print("[位置合わせ]", r["reg"])
    for k, v in r["outputs"].items():
        print(f"[出力] {k}: {v}")

    if args.showcase:
        ir_gray = cv2.imread(args.ir, cv2.IMREAD_GRAYSCALE)
        vis_color = cv2.imread(args.vis, cv2.IMREAD_COLOR)
        vis_gray = cv2.cvtColor(vis_color, cv2.COLOR_BGR2GRAY)
        H, W = ir_gray.shape
        ext = HikmicroExtractor(args.ir); ext.process_image()
        raw = ext.get_thermal_np()
        base = thermal_gray(raw, (W, H), denoise=args.denoise)
        vis_aligned = warp_vis(vis_color, register_vis_to_ir(ir_gray, vis_gray))
        tiles = []
        for name in PALETTES:
            img = fusion_detail(apply_palette(base, name), vis_aligned)
            cv2.putText(img, name, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            tiles.append(img)
        while len(tiles) % 4: tiles.append(np.zeros_like(tiles[0]))
        rows = [np.hstack(tiles[i:i+4]) for i in range(0, len(tiles), 4)]
        sc = prefix + "_palettes.png"
        cv2.imwrite(sc, np.vstack(rows))
        print(f"[出力] palettes: {sc}")
