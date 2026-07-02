"""hikmicropy コマンドラインインターフェース.

サブコマンド:
  process  IR/VIS ペア1組から合成画像 + visible + metadata (+ html) を出力。
  batch    フォルダ内の HM*.jpeg / HM*.VIS.jpeg を自動ペアリングして一括処理。
  export   IR 1枚から生値/温度 CSV と Plotly HTML を出力（VIS 不要）。

温度較正:
  --tmin/--tmax を渡すと per-image 2点線形較正で℃出力。渡さなければ OCR で
  スケールバーを読み、失敗時は raw のみ（未較正）で出力する。定量用途は
  --tmin/--tmax の手入力を推奨（OCR は著者機 Pocket2 レイアウト前提の補助）。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .extractor import HikmicroExtractor
from .fusion import PALETTES, process


def _cmd_process(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = str(out_dir / Path(args.ir).stem)
    process(
        args.ir, args.vis, prefix,
        t_min=args.tmin, t_max=args.tmax,
        palette=args.palette, html=args.html, html_embed_js=args.html_embed_js,
    )
    print(f"[process] {Path(args.ir).name} -> {prefix}_*.png / _metadata.json"
          + (" / _thermal.html" if args.html else ""))
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    src = Path(args.src_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    irs = sorted(p for p in src.glob("HM*.jpeg") if not p.name.endswith(".VIS.jpeg"))
    missing: list[str] = []
    done = 0
    for ir in irs:
        vis = ir.with_name(ir.stem + ".VIS.jpeg")
        if not vis.exists():
            if args.allow_thermal_only:
                print(f"[batch] {ir.name}: VIS なし（--allow-thermal-only は未実装のためスキップ）")
            missing.append(ir.name)
            continue
        prefix = str(out_dir / ir.stem)
        process(str(ir), str(vis), prefix,
                t_min=args.tmin, t_max=args.tmax,
                palette=args.palette, html=args.html)
        done += 1
        print(f"[batch] {ir.name} -> {ir.stem}_*")
    print(f"[batch] 完了 {done} 件 / VIS 欠落 {len(missing)} 件"
          + (f": {missing}" if missing else ""))
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / Path(args.ir).stem
    ext = HikmicroExtractor(args.ir)
    t = ext.process_image()
    print(f"[export] {Path(args.ir).name}  {t.width}x{t.height}  "
          f"raw min={t.raw_min} max={t.raw_max}")
    if args.csv:
        csv_path = str(base) + ("_thermal.csv" if args.tmin is not None else "_raw.csv")
        ext.export_thermal_to_csv(csv_path, args.tmin, args.tmax)
        print(f"[export] CSV -> {csv_path}")
    if args.html:
        from .plotly_export import export_plotly_html
        temperature_c = None
        if args.tmin is not None and args.tmax is not None:
            temperature_c = ext.to_celsius(args.tmin, args.tmax)
        html_path = str(base) + "_thermal.html"
        export_plotly_html(t.raw, html_path, temperature_c=temperature_c,
                           include_plotlyjs=True if args.html_embed_js else "cdn")
        print(f"[export] HTML -> {html_path}")
    return 0


def _add_temp_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tmin", type=float, default=None,
                   help="スケールバー下端の温度[℃]（手入力。定量用途は推奨）")
    p.add_argument("--tmax", type=float, default=None,
                   help="スケールバー上端の温度[℃]（手入力。定量用途は推奨）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hikmicropy",
        description="HIKMICRO Pocket2 放射温度JPEG の抽出・合成・解析",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pp = sub.add_parser("process", help="IR/VIS ペア1組を処理")
    pp.add_argument("ir", help="IR JPEG (HM*.jpeg)")
    pp.add_argument("vis", help="可視光 JPEG (HM*.VIS.jpeg)")
    pp.add_argument("--palette", default="arctic", choices=PALETTES)
    pp.add_argument("--out-dir", default="output")
    pp.add_argument("--html", action="store_true", help="Plotly HTML も出力")
    pp.add_argument("--html-embed-js", action="store_true", help="HTML に plotly.js を埋め込む")
    _add_temp_args(pp)
    pp.set_defaults(func=_cmd_process)

    pb = sub.add_parser("batch", help="フォルダを一括処理（HM*.jpeg + HM*.VIS.jpeg）")
    pb.add_argument("src_dir", help="入力フォルダ")
    pb.add_argument("--palette", default="arctic", choices=PALETTES)
    pb.add_argument("--out-dir", default="output")
    pb.add_argument("--html", action="store_true")
    pb.add_argument("--allow-thermal-only", action="store_true",
                    help="VIS が無い IR も対象にする（現状は警告のみ）")
    _add_temp_args(pb)
    pb.set_defaults(func=_cmd_batch)

    pe = sub.add_parser("export", help="IR 1枚から CSV / HTML を出力（VIS 不要）")
    pe.add_argument("ir", help="IR JPEG (HM*.jpeg)")
    pe.add_argument("--out-dir", default="output")
    pe.add_argument("--csv", action="store_true", help="CSV を出力")
    pe.add_argument("--html", action="store_true", help="Plotly HTML を出力")
    pe.add_argument("--html-embed-js", action="store_true")
    _add_temp_args(pe)
    pe.set_defaults(func=_cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
