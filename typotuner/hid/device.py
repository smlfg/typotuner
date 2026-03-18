"""Raw hidraw I/O for SteelSeries Apex Pro TKL 2023.

No external dependencies — uses ioctl directly on /dev/hidraw*.
Device discovery via /sys/class/hidraw/*/device/uevent.
"""

from __future__ import annotations

import fcntl
import os
import struct
from pathlib import Path

# SteelSeries Apex Pro TKL 2023
VENDOR_ID = 0x1038
PRODUCT_ID = 0x1628
TARGET_INTERFACE = 1  # Vendor-specific (Usage Page 0xFFC0)

# ioctl constants for HID feature reports
# From linux/hidraw.h: HIDIOCGFEATURE(len) = _IOC(_IOC_READ|_IOC_WRITE, 'H', 0x07, len)
# HIDIOCSFEATURE(len) = _IOC(_IOC_READ|_IOC_WRITE, 'H', 0x06, len)
_IOC_WRITE = 1
_IOC_READ = 2
_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS


def _ioc(direction: int, type_: int, nr: int, size: int) -> int:
    return (
        (direction << _IOC_DIRSHIFT)
        | (type_ << _IOC_TYPESHIFT)
        | (nr << _IOC_NRSHIFT)
        | (size << _IOC_SIZESHIFT)
    )


def _hidiocgfeature(length: int) -> int:
    """HIDIOCGFEATURE(len) — get feature report."""
    return _ioc(_IOC_READ | _IOC_WRITE, ord("H"), 0x07, length)


def _hidiocsfeature(length: int) -> int:
    """HIDIOCSFEATURE(len) — set feature report."""
    return _ioc(_IOC_READ | _IOC_WRITE, ord("H"), 0x06, length)


# Standard report sizes for Apex Pro TKL 2023
FEATURE_REPORT_SIZE = 644
OUTPUT_REPORT_SIZE = 64


class DeviceNotFoundError(Exception):
    """Raised when the SteelSeries device is not found."""


class DevicePermissionError(Exception):
    """Raised when we lack permissions to access the device."""


def find_device(
    vid: int = VENDOR_ID,
    pid: int = PRODUCT_ID,
    interface: int = TARGET_INTERFACE,
) -> str:
    """Find the hidraw path for the target device and interface.

    Searches /sys/class/hidraw/*/device/uevent for matching VID:PID,
    then checks the interface number.

    Returns:
        Path like '/dev/hidraw7'

    Raises:
        DeviceNotFoundError: Device not found or wrong interface
    """
    hidraw_base = Path("/sys/class/hidraw")
    if not hidraw_base.exists():
        raise DeviceNotFoundError("No /sys/class/hidraw — is hidraw module loaded?")

    vid_str = f"{vid:04X}"
    pid_str = f"{pid:04X}"

    for hidraw_dir in sorted(hidraw_base.iterdir()):
        uevent_path = hidraw_dir / "device" / "uevent"
        if not uevent_path.exists():
            continue

        uevent = uevent_path.read_text()

        # Check VID:PID — uevent contains HID_ID=0003:00001038:00001628
        # or similar format
        has_vid_pid = False
        for line in uevent.splitlines():
            if line.startswith("HID_ID="):
                # Format: HID_ID=BBBB:VVVVVVVV:PPPPPPPP
                parts = line.split("=", 1)[1].split(":")
                if len(parts) >= 3:
                    uevent_vid = parts[1].lstrip("0").upper() or "0"
                    uevent_pid = parts[2].lstrip("0").upper() or "0"
                    if uevent_vid == vid_str.lstrip("0") and uevent_pid == pid_str.lstrip("0"):
                        has_vid_pid = True
                break

        if not has_vid_pid:
            continue

        # Check interface number via the device path
        # The sysfs path typically contains something like:
        # /sys/devices/.../1038:1628.XXXX/YYYY:1038:1628.ZZZZ/hidraw/hidrawN
        # The interface number is encoded in the USB path
        device_path = (hidraw_dir / "device").resolve()
        device_path_str = str(device_path)

        # Try to find interface number from the path or from the
        # bInterfaceNumber file in the USB device tree
        iface_found = _check_interface(device_path, interface)
        if iface_found:
            dev_path = f"/dev/{hidraw_dir.name}"
            if os.path.exists(dev_path):
                return dev_path

    raise DeviceNotFoundError(
        f"SteelSeries device {vid:04x}:{pid:04x} interface {interface} not found. "
        f"Is the keyboard connected? Check udev rules for permissions."
    )


def _check_interface(device_path: Path, target_interface: int) -> bool:
    """Check if a HID device sysfs path corresponds to the target USB interface."""
    # Walk up the sysfs tree looking for bInterfaceNumber
    path = device_path
    for _ in range(10):  # max depth
        bintf = path / "bInterfaceNumber"
        if bintf.exists():
            try:
                iface_num = int(bintf.read_text().strip())
                return iface_num == target_interface
            except (ValueError, OSError):
                pass
        parent = path.parent
        if parent == path:
            break
        path = parent
    # Fallback: couldn't determine interface, accept it
    return True


def open_device(path: str) -> int:
    """Open a hidraw device and return the file descriptor.

    Raises:
        DevicePermissionError: If we lack permissions
        OSError: For other I/O errors
    """
    try:
        fd = os.open(path, os.O_RDWR)
    except PermissionError as e:
        raise DevicePermissionError(
            f"Permission denied for {path}. "
            f"Add udev rule or run with appropriate permissions."
        ) from e
    return fd


def close_device(fd: int) -> None:
    """Close a hidraw file descriptor."""
    os.close(fd)


def get_feature(fd: int, report_id: int = 0x00, size: int = FEATURE_REPORT_SIZE) -> bytes:
    """Read a HID feature report via ioctl.

    Args:
        fd: Open hidraw file descriptor
        report_id: Report ID byte (first byte of buffer)
        size: Expected report size including report ID byte

    Returns:
        Raw bytes of the feature report
    """
    buf = bytearray(size)
    buf[0] = report_id
    ioctl_code = _hidiocgfeature(size)
    fcntl.ioctl(fd, ioctl_code, buf)
    return bytes(buf)


def set_feature(fd: int, data: bytes) -> None:
    """Write a HID feature report via ioctl.

    Args:
        fd: Open hidraw file descriptor
        data: Complete report data including report ID as first byte
    """
    buf = bytearray(data)
    ioctl_code = _hidiocsfeature(len(buf))
    fcntl.ioctl(fd, ioctl_code, buf)


def write_output(fd: int, data: bytes, size: int = OUTPUT_REPORT_SIZE) -> None:
    """Write an output report (interrupt transfer).

    Pads data to `size` bytes with zeros if shorter.
    """
    padded = bytearray(size)
    padded[: len(data)] = data
    os.write(fd, bytes(padded))


def read_input(fd: int, size: int = OUTPUT_REPORT_SIZE, timeout_ms: int = 1000) -> bytes | None:
    """Read an input report with timeout.

    Args:
        fd: Open hidraw file descriptor
        size: Expected report size
        timeout_ms: Timeout in milliseconds

    Returns:
        Report bytes, or None on timeout
    """
    import select

    ready, _, _ = select.select([fd], [], [], timeout_ms / 1000.0)
    if not ready:
        return None
    return os.read(fd, size)


def get_device_info(path: str) -> dict:
    """Get device information from sysfs.

    Returns dict with keys: name, vendor_id, product_id, hidraw_path
    """
    hidraw_name = Path(path).name  # e.g. "hidraw7"
    sys_path = Path(f"/sys/class/hidraw/{hidraw_name}")

    info = {
        "hidraw_path": path,
        "hidraw_name": hidraw_name,
        "vendor_id": VENDOR_ID,
        "product_id": PRODUCT_ID,
        "name": "SteelSeries Apex Pro TKL 2023",
    }

    # Try to read the HID device name
    name_path = sys_path / "device" / "name"  # not always present
    # Alternative: walk up to USB device for product string
    device_path = (sys_path / "device").resolve()
    for _ in range(10):
        product_file = device_path / "product"
        if product_file.exists():
            try:
                info["name"] = product_file.read_text().strip()
            except OSError:
                pass
            break
        parent = device_path.parent
        if parent == device_path:
            break
        device_path = parent

    return info
