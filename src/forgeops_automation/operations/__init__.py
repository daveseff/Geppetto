from .base import Operation
from .file import FileOperation
from .package import PackageOperation
from .service import ServiceOperation

OPERATION_REGISTRY = {
    "package": PackageOperation,
    "file": FileOperation,
    "service": ServiceOperation,
}

__all__ = [
    "Operation",
    "FileOperation",
    "PackageOperation",
    "ServiceOperation",
    "OPERATION_REGISTRY",
]
