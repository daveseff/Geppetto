from .authorized_key import AuthorizedKeyOperation
from .base import Operation
from .file import FileOperation
from .package import PackageOperation
from .service import ServiceOperation
from .user import UserOperation

OPERATION_REGISTRY = {
    "package": PackageOperation,
    "file": FileOperation,
    "service": ServiceOperation,
    "user": UserOperation,
    "authorized_key": AuthorizedKeyOperation,
}

__all__ = [
    "Operation",
    "FileOperation",
    "PackageOperation",
    "ServiceOperation",
    "UserOperation",
    "AuthorizedKeyOperation",
    "OPERATION_REGISTRY",
]
