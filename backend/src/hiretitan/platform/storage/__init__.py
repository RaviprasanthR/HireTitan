"""File storage port and the local volume adapter."""

from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.platform.storage.port import FileStoragePort

__all__ = ["FileStoragePort", "LocalFileStorage"]
