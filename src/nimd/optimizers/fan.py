"""Fan optimizer module for PWM-controllable fans via hwmon/thermal interfaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    HardwareOptimizer,
    HardwareType,
    Profile,
    ProbeResult,
    ApplyResult,
    StatusResult,
    InvalidProfile,
    HardwareNotFound,
    SafeModeViolation,
)

logger = logging.getLogger(__name__)


@dataclass
class FanDevice:
    hwmon_path: Path
    name: str
    pwm_enable_path: Path
    pwm_path: Path
    fan_input_path: Optional[Path]
    temp_input_paths: List[Path]
    original_pwm_enable: Optional[int] = None
    original_pwm: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hwmon_path": str(self.hwmon_path),
            "name": self.name,
            "pwm_enable_path": str(self.pwm_enable_path),
            "pwm_path": str(self.pwm_path),
            "fan_input_path": str(self.fan_input_path) if self.fan_input_path else None,
            "temp_input_paths": [str(p) for p in self.temp_input_paths],
            "original_pwm_enable": self.original_pwm_enable,
            "original_pwm": self.original_pwm,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FanDevice":
        return cls(
            hwmon_path=Path(data["hwmon_path"]),
            name=data["name"],
            pwm_enable_path=Path(data["pwm_enable_path"]),
            pwm_path=Path(data["pwm_path"]),
            fan_input_path=Path(data["fan_input_path"]) if data["fan_input_path"] else None,
            temp_input_paths=[Path(p) for p in data["temp_input_paths"]],
            original_pwm_enable=data.get("original_pwm_enable"),
            original_pwm=data.get("original_pwm"),
        )


class FanOptimizer(HardwareOptimizer):
    HARDWARE_TYPE = HardwareType.FAN
    SUPPORTED_PROFILES = [Profile.SILENT, Profile.BALANCED, Profile.PERFORMANCE, Profile.CUSTOM]

    PWM_MIN = 0
    PWM_MAX = 255
    TEMP_MIN = 0
    TEMP_MAX = 120
    HW_MON_BASE = Path("/sys/class/hwmon")
    THERMAL_BASE = Path("/sys/class/thermal")

    SILENT_CURVE: List[Tuple[int, int]] = [
        (30, 30), (40, 35), (50, 45), (60, 55), (70, 70), (80, 100)
    ]
    BALANCED_CURVE: List[Tuple[int, int]] = [
        (30, 30), (40, 45), (50, 60), (60, 75), (70, 100), (80, 255)
    ]
    PERFORMANCE_CURVE: List[Tuple[int, int]] = [
        (25, 40), (35, 60), (45, 85), (55, 120), (65, 180), (75, 255)
    ]

    def __init__(self):
        self._devices: List[FanDevice] = []
        self._current_profile: Optional[Profile] = None
        self._custom_curve: Optional[List[Tuple[int, int]]] = None

    def probe(self) -> ProbeResult:
        self._devices = []
        errors: List[str] = []

        if not self.HW_MON_BASE.exists():
            return ProbeResult(False, [], "hwmon sysfs not found")

        for hwmon_dir in sorted(self.HW_MON_BASE.glob("hwmon*")):
            try:
                device = self._probe_hwmon_dir(hwmon_dir)
                if device:
                    self._devices.append(device)
            except (PermissionError, OSError) as e:
                errors.append(f"{hwmon_dir.name}: {e}")

        if not self._devices:
            return ProbeResult(False, [], "No PWM-controllable fans found" + (f" ({'; '.join(errors)})" if errors else ""))

        devices_data = [d.to_dict() for d in self._devices]
        return ProbeResult(True, devices_data, None)

    def _probe_hwmon_dir(self, hwmon_dir: Path) -> Optional[FanDevice]:
        name_path = hwmon_dir / "name"
        name = self._safe_read(str(name_path)) or hwmon_dir.name

        pwm_enable_paths = sorted(hwmon_dir.glob("pwm*_enable"))
        if not pwm_enable_paths:
            return None

        for pwm_enable_path in pwm_enable_paths:
            pwm_num = pwm_enable_path.stem.replace("pwm", "").replace("_enable", "")
            pwm_path = hwmon_dir / f"pwm{pwm_num}"
            fan_input_path = hwmon_dir / f"fan{pwm_num}_input"

            if not pwm_path.exists():
                continue

            enable_val = self._safe_read(str(pwm_enable_path))
            if enable_val is None:
                continue
            try:
                if int(enable_val) not in (0, 1, 2):
                    continue
            except ValueError:
                continue

            temp_paths = sorted(hwmon_dir.glob("temp*_input"))
            valid_temps = [p for p in temp_paths if self._safe_read(str(p)) is not None]

            return FanDevice(
                hwmon_path=hwmon_dir,
                name=name,
                pwm_enable_path=pwm_enable_path,
                pwm_path=pwm_path,
                fan_input_path=fan_input_path if fan_input_path.exists() else None,
                temp_input_paths=valid_temps,
            )

        return None

    def apply(self, profile: Profile, custom_params: Optional[Dict[str, Any]] = None) -> ApplyResult:
        if profile not in self.SUPPORTED_PROFILES:
            raise InvalidProfile(f"Unsupported profile: {profile.value}")

        if not self._devices:
            probe_result = self.probe()
            if not probe_result.available:
                raise HardwareNotFound(probe_result.error or "No fan devices available")

        if profile == Profile.CUSTOM:
            curve = custom_params.get("curve") if custom_params else None
            if not curve or not isinstance(curve, list) or len(curve) < 2:
                raise InvalidProfile("CUSTOM profile requires 'curve' parameter: list of (temp_c, pwm%) tuples")
            self._custom_curve = self._validate_curve(curve)
        else:
            self._custom_curve = None

        self._current_profile = profile
        applied: Dict[str, Any] = {"profile": profile.value, "devices": []}
        reverted: Dict[str, Any] = {"devices": []}
        warnings: List[str] = []

        for device in self._devices:
            try:
                orig_enable = self._safe_read(str(device.pwm_enable_path))
                orig_pwm = self._safe_read(str(device.pwm_path))

                device.original_pwm_enable = int(orig_enable) if orig_enable is not None else None
                device.original_pwm = int(orig_pwm) if orig_pwm is not None else None

                reverted["devices"].append({
                    "hwmon_path": str(device.hwmon_path),
                    "pwm_enable": device.original_pwm_enable,
                    "pwm": device.original_pwm,
                })

                if not self._safe_write(str(device.pwm_enable_path), "1"):
                    warnings.append(f"{device.name}: Failed to set manual mode (pwm_enable=1)")
                    continue

                temp = self._read_highest_temp(device)
                if temp is None:
                    warnings.append(f"{device.name}: No temperature reading available")
                    temp = 40

                pwm_value = self._calculate_pwm(temp, profile)
                if not self._safe_write(str(device.pwm_path), str(pwm_value), (self.PWM_MIN, self.PWM_MAX)):
                    warnings.append(f"{device.name}: Failed to write PWM value {pwm_value}")
                    continue

                applied["devices"].append({
                    "hwmon_path": str(device.hwmon_path),
                    "temp_c": temp,
                    "pwm_value": pwm_value,
                    "pwm_percent": round(pwm_value * 100 / 255),
                })

            except (PermissionError, OSError, ValueError) as e:
                warnings.append(f"{device.name}: {e}")

        success = len(applied["devices"]) > 0
        return ApplyResult(success, applied, reverted, warnings, None if success else "No devices were configured")

    def _read_highest_temp(self, device: FanDevice) -> Optional[int]:
        temps: List[int] = []

        for temp_path in device.temp_input_paths:
            val = self._safe_read(str(temp_path))
            if val is not None:
                try:
                    temp_c = int(val) // 1000
                    if self.TEMP_MIN <= temp_c <= self.TEMP_MAX:
                        temps.append(temp_c)
                except ValueError:
                    pass

        if not temps:
            for thermal_zone in self.THERMAL_BASE.glob("thermal_zone*"):
                temp_path = thermal_zone / "temp"
                val = self._safe_read(str(temp_path))
                if val is not None:
                    try:
                        temp_c = int(val) // 1000
                        if self.TEMP_MIN <= temp_c <= self.TEMP_MAX:
                            temps.append(temp_c)
                    except ValueError:
                        pass

        return max(temps) if temps else None

    def _calculate_pwm(self, temp_c: int, profile: Profile) -> int:
        curve = self._get_curve(profile)
        return self._interpolate_curve(temp_c, curve)

    def _get_curve(self, profile: Profile) -> List[Tuple[int, int]]:
        if profile == Profile.CUSTOM and self._custom_curve:
            return self._custom_curve
        elif profile == Profile.SILENT:
            return self.SILENT_CURVE
        elif profile == Profile.BALANCED:
            return self.BALANCED_CURVE
        elif profile == Profile.PERFORMANCE:
            return self.PERFORMANCE_CURVE
        return self.BALANCED_CURVE

    def _validate_curve(self, curve: List[Any]) -> List[Tuple[int, int]]:
        if len(curve) < 2:
            raise InvalidProfile("Curve must have at least 2 points")
        validated: List[Tuple[int, int]] = []
        for point in curve:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise InvalidProfile(f"Invalid curve point: {point}, expected (temp_c, pwm_percent)")
            temp_c, pwm_pct = point
            if not isinstance(temp_c, (int, float)) or not isinstance(pwm_pct, (int, float)):
                raise InvalidProfile(f"Curve values must be numeric: {point}")
            if not (self.TEMP_MIN <= temp_c <= self.TEMP_MAX):
                raise SafeModeViolation(f"Temperature {temp_c}°C out of safe range [{self.TEMP_MIN}, {self.TEMP_MAX}]")
            if not (0 <= pwm_pct <= 100):
                raise SafeModeViolation(f"PWM percentage {pwm_pct}% out of range [0, 100]")
            pwm_val = round(pwm_pct * 255 / 100)
            validated.append((int(temp_c), pwm_val))

        validated.sort(key=lambda x: x[0])
        return validated

    def _interpolate_curve(self, temp_c: int, curve: List[Tuple[int, int]]) -> int:
        if temp_c <= curve[0][0]:
            return curve[0][1]
        if temp_c >= curve[-1][0]:
            return curve[-1][1]

        for i in range(len(curve) - 1):
            t1, p1 = curve[i]
            t2, p2 = curve[i + 1]
            if t1 <= temp_c <= t2:
                if t2 == t1:
                    return p1
                ratio = (temp_c - t1) / (t2 - t1)
                return round(p1 + ratio * (p2 - p1))

        return curve[-1][1]

    def status(self) -> StatusResult:
        devices_data: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {"total_devices": len(self._devices), "active_devices": 0}

        for device in self._devices:
            enable_val = self._safe_read(str(device.pwm_enable_path))
            pwm_val = self._safe_read(str(device.pwm_path))
            fan_rpm = None
            if device.fan_input_path:
                rpm_val = self._safe_read(str(device.fan_input_path))
                if rpm_val is not None:
                    try:
                        fan_rpm = int(rpm_val)
                    except ValueError:
                        pass

            temps: List[int] = []
            for temp_path in device.temp_input_paths:
                val = self._safe_read(str(temp_path))
                if val is not None:
                    try:
                        temps.append(int(val) // 1000)
                    except ValueError:
                        pass

            device_info = {
                "hwmon_path": str(device.hwmon_path),
                "name": device.name,
                "pwm_enable": int(enable_val) if enable_val is not None else None,
                "pwm_value": int(pwm_val) if pwm_val is not None else None,
                "pwm_percent": round(int(pwm_val) * 100 / 255) if pwm_val is not None else None,
                "fan_rpm": fan_rpm,
                "temperatures_c": temps,
                "max_temp_c": max(temps) if temps else None,
            }
            devices_data.append(device_info)

            if enable_val == "1":
                metrics["active_devices"] += 1

        return StatusResult(self._current_profile, metrics, devices_data)

    def revert(self, previous_state: Dict[str, Any]) -> ApplyResult:
        reverted: Dict[str, Any] = {"devices": []}
        warnings: List[str] = []
        success_count = 0

        for dev_state in previous_state.get("devices", []):
            hwmon_path = Path(dev_state["hwmon_path"])
            device = next((d for d in self._devices if d.hwmon_path == hwmon_path), None)
            if not device:
                warnings.append(f"Device not found: {hwmon_path}")
                continue

            orig_enable = dev_state.get("pwm_enable")
            orig_pwm = dev_state.get("pwm")

            if orig_enable is not None:
                if self._safe_write(str(device.pwm_enable_path), str(orig_enable)):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore pwm_enable={orig_enable}")

            if orig_pwm is not None:
                if self._safe_write(str(device.pwm_path), str(orig_pwm), (self.PWM_MIN, self.PWM_MAX)):
                    success_count += 1
                else:
                    warnings.append(f"{device.name}: Failed to restore pwm={orig_pwm}")

            reverted["devices"].append({
                "hwmon_path": str(hwmon_path),
                "restored_pwm_enable": orig_enable,
                "restored_pwm": orig_pwm,
            })

        self._current_profile = None
        return ApplyResult(
            success=success_count > 0,
            applied={},
            reverted=reverted,
            warnings=warnings,
            error=None if success_count > 0 else "No devices were reverted"
        )


def create_fan_optimizer() -> FanOptimizer:
    return FanOptimizer()