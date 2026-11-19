"""GPU optimizer module for NVIDIA, AMD, and Intel GPUs via vendor tools and sysfs."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
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
    PermissionDenied,
)

logger = logging.getLogger(__name__)


@dataclass
class GPUDevice:
    index: int
    vendor: str
    name: str
    uuid: str
    bus_id: str
    driver_version: str
    paths: Dict[str, Optional[Path]] = field(default_factory=dict)
    original: Dict[str, Any] = field(default_factory=dict)

    def path(self, key: str) -> Optional[Path]:
        return self.paths.get(key)

    def set_path(self, key: str, p: Path) -> None:
        self.paths[key] = p

    def orig(self, key: str, default: Any = None) -> Any:
        return self.original.get(key, default)

    def set_orig(self, key: str, val: Any) -> None:
        self.original[key] = val

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "vendor": self.vendor,
            "name": self.name,
            "uuid": self.uuid,
            "bus_id": self.bus_id,
            "driver_version": self.driver_version,
            "paths": {k: str(v) if v else None for k, v in self.paths.items()},
            "original": self.original,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GPUDevice":
        dev = cls(
            index=data["index"],
            vendor=data["vendor"],
            name=data["name"],
            uuid=data["uuid"],
            bus_id=data["bus_id"],
            driver_version=data["driver_version"],
            paths={k: Path(v) if v else None for k, v in data.get("paths", {}).items()},
            original=data.get("original", {}),
        )
        return dev


class GpuOptimizer(HardwareOptimizer):
    HARDWARE_TYPE = HardwareType.GPU
    SUPPORTED_PROFILES = [Profile.SILENT, Profile.BALANCED, Profile.PERFORMANCE, Profile.CUSTOM]

    POWER_FACTORS = {Profile.SILENT: 0.7, Profile.BALANCED: 1.0, Profile.PERFORMANCE: 1.0}
    NVIDIA_SMI = "nvidia-smi"
    ROCM_SMI = "rocm-smi"
    INTEL_GPU_TOP = "intel_gpu_top"
    DRM_BASE = Path("/sys/class/drm")
    HWMON_BASE = Path("/sys/class/hwmon")

    def __init__(self) -> None:
        self._devices: List[GPUDevice] = []
        self._current_profile: Optional[Profile] = None
        self._custom_params: Optional[Dict[str, Any]] = None

    def probe(self) -> ProbeResult:
        self._devices = []
        for probe_fn in (self._probe_nvidia, self._probe_amd, self._probe_intel):
            self._devices.extend(probe_fn())
        if not self._devices:
            return ProbeResult(False, [], "No GPU devices found")
        return ProbeResult(True, [d.to_dict() for d in self._devices], None)

    def _probe_nvidia(self) -> List[GPUDevice]:
        devices: List[GPUDevice] = []
        try:
            out = subprocess.run(
                [
                    self.NVIDIA_SMI,
                    "--query-gpu=index,name,uuid,pci.bus_id,driver_version,power.limit,power.default_limit,power.min_limit,power.max_limit",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if out.returncode != 0:
                return devices
            for line in out.stdout.strip().splitlines():
                p = [x.strip() for x in line.split(",")]
                if len(p) < 9:
                    continue
                dev = GPUDevice(int(p[0]), "nvidia", p[1], p[2], p[3], p[4])
                pw_min = float(p[7]) if p[7] != "[Not Supported]" else 0
                pw_max = float(p[8]) if p[8] != "[Not Supported]" else 0
                for hw in self.HWMON_BASE.glob("hwmon*"):
                    if self._safe_read(str(hw / "name")) == "nvidia":
                        dev.set_path("power_limit", hw / "power1_cap")
                        dev.set_path("power_min", hw / "power1_cap_min")
                        dev.set_path("power_max", hw / "power1_cap_max")
                        dev.set_path("temp", hw / "temp1_input")
                        dev.set_path("power_draw", hw / "power1_input")
                        dev.set_path("util_gpu", hw / "gpu_busy_percent")
                        dev.set_path("util_mem", hw / "vram_busy_percent")
                        dev.set_path("clk_gfx", hw / "freq1_input")
                        dev.set_path("clk_mem", hw / "freq2_input")
                        break
                if pw_min and pw_max:
                    dev.set_orig("power_min_w", int(pw_min))
                    dev.set_orig("power_max_w", int(pw_max))
                    dev.set_orig("power_limit", int(float(p[6]) * 1e6) if p[6] != "[Not Supported]" else int(pw_max * 1e6))
                devices.append(dev)
        except Exception as e:
            logger.debug(f"NVIDIA probe failed: {e}")
        return devices

    def _probe_amd(self) -> List[GPUDevice]:
        devices: List[GPUDevice] = []
        try:
            out = subprocess.run(
                [self.ROCM_SMI, "--showproductname", "--showuniqueid", "--showdriverversion", "--csv"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            rocm_data: Dict[str, Dict[str, str]] = {}
            if out.returncode == 0:
                for line in out.stdout.strip().splitlines()[1:]:
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) >= 4:
                        idx = parts[0]
                        rocm_data[idx] = {
                            "name": parts[1],
                            "uuid": parts[2],
                            "driver": parts[3],
                        }
        except Exception:
            rocm_data = {}

        for card in sorted(self.DRM_BASE.glob("card*")):
            dev_path = card / "device"
            if not dev_path.exists() or self._safe_read(str(dev_path / "vendor")) != "0x1002":
                continue
            idx = len(devices)
            rocm = rocm_data.get(str(idx), {})
            dev = GPUDevice(
                idx,
                "amd",
                rocm.get("name") or self._safe_read(str(dev_path / "product_name")) or card.name,
                rocm.get("uuid") or self._safe_read(str(next(dev_path.glob("*unique*"), ""))) or f"amd-{card.name}",
                self._read_pci_slot(dev_path) or f"pci-{card.name}",
                rocm.get("driver") or self._safe_read(str(dev_path / "driver" / "module" / "version")) or "amdgpu",
            )
            for hw in self.HWMON_BASE.glob("hwmon*"):
                if "amdgpu" in (self._safe_read(str(hw / "name")) or ""):
                    dev.set_path("power_limit", hw / "power1_cap")
                    dev.set_path("power_min", hw / "power1_cap_min")
                    dev.set_path("power_max", hw / "power1_cap_max")
                    dev.set_path("temp", hw / "temp1_input")
                    dev.set_path("power_draw", hw / "power1_input")
                    dev.set_path("util_gpu", hw / "gpu_busy_percent")
                    dev.set_path("util_mem", hw / "vram_busy_percent")
                    dev.set_path("clk_gfx", hw / "freq1_input")
                    dev.set_path("clk_mem", hw / "freq2_input")
                    dev.set_path("perf_level", dev_path / "power_dpm_force_performance_level")
                    dev.set_path("pp_table", dev_path / "pp_table")
                    break
            devices.append(dev)
        return devices

    def _probe_intel(self) -> List[GPUDevice]:
        devices: List[GPUDevice] = []
        try:
            out = subprocess.run(
                [self.INTEL_GPU_TOP, "-J", "-o", "-", "-s", "100"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            intel_json: Dict[str, Any] = {}
            if out.returncode == 0:
                import json
                intel_json = json.loads(out.stdout)
        except Exception:
            intel_json = {}

        for card in sorted(self.DRM_BASE.glob("card*")):
            dev_path = card / "device"
            if not dev_path.exists() or self._safe_read(str(dev_path / "vendor")) != "0x8086":
                continue
            if (cls := self._safe_read(str(dev_path / "class"))) and not cls.startswith("0x03"):
                continue
            idx = len(devices)
            dev = GPUDevice(
                idx,
                "intel",
                self._safe_read(str(dev_path / "product_name")) or card.name,
                f"intel-{card.name}",
                self._read_pci_slot(dev_path) or f"pci-{card.name}",
                "i915",
            )
            for hw in self.HWMON_BASE.glob("hwmon*"):
                hw_name = self._safe_read(str(hw / "name")) or ""
                if any(x in hw_name for x in ("i915", "intel")):
                    dev.set_path("power_limit", hw / "power1_cap")
                    dev.set_path("power_min", hw / "power1_cap_min")
                    dev.set_path("power_max", hw / "power1_cap_max")
                    dev.set_path("temp", hw / "temp1_input")
                    dev.set_path("power_draw", hw / "power1_input")
                    dev.set_path("util_gpu", hw / "gpu_busy_percent")
                    dev.set_path("mem_used", hw / "vram_used_bytes")
                    dev.set_path("mem_total", hw / "vram_total_bytes")
                    break
            devices.append(dev)
        return devices

    def _read_pci_slot(self, dev_path: Path) -> Optional[str]:
        uevent = dev_path / "uevent"
        if uevent.exists():
            for line in (self._safe_read(str(uevent)) or "").splitlines():
                if line.startswith("PCI_SLOT_NAME="):
                    return line.split("=", 1)[1]
        return None

    def apply(self, profile: Profile, custom_params: Optional[Dict[str, Any]] = None) -> ApplyResult:
        if profile not in self.SUPPORTED_PROFILES:
            raise InvalidProfile(f"Unsupported profile: {profile.value}")
        if not self._devices:
            probe = self.probe()
            if not probe.available:
                raise HardwareNotFound(probe.error or "No GPU devices available")

        if profile == Profile.CUSTOM:
            if not custom_params or not any(custom_params.get(k) for k in ("power_limit_w", "core_clock_offset", "mem_clock_offset")):
                raise InvalidProfile("CUSTOM requires power_limit_w, core_clock_offset, or mem_clock_offset")
            self._custom_params = custom_params
        else:
            self._custom_params = None

        self._current_profile = profile
        applied: Dict[str, Any] = {"profile": profile.value, "devices": []}
        reverted: Dict[str, Any] = {"devices": []}
        warns: List[str] = []

        for dev in self._devices:
            try:
                reverted["devices"].append(self._capture_state(dev))
                if res := self._apply_dev(dev, profile):
                    applied["devices"].append(res)
                else:
                    warns.append(f"{dev.name}: no settings applied")
            except Exception as e:
                warns.append(f"{dev.name}: {e}")

        success = bool(applied["devices"])
        return ApplyResult(success, applied, reverted, warns, None if success else "No devices configured")

    def _capture_state(self, dev: GPUDevice) -> Dict[str, Any]:
        state = {"index": dev.index, "vendor": dev.vendor, "uuid": dev.uuid}
        for key in ("power_limit", "core_clock_offset", "mem_clock_offset", "perf_level"):
            p = dev.path(key)
            if p and p.exists():
                val = self._safe_read(str(p))
                if val:
                    try:
                        dev.set_orig(key, int(val))
                        state[key] = dev.orig(key)
                    except ValueError:
                        pass
        return state

    def _apply_dev(self, dev: GPUDevice, profile: Profile) -> Optional[Dict[str, Any]]:
        applied = {"index": dev.index, "vendor": dev.vendor, "uuid": dev.uuid, "settings": {}}
        if not self._require_root():
            return None
        if dev.vendor == "nvidia":
            self._apply_nvidia(dev, profile, applied)
        elif dev.vendor == "amd":
            self._apply_amd(dev, profile, applied)
        elif dev.vendor == "intel":
            self._apply_intel(dev, profile, applied)
        return applied if applied["settings"] else None

    def _set_power_limit(self, dev: GPUDevice, profile: Profile, applied: Dict[str, Any]) -> None:
        pmin, pmax = dev.path("power_min"), dev.path("power_max")
        if not (pmin and pmax and pmin.exists() and pmax.exists()):
            return
        min_uw = int(self._safe_read(str(pmin)) or 0)
        max_uw = int(self._safe_read(str(pmax)) or 0)
        if not (min_uw and max_uw):
            return
        min_w, max_w = min_uw // 1_000_000, max_uw // 1_000_000
        if profile == Profile.CUSTOM and self._custom_params:
            target_w = self._custom_params.get("power_limit_w", max_w)
        else:
            target_w = int(max_w * self.POWER_FACTORS.get(profile, 1.0))
        target_w = max(min_w, min(max_w, target_w))
        if self._safe_write(str(dev.path("power_limit")), str(target_w * 1_000_000), (min_uw, max_uw)):
            applied["settings"]["power_limit_w"] = target_w

    def _apply_nvidia(self, dev: GPUDevice, profile: Profile, applied: Dict[str, Any]) -> None:
        self._set_power_limit(dev, profile, applied)
        core = mem = 0
        if profile == Profile.CUSTOM and self._custom_params:
            core, mem = self._custom_params.get("core_clock_offset", 0), self._custom_params.get("mem_clock_offset", 0)
        elif profile == Profile.PERFORMANCE:
            core, mem = 100, 500
        elif profile == Profile.SILENT:
            core, mem = -100, -200
        for off, name, val in [(core, "core_clock_offset", "core"), (mem, "mem_clock_offset", "memory")]:
            if off:
                try:
                    subprocess.run(
                        [self.NVIDIA_SMI, "-i", str(dev.index), "-ac", f"{off if name == 'core_clock_offset' else 0},{off if name == 'mem_clock_offset' else 0}"],
                        capture_output=True,
                        timeout=10,
                        check=True,
                    )
                    applied["settings"][name] = off
                except subprocess.SubprocessError:
                    pass

    def _apply_amd(self, dev: GPUDevice, profile: Profile, applied: Dict[str, Any]) -> None:
        self._set_power_limit(dev, profile, applied)
        if pl := dev.path("perf_level"):
            level = "auto"
            if profile == Profile.SILENT:
                level = "low"
            elif profile == Profile.PERFORMANCE:
                level = "high"
            elif profile == Profile.CUSTOM and self._custom_params:
                level = self._custom_params.get("perf_level", "auto")
            if self._safe_write(str(pl), level):
                applied["settings"]["perf_level"] = level
        pp_tbl = dev.path("pp_table")
        if pp_tbl and pp_tbl.exists():
            core = mem = 0
            if profile == Profile.CUSTOM and self._custom_params:
                core, mem = self._custom_params.get("core_clock_offset", 0), self._custom_params.get("mem_clock_offset", 0)
            elif profile == Profile.PERFORMANCE:
                core, mem = 5, 10
            elif profile == Profile.SILENT:
                core, mem = -5, -10
            if core or mem:
                applied["settings"].update(
                    {"pp_table_modified": True, "core_clock_offset_pct": core, "mem_clock_offset_pct": mem}
                )
        if profile == Profile.CUSTOM and self._custom_params:
            if (core_off := self._custom_params.get("core_clock_offset")) is not None:
                try:
                    subprocess.run(
                        [self.ROCM_SMI, "--setclk", f"{core_off}", "-d", str(dev.index)],
                        capture_output=True,
                        timeout=10,
                        check=True,
                    )
                    applied["settings"]["core_clock_offset_mhz"] = core_off
                except subprocess.SubprocessError:
                    pass
            if (mem_off := self._custom_params.get("mem_clock_offset")) is not None:
                try:
                    subprocess.run(
                        [self.ROCM_SMI, "--setmclk", f"{mem_off}", "-d", str(dev.index)],
                        capture_output=True,
                        timeout=10,
                        check=True,
                    )
                    applied["settings"]["mem_clock_offset_mhz"] = mem_off
                except subprocess.SubprocessError:
                    pass

    def _apply_intel(self, dev: GPUDevice, profile: Profile, applied: Dict[str, Any]) -> None:
        self._set_power_limit(dev, profile, applied)
        if profile == Profile.CUSTOM and self._custom_params:
            if (core_off := self._custom_params.get("core_clock_offset")) is not None:
                applied["settings"]["core_clock_offset_requested"] = core_off
            if (mem_off := self._custom_params.get("mem_clock_offset")) is not None:
                applied["settings"]["mem_clock_offset_requested"] = mem_off

    def status(self) -> StatusResult:
        devs_data: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {"total_devices": len(self._devices), "by_vendor": {}}
        for dev in self._devices:
            info: Dict[str, Any] = {
                "index": dev.index,
                "vendor": dev.vendor,
                "name": dev.name,
                "uuid": dev.uuid,
                "bus_id": dev.bus_id,
                "driver_version": dev.driver_version,
            }
            readers = [
                ("temp", "temperature_c", lambda v: int(v) // 1000),
                ("util_gpu", "utilization_gpu_percent", int),
                ("util_mem", "utilization_mem_percent", int),
                ("power_draw", "power_draw_w", lambda v: round(int(v) / 1e6, 1)),
                ("power_limit", "power_limit_w", lambda v: round(int(v) / 1e6, 1)),
                ("clk_gfx", "clock_graphics_mhz", int),
                ("clk_mem", "clock_memory_mhz", int),
                ("mem_used", "memory_used_mb", lambda v: int(v) // (1024 * 1024)),
                ("mem_total", "memory_total_mb", lambda v: int(v) // (1024 * 1024)),
                ("perf_level", "perf_level", str.strip),
            ]
            for key, out_key, conv in readers:
                p = dev.path(key)
                if p and p.exists():
                    val = self._safe_read(str(p))
                    if val:
                        try:
                            info[out_key] = conv(val)
                        except (ValueError, TypeError):
                            pass
            devs_data.append(info)
            v = dev.vendor
            metrics["by_vendor"].setdefault(v, {"count": 0, "total_power_w": 0.0})
            metrics["by_vendor"][v]["count"] += 1
            if "power_draw_w" in info:
                metrics["by_vendor"][v]["total_power_w"] += info["power_draw_w"]
        return StatusResult(self._current_profile, metrics, devs_data)

    def revert(self, prev: Dict[str, Any]) -> ApplyResult:
        if not self._require_root():
            return ApplyResult(False, {}, {}, [], "Root required for revert")
        reverted: Dict[str, Any] = {"devices": []}
        warns: List[str] = []
        ok_cnt = 0
        for st in prev.get("devices", []):
            dev = next((d for d in self._devices if d.uuid == st.get("uuid")), None)
            if not dev:
                warns.append(f"Device not found: {st.get('uuid')}")
                continue
            ok = True
            if dev.path("power_limit") and "power_limit" in st:
                ok &= self._safe_write(str(dev.path("power_limit")), str(st["power_limit"]))
            if dev.vendor == "nvidia":
                try:
                    subprocess.run([self.NVIDIA_SMI, "-i", str(dev.index), "-rac"], capture_output=True, timeout=10, check=True)
                except subprocess.SubprocessError:
                    ok = False
            elif dev.vendor == "amd" and dev.path("perf_level") and "perf_level" in st:
                ok &= self._safe_write(str(dev.path("perf_level")), st["perf_level"])
            if ok:
                ok_cnt += 1
            reverted["devices"].append({"index": dev.index, "vendor": dev.vendor, "uuid": dev.uuid, "restored": ok})
        self._current_profile = self._custom_params = None
        return ApplyResult(ok_cnt > 0, {}, reverted, warns, None if ok_cnt else "No devices reverted")


def create_gpu_optimizer() -> GpuOptimizer:
    return GpuOptimizer()