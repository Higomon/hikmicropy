"""フォルダ内の HIKMICRO ペアを一括処理する例.

使い方:
    python examples/batch_process.py <入力フォルダ> <出力フォルダ> [パレット]

<入力フォルダ> 内の HM*.jpeg（IR）と HM*.VIS.jpeg（可視光）を自動ペアリングし、
arctic 合成画像・可視光整列画像・metadata・Plotly HTML を出力する。
CLI `hikmicropy batch` と同等。ライブラリ API の利用例として置いている。
"""

from __future__ import annotations

import sys
from pathlib import Path

from hikmicropy import process


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    palette = sys.argv[3] if len(sys.argv) > 3 else "arctic"
    out_dir.mkdir(parents=True, exist_ok=True)

    irs = sorted(p for p in src.glob("HM*.jpeg") if not p.name.endswith(".VIS.jpeg"))
    missing = []
    for ir in irs:
        vis = ir.with_name(ir.stem + ".VIS.jpeg")
        if not vis.exists():
            missing.append(ir.name)
            continue
        process(str(ir), str(vis), str(out_dir / ir.stem), palette=palette, html=True)
        print("done:", ir.name)
    if missing:
        print("VIS 欠落でスキップ:", missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
