import numpy as np

from hikmicropy import fusion


def test_lut_shapes_and_palette_output():
    for lut in fusion._LUTS.values():
        assert lut.shape == (256, 3)

    u8 = np.arange(256, dtype=np.uint8).reshape(16, 16)
    out = fusion.apply_palette(u8, "arctic")
    assert out.shape == (16, 16, 3)
    assert out.dtype == np.uint8
