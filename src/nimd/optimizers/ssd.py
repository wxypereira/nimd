"""SSD/NVMe optimizer module for I/O scheduler, queue depth, and power management via sysfs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

from .base import (
    HardwareOptimizer,
    HardwareType,
    Profile,
    ProbeResult,
    ApplyResult,
    StatusResult,
    InvalidProfile,
    HardwareNotFound,
    PermissionDenied,
    SafeModeViolation,
    DeviceBusy,
)

logger = logging.getLogger(__name__)


@dataclass
class SsdDevice:
    block_path: Path
    name: str
    device_type: str
    rotational: bool
    scheduler_path: Path
    nr_requests_path: Path
    read_ahead_path: Path
    apst_path: Optional[Path]
    wce_path: Optional[Path]
    model: str
    firmware: str
    available_schedulers: List[str] = field(default_factory=list)
    original_scheduler: Optional[str] = None
    original_nr_requests: Optional[int] = None
    original_read_ahead: Optional[int] = None
    original_apst: Optional[int] = None
    original_wce: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_path": str(self.block_path),
            "name": self.name,
            "device_type": self.device_type,
            "rotational": self.rotational,
            "scheduler_path": str(self.scheduler_path),
            "nr_requests_path": str(self.nr_requests_path),
            "read_ahead_path": str(self.read_ahead_path),
            "apst_path": str(self.apst_path) if self.apst_path else None,
            "wce_path": str(self.wce_path) if self.wce_path else None,
            "model": self.model,
            "firmware": self.firmware,
            "available_schedulers": self.available_schedulers,
            "original_scheduler": self.original_scheduler,
            "original_nr_requests": self.original_nr_requests,
            "original_read_ahead": self.original_read_ahead,
            "original_apst": self.original_apst,
            "original_wce": self.original_wce,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SsdDevice":
        return cls(
            block_path=Path(data["block_path"]),
            name=data["name"],
            device_type=data["device_type"],
            rotational=data["rotational"],
            scheduler_path=Path(data["scheduler_path"]),
            nr_requests_path=Path(data["nr_requests_path"]),
            read_ahead_path=Path(data["read_ahead_path"]),
            apst_path=Path(data["apst_path"]) if data["apst_path"] else None,
            wce_path=Path(data["wce_path"]) if data["wce_path"] else None,
            model=data["model"],
            firmware=data["firmware"],
            available_schedulers=data.get("available_schedulers", []),
            original_scheduler=data.get("original_scheduler"),
            original_nr_requests=data.get("original_nr_requests"),
            original_read_ahead=data.get("original_read_ahead"),
            original_apst=data.get("original_apst"),
            original_wce=data.get("original_wce"),
        )


class SsdOptimizer(HardwareOptimizer):
    HARDWARE_TYPE = HardwareType.SSD
    SUPPORTED_PROFILES = [Profile.SILENT, Profile.BALANCED, Profile.PERFORMANCE, Profile.CUSTOM]

    BLOCK_BASE = Path("/sys/block")
    NVME_PATTERN = re.compile(r"^nvme\d+n\d+$")
    SATA_PATTERN = re.compile(r"^sd[a-z]+$")
    APST_PATTERN = re.compile(r"^nvme\d+$")

    NR_REQUESTS_MIN = 32
    NR_REQUESTS_MAX = 4096
    READ_AHEAD_MIN = 0
    READ_AHEAD_MAX = 16384
    APST_ENABLED = 1
    APST_DISABLED = 0
    WCE_ENABLED = 1
    WCE_DISABLED = 0

    SCHEDULER_NONE = "none"
    SCHEDULER_MQ_DEADLINE = "mq-deadline"
    SCHEDULER_KYBER = "kyber"
    SCHEDULER_BFQ = "bfq"
    VALID_SCHEDULERS: Set[str] = {SCHEDULER_NONE, SCHEDULER_MQ_DEADLINE, SCHEDULER_KYBER, SCHEDULER_BFQ}

    def __init__(self):
        self._devices: List[SsdDevice] = []
        self._current_profile: Optional[Profile] = None
        self._custom_params: Optional[Dict[str, Any]] = None

    def probe(self) -> ProbeResult:
        self._devices = []
        errors: List[str] = []

        if not self.BLOCK_BASE.exists():
            return ProbeResult(False, [], "Block sysfs not found at /sys/block")

        for block_dir in sorted(self.BLOCK_BASE.iterdir()):
            try:
                device = self._probe_block_device(block_dir)
                if device:
                    self._devices.append(device)
            except (PermissionError, OSError) as e:
                errors.append(f"{block_dir.name}: {e}")

        if not self._devices:
            return ProbeResult(False, [], "No SSD/NVMe devices found" + (f" ({'; '.join(errors)})" if errors else ""))

        return ProbeResult(True, [d.to_dict() for d in self._devices], None)

    def _probe_block_device(self, block_dir: Path) -> Optional[SsdDevice]:
        name = block_dir.name
        is_nvme = bool(self.NVME_PATTERN.match(name))
        is_sata = bool(self.SATA_PATTERN.match(name))
        if not (is_nvme or is_sata):
            return None

        rotational_path = block_dir / "queue" / "rotational"
        rotational_val = self._safe_read(str(rotational_path))
        if rotational_val is None:
            return None
        try:
            rotational = int(rotational_val) != 0
        except ValueError:
            return None
        if rotational:
            return None

        device_type = "nvme" if is_nvme else "sata"
        scheduler_path = block_dir / "queue" / "scheduler"
        nr_requests_path = block_dir / "queue" / "nr_requests"
        read_ahead_path = block_dir / "queue" / "read_ahead_kb"

        for p in (scheduler_path, nr_requests_path, read_ahead_path):
            if not p.exists():
                return None

        available_schedulers = self._parse_available_schedulers(scheduler_path)
        if not available_schedulers:
            return None

        model = self._read_model(block_dir, device_type)
        firmware = self._read_firmware(block_dir, device_type)
        apst_path = self._find_apst_path(block_dir, device_type)
        wce_path = self._find_wce_path(block_dir, device_type)

        return SsdDevice(
            block_path=block_dir,
            name=name,
            device_type=device_type,
            rotational=rotational,
            scheduler_path=scheduler_path,
            nr_requests_path=nr_requests_path,
            read_ahead_path=read_ahead_path,
            apst_path=apst_path,
            wce_path=wce_path,
            model=model,
            firmware=firmware,
            available_schedulers=available_schedulers,
        )

    def _parse_available_schedulers(self, scheduler_path: Path) -> List[str]:
        content = self._safe_read(str(scheduler_path))
        if content is None:
            return []
        return [t.strip("[]") for t in content.split() if t.strip("[]") in self.VALID_SCHEDULERS]

    def _read_model(self, block_dir: Path, device_type: str) -> str:
        model_path = block_dir / "device" / "model"
        return self._safe_read(str(model_path)) or "unknown"

    def _read_firmware(self, block_dir: Path, device_type: str) -> str:
        fw_path = block_dir / "device" / ("firmware_rev" if device_type == "nvme" else "rev")
        return self._safe_read(str(fw_path)) or "unknown"

    def _find_apst_path(self, block_dir: Path, device_type: str) -> Optional[Path]:
        if device_type != "nvme":
            return None
        for base in (block_dir / "device", block_dir / "device" / ".." / ".."):
            try:
                apst_path = (base / "apst").resolve()
                if apst_path.exists():
                    return apst_path
            except (OSError, FileNotFoundError):
                pass
        return None

    def _find_wce_path(self, block_dir: Path, device_type: str) -> Optional[Path]:
        if device_type == "nvme":
            return None
        for base in (block_dir / "device", block_dir / "queue"):
            wce_path = base / "write_cache"
            if wce_path.exists():
                return wce_path
        return None

    def apply(self, profile: Profile, custom_params: Optional[Dict[str, Any]] = None) -> ApplyResult:
        if profile not in self.SUPPORTED_PROFILES:
            raise InvalidProfile(f"Unsupported profile: {profile.value}")

        if not self._devices:
            probe_result = self.probe()
            if not probe_result.available:
                raise HardwareNotFound(probe_result.error or "No SSD devices available")

        if not self._require_root():
            raise PermissionDenied("Root privileges required to apply SSD optimizations")

        if profile == Profile.CUSTOM:
            self._custom_params = custom_params or {}
            scheduler = self._custom_params.get("scheduler")
            nr_requests = self._custom_params.get("nr_requests")
            apst_enabled = self._custom_params.get("apst_enabled")
            wce_enabled = self._custom_params.get("write_cache_enabled")
            read_ahead = self._custom_params.get("read_ahead_kb")

            if scheduler and scheduler not in self.VALID_SCHEDULERS:
                raise InvalidProfile(f"Invalid scheduler: {scheduler}")
            if nr_requests is not None and not (self.NR_REQUESTS_MIN <= nr_requests <= self.NR_REQUESTS_MAX):
                raise SafeModeViolation(f"nr_requests must be in [{self.NR_REQUESTS_MIN}, {self.NR_REQUESTS_MAX}]")
            if apst_enabled is not None and not isinstance(apst_enabled, bool):
                raise InvalidProfile("apst_enabled must be boolean")
            if wce_enabled is not None and not isinstance(wce_enabled, bool):
                raise InvalidProfile("write_cache_enabled must be boolean")
            if read_ahead is not None and not (self.READ_AHEAD_MIN <= read_ahead <= self.READ_AHEAD_MAX):
                raise SafeModeViolation(f"read_ahead_kb must be in [{self.READ_AHEAD_MIN}, {self.READ_AHEAD_MAX}]")
        else:
            self._custom_params = None

        self._current_profile = profile
        applied: Dict[str, Any] = {"profile": profile.value, "devices": []}
        reverted: Dict[str, Any] = {"devices": []}
        warnings: List[str] = []

        for device in self._devices:
            try:
                device.original_scheduler = self._read_current_scheduler(device)
                device.original_nr_requests = self._safe_read_int(device.nr_requests_path)
                device.original_read_ahead = self._safe_read_int(device.read_ahead_path)
                device.original_apst = self._safe_read_int(device.apst_path) if device.apst_path else None
                device.original_wce = self._safe_read_int(device.wce_path) if device.wce_path else None

                reverted["devices"].append({
                    "block_path": str(device.block_path),
                    "scheduler": device.original_scheduler,
                    "nr_requests": device.original_nr_requests,
                    "read_ahead_kb": device.original_read_ahead,
                    "apst": device.original_apst,
                    "write_cache": device.original_wce,
                })

                scheduler_val, nr_requests_val, apst_val, wce_val, read_ahead_val = self._get_profile_values(device, profile)

                if scheduler_val and scheduler_val not in device.available_schedulers:
                    warnings.append(f"{device.name}: Scheduler '{scheduler_val}' not available, skipping")
                    scheduler_val = None

                if scheduler_val:
                    if not self._safe_write(str(device.scheduler_path), scheduler_val):
                        warnings.append(f"{device.name}: Failed to set scheduler={scheduler_val}")

                if nr_requests_val is not None:
                    if not self._safe_write(str(device.nr_requests_path), str(nr_requests_val), (self.NR_REQUESTS_MIN, self.NR_REQUESTS_MAX)):
                        warnings.append(f"{device.name}: Failed to set nr_requests={nr_requests_val}")

                if read_ahead_val is not None:
                    if not self._safe_write(str(device.read_ahead_path), str(read_ahead_val), (self.READ_AHEAD_MIN, self.READ_AHEAD_MAX)):
                        warnings.append(f"{device.name}: Failed to set read_ahead_kb={read_ahead_val}")

                if apst_val is not None and device.apst_path:
                    if not self._safe_write(str(device.apst_path), str(apst_val), (self.APST_DISABLED, self.APST_ENABLED)):
                        warnings.append(f"{device.name}: Failed to set APST={apst_val}")

                if wce_val is not None and device.wce_path:
                    if not self._safe_write(str(device.wce_path), str(wce_val), (self.WCE_DISABLED, self.WCE_ENABLED)):
                        warnings.append(f"{device.name}: Failed to set write_cache={wce_val}")

                applied["devices"].append({
                    "block_path": str(device.block_path),
                    "scheduler": scheduler_val,
                    "nr_requests": nr_requests_val,
                    "read_ahead_kb": read_ahead_val,
                    "apst": apst_val,
                    "write_cache": wce_val,
                })

            except (PermissionError, OSError, ValueError) as e:
                warnings.append(f"{device.name}: {e}")

        success = len(applied["devices"]) > 0
        return ApplyResult(success, applied, reverted, warnings, None if success else "No devices were configured")

    def _get_profile_values(
        self, device: SsdDevice, profile: Profile
    ) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int], Optional[int]]:
        if profile == Profile.CUSTOM and self._custom_params:
            cp = self._custom_params
            scheduler = cp.get("scheduler")
            nr_requests = cp.get("nr_requests")
            apst = self.APST_ENABLED if cp.get("apst_enabled") else self.APST_DISABLED if cp.get("apst_enabled") is not None else None
            wce = self.WCE_ENABLED if cp.get("write_cache_enabled") else self.WCE_DISABLED if cp.get("write_cache_enabled") is not None else None
            read_ahead = cp.get("read_ahead_kb")
            return scheduler, nr_requests, apst, wce, read_ahead

        if profile == Profile.SILENT:
            scheduler = self.SCHEDULER_MQ_DEADLINE if self.SCHEDULER_MQ_DEADLINE in device.available_schedulers else self.SCHEDULER_BFQ if self.SCHEDULER_BFQ in device.available_schedulers else None
            return scheduler, 128, self.APST_ENABLED, self.WCE_ENABLED, 256

        if profile == Profile.BALANCED:
            if device.device_type == "nvme":
                scheduler = self.SCHEDULER_NONE if self.SCHEDULER_NONE in device.available_schedulers else None
            else:
                scheduler = self.SCHEDULER_MQ_DEADLINE if self.SCHEDULER_MQ_DEADLINE in device.available_schedulers else self.SCHEDULER_KYBER if self.SCHEDULER_KYBER in device.available_schedulers else None
            return scheduler, device.original_nr_requests, self.APST_ENABLED if device.device_type == "nvme" else None, self.WCE_ENABLED, device.original_read_ahead

        if profile == Profile.PERFORMANCE:
            scheduler = self.SCHEDULER_NONE if self.SCHEDULER_NONE in device.available_schedulers else None
            return scheduler, 4096, self.APST_DISABLED, self.WCE_ENABLED, 8192

        return None, None, None, None, None

    def _read_current_scheduler(self, device: SsdDevice) -> Optional[str]:
        content = self._safe_read(str(device.scheduler_path))
        if content is None:
            return None
        for token in content.split():
            token = token.strip("[]")
            if token:
                return token
        return None

    def _safe_read_int(self, path: Path) -> Optional[int]:
        val = self._safe_read(str(path))
        if val is None:
            return None
        try:
            return int(val)
        except ValueError:
            return None

    def status(self) -> StatusResult:
        devices_data: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {"total_devices": len(self._devices), "nvme_count": 0, "sata_count": 0}

        for device in self._devices:
            current_scheduler = self._read_current_scheduler(device)
            current_nr_requests = self._safe_read_int(device.nr_requests_path)
            current_read_ahead = self._safe_read_int(device.read_ahead_path)
            current_apst = self._safe_read_int(device.apst_path) if device.apst_path else None
            current_wce = self._safe_read_int(device.wce_path) if device.wce_path else None

            if device.device_type == "nvme":
                metrics["nvme_count"] += 1
            else:
                metrics["sata_count"] += 1

            devices_data.append({
                "block_path": str(device.block_path),
                "name": device.name,
                "device_type": device.device_type,
                "model": device.model,
                "firmware": device.firmware,
                "scheduler": current_scheduler,
                "available_schedulers": device.available_schedulers,
                "nr_requests": current_nr_requests,
                "read_ahead_kb": current_read_ahead,
                "apst_enabled": current_apst == self.APST_ENABLED if current_apst is not None else None,
                "write_cache_enabled": current_wce == self.WCE_ENABLED if current_wce is not None else None,
            })

        return StatusResult(self._current_profile, metrics, devices_data)

    def revert(self, previous_state: Dict[str, Any]) -> ApplyResult:
        reverted: Dict[str, Any] = {"devices": []}
        warnings: List[str] = []
        success_count = 0

        for dev_state in previous_state.get("devices", []):
            block_path = Path(dev_state["block_path"])
            device = next((d for d in self._devices if d.block_path == block_path), None)
            if not device:
                warnings.append(f"Device not found: {block_path}")
                continue

            orig_scheduler = dev_state.get("scheduler")
            orig_nr_requests = dev_state.get("nr_requests")
            orig_read_ahead = dev_state.get("read_ahead_kb")
            orig_apst = dev_state.get("apst")
            orig_wce = dev_state.get("write_cache")

            if orig_scheduler is not None:
                if orig_scheduler in device.available_schedulers:
                    if self._safe_write(str(device.scheduler_path), orig_scheduler):
                        success_count += 1
                    else:
                        warnings.append(f"{device.name}: Failed to restore scheduler={orig_scheduler}")
                else:
                    warnings.append(f"{device.name}: Original scheduler '{orig_scheduler}' no longer available")

            if orig_nr_requests is not None:
                if self._safe_write(str(device.nr_requests_path), str(orig_nr_requests), (self.NR_REQUESTS_MIN, self.NR_REQUESTS_MAX)):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore nr_requests={orig_nr_requests}")

            if orig_read_ahead is not None:
                if self._safe_write(str(device.read_ahead_path), str(orig_read_ahead), (self.READ_AHEAD_MIN, self.READ_AHEAD_MAX)):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore read_ahead_kb={orig_read_ahead}")

            if orig_apst is not None and device.apst_path:
                if self._safe_write(str(device.apst_path), str(orig_apst), (self.APST_DISABLED, self.APST_ENABLED)):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore APST={orig_apst}")

            if orig_wce is not None and device.wce_path:
                if self._safe_write(str(device.wce_path), str(orig_wce), (self.WCE_DISABLED, self.WCE_ENABLED)):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore write_cache={orig_wce}")

            reverted["devices"].append({
                "block_path": str(block_path),
                "restored_scheduler": orig_scheduler,
                "restored_nr_requests": orig_nr_requests,
                "restored_read_ahead_kb": orig_read_ahead,
                "restored_apst": orig_apst,
                "restored_write_cache": orig_wce,
            })

        self._current_profile = None
        self._custom_params = None
        return ApplyResult(
            success=success_count > 0,
            applied={},
            reverted=reverted,
            warnings=warnings,
            error=None if success_count > 0 else "No devices were reverted"
        )


def create_ssd_optimizer() -> SsdOptimizer:
    return SsdOptimizer()