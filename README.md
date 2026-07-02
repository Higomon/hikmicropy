# hikmicropy

**日本語** ・ [English](README.en.md)

HIKMICRO Pocket2 の放射測定 JPEG から画素ごとの温度データを抽出し、可視画像と位置合わせした
合成画像・対話的な温度マップを生成する Python パッケージである。

## こんなときに

- 撮影後でも、画像上の**任意点の温度**を知りたい。
- **メーカーロゴが入った画像**を使いたくない。

hikmicropy は画素ごとの温度を保持するため、撮影後に任意点の温度を確認でき（対話的 HTML で
ホバー）、ロゴや UI を含まない画像を出力する。

## ⚠️ 必須：可視光画像の出力

**撮影前に、カメラ本体で可視光画像の保存を有効にすること。**

出力ファイル例

- IR画像 … `HM****.jpeg`
- 可視光画像 … `HM****.VIS.jpeg`

これがないと合成画像を生成できない。

## 概要

HIKMICRO Pocket2 が保存する `HM****.jpeg` には、表示用の画像に加えて画素ごとの生センサ値
（放射測定データ）が埋め込まれている。生値はそのままでは温度ではないため、本ツールは生値を
抽出し、画像ごとの Max / Min 温度へ合わせて℃へ較正する。壁面などの相対的に低温な領域（例:
雨漏りによる含水部）の検出を主な用途に想定する。

## 出力例

`process` は **可視光画像と合成画像を対で出力する**。合成画像は温度カラーマップに
可視画像の外形エッジを重ねたもので、構造とともに温度分布を判読できる。

カメラ内蔵の書き出しとの違いは次の通りである。

![メーカー標準出力と hikmicropy 合成出力の比較](docs/images/manufacturer_vs_hikmicropy.ja.png)

合成前の IR のみ画像では温度分布は読めるが、部材の境界や汚れ・目地などの構造は判読しにくい。
可視画像由来の外形エッジを重ねることで、温度分布を構造と対応づけて見られる。

| 可視光（IR 画角に整列） | IRのみ（温度カラー） |
|---|---|
| ![visible](samples/example_visible.png) | ![IRのみ](samples/example_thermal.png) |

`--html` 指定時は、合成画像を背景にした Plotly HTML も出力できる。画像上をマウスオーバーすると、
近傍画素の推定温度と生値がツールチップで表示される。

![Plotly HTML の温度 hover 表示](docs/images/plotly_hover.gif)

## 主な機能

- 放射測定 JPEG から**生センサ値（256×192, `uint16`）**を抽出する。
- 写真の温度目盛り（Max/Min）を用いた**画像ごとの2点線形較正**で℃へ変換する。
- 可視画像を IR 画角へ整列（拡大・平行移動のみ、回転なし）し、**外形エッジを重ねる**。
- **可視光画像と合成画像を同時に出力**する（合成には可視画像が必要）。
- **カラーパレットを選択可能**（既定は含水部を青系で示す `arctic`）。
- **合成画像を背景とする対話的 HTML（Plotly）を出力**し、**任意点をマウスオーバーすると
  その画素の推定温度と生値を表示**する。
- 処理メタデータ（較正の由来・OCR 一致度を含む）を JSON で記録する。
- 出力画像に**メーカーロゴを含まない**。

## カラーパレット

`--palette` で選択する。含水部（低温部）を強調するには既定の `arctic` が適する。

![パレット一覧](docs/images/palettes.ja.png)

## インストール

依存はすべて Windows・macOS・Linux 共通であり、**プラットフォームごとに異なる環境定義は不要**である。

### conda

```bash
conda env create -f environment.yml   # 3 OS 共通
conda activate hikmicropy
pip install -e .
```

### pip

```bash
pip install -e .            # コア
pip install -e ".[viz]"     # + matplotlib（HikmicroExtractor.plot 用、任意）
```

## 使い方

```bash
# 可視光を伴う1組を処理（合成・可視光・メタデータ・HTML を出力）
hikmicropy process IR.jpeg IR.VIS.jpeg --palette arctic --out-dir output --html

# フォルダを一括処理（HM*.jpeg と HM*.VIS.jpeg を自動で対応付け）
hikmicropy batch ./photos --palette arctic --out-dir output --html

# IR 1枚から CSV / HTML を出力（可視光不要。ただし合成は生成されない）
hikmicropy export IR.jpeg --tmin 31.4 --tmax 33.8 --csv --html
```

`process` は1組につき `*_fusion.png`（合成画像）・`*_visible.png`・`*_metadata.json` を出力し、`--html` 指定時は
`*_thermal.html` を加える。**外形エッジ付きの合成画像を得るには可視光画像（`*.VIS.jpeg`）が
必須**であり、可視光がない場合は `export`（CSV/HTML のみ）を用いる。

## Python API

```python
from hikmicropy import HikmicroExtractor, process

ext = HikmicroExtractor("IR.jpeg")
raw = ext.get_thermal_np()                        # (192, 256) uint16
temp_c = ext.to_celsius(t_min=31.4, t_max=33.8)   # ℃

process("IR.jpeg", "IR.VIS.jpeg", "output/scene01", palette="arctic", html=True)
```

## 温度較正の位置づけ

生値は℃ではない。本ツールは**画像ごとにその画像の目盛り（Max/Min）へ合わせる2点線形較正**を行う。

```
T(℃) = t_min + (raw − raw_min) / (raw_max − raw_min) × (t_max − t_min)
```

- **較正は画像ごとに必要である。** 全画像に共通する単一の変換式は成立しない。撮影ごとにセンサの
  基準値が変動し、同一の生値が画像によって異なる温度に対応するためである。
- **2つの目盛り点は厳密に一致するが、その間の画素の精度は未検証である。** 数℃程度の範囲では線形
  近似が妥当と見込まれるが、厳密な数値化には既知温度の基準体または解析ソフトの CSV を要する。
- 本較正はメーカー公式の放射測定式ではない。

温度目盛りは `--tmin/--tmax`（推奨）または OCR で与える。

## Tesseract（OCR 自動読み取りに必要）

温度目盛りを OCR で自動読み取りするには、Tesseract 本体が必要である。

![温度目盛り（凡例カラーバー）](docs/images/scale_bar.ja.png)

**温度目盛り**とは、メーカー標準出力画像の左にある凡例カラーバーとその Max / Min 値を指す。
OCR はこの表示を読み取り、生値から℃への2点線形較正に使う。

| OS | 導入方法 |
|---|---|
| Windows | `conda install -c conda-forge tesseract`、または UB Mannheim 版インストーラ |
| macOS | `brew install tesseract` |
| Linux | `apt install tesseract-ocr` 等 |

Tesseract がない場合は `--tmin/--tmax` で温度目盛りを手入力する。定量用途では手入力を推奨する。
OCR は **Pocket2 の表示レイアウトを前提**とするため他機種・他解像度では失敗しうる。記録される
`ocr_confidence` は OCR の読み取り一致度であり、温度の正しさそのものを保証するものではない。

## ライセンス

MIT（`LICENSE` を参照）。
