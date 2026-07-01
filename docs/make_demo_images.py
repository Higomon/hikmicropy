"""README 用のデモ画像を合成データから生成する（現場の実測画像は使わない）.

出力:
  docs/images/overview.png   機能概要（raw → 温度カラー化 → 冷点検出）の3ステップ図
  docs/images/palettes.png   7 つのカラーパレット一覧

実行:
  python docs/make_demo_images.py

注意: 日本語ラベルの描画に CJK フォントが要る（macOS の Hiragino 等を優先使用）。
Linux/CI で再生成するとフォント次第で日本語が □ 化することがある（同梱済み画像は生成済み）。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # GUI を出さない
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from hikmicropy import fusion

OUT = Path(__file__).resolve().parent / "images"
OUT.mkdir(parents=True, exist_ok=True)

H, W = 192, 256


def synthetic_scene() -> np.ndarray:
    """雨漏り壁を模した合成温度場[℃]（下がった冷点＝濡れ候補、上に暖かい領域）."""
    yy, xx = np.mgrid[0:H, 0:W]
    T = 27.0 + 0.004 * (H - yy)                       # 壁の緩い温度勾配
    T += 4.5 * np.exp(-(((xx - 200) / 45) ** 2 + ((yy - 55) / 40) ** 2))   # 暖かい領域
    T -= 6.5 * np.exp(-(((xx - 95) / 38) ** 2 + ((yy - 125) / 30) ** 2))   # 冷たい濡れ patch
    T -= 3.0 * np.exp(-(((xx - 155) / 20) ** 2 + ((yy - 150) / 18) ** 2))  # 小さな湿り
    T += 0.35 * np.sin(yy / 9.0)                      # 目地のような微構造
    rng = np.random.default_rng(7)
    T += rng.normal(0.0, 0.22, (H, W))
    return T


def to_u8(T: np.ndarray) -> np.ndarray:
    return ((T - T.min()) / (T.max() - T.min()) * 255).astype(np.uint8)


def palette_rgb(u8: np.ndarray, name: str) -> np.ndarray:
    """apply_palette は BGR を返すので matplotlib 用に RGB へ変換."""
    bgr = fusion.apply_palette(u8, name)
    return bgr[:, :, ::-1]


def arctic_cmap() -> ListedColormap:
    # apply_palette と同じ経路で 0..255 ランプを着色して colormap 化する
    # （_LUTS を直接使うと BGR/並びの差で色が反転するため）。
    ramp = np.arange(256, dtype=np.uint8).reshape(1, 256)
    rgb = fusion.apply_palette(ramp, "arctic")[0][:, ::-1] / 255.0  # BGR→RGB, (256,3)
    return ListedColormap(rgb)


def make_overview(T: np.ndarray) -> None:
    u8 = to_u8(T)
    tmin, tmax = float(T.min()), float(T.max())
    # 最も冷たい領域（雨漏り濡れ候補）の重心
    thr = np.percentile(T, 2)
    ys, xs = np.nonzero(T <= thr)
    cy, cx = ys.mean(), xs.mean()

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.9))
    fig.suptitle("hikmicropy: サーモ写真から「温度」と「濡れ（冷点）」を取り出す",
                 fontsize=14, fontweight="bold")

    axes[0].imshow(u8, cmap="gray")
    axes[0].set_title("① 生データ（そのままでは温度不明）", fontsize=11)

    cmap = arctic_cmap()
    im = axes[1].imshow(T, cmap=cmap, vmin=tmin, vmax=tmax)
    axes[1].set_title("② 温度に変換して色分け（℃）", fontsize=11)
    cbar = fig.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04)
    cbar.set_label("温度 [℃]")

    axes[2].imshow(T, cmap=cmap, vmin=tmin, vmax=tmax)
    circ = plt.Circle((cx, cy), 34, fill=False, color="black", lw=2.4)
    axes[2].add_patch(circ)
    axes[2].annotate("冷点＝濡れ候補",
                     xy=(cx, cy - 30), xytext=(cx + 8, max(24, cy - 92)),
                     color="black", fontsize=11, fontweight="bold", ha="center",
                     bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85),
                     arrowprops=dict(arrowstyle="->", color="black", lw=1.8))
    axes[2].set_title("③ いちばん冷たい所を自動で強調", fontsize=11)

    for ax in axes:
        ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / "overview.png", dpi=130)
    plt.close(fig)


def make_palettes(T: np.ndarray) -> None:
    u8 = to_u8(T)
    names = fusion.PALETTES
    ncol = 4
    nrow = (len(names) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(12.5, 3.2 * nrow))
    fig.suptitle("カラーパレット（--palette で選択）", fontsize=14, fontweight="bold")
    axes = axes.ravel()
    for ax, name in zip(axes, names):
        ax.imshow(palette_rgb(u8, name))
        label = f"{name}  （既定）" if name == "arctic" else name
        ax.set_title(label, fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
    for ax in axes[len(names):]:
        ax.axis("off")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / "palettes.png", dpi=130)
    plt.close(fig)


def _set_jp_font() -> None:
    # 日本語ラベルの豆腐(□)化を避ける。無ければ既定のまま（英字は出る）。
    for cand in ("Hiragino Sans", "Hiragino Maru Gothic Pro", "YuGothic",
                 "Noto Sans CJK JP", "Apple SD Gothic Neo"):
        try:
            plt.rcParams["font.family"] = cand
            from matplotlib.font_manager import findfont, FontProperties
            findfont(FontProperties(family=cand), fallback_to_default=False)
            plt.rcParams["axes.unicode_minus"] = False
            return
        except Exception:
            continue


def main() -> None:
    _set_jp_font()
    T = synthetic_scene()
    make_overview(T)
    make_palettes(T)
    print("wrote:", OUT / "overview.png", "/", OUT / "palettes.png")


if __name__ == "__main__":
    main()
