"""Common base classes for hardware optimizers."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class HardwareType(Enum):
    FAN = "fan"
    GPU = "gpu"
    SSD = "ssd"
    HDD = "hdd"


class Profile(Enum):
    SILENT = "silent"
    BALANCED = "balanced"
    PERFORMANCE = "performance"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ProbeResult:
    available: bool
    devices: List[Dict[str, Any]]
    error: Optional[str] = None


@dataclass(frozen=True)
class ApplyResult:
    success: bool
    applied: Dict[str, Any]
    reverted: Dict[str, Any]
    warnings: List[str]
    error: Optional[str] = None


@dataclass(frozen=True)
class StatusResult:
    current_profile: Optional[Profile]
    metrics: Dict[str, Any]
    devices: List[Dict[str, Any]]


class OptimizerError(Exception):
    code: str = "OPTIMIZER_ERROR"

    def __init__(self, message: str):
        super().__init__(message)


class HardwareNotFound(OptimizerError):
    code = "HARDWARE_NOT_FOUND"


class PermissionDenied(OptimizerError):
    code = "PERMISSION_DENIED"


class InvalidProfile(OptimizerError):
    code = "INVALID_PROFILE"


class SafeModeViolation(OptimizerError):
    code = "SAFE_MODE_VIOLATION"


class DeviceBusy(OptimizerError):
    code = "DEVICE_BUSY"


class HardwareOptimizer(ABC):
    HARDWARE_TYPE: HardwareType
    SUPPORTED_PROFILES: List[Profile]

    @abstractmethod
    def probe(self) -> ProbeResult:
        ...

    @abstractmethod
    def apply(self, profile: Profile, custom_params: Optional[Dict[str, Any]] = None) -> ApplyResult:
        ...

    @abstractmethod
    def status(self) -> StatusResult:
        ...

    @abstractmethod
    def revert(self, previous_state: Dict[str, Any]) -> ApplyResult:
        ...

    def _safe_read(self, path: str) -> Optional[str]:
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except (PermissionError, FileNotFoundError, OSError):
            return None

    def _safe_write(self, path: str, value: str, validate_range: Optional[Tuple[int, int]] = None) -> bool:
        try:
            if not Path(path).exists():
                return False
            if validate_range:
                val = int(value)
                if not (validate_range[0] <= val <= validate_range[1]):
                    return False
            with open(path, "w") as f:
                f.write(value)
            return True
        except (PermissionError, FileNotFoundError, OSError, ValueError):
            return False

    def _require_root(self) -> bool:
        return os.geteuid() == 0