# Linux System Optimization Toolkit

Toolkit para diagnóstico, tuning e benchmark de sistemas Linux (Arch/Manjaro/CachyOS).

## Arquitetura

```
src/auditor/      → Diagnóstico passivo (Python)
scripts/          → Tuning agressivo + Benchmarks (Bash)
data/             → Outputs gerados (gitignored)
docs/             → Documentação técnica
```

| Componente | Função | Modo |
|------------|--------|------|
| `src/auditor/audit.py` | Pacotes, boot, hardware, overclock | Read-only |
| `scripts/performance.sh` | Governor, turbo, C-states, scheduler, THP | **Root / Write** |
| `scripts/benchmark.sh` | stress-ng + sysbench suite | Read-only |

## Dependências de Sistema

```bash
# Base (Arch/Manjaro/CachyOS)
sudo pacman -S python lm_sensors dmidecode util-linux

# Auditor (hardware details)
sudo pacman -S --needed lm_sensors dmidecode

# Performance tuning
sudo pacman -S cpupower  # opcional, para verificação

# Benchmarks
sudo pacman -S stress-ng sysbench
```

## Uso Rápido

```bash
# 1. Diagnóstico passivo (seguro)
python -m src.auditor.audit
# Gera: data/diagnostico_sistema.md

# 2. Baseline benchmark
./scripts/benchmark.sh
# Gera: data/benchmarks/benchmark_YYYYMMDD_HHMMSS.log

# 3. Tuning agressivo (REQUER ROOT + MONITORAMENTO)
sudo ./scripts/performance.sh
# Monitorar: watch -n1 sensors

# 4. Benchmark pós-tuning
./scripts/benchmark.sh

# 5. Comparar resultados
grep -E "(bogo ops|events per second|MHz)" data/benchmarks/*.log
```

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PROJECT_ROOT` | Auto-detectado | Raiz do projeto (para scripts) |
| `DATA_DIR` | `$PROJECT_ROOT/data` | Diretório de outputs |

## Persistência do Tuning (Opcional)

```bash
# systemd service (edite ExecStart para seu caminho real)
sudo tee /etc/systemd/system/cpu-performance.service <<'EOF'
[Unit]
Description=CPU Performance Mode
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/CAMINHO/ABSOLUTO/scripts/performance.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now cpu-performance
```

## Reversão Rápida

```bash
# Restaurar governors powersave
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo powersave > "$cpu"
done

# Reabilitar serviços de power management
sudo systemctl unmask thermald tuned power-profiles-daemon
sudo systemctl enable --now thermald tuned power-profiles-daemon
```

## Segurança

> ⚠️ `performance.sh` desabilita proteções térmicas (C-states, energy-aware scheduling). **Use por sua conta e risco**. Monitore temperaturas constantemente. Não use em laptops sem refrigeração adequada.

## Licença

MIT