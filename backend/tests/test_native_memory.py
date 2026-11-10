from types import SimpleNamespace

import pytest

from app.core import native_memory
from app.core.errors import AppError
from app.services.pdf_service import PdfService


@pytest.fixture(autouse=True)
def fresh_trimmer():
    native_memory._trimmer.cache_clear()
    yield
    native_memory._trimmer.cache_clear()


def test_non_linux_is_a_safe_noop(monkeypatch):
    monkeypatch.setattr(native_memory.sys, "platform", "win32")
    monkeypatch.setattr(native_memory.ctypes, "CDLL", lambda *_: pytest.fail("loaded foreign libc"))
    assert native_memory.release_native_memory() is False


@pytest.mark.parametrize("missing", ["gnu_get_libc_version", "malloc_trim"])
def test_missing_libc_symbols_are_a_safe_noop(monkeypatch, missing):
    monkeypatch.setattr(native_memory.sys, "platform", "linux")
    library=SimpleNamespace(gnu_get_libc_version=object(),malloc_trim=object())
    delattr(library,missing)
    monkeypatch.setattr(native_memory.ctypes,"CDLL",lambda *_:library)
    assert native_memory.release_native_memory() is False


def test_loader_failure_cannot_fail_ocr(monkeypatch):
    monkeypatch.setattr(native_memory.sys,"platform","linux")
    def unavailable(*_):
        raise OSError("unavailable allocator")
    monkeypatch.setattr(native_memory.ctypes,"CDLL",unavailable)
    assert native_memory.release_native_memory() is False


def test_native_hint_signature_and_live_bytes_remain_unchanged(monkeypatch):
    monkeypatch.setattr(native_memory.sys,"platform","linux")
    calls=[]
    class Hint:
        def __call__(self,pad):
            calls.append(pad)
            return 1
    hint=Hint()
    monkeypatch.setattr(native_memory.ctypes,"CDLL",lambda *_:SimpleNamespace(gnu_get_libc_version=object(),malloc_trim=hint))
    before=b"immutable canonical PNG owner"
    assert native_memory.release_native_memory() is True
    assert native_memory.release_native_memory() is True
    assert calls==[0,0] and before==b"immutable canonical PNG owner"
    assert hint.argtypes==[native_memory.ctypes.c_size_t] and hint.restype==native_memory.ctypes.c_int


def test_pdf_error_still_returns_native_memory_hint(settings,monkeypatch):
    calls=[]
    monkeypatch.setattr("app.services.pdf_service.release_native_memory",lambda:calls.append("closed"))
    with pytest.raises(AppError):
        PdfService(settings).render(b"invalid PDF",1)
    assert calls==["closed"]
