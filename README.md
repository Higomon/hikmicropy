# hikmicropy

**日本語** ・ [English](README.en.md)

**HIKMICRO Pocket2 のサーモ写真から「温度」を取り出して、見やすく色分け・解析する Python ツールです。**

サーモカメラ HIKMICRO Pocket2 で撮った写真（`HM****.jpeg`）には、見た目の画像だけでなく
**1画素ごとの温度のもと（生データ）が隠れて入っています**。hikmicropy はそれを取り出し、
本物の温度[℃]に直し、色分け画像やマウスでなぞって温度を読めるグラフにします。
雨漏り診断のように「まわりより冷たい＝濡れている所」を探す用途に向いています。

![機能概要](docs/images/overview.png)

## これは何をするもの？（3ステップ）

1. **① 生データを取り出す** — 写真の中に埋め込まれた温度のもと（256×192 の数値）を読み出します。そのままでは温度が分かりません。
2. **② 温度に変換して色分け** — カメラが写真に焼き込んだ目盛り（Max/Min ℃）を使って、各画素を本物の温度[℃]に直し、色で見やすくします。
3. **③ 冷たい所を強調** — いちばん冷たい部分（雨漏りの濡れ候補など）を自動で見つけて示します。

## できること

- サーモ写真から**生の温度データ（256×192）**を取り出す
- **本物の温度[℃]**に変換（写真の目盛りを使った1枚ごとの2点補正）
- 可視光写真をサーモの画角にぴったり重ねて、**輪郭くっきりの合成画像**を作る
- **色（パレット）を選べる**（雨漏り向けは冷たい所が青く見える `arctic` が既定）
- **マウスでなぞると温度が出る**グラフ（HTML）を書き出す
- 処理結果を JSON で記録

## 色（パレット）の例

`--palette` で見た目を選べます。冷たい所（濡れ候補）を目立たせたいなら既定の `arctic` が分かりやすいです。

![カラーパレット一覧](docs/images/palettes.png)

## インストール

### conda（おすすめ）

```bash
conda env create -f environment.yml
conda activate hikmicropy
pip install -e .
```

### pip

```bash
pip install -e .
```

### 目盛りの自動読み取り（OCR）を使う場合だけ

写真に焼き込まれた温度目盛りを自動で読むには Tesseract が必要です（任意）。

```bash
brew install tesseract      # macOS
```

OCR がなくても、温度は `--tmin/--tmax` で手入力できます（**正確さを重視するなら手入力がおすすめ**）。

## 使い方（コマンド）

```bash
# サーモ写真1枚 + 可視光1枚を処理（合成画像・温度・HTMLを出力）
hikmicropy process サーモ.jpeg サーモ.VIS.jpeg --palette arctic --out-dir output --html

# フォルダごと一括（HM*.jpeg と HM*.VIS.jpeg を自動でペアにします）
hikmicropy batch ./写真フォルダ --palette arctic --out-dir output --html

# サーモ写真1枚から CSV / HTML だけ出す（可視光なしでOK）
hikmicropy export サーモ.jpeg --tmin 31.4 --tmax 33.8 --csv --html
```

1枚につき `*_fusion.png`（合成画像）、`*_visible.png`（重ねた可視光）、`*_metadata.json`、
`--html` を付けると `*_thermal.html`（なぞって温度が読めるグラフ）が出ます。

## Python から使う

```python
from hikmicropy import HikmicroExtractor, process

# 生データと温度
ext = HikmicroExtractor("サーモ.jpeg")
raw = ext.get_thermal_np()                        # (192, 256) の生データ
temp_c = ext.to_celsius(t_min=31.4, t_max=33.8)   # ℃

# 合成画像・温度・HTML まで一気に
process("サーモ.jpeg", "サーモ.VIS.jpeg", "output/scene01", palette="arctic", html=True)
```

## 温度の見方と注意（大切）

生データはそのままでは℃ではありません。hikmicropy は**写真1枚ごとに、その写真の目盛り
（Max/Min ℃）に合わせて温度へ直します**。ここは正直に書いておきます。

- **1枚ごとの補正が必要です。** 「全部の写真に使える1つの計算式」は作れません。撮影ごとに
  センサーの基準がわずかにずれるため、同じ生の値でも写真によって温度が違います。だから
  各写真の目盛りに合わせ直します。
- **目盛りの2点はぴったり合いますが、その間の細かい正確さは未検証です。** 数℃の範囲なら
  ほぼ問題ない見込みですが、厳密な数値化には別の検証（既知温度の基準体や解析ソフトの
  CSV）が要ります。
- これはメーカー公式の温度変換式ではありません。

### 温度目盛り（Max/Min）の入れ方

1. **手入力（正確さ重視ならこちら）:** 写真に写っている値を `--tmin/--tmax` で渡します。
2. **OCR（お手軽）:** 省略するとカメラが焼き込んだ目盛りを自動で読みます。ただし
   **Pocket2 の表示レイアウト前提**なので、他機種・他解像度では外すことがあり、その時は
   温度なし（生データのみ）に切り替わります。記録される `ocr_confidence` は「OCR の読みの
   一致度」であって、温度の正しさそのものではありません。

## テスト

```bash
pytest -q
```

実測の現場写真は同梱していません。抽出・較正のテストは合成データで行い、OCR はモックで
検証するので、Tesseract がなくてもテストは通ります。

## ライセンス

MIT（`LICENSE` を参照）。
