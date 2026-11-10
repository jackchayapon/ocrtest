import asyncio
import io
from hashlib import sha256

import cv2
import httpx
import numpy as np
import pytest
from PIL import Image

from app.pipelines.benchmark import BenchmarkPipelineAdapter
from app.services.image_service import ImageService
from tests.test_benchmark_pipeline import DETECTION_ENDPOINT, config, fixtures


@pytest.mark.parametrize("roi", [None, dict(x1=0, y1=0, x2=64, y2=48),
                                 dict(x1=7, y1=9, x2=57, y2=41)])
@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P"])
def test_borrowed_crop_pixels_match_standalone_png(settings, mode, roi):
    images = ImageService(settings)
    with Image.new(mode, (64, 48)) as original:
        original.info["icc_profile"] = b"synthetic profile"
        expected = images.canonical_crop(original, roi)
        crop = images.canonical_crop(original, roi, share_source=True)
        assert crop.png == expected.png and crop.sha256 == expected.sha256
        with images.open(expected.png) as reference, crop.pixels(images) as pixels:
            assert pixels.mode == "RGB" and pixels.size == reference.size
            assert pixels.tobytes() == reference.tobytes()
        assert original.getpixel((0, 0)) is not None
        assert original.info["icc_profile"] == b"synthetic profile"


def test_full_page_reuses_only_proven_identical_bytes_and_does_not_copy_pixels(settings, monkeypatch):
    images = ImageService(settings)
    with Image.new("RGB", (64, 48), "red") as original:
        encoded = images.encode_png(original)
        uncompressed = io.BytesIO()
        original.save(uncompressed, format="PNG", compress_level=0)
        other = uncompressed.getvalue()
        def unexpected_copy(*args, **kwargs):
            pytest.fail("metadata-free full-page crop must not duplicate its pixels")
        monkeypatch.setattr(original, "crop", unexpected_copy)
        roi = dict(x1=0, y1=0, x2=64, y2=48)
        crop = images.canonical_crop(original, roi, share_source=True, encoded_source=encoded)
        assert crop.png is encoded
        with crop.pixels(images) as pixels:
            assert pixels is original
        different = images.canonical_crop(original, roi, encoded_source=other)
        assert different.png == encoded and different.png is not other
        assert different.sha256 == sha256(encoded).hexdigest()


def test_matching_png_does_not_allocate_output_bytesio(settings, monkeypatch):
    with Image.new("RGB", (64, 48), "red") as image:
        reference = ImageService.encode_png(image)
        def unexpected_buffer(*args, **kwargs):
            pytest.fail("matching PNG must compare chunks rather than buffer another PNG")
        monkeypatch.setattr("app.services.image_service.io.BytesIO", unexpected_buffer)
        assert ImageService.encode_png(image, reuse=reference) is reference


@pytest.mark.parametrize("seed", [3, 48, 71])
def test_prefix_rectification_retains_exact_opencv_pixels_and_png(settings, seed):
    rng = np.random.default_rng(seed)
    data = rng.integers(0, 256, (384, 512, 3), dtype=np.uint8)
    images = ImageService(settings)
    polygons = [np.float32([[0, 0], [20, 0], [20, 15], [0, 15]]),
                np.float32([[400, 300], [512, 302], [510, 384], [399, 382]])]
    for _ in range(30):
        polygons.append(np.float32([[rng.uniform(0, 25), rng.uniform(0, 15)],
                                    [rng.uniform(80, 120), rng.uniform(0, 15)],
                                    [rng.uniform(80, 120), rng.uniform(70, 95)],
                                    [rng.uniform(0, 25), rng.uniform(70, 95)]]))
    with Image.fromarray(data) as image:
        for quad in polygons:
            width = round(max(np.linalg.norm(quad[1]-quad[0]), np.linalg.norm(quad[2]-quad[3])))
            height = round(max(np.linalg.norm(quad[3]-quad[0]), np.linalg.norm(quad[2]-quad[1])))
            target = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
            expected = cv2.warpPerspective(data, cv2.getPerspectiveTransform(quad, target),
                                            (width, height), flags=cv2.INTER_CUBIC,
                                            borderMode=cv2.BORDER_REPLICATE)
            with Image.fromarray(expected) as reference:
                assert images.rectify_quad(image, quad) == images.encode_png(reference)


def test_small_detected_quad_does_not_materialize_whole_source_array(settings, monkeypatch):
    arrays = []
    asarray = np.asarray
    def tracked(value, *args, **kwargs):
        if isinstance(value, Image.Image):
            arrays.append(value.size)
        return asarray(value, *args, **kwargs)
    monkeypatch.setattr("app.services.image_service.np.asarray", tracked)
    with Image.new("RGB", (1024, 768)) as source:
        result = ImageService(settings).rectify_quad(source, [[1, 1], [20, 1], [20, 15], [1, 15]])
        assert result.startswith(b"\x89PNG")
        assert arrays == [(24, 19)]


@pytest.mark.parametrize("share", [False, True])
def test_owned_pixel_context_closes_on_cancellation_but_not_source(settings, share):
    images = ImageService(settings)
    with Image.new("RGB", (80, 60), "blue") as original:
        crop = images.canonical_crop(original, dict(x1=5, y1=6, x2=65, y2=45), share_source=share)
        with pytest.raises(asyncio.CancelledError), crop.pixels(images) as temporary:
            raise asyncio.CancelledError()
        with pytest.raises(ValueError, match="closed"):
            temporary.getpixel((0, 0))
        assert original.getpixel((0, 0)) == (0, 0, 255)


@pytest.mark.parametrize("share", [False, True])
@pytest.mark.parametrize("failure", [None, "gateway", "cancel"])
def test_adapter_releases_owned_pixels_before_rec_wait(settings, monkeypatch, share, failure):
    det, rec = fixtures()
    det["data"]["result"]["results"][0]["dt_polys"] = [[[1, 1], [30, 1], [30, 15], [1, 15]]]
    det["data"]["result"]["results"][0]["dt_scores"] = [.95]
    rec["data"]["results"] = rec["data"]["results"][:1]
    rec["data"]["count"] = 1
    images = ImageService(settings)
    with Image.new("RGB", (100, 80), "white") as original:
        roi = dict(x1=10, y1=12, x2=90, y2=70)
        crop = images.canonical_crop(original, roi, share_source=share)
        adapter = BenchmarkPipelineAdapter(config(), settings)
        seen = []
        rectify = adapter.images.rectify_quad
        def tracked(image, polygon):
            seen.append(image)
            return rectify(image, polygon)
        monkeypatch.setattr(adapter.images, "rectify_quad", tracked)
        async def send(request):
            if request["url"].endswith(DETECTION_ENDPOINT):
                return det
            assert seen
            for temporary in seen:
                with pytest.raises(ValueError, match="closed"):
                    temporary.getpixel((0, 0))
            assert original.getpixel((0, 0)) == (255, 255, 255)
            await asyncio.sleep(0)
            if failure == "cancel":
                raise asyncio.CancelledError()
            if failure == "gateway":
                raise httpx.ReadError("synthetic transport failure")
            return rec
        monkeypatch.setattr(adapter.gateway, "send", send)
        invocation = adapter.run(original_image=original, cropped_image=crop, roi=roi)
        if failure:
            with pytest.raises(asyncio.CancelledError if failure == "cancel" else httpx.ReadError):
                asyncio.run(invocation)
        else:
            result = asyncio.run(invocation)
            assert result.text == rec["data"]["results"][0]["text"]
            assert result.diagnostics["crop_sha256"] == crop.sha256
        assert original.getpixel((0, 0)) == (255, 255, 255)
