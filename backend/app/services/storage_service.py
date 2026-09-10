from abc import ABC, abstractmethod
from pathlib import Path

from app.core.errors import AppError


class StorageService(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def healthy(self) -> bool: ...


class LocalStorageService(StorageService):
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise AppError("Invalid storage key")
        return path

    def put(self, key, data):
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, key):
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise AppError("Stored image is unavailable", 404) from None

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)

    def healthy(self):
        import os

        return self.root.is_dir() and os.access(self.root, os.R_OK | os.W_OK)
