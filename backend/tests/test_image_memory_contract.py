import io
from hashlib import sha256

import cv2
import numpy as np
import pytest
from PIL import Image, ImageOps

from app.services.image_service import ImageService


@pytest.mark.parametrize("orientation", range(1, 9))
def test_upload_orientation_retains_exact_reference_png(settings, orientation):
    service = ImageService(settings)
    with Image.new("RGB", (96, 64)) as image:
        image.putdata([(i % 256, (i // 96) * 3, (i * 7) % 256) for i in range(96 * 64)])
        exif = Image.Exif()
        exif[274] = orientation
        source = io.BytesIO()
        image.save(source, format="JPEG", quality=95, exif=exif)
    data = source.getvalue()
    with Image.open(io.BytesIO(data)) as decoded:
        with ImageOps.exif_transpose(decoded) as rotated:
            with rotated.convert("RGB") as reference:
                expected = service.encode_png(reference)
                expected_size = reference.size
    result, width, height = service.decode_upload(data, "image/jpeg")
    assert result == expected
    assert (width, height) == expected_size


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P", "CMYK"])
def test_open_and_upload_preserve_conversion_and_close_lifetime(settings, mode):
    service = ImageService(settings)
    with Image.new(mode, (40, 30)) as source:
        output = io.BytesIO()
        source.save(output, format="TIFF")
    data = output.getvalue()
    original_hash = sha256(data).hexdigest()
    with Image.open(io.BytesIO(data)) as decoded:
        with ImageOps.exif_transpose(decoded) as rotated:
            with rotated.convert("RGB") as reference:
                expected_png = service.encode_png(reference)
                expected_pixels = reference.tobytes()
    png, _, _ = service.decode_upload(data, "image/tiff")
    assert png == expected_png
    with service.open(data) as image:
        assert image.mode == "RGB" and image.format is None
        assert image.tobytes() == expected_pixels  # Pixels survive closed input-buffer scope.
    assert sha256(data).hexdigest() == original_hash


@pytest.mark.parametrize("roi", [None, {"x1": 3, "y1": 4, "x2": 25, "y2": 22}])
@pytest.mark.parametrize("mode", ["RGB", "L", "RGBA", "P"])
def test_roi_png_bytes_dimensions_and_hash_match_opencv_reference(settings, roi, mode):
    service = ImageService(settings)
    with Image.new(mode, (40, 30)) as source:
        source.info.update(icc_profile=b"synthetic profile", dpi=(120, 120))
        before = source.tobytes()
        if roi is None:
            reference = source.copy()
        else:
            pixels = np.asarray(source)
            region = pixels[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]]
            reference = Image.fromarray(cv2.copyMakeBorder(region, 0, 0, 0, 0, cv2.BORDER_CONSTANT))
        with reference:
            expected = service.encode_png(reference)
            expected_size = reference.size
        crop = service.canonical_crop(source, roi)
        assert crop.png == expected
        assert crop.sha256 == sha256(expected).hexdigest()
        assert (crop.width, crop.height) == expected_size
        assert source.tobytes() == before
        assert source.info["icc_profile"] == b"synthetic profile"
