import pytest

from pdf2jpg.form import FormError, build_options, describe_size


def test_pixels_mode_both_values():
    result = build_options(size_mode="pixels", width="1920", height="1080")
    assert (result.options.width, result.options.height) == (1920, 1080)
    assert result.pages_spec == ""


def test_pixels_mode_width_only():
    result = build_options(size_mode="pixels", width="1080", height="")
    assert result.options.width == 1080
    assert result.options.height is None


def test_pixels_mode_requires_one_value():
    with pytest.raises(FormError) as excinfo:
        build_options(size_mode="pixels", width=" ", height="")
    assert excinfo.value.field == "width"


def test_dpi_mode_ignores_pixel_fields():
    result = build_options(size_mode="dpi", width="1920", height="1080", dpi="300")
    assert result.options.dpi == 300
    assert result.options.width is None and result.options.height is None


def test_scale_mode():
    result = build_options(size_mode="scale", scale="2.5")
    assert result.options.scale == 2.5


@pytest.mark.parametrize(
    "kwargs, field",
    [
        ({"size_mode": "pixels", "width": "abc"}, "width"),
        ({"size_mode": "dpi", "dpi": "x"}, "dpi"),
        ({"size_mode": "scale", "scale": "-"}, "scale"),
        ({"size_mode": "pixels", "width": "10", "quality": "high"}, "quality"),
        ({"size_mode": "pixels", "width": "10", "background": "notacolor"}, "background"),
        ({"size_mode": "pixels", "width": "10", "pages": "5-1"}, "pages"),
        ({"size_mode": "bogus"}, "size_mode"),
    ],
)
def test_invalid_input_reports_field(kwargs, field):
    with pytest.raises(FormError) as excinfo:
        build_options(**kwargs)
    assert excinfo.value.field == field


def test_option_level_validation_is_surfaced():
    with pytest.raises(FormError):
        build_options(size_mode="pixels", width="0")
    with pytest.raises(FormError):
        build_options(size_mode="pixels", width="10", quality="200")


def test_background_accepts_named_colors():
    result = build_options(size_mode="pixels", width="10", background="black")
    assert result.options.background == "black"


def test_pages_spec_expanded_per_document():
    result = build_options(size_mode="pixels", width="100", pages="1,3-4")
    assert result.pages_for_document(10) == [0, 2, 3]
    assert result.pages_for_document(3) == [0, 2]  # 総ページ数で打ち切り


def test_pages_spec_empty_means_all_pages():
    result = build_options(size_mode="pixels", width="100")
    assert result.pages_for_document(5) is None


def test_grayscale_flag():
    assert build_options(size_mode="dpi", grayscale=True).options.grayscale is True


def test_describe_size():
    assert "1920x1080" in describe_size(build_options(size_mode="pixels", width="1920", height="1080").options)
    assert "比率維持" in describe_size(build_options(size_mode="pixels", width="800", height="").options)
    assert "300 dpi" in describe_size(build_options(size_mode="dpi", dpi="300").options)
    assert "2 倍" in describe_size(build_options(size_mode="scale", scale="2").options)
