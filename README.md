# hikmicropy

Extract, fuse, and analyze **HIKMICRO Pocket2 radiometric JPEG** images in Python.

HIKMICRO Pocket2 saves a single `HM*.jpeg` that concatenates several payloads. `hikmicropy`
reverse-engineers the trailing `HDRI` block to recover the raw radiometric sensor array
(256×192 `uint16`), aligns the visual image to the thermal frame, renders FLIR-style fusion
images (default `arctic`, good for water-leak inspection), and exports an interactive Plotly
heatmap you can hover to read temperatures.

## Features

- Extract the embedded `HDRI` raw thermal array (256×192 `uint16`) from a HIKMICRO radiometric JPEG.
- Per-image two-point linear temperature calibration from the camera-rendered scale bar.
- Crop and align the visual image to the IR frame (scale + translation only; no false rotation).
- FLIR-style color palettes (`arctic`, `ironbow`, `lava`, ...) with visual-detail fusion.
- Temperature legend + capture timestamp burned onto the fusion image.
- Interactive Plotly HTML heatmap with raw / temperature hover values.
- Processing metadata (including OCR confidence) written as JSON.

## Install

### conda

```bash
conda env create -f environment.yml
conda activate hikmicropy
pip install -e .
```

### pip

```bash
pip install -e .            # core
pip install -e ".[viz]"     # + matplotlib for HikmicroExtractor.plot()
```

### Tesseract (optional, for OCR)

Reading the burned-in scale bar with OCR needs the Tesseract binary:

```bash
brew install tesseract      # macOS
```

OCR is optional. For quantitative work, prefer passing `--tmin/--tmax` manually (see below).

## CLI

```bash
# One IR/VIS pair
hikmicropy process HM..._IR.jpeg HM..._IR.VIS.jpeg --palette arctic --out-dir output --html

# A whole folder (auto-pairs HM*.jpeg with HM*.VIS.jpeg)
hikmicropy batch ./photos --palette arctic --out-dir output --html

# CSV / HTML from a single IR image (no VIS needed)
hikmicropy export HM..._IR.jpeg --tmin 31.4 --tmax 33.8 --csv --html
```

Outputs per image: `*_fusion.png`, `*_visible.png`, `*_metadata.json`, and (with `--html`)
`*_thermal.html`.

## Python API

```python
from hikmicropy import HikmicroExtractor, process

# Raw array + calibrated temperature
ext = HikmicroExtractor("HM..._IR.jpeg")
raw = ext.get_thermal_np()                 # (192, 256) uint16
temp_c = ext.to_celsius(t_min=31.4, t_max=33.8)   # degC

# Full fusion + metadata (+ optional Plotly HTML)
process("HM..._IR.jpeg", "HM..._IR.VIS.jpeg", "output/scene01",
        palette="arctic", html=True)
```

## Temperature calibration — read this

The raw `HDRI` values are **not** degrees Celsius. HIKMICRO computes temperature with a
proprietary radiometric model and burns the resulting scale-bar range (e.g. `31.4–33.8 °C`)
into the display image. `hikmicropy` recovers degrees with a **per-image two-point linear
calibration**, anchoring each frame to its own scale-bar `t_min/t_max`:

```
T(°C) = t_min + (raw - raw_min) / (raw_max - raw_min) * (t_max - t_min)
```

Key facts (measured, see "Notes on accuracy"):

- **Calibration must be per-image.** A single global `raw → °C` formula does **not** work:
  the raw sensor baseline drifts from shot to shot, so the same raw value maps to different
  temperatures in different frames. Re-anchoring each frame to its own scale bar absorbs that.
- **Anchors are exact; the in-between is expected-good but unmeasured.** The two anchors match
  the camera exactly by construction. Accuracy for pixels *between* the anchors (intra-image
  linearity) is physically expected to be excellent over a few-degree span but is not yet
  measured — it needs ≥3 known temperatures in one frame.
- This is not a manufacturer-published radiometric formula. No public per-pixel formula for the
  Pocket2 JPEG was found.

### Getting `t_min/t_max`

1. **Manual (recommended for quantitative use):** pass `--tmin/--tmax` read from the image.
2. **OCR (convenience):** if omitted, `hikmicropy` OCRs the burned-in scale bar. This is fitted
   to the **Pocket2 overlay layout** and may miss on other models/resolutions, in which case it
   falls back to uncalibrated raw. The recorded `ocr_confidence` is the **OCR agreement ratio**,
   not a measure of temperature correctness (a consistent misread can still score 1.0).

### Validating accuracy (optional)

- `hikmicropy.calibration` can compare the extracted raw against a **HIKMICRO Analyzer** per-pixel
  temperature CSV and report RMSE / max error.
- Without Analyzer, put **two known-temperature reference bodies** (e.g. ice water ≈ 0 °C and a
  measured warm object) in one frame to obtain ≥3 known temperatures and check intra-image linearity.

## Tests

```bash
pytest -q
```

Core extraction and calibration are tested against a synthetic HDRI fixture (no field images
required). OCR logic is tested with mocked candidates, so Tesseract is not needed for the suite.

## License

MIT. See `LICENSE`.
