"""HDD optimizer module for I/O scheduler, read-ahead, APM, and spindown via sysfs and hdparm."""

from __future__ import annotations

import logging
import re
import subprocess
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
class HddDevice:
    block_path: Path
    name: str
    device_path: Path
    rotational: bool
    scheduler_path: Path
    nr_requests_path: Path
    read_ahead_path: Path
    model: str
    firmware: str
    available_schedulers: List[str] = field(default_factory=list)
    original_scheduler: Optional[str] = None
    original_nr_requests: Optional[int] = None
    original_read_ahead: Optional[int] = None
    original_apm: Optional[int] = None
    original_spindown: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_path": str(self.block_path),
            "name": self.name,
            "device_path": str(self.device_path),
            "rotational": self.rotational,
            "scheduler_path": str(self.scheduler_path),
            "nr_requests_path": str(self.nr_requests_path),
            "read_ahead_path": str(self.read_ahead_path),
            "model": self.model,
            "firmware": self.firmware,
            "available_schedulers": self.available_schedulers,
            "original_scheduler": self.original_scheduler,
            "original_nr_requests": self.original_nr_requests,
            "original_read_ahead": self.original_read_ahead,
            "original_apm": self.original_apm,
            "original_spindown": self.original_spindown,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HddDevice":
        return cls(
            block_path=Path(data["block_path"]),
            name=data["name"],
            device_path=Path(data["device_path"]),
            rotational=data["rotational"],
            scheduler_path=Path(data["scheduler_path"]),
            nr_requests_path=Path(data["nr_requests_path"]),
            read_ahead_path=Path(data["read_ahead_path"]),
            model=data["model"],
            firmware=data["firmware"],
            available_schedulers=data.get("available_schedulers", []),
            original_scheduler=data.get("original_scheduler"),
            original_nr_requests=data.get("original_nr_requests"),
            original_read_ahead=data.get("original_read_ahead"),
            original_apm=data.get("original_apm"),
            original_spindown=data.get("original_spindown"),
        )


class HddOptimizer(HardwareOptimizer):
    HARDWARE_TYPE = HardwareType.HDD
    SUPPORTED_PROFILES = [Profile.SILENT, Profile.BALANCED, Profile.PERFORMANCE, Profile.CUSTOM]

    BLOCK_BASE = Path("/sys/block")
    HD_PATTERN = re.compile(r"^sd[a-z]+$")

    READ_AHEAD_MIN = 0
    READ_AHEAD_MAX = 16384
    APM_MIN = 1
    APM_MAX = 254
    SPINDOWN_MIN = 0
    SPINDOWN_MAX = 255

    SCHEDULER_MQ_DEADLINE = "mq-deadline"
    SCHEDULER_BFQ = "bfq"
    SCHEDULER_KYBER = "kyber"
    VALID_SCHEDULERS: Set[str] = {SCHEDULER_MQ_DEADLINE, SCHEDULER_BFQ, SCHEDULER_KYBER}

    HDPARM_PATH = "/usr/sbin/hdparm"

    SILENT_READ_AHEAD = 128
    SILENT_APM = 128
    SILENT_SPINDOWN = 240

    BALANCED_READ_AHEAD = 256
    BALANCED_APM = 254
    BALANCED_SPINDOWN = 0

    PERFORMANCE_READ_AHEAD = 8192
    PERFORMANCE_APM = 254
    PERFORMANCE_SPINDOWN = 0

    def __init__(self):
        self._devices: List[HddDevice] = []
        self._current_profile: Optional[Profile] = None
        self._custom_params: Optional[Dict[str, Any]] = None

    def probe(self) -> ProbeResult:
        self._devices = []
        errors: List[str] = []

        if not self.BLOCK_BASE.exists():
            return ProbeResult(False, [], "Block sysfs not found at /sys/block")

        if not Path(self.HDPARM_PATH).exists():
            errors.append(f"hdparm not found at {self.HDPARM_PATH}")

        for block_dir in sorted(self.BLOCK_BASE.iterdir()):
            try:
                device = self._probe_block_device(block_dir)
                if device:
                    self._devices.append(device)
            except (PermissionError, OSError) as e:
                errors.append(f"{block_dir.name}: {e}")

        if not self._devices:
            return ProbeResult(False, [], "No HDD devices found" + (f" ({'; '.join(errors)})" if errors else ""))

        return ProbeResult(True, [d.to_dict() for d in self._devices], None)

    def _probe_block_device(self, block_dir: Path) -> Optional[HddDevice]:
        name = block_dir.name
        if not self.HD_PATTERN.match(name):
            return None

        rotational_path = block_dir / "queue" / "rotational"
        rotational_val = self._safe_read(str(rotational_path))
        if rotational_val is None:
            return None
        try:
            rotational = int(rotational_val) != 0
        except ValueError:
            return None
        if not rotational:
            return None

        scheduler_path = block_dir / "queue" / "scheduler"
        nr_requests_path = block_dir / "queue" / "nr_requests"
        read_ahead_path = block_dir / "queue" / "read_ahead_kb"

        for p in (scheduler_path, nr_requests_path, read_ahead_path):
            if not p.exists():
                return None

        available_schedulers = self._parse_available_schedulers(scheduler_path)
        if not available_schedulers:
            return None

        model = self._read_model(block_dir)
        firmware = self._read_firmware(block_dir)

        device_path = Path(f"/dev/{name}")
        if not device_path.exists():
            return None

        return HddDevice(
            block_path=block_dir,
            name=name,
            device_path=device_path,
            rotational=rotational,
            scheduler_path=scheduler_path,
            nr_requests_path=nr_requests_path,
            read_ahead_path=read_ahead_path,
            model=model,
            firmware=firmware,
            available_schedulers=available_schedulers,
        )

    def _parse_available_schedulers(self, scheduler_path: Path) -> List[str]:
        content = self._safe_read(str(scheduler_path))
        if content is None:
            return []
        return [t.strip("[]") for t in content.split() if t.strip("[]") in self.VALID_SCHEDULERS]

    def _read_model(self, block_dir: Path) -> str:
        model_path = block_dir / "device" / "model"
        return self._safe_read(str(model_path)) or "unknown"

    def _read_firmware(self, block_dir: Path) -> str:
        fw_path = block_dir / "device" / "rev"
        return self._safe_read(str(fw_path)) or "unknown"

    def _run_hdparm(self, args: List[str]) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.HDPARM_PATH] + args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0, result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError, OSError, PermissionError) as e:
            logger.debug("hdparm failed: %s", e)
            return False, str(e)

    def _read_apm(self, device_path: Path) -> Optional[int]:
        success, output = self._run_hdparm(["-B", str(device_path)])
        if not success:
            return None
        match = re.search(r"APM level\s*=\s*(\d+)", output)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _read_spindown(self, device_path: Path) -> Optional[int]:
        success, output = self._run_hdparm(["-I", str(device_path)])
        if not success:
            return None
        match = re.search(r"Power management.*standby.*?(\d+)", output, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _set_apm(self, device_path: Path, value: int) -> bool:
        if not (self.APM_MIN <= value <= self.APM_MAX):
            return False
        success, _ = self._run_hdparm(["-B", str(value), str(device_path)])
        return success

    def _set_spindown(self, device_path: Path, value: int) -> bool:
        if not (self.SPINDOWN_MIN <= value <= self.SPINDOWN_MAX):
            return False
        success, _ = self._run_hdparm(["-S", str(value), str(device_path)])
        return success

    def apply(self, profile: Profile, custom_params: Optional[Dict[str, Any]] = None) -> ApplyResult:
        if profile not in self.SUPPORTED_PROFILES:
            raise InvalidProfile(f"Unsupported profile: {profile.value}")

        if not self._devices:
            probe_result = self.probe()
            if not probe_result.available:
                raise HardwareNotFound(probe_result.error or "No HDD devices available")

        if not self._require_root():
            raise PermissionDenied("Root privileges required to apply HDD optimizations")

        if profile == Profile.CUSTOM:
            self._custom_params = custom_params or {}
            scheduler = self._custom_params.get("scheduler")
            read_ahead = self._custom_params.get("read_ahead_kb")
            apm_level = self._custom_params.get("apm_level")
            spindown_sec = self._custom_params.get("spindown_sec")

            if scheduler and scheduler not in self.VALID_SCHEDULERS:
                raise InvalidProfile(f"Invalid scheduler: {scheduler}")
            if read_ahead is not None and not (self.READ_AHEAD_MIN <= read_ahead <= self.READ_AHEAD_MAX):
                raise SafeModeViolation(f"read_ahead_kb must be in [{self.READ_AHEAD_MIN}, {self.READ_AHEAD_MAX}]")
            if apm_level is not None and not (self.APM_MIN <= apm_level <= self.APM_MAX):
                raise SafeModeViolation(f"apm_level must be in [{self.APM_MIN}, {self.APM_MAX}]")
            if spindown_sec is not None and not (self.SPINDOWN_MIN <= spindown_sec <= self.SPINDOWN_MAX):
                raise SafeModeViolation(f"spindown must be in [{self.SPINDOWN_MIN}, {self.SPINDOWN_MAX}] (5s units)")
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
                device.original_apm = self._read_apm(device.device_path)
                device.original_spindown = self._read_spindown(device.device_path)

                reverted["devices"].append({
                    "block_path": str(device.block_path),
                    "scheduler": device.original_scheduler,
                    "nr_requests": device.original_nr_requests,
                    "read_ahead_kb": device.original_read_ahead,
                    "apm": device.original_apm,
                    "spindown": device.original_spindown,
                })

                scheduler_val, read_ahead_val, apm_val, spindown_val = self._get_profile_values(device, profile)

                if scheduler_val and scheduler_val not in device.available_schedulers:
                    warnings.append(f"{device.name}: Scheduler '{scheduler_val}' not available, skipping")
                    scheduler_val = None

                if scheduler_val:
                    if not self._safe_write(str(device.scheduler_path), scheduler_val):
                        warnings.append(f"{device.name}: Failed to set scheduler={scheduler_val}")

                if read_ahead_val is not None:
                    if not self._safe_write(str(device.read_ahead_path), str(read_ahead_val), (self.READ_AHEAD_MIN, self.READ_AHEAD_MAX)):
                        warnings.append(f"{device.name}: Failed to set read_ahead_kb={read_ahead_val}")

                if apm_val is not None:
                    if not self._set_apm(device.device_path, apm_val):
                        warnings.append(f"{device.name}: Failed to set APM={apm_val}")

                if spindown_val is not None:
                    if not self._set_spindown(device.device_path, spindown_val):
                        warnings.append(f"{device.name}: Failed to set spindown={spindown_val}")

                applied["devices"].append({
                    "block_path": str(device.block_path),
                    "scheduler": scheduler_val,
                    "read_ahead_kb": read_ahead_val,
                    "apm": apm_val,
                    "spindown": spindown_val,
                })

            except (PermissionError, OSError, ValueError) as e:
                warnings.append(f"{device.name}: {e}")

        success = len(applied["devices"]) > 0
        return ApplyResult(success, applied, reverted, warnings, None if success else "No devices were configured")

    def _get_profile_values(
        self, device: HddDevice, profile: Profile
    ) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
        if profile == Profile.CUSTOM and self._custom_params:
            cp = self._custom_params
            return (
                cp.get("scheduler"),
                cp.get("read_ahead_kb"),
                cp.get("apm_level"),
                cp.get("spindown_sec"),
            )

        if profile == Profile.SILENT:
            scheduler = self.SCHEDULER_BFQ if self.SCHEDULER_BFQ in device.available_schedulers else None
            return scheduler, self.SILENT_READ_AHEAD, self.SILENT_APM, self.SILENT_SPINDOWN

        if profile == Profile.BALANCED:
            scheduler = self.SCHEDULER_MQ_DEADLINE if self.SCHEDULER_MQ_DEADLINE in device.available_schedulers else self.SCHEDULER_KYBER if self.SCHEDULER_KYBER in device.available_schedulers else None
            return scheduler, self.BALANCED_READ_AHEAD, self.BALANCED_APM, self.BALANCED_SPINDOWN

        if profile == Profile.PERFORMANCE:
            scheduler = self.SCHEDULER_MQ_DEADLINE if self.SCHEDULER_MQ_DEADLINE in device.available_schedulers else None
            return scheduler, self.PERFORMANCE_READ_AHEAD, self.PERFORMANCE_APM, self.PERFORMANCE_SPINDOWN

        return None, None, None, None

    def _read_current_scheduler(self, device: HddDevice) -> Optional[str]:
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
        metrics: Dict[str, Any] = {"total_devices": len(self._devices)}

        for device in self._devices:
            current_scheduler = self._read_current_scheduler(device)
            current_read_ahead = self._safe_read_int(device.read_ahead_path)
            current_apm = self._read_apm(device.device_path)
            current_spindown = self._read_spindown(device.device_path)

            metrics["total_devices"] += 0

            devices_data.append({
                "block_path": str(device.block_path),
                "name": device.name,
                "device_path": str(device.device_path),
                "model": device.model,
                "firmware": device.firmware,
                "scheduler": current_scheduler,
                "available_schedulers": device.available_schedulers,
                "read_ahead_kb": current_read_ahead,
                "apm_level": current_apm,
                "spindown_timeout": current_spindown,
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
            orig_read_ahead = dev_state.get("read_ahead_kb")
            orig_apm = dev_state.get("apm")
            orig_spindown = dev_state.get("spindown")

            if orig_scheduler is not None:
                if orig_scheduler in device.available_schedulers:
                    if self._safe_write(str(device.scheduler_path), orig_scheduler):
                        success_count += 1
                    else:
                        warnings.append(f"{device.name}: Failed to restore scheduler={orig_scheduler}")
                else:
                    warnings.append(f"{device.name}: Original scheduler '{orig_scheduler}' no longer available")

            if orig_read_ahead is not None:
                if self._safe_write(str(device.read_ahead_path), str(orig_read_ahead), (self.READ_AHEAD_MIN, self.READ_AHEAD_MAX)):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore read_ahead_kb={orig_read_ahead}")

            if orig_apm is not None:
                if self._set_apm(device.device_path, orig_apm):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore APM={orig_apm}")

            if orig_spindown is not None:
                if self._set_spindown(device.device_path, orig_spindown):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore spindown={orig_spindown}")

            reverted["devices"].append({
                "block_path": str(block_path),
                "restored_scheduler": orig_scheduler,
                "restored_read_ahead_kb": orig_read_ahead,
                "restored_apm": orig_apm,
                "restored_spindown": orig_spindown,
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


def create_hdd_optimizer() -> HddOptimizer:
    return HddOptimizer()