"""Generate README demo images (synthetic data only).

Produces language-matched color-palette galleries and a Plotly hover GIF. Uses a
synthetic thermal field, so no field imagery or absolute paths are referenced.

Run:
  python docs/make_demo_images.py

Note: the Japanese figure needs a CJK font (Hiragino on macOS is preferred). On Linux/CI
the Japanese title may render as tofu (□) depending on installed fonts; the committed
images are already generated. The hover GIF additionally needs Playwright with a Chromium
browser installed; if unavailable, the script skips that GIF.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import matplotlib

matplotlib.use("Agg")  # no GUI window
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw

from hikmicropy import fusion
from hikmicropy.plotly_export import export_plotly_html

OUT = Path(__file__).resolve().parent / "images"
OUT.mkdir(parents=True, exist_ok=True)

H, W = 192, 256

TITLES = {
    "ja": "カラーパレット（--palette で選択）",
    "en": "Color palettes (choose with --palette)",
}
DEFAULT_TAG = {"ja": "（既定）", "en": "(default)"}
HOVER_GIF = OUT / "plotly_hover.gif"
HOVER_POINTS = [(180, 370), (350, 260), (535, 165), (610, 420)]


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


def make_hover_background(u8: np.ndarray) -> np.ndarray:
    """Synthetic detail-composite background for the Plotly hover GIF."""
    bg = Image.fromarray(palette_rgb(u8, "arctic")).resize(
        (W * 3, H * 3), Image.Resampling.BICUBIC
    )
    draw = ImageDraw.Draw(bg, "RGBA")
    for off in (80, 180, 290, 420):
        draw.line([(0, off), (W * 3, off + 40)], fill=(255, 255, 255, 45), width=3)
        draw.line([(0, off + 6), (W * 3, off + 46)], fill=(0, 0, 0, 45), width=2)
    return np.array(bg)


def draw_cursor(frame: Image.Image, x: int, y: int) -> None:
    """Draw a small cursor because browser screenshots do not include one."""
    draw = ImageDraw.Draw(frame, "RGBA")
    shape = [
        (x, y),
        (x + 2, y + 24),
        (x + 8, y + 18),
        (x + 14, y + 31),
        (x + 20, y + 28),
        (x + 14, y + 16),
        (x + 23, y + 16),
    ]
    draw.polygon(shape, fill=(255, 255, 255, 245))
    draw.line(shape + [shape[0]], fill=(20, 20, 20, 245), width=2)


def make_plotly_hover_gif(temp_c: np.ndarray, u8: np.ndarray) -> None:
    """Render the real Plotly HTML hover state and save it as an animated GIF."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - docs-only optional dependency
        print(f"skipped {HOVER_GIF}: Playwright is unavailable ({exc})")
        return

    raw = (4300 + (temp_c - temp_c.min()) / (temp_c.max() - temp_c.min()) * 900).astype(
        np.float64
    )
    background_rgb = make_hover_background(u8)

    frames: list[Image.Image] = []
    try:
        with TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "plotly_hover.html"
            export_plotly_html(
                raw,
                html_path,
                temperature_c=temp_c,
                background_rgb=background_rgb,
                title="Plotly HTML hover demo",
                include_plotlyjs=True,
            )

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport={"width": 760, "height": 560},
                    device_scale_factor=1,
                )
                page.goto(html_path.as_uri(), wait_until="load")
                page.wait_for_selector(".plot-container", timeout=10_000)
                page.wait_for_timeout(800)

                for x, y in HOVER_POINTS:
                    page.mouse.move(x, y)
                    page.wait_for_timeout(500)
                    shot = page.screenshot(full_page=False)
                    frame = Image.open(BytesIO(shot)).convert("RGBA")
                    draw_cursor(frame, x, y)
                    frames.append(frame.convert("RGB"))

                browser.close()
    except Exception as exc:  # pragma: no cover - docs-only optional dependency
        print(f"skipped {HOVER_GIF}: browser rendering failed ({exc})")
        return

    palette_frames = [
        frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=96)
        for frame in frames
    ]
    palette_frames[0].save(
        HOVER_GIF,
        save_all=True,
        append_images=palette_frames[1:],
        duration=[900] * len(palette_frames),
        loop=0,
        optimize=True,
    )
    print("wrote:", HOVER_GIF)


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
    temp_c = synthetic_scene()
    u8 = to_u8(temp_c)
    for lang in ("ja", "en"):
        make_palettes(u8, lang)
    make_plotly_hover_gif(temp_c, u8)
    print("wrote:", OUT / "palettes.ja.png", "/", OUT / "palettes.en.png")


if __name__ == "__main__":
    main()
