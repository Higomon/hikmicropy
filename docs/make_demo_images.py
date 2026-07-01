"""Generate the color-palette gallery used in the README (synthetic data only).

Produces a Japanese-titled and an English-titled version so each README can embed
a language-matched figure. Uses a synthetic thermal field, so no field imagery or
absolute paths are referenced.

Run:
  python docs/make_demo_images.py

Note: the Japanese figure needs a CJK font (Hiragino on macOS is preferred). On Linux/CI
the Japanese title may render as tofu (□) depending on installed fonts; the committed
images are already generated.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no GUI window
import matplotlib.pyplot as plt
import numpy as np

from hikmicropy import fusion

OUT = Path(__file__).resolve().parent / "images"
OUT.mkdir(parents=True, exist_ok=True)

H, W = 192, 256

TITLES = {
    "ja": "カラーパレット（--palette で選択）",
    "en": "Color palettes (choose with --palette)",
}
DEFAULT_TAG = {"ja": "（既定）", "en": "(default)"}


def synthetic_scene() -> np.ndarray:
    """A synthetic wall-like thermal field with a cold (damp) region and a warm region."""
    yy, xx = np.mgrid[0:H, 0:W]
    T = 27.0 + 0.004 * (H - yy)
    T += 4.5 * np.exp(-(((xx - 200) / 45) ** 2 + ((yy - 55) / 40) ** 2))
    T -= 6.5 * np.exp(-(((xx - 95) / 38) ** 2 + ((yy - 125) / 30) ** 2))
    T -= 3.0 * np.exp(-(((xx - 155) / 20) ** 2 + ((yy - 150) / 18) ** 2))
    T += 0.35 * np.sin(yy / 9.0)
    rng = np.random.default_rng(7)
    T += rng.normal(0.0, 0.22, (H, W))
    return T


def to_u8(T: np.ndarray) -> np.ndarray:
    return ((T - T.min()) / (T.max() - T.min()) * 255).astype(np.uint8)


def palette_rgb(u8: np.ndarray, name: str) -> np.ndarray:
    return fusion.apply_palette(u8, name)[:, :, ::-1]  # BGR -> RGB


def make_palettes(u8: np.ndarray, lang: str) -> None:
    names = fusion.PALETTES
    ncol = 4
    nrow = (len(names) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(12.5, 3.2 * nrow))
    fig.suptitle(TITLES[lang], fontsize=14, fontweight="bold")
    axes = axes.ravel()
    for ax, name in zip(axes, names):
        ax.imshow(palette_rgb(u8, name))
        label = f"{name}  {DEFAULT_TAG[lang]}" if name == "arctic" else name
        ax.set_title(label, fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
    for ax in axes[len(names):]:
        ax.axis("off")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / f"palettes.{lang}.png", dpi=130)
    plt.close(fig)


def _set_jp_font() -> None:
    from matplotlib.font_manager import FontProperties, findfont

    for cand in ("Hiragino Sans", "Hiragino Maru Gothic Pro", "YuGothic",
                 "Noto Sans CJK JP", "Apple SD Gothic Neo"):
        try:
            findfont(FontProperties(family=cand), fallback_to_default=False)
            plt.rcParams["font.family"] = cand
            plt.rcParams["axes.unicode_minus"] = False
            return
        except Exception:
            continue


def main() -> None:
    _set_jp_font()
    u8 = to_u8(synthetic_scene())
    for lang in ("ja", "en"):
        make_palettes(u8, lang)
    print("wrote:", OUT / "palettes.ja.png", "/", OUT / "palettes.en.png")


if __name__ == "__main__":
    main()
