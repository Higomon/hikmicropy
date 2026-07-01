"""HIKMICRO Pocket2 サーモグラフィ JPEG から生ラジオメトリ配列を抽出するライブラリ.

FLIR の flir_image_extractor と同じ発想で、HIKMICRO Pocket2 が撮影した放射温度
JPEG に埋め込まれた「生センサ値（16bit）」を numpy 配列として取り出し、後解析
できるようにする。

--------------------------------------------------------------------------
ファイル構造（HIKMICRO Pocket2, 本リポジトリの実測でリバースエンジニアリング）
--------------------------------------------------------------------------
1 枚の *.jpeg は複数のデータを連結して持つ:

  [1] EXIF サムネイル JPEG
  [2] カラー化された表示用 IR JPEG（640x480, パレット/スケールバー焼き込み）
  [3] 可視光と位置合わせ用の埋め込み JPEG
  [4] "HDRI" ブロック  … ★これが生ラジオメトリ本体★
  [5] ZIP（tvfParam.dat = 温度較正パラメータ, AGC/DDE/DNR = 画像処理設定）

"HDRI" ブロックのヘッダ（先頭からのバイトオフセット, little-endian）:
  off 0  : b"HDRI"          マジック
  off 12 : uint32  width    センサ幅  = 256
  off 16 : uint32  height   センサ高  = 192
  off 20 : uint32  datasize  生データ領域のバイト数（= w*h*2 + 1024 の付加領域）
  off 44 : uint16[h*w]      生センサ値（row-major, little-endian, uint16）

--------------------------------------------------------------------------
生センサ値 → 絶対温度[℃] への較正
--------------------------------------------------------------------------
生センサ値そのものは「単純な固定小数点の温度」ではない（例: raw/16-273.15 は
実測と一致しない）。HIKMICRO は放射率・反射温度等を加味した独自の放射モデルで
絶対温度を計算し、その結果を表示用 IR 画像 [2] のスケールバー（例: 31.4℃〜
33.8℃）として焼き込む。

Pocket2 はオートレンジ（パレット下端 = シーン最小温度, 上端 = 最大温度）なので、

    T(℃) = t_min + (raw - raw_min) / (raw_max - raw_min) * (t_max - t_min)

の 2 点線形較正で、カメラ表示と一致する絶対温度が復元できる（数℃スパンなので
線形近似は十分正確, 2 つのアンカー点では厳密一致）。t_min / t_max は各画像の
スケールバー数値を渡す（EXIF には温度メタデータが無いため, 画面表示から読む）。

t_min / t_max を渡さない場合でも、生配列による「相対」解析（冷たい湿潤スポット
の検出 = 雨漏り診断など）は較正なしで可能。
"""

from __future__ import annotations

import struct
import zipfile
import io
from dataclasses import dataclass

import numpy as np


HDRI_MAGIC = b"HDRI"
# HDRI ヘッダ内フィールドのオフセット
_OFF_WIDTH = 12
_OFF_HEIGHT = 16
_OFF_DATASIZE = 20
_OFF_FRAME = 44  # 生 uint16 フレームの開始位置（マジックからの相対）


@dataclass
class HikThermal:
    """抽出結果を保持するコンテナ."""

    raw: np.ndarray          # 生センサ値 (H, W) uint16
    width: int
    height: int
    image_path: str

    @property
    def raw_min(self) -> int:
        return int(self.raw.min())

    @property
    def raw_max(self) -> int:
        return int(self.raw.max())


class HikmicroExtractor:
    """HIKMICRO Pocket2 サーモ JPEG の抽出器.

    使い方:
        ext = HikmicroExtractor("HM...115933.jpeg")
        ext.process_image()
        raw = ext.get_thermal_np()                 # 生 uint16 配列
        tc  = ext.to_celsius(t_min=31.4, t_max=33.8)  # 絶対温度[℃]
        ext.export_thermal_to_csv("out.csv")
        ext.plot("out.png", t_min=31.4, t_max=33.8)
    """

    def __init__(self, image_path: str):
        self.image_path = image_path
        self.thermal: HikThermal | None = None

    # ------------------------------------------------------------------ #
    # 抽出
    # ------------------------------------------------------------------ #
    def process_image(self) -> HikThermal:
        """JPEG を読み込み HDRI ブロックから生ラジオメトリ配列を取り出す."""
        with open(self.image_path, "rb") as f:
            data = f.read()

        pos = data.rfind(HDRI_MAGIC)
        if pos < 0:
            raise ValueError(
                "HDRI ブロックが見つかりません。HIKMICRO Pocket2 の"
                "放射温度 JPEG（サーモ画像）ではない可能性があります。"
            )

        width = struct.unpack_from("<I", data, pos + _OFF_WIDTH)[0]
        height = struct.unpack_from("<I", data, pos + _OFF_HEIGHT)[0]
        datasize = struct.unpack_from("<I", data, pos + _OFF_DATASIZE)[0]

        if not (0 < width <= 4096 and 0 < height <= 4096):
            raise ValueError(f"HDRI ヘッダの解像度が不正です: {width}x{height}")

        n_bytes = width * height * 2
        if n_bytes > datasize:
            raise ValueError(
                f"生データ領域({datasize}B)が解像度({width}x{height})に不足しています。"
            )

        frame_start = pos + _OFF_FRAME
        buf = data[frame_start:frame_start + n_bytes]
        if len(buf) < n_bytes:
            raise ValueError("生データが途中で切れています（ファイル破損）。")

        raw = np.frombuffer(buf, dtype="<u2").reshape(height, width)
        self.thermal = HikThermal(
            raw=raw.copy(), width=width, height=height, image_path=self.image_path
        )
        return self.thermal

    # ------------------------------------------------------------------ #
    # 取得系
    # ------------------------------------------------------------------ #
    def _ensure(self) -> HikThermal:
        if self.thermal is None:
            self.process_image()
        assert self.thermal is not None
        return self.thermal

    def get_thermal_np(self) -> np.ndarray:
        """生センサ値の numpy 配列 (H, W) uint16 を返す."""
        return self._ensure().raw

    def to_celsius(
        self,
        t_min: float,
        t_max: float,
        raw_min: float | None = None,
        raw_max: float | None = None,
    ) -> np.ndarray:
        """スケールバーの 2 点 (t_min, t_max)[℃] で生配列を絶対温度[℃]へ較正.

        Pocket2 のオートレンジでは パレット下端=シーン最小, 上端=最大 なので、
        既定では raw_min / raw_max にフレームの実測 min/max を用いる。手動レンジ
        撮影などで別の対応点が分かっている場合は raw_min / raw_max を明示する。
        """
        raw = self._ensure().raw.astype(np.float64)
        rmin = raw.min() if raw_min is None else float(raw_min)
        rmax = raw.max() if raw_max is None else float(raw_max)
        if rmax == rmin:
            return np.full_like(raw, (t_min + t_max) / 2.0)
        return t_min + (raw - rmin) / (rmax - rmin) * (t_max - t_min)

    # ------------------------------------------------------------------ #
    # 出力系
    # ------------------------------------------------------------------ #
    def export_thermal_to_csv(
        self, csv_path: str, t_min: float | None = None, t_max: float | None = None
    ) -> None:
        """温度配列を CSV 出力（FLIR extractor と同じ用途）.

        t_min / t_max を渡すと℃で、渡さないと生センサ値で出力する。
        """
        if t_min is not None and t_max is not None:
            arr = self.to_celsius(t_min, t_max)
            fmt = "%.2f"
        else:
            arr = self._ensure().raw
            fmt = "%d"
        np.savetxt(csv_path, arr, delimiter=",", fmt=fmt)

    def plot(
        self,
        save_path: str | None = None,
        t_min: float | None = None,
        t_max: float | None = None,
        cmap: str = "inferno",
    ):
        """ヒートマップを描画（save_path 指定時は Agg で保存, GUI を出さない）."""
        import matplotlib

        if save_path is not None:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if t_min is not None and t_max is not None:
            arr = self.to_celsius(t_min, t_max)
            label = "Temperature [degC]"
        else:
            arr = self._ensure().raw
            label = "Raw sensor value"

        fig, ax = plt.subplots(figsize=(8, 6))
        im = ax.imshow(arr, cmap=cmap)
        fig.colorbar(im, ax=ax, label=label)
        ax.set_title("HIKMICRO Pocket2 thermal")
        fig.tight_layout()
        if save_path is not None:
            fig.savefig(save_path, dpi=120)
            plt.close(fig)
        else:
            plt.show()
        return arr

    # ------------------------------------------------------------------ #
    # 相対解析（較正なしでも可能: 雨漏り診断など）
    # ------------------------------------------------------------------ #
    def find_cold_region(self, percentile: float = 2.0):
        """最も冷たい領域（雨漏りの湿潤・蒸発冷却スポット候補）の統計を返す.

        戻り値 dict:
          threshold : 下位 percentile% の生値しきい値
          n_pixels  : しきい値以下の画素数
          centroid  : (row, col) 冷点クラスタの重心
          raw_mean/raw_min : 生値統計
        """
        raw = self._ensure().raw.astype(np.float64)
        thr = np.percentile(raw, percentile)
        mask = raw <= thr
        ys, xs = np.nonzero(mask)
        centroid = (float(ys.mean()), float(xs.mean())) if len(ys) else (None, None)
        return {
            "threshold": float(thr),
            "n_pixels": int(mask.sum()),
            "centroid": centroid,
            "raw_min": float(raw.min()),
            "raw_mean": float(raw.mean()),
        }

    # ------------------------------------------------------------------ #
    # おまけ: 埋め込みパラメータ ZIP（tvfParam.dat 等）の取り出し
    # ------------------------------------------------------------------ #
    def extract_param_zip(self) -> dict[str, bytes]:
        """ファイル内に連結された ZIP を走査し {ファイル名: bytes} を返す."""
        with open(self.image_path, "rb") as f:
            data = f.read()
        result: dict[str, bytes] = {}
        i = 0
        while True:
            j = data.find(b"PK\x03\x04", i)
            if j < 0:
                break
            try:
                # 各 local header を単体 ZIP として読む
                method = struct.unpack_from("<H", data, j + 8)[0]
                csize = struct.unpack_from("<I", data, j + 18)[0]
                fnlen = struct.unpack_from("<H", data, j + 26)[0]
                eflen = struct.unpack_from("<H", data, j + 28)[0]
                name = data[j + 30:j + 30 + fnlen].decode("latin1")
                ds = j + 30 + fnlen + eflen
                comp = data[ds:ds + csize]
                if method == 0:
                    raw = comp
                else:
                    import zlib

                    raw = zlib.decompress(comp, -15)
                result[name] = raw
            except Exception:
                pass
            i = j + 4
        return result


# ---------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------- #
def _main() -> None:
    import argparse
    import os

    p = argparse.ArgumentParser(
        description="HIKMICRO Pocket2 サーモ JPEG から生ラジオメトリを抽出して解析"
    )
    p.add_argument("input", help="入力 JPEG（HIKMICRO Pocket2 サーモ画像）")
    p.add_argument("--tmin", type=float, default=None,
                   help="スケールバー下端の温度[℃]（画面表示から読む）")
    p.add_argument("--tmax", type=float, default=None,
                   help="スケールバー上端の温度[℃]（画面表示から読む, 例: Max の値）")
    p.add_argument("--csv", action="store_true", help="温度/生値 CSV を出力")
    p.add_argument("--png", action="store_true", help="ヒートマップ PNG を出力")
    args = p.parse_args()

    ext = HikmicroExtractor(args.input)
    t = ext.process_image()
    print(f"[抽出] {os.path.basename(args.input)}  解像度 {t.width}x{t.height}")
    print(f"[生値] min={t.raw_min}  max={t.raw_max}  mean={t.raw.mean():.1f}  span={t.raw_max - t.raw_min}")

    if args.tmin is not None and args.tmax is not None:
        tc = ext.to_celsius(args.tmin, args.tmax)
        print(f"[較正] スケールバー {args.tmin}〜{args.tmax}℃ で 2 点線形較正")
        print(f"[温度] min={tc.min():.2f}℃  max={tc.max():.2f}℃  mean={tc.mean():.2f}℃")

    cold = ext.find_cold_region()
    cy, cx = cold["centroid"]
    print(f"[冷点] 下位2%画素={cold['n_pixels']}  重心(row,col)=({cy:.0f},{cx:.0f})"
          " ← 雨漏り湿潤スポット候補")

    # 生成物はソース画像フォルダを汚さず、モジュール直下の output/ に集約する
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, os.path.splitext(os.path.basename(args.input))[0])
    if args.csv:
        out = base + "_thermal.csv"
        ext.export_thermal_to_csv(out, args.tmin, args.tmax)
        print(f"[出力] CSV -> {out}")
    if args.png:
        out = base + "_thermal.png"
        ext.plot(out, args.tmin, args.tmax)
        print(f"[出力] PNG -> {out}")


if __name__ == "__main__":
    _main()
