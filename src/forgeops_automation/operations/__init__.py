from .authorized_key import AuthorizedKeyOperation
from .base import Operation
from .file import FileOperation
from .mount import BlockDeviceMountOperation, EfsMountOperation
from .package import PackageOperation
from .remote import RemoteFileOperation, RpmInstallOperation
from .service import ServiceOperation
from .user import UserOperation

OPERATION_REGISTRY = {
    "package": PackageOperation,
    "file": FileOperation,
    "service": ServiceOperation,
    "user": UserOperation,
    "authorized_key": AuthorizedKeyOperation,
    "efs_mount": EfsMountOperation,
    "block_device": BlockDeviceMountOperation,
    "remote_file": RemoteFileOperation,
    "rpm": RpmInstallOperation,
}

__all__ = [
    "Operation",
    "FileOperation",
    "PackageOperation",
    "ServiceOperation",
    "UserOperation",
    "AuthorizedKeyOperation",
    "EfsMountOperation",
    "BlockDeviceMountOperation",
    "RemoteFileOperation",
    "RpmInstallOperation",
    "OPERATION_REGISTRY",
]
