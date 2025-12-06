from .authorized_key import AuthorizedKeyOperation
from .base import Operation
from .cron import CronOperation
from .file import FileOperation
from .mount import BlockDeviceMountOperation, EfsMountOperation, NetworkMountOperation
from .package import PackageOperation
from .remote import RemoteFileOperation, RpmInstallOperation
from .service import ServiceOperation
from .sysctl import SysctlOperation
from .timezone import TimezoneOperation
from .user import UserOperation

OPERATION_REGISTRY = {
    "package": PackageOperation,
    "file": FileOperation,
    "service": ServiceOperation,
    "user": UserOperation,
    "authorized_key": AuthorizedKeyOperation,
    "efs_mount": EfsMountOperation,
    "block_device": BlockDeviceMountOperation,
    "network_mount": NetworkMountOperation,
    "remote_file": RemoteFileOperation,
    "rpm": RpmInstallOperation,
    "timezone": TimezoneOperation,
    "sysctl": SysctlOperation,
    "cron": CronOperation,
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
    "NetworkMountOperation",
    "RemoteFileOperation",
    "RpmInstallOperation",
    "TimezoneOperation",
    "SysctlOperation",
    "CronOperation",
    "OPERATION_REGISTRY",
]
