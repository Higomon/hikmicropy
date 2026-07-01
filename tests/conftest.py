"""合成の HIKMICRO 風放射温度JPEG フィクスチャ.

実測の現場画像を公開リポに含めないため、末尾に有効な HDRI ブロックを付与した
合成 JPEG を生成し、抽出・較正のコアをテストする。焼き込みスケールバーや VIS ペアが
必要な OCR/フュージョンのテストは、実画像を要するため別途モックで検証する。
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

_W, _H = 256, 192


@pytest.fixture(scope="session")
def synthetic_ir_jpeg(tmp_path_factory) -> str:
    from PIL import Image

    path = tmp_path_factory.mktemp("hik") / "HM20260101120000.jpeg"
    # コンテナとして最小の有効 JPEG
    Image.new("RGB", (32, 24), (40, 40, 40)).save(path, format="JPEG")
    jpeg = path.read_bytes()

    # HDRI ブロック: off0="HDRI", off12=width, off16=height, off20=datasize, off44=frame
    frame = np.linspace(4500, 4700, _W * _H).astype("<u2")  # raw_min < raw_max の勾配
    header = bytearray(44)
    header[0:4] = b"HDRI"
    struct.pack_into("<I", header, 12, _W)
    struct.pack_into("<I", header, 16, _H)
    struct.pack_into("<I", header, 20, _W * _H * 2 + 1024)  # datasize >= w*h*2
    path.write_bytes(jpeg + bytes(header) + frame.tobytes())
    return str(path)
