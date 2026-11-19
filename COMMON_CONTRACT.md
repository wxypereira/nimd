# COMMON-CONTRACT — Interface Mínima Compartilhada para HardwareOptimizer

## Protocolo Base (Python ABC)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


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
    """Resultado da sondagem de hardware."""
    available: bool
    devices: List[Dict[str, Any]]
    error: Optional[str] = None


@dataclass(frozen=True)
class ApplyResult:
    """Resultado da aplicação de perfil."""
    success: bool
    applied: Dict[str, Any]
    reverted: Dict[str, Any]
    warnings: List[str]
    error: Optional[str] = None


@dataclass(frozen=True)
class StatusResult:
    """Estado atual do hardware."""
    current_profile: Optional[Profile]
    metrics: Dict[str, Any]
    devices: List[Dict[str, Any]]


class HardwareOptimizer(ABC):
    """Contrato base para otimizadores de hardware isolados."""

    # Identificador único do domínio (fan, gpu, ssd, hdd)
    HARDWARE_TYPE: HardwareType

    # Perfis suportados por este otimizador
    SUPPORTED_PROFILES: List[Profile]

    @abstractmethod
    def probe(self) -> ProbeResult:
        """
        Detecta hardware compatível e verifica permissões/caminhos.
        NÃO modifica estado do sistema.
        """
        ...

    @abstractmethod
    def apply(self, profile: Profile, custom_params: Optional[Dict[str, Any]] = None) -> ApplyResult:
        """
        Aplica perfil de otimização.
        - Valida existência/permissão de paths antes de escrita
        - Respeita SAFE_MODE (limites de fábrica)
        - Retorna estado anterior para revert()
        """
        ...

    @abstractmethod
    def status(self) -> StatusResult:
        """Lê estado atual (métricas, perfil ativo, devices)."""
        ...

    @abstractmethod
    def revert(self, previous_state: Dict[str, Any]) -> ApplyResult:
        """Restaura estado anterior capturado pelo apply()."""
        ...

    # ===== Helpers de segurança (implementação base) =====

    def _safe_read(self, path: str) -> Optional[str]:
        """Leitura segura com tratamento de PermissionError/FileNotFoundError."""
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except (PermissionError, FileNotFoundError, OSError):
            return None

    def _safe_write(self, path: str, value: str, validate_range: Optional[tuple] = None) -> bool:
        """Escrita segura com validação de limites e verificação de permissão."""
        try:
            # Verifica se path existe e é writable
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
        """Verifica se está rodando como root."""
        return os.geteuid() == 0
```

## Convenções de Integração (nimd)

| Ponto | Descrição |
|-------|-----------|
| **Registro** | `nimd.core.registry.register_optimizer(optimizer_instance)` |
| **Descoberta** | Auto-import via `nimd.optimizers` package (entry_points) |
| **CLI** | `nimd optimize <fan|gpu|ssd|hdd> --profile <profile> [--dry-run]` |
| **JSON API** | `{"type": "optimizer", "domain": "fan", "action": "apply", "profile": "balanced"}` |
| **Persistência** | Estado anterior salvo em `/var/lib/nimd/state/<domain>.json` |

## Tipos de Erro Tipados

```python
class OptimizerError(Exception):
    """Base para erros de otimizador."""
    code: str

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
```

## Limites de Segurança (SAFE_MODE)

| Domínio | Parâmetro | Mín | Máx | Fonte |
|---------|-----------|-----|-----|-------|
| fan | pwm | 0 | 255 | hwmon spec |
| gpu | power_limit_w | vendor_min | vendor_max | nvidia-smi/rocm-smi |
| ssd | nr_requests | 1 | 4096 | blk-mq |
| hdd | apm_level | 1 | 254 | ATA-8 |