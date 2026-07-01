from hikmicropy import HikmicroExtractor


def test_extract_hdri_shape_and_range(synthetic_ir_jpeg):
    ext = HikmicroExtractor(synthetic_ir_jpeg)
    thermal = ext.process_image()

    assert thermal.raw.shape == (192, 256)
    assert thermal.raw_min < thermal.raw_max
    assert isinstance(thermal.raw_min, int)
    assert isinstance(thermal.raw_max, int)


def test_to_celsius_anchors_are_exact(synthetic_ir_jpeg):
    # per-image 2点線形較正: raw_min→t_min, raw_max→t_max がアンカーで厳密一致
    ext = HikmicroExtractor(synthetic_ir_jpeg)
    ext.process_image()
    tc = ext.to_celsius(t_min=30.0, t_max=40.0)
    assert abs(float(tc.min()) - 30.0) < 1e-6
    assert abs(float(tc.max()) - 40.0) < 1e-6
