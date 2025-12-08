from pathlib import Path

from forgeops_automation.operations.timezone import TimezoneOperation
from forgeops_automation.types import HostConfig
from forgeops_automation.executors import LocalExecutor


def test_timezone_creates_symlink(tmp_path: Path) -> None:
    zone_dir = tmp_path / "zoneinfo"
    zone_dir.mkdir()
    brisbane = zone_dir / "Australia" / "Brisbane"
    brisbane.parent.mkdir(parents=True)
    brisbane.write_text("timezone-data")
    localtime = tmp_path / "localtime"
    etc_zone = tmp_path / "timezone"

    spec = {
        "zone": "Australia/Brisbane",
        "zoneinfo_dir": str(zone_dir),
        "localtime_path": str(localtime),
        "manage_etc_timezone": True,
        "etc_timezone_path": str(etc_zone),
    }
    op = TimezoneOperation(spec)
    executor = LocalExecutor(HostConfig(name="local"), dry_run=False)

    result = op.apply(HostConfig("local"), executor)
    assert result.changed is True
    assert localtime.is_symlink()
    assert localtime.readlink() == brisbane
    assert etc_zone.read_text().strip() == "Australia/Brisbane"

    result = op.apply(HostConfig("local"), executor)
    assert result.changed is False

    remove_op = TimezoneOperation(
        {
            "zone": "Australia/Brisbane",
            "zoneinfo_dir": str(zone_dir),
            "localtime_path": str(localtime),
            "manage_etc_timezone": True,
            "etc_timezone_path": str(etc_zone),
            "state": "absent",
        }
    )
    result = remove_op.apply(HostConfig("local"), executor)
    assert result.changed is True
    assert not localtime.exists()
    assert not etc_zone.exists()
