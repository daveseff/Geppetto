from .base import Operation
from .file import FileOperation
from .package import PackageOperation

OPERATION_REGISTRY = {
    "package": PackageOperation,
    "file": FileOperation,
}

__all__ = ["Operation", "FileOperation", "PackageOperation", "OPERATION_REGISTRY"]
