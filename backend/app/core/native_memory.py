"""Return already-freed native image buffers to the OS where libc supports it."""
import ctypes
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def _trimmer():
    if not sys.platform.startswith("linux"):
        return None
    try:
        library = ctypes.CDLL(None)
        # This is a GNU-libc hint, not a portable allocator API.
        library.gnu_get_libc_version
        trim = library.malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        return trim
    except (AttributeError, OSError):
        return None


def release_native_memory():
    """Best effort only: live images/bytes are untouched; no forced Python GC."""
    trim = _trimmer()
    if trim is None:
        return False
    try:
        return bool(trim(0))
    except OSError:
        return False
