# Linux System Optimization Toolkit

Conjunto de ferramentas para diagnóstico, tuning e benchmark de sistemas Linux (Arch/Manjaro/CachyOS).

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
| `scripts/optimize_memory.sh` | Drop caches + memory compaction + cron | **Root / Write** |
| `scripts/benchmark.sh` | stress-ng + sysbench suite | Read-only |
| `scripts/test_benchmarks.sh` | Suite comparativa automatizada | **Root / Write** |
| `scripts/generate_comparison_report.sh` | Gera relatório a partir de logs | Read-only |

## Dependências de Sistema

```bash
# Base (Arch/Manjaro/CachyOS)
sudo pacman -S python lm_sensors dmidecode util-linux

# Auditor (hardware details)
sudo pacman -S --needed lm_sensors dmidecode

# Performance tuning
sudo pacman -S cpupower  # opcional, para verificação

# Benchmarks
sudo pacman -S stress-ng sysbench bc cronie
sudo systemctl enable --now cronie
```

## Uso Rápido

```bash
# 1. Diagnóstico passivo (seguro)
python -m src.auditor.audit
# Gera: data/diagnostico_sistema.md

# 2. Baseline benchmark
./scripts/benchmark.sh
# Gera: data/benchmarks/benchmark_YYYYMMDD_HHMMSS.log

# 3. Tuning de performance (REQUER ROOT + MONITORAMENTO)
sudo ./scripts/performance.sh
# Monitorar: watch -n1 sensors

# 4. Otimização de memória (REQUER ROOT)
sudo ./scripts/optimize_memory.sh --no-cron

# 5. Benchmark pós-tuning
./scripts/benchmark.sh

# 6. Comparar resultados
grep -E "(bogo ops|events per second|MHz)" data/benchmarks/*.log

# 7. Suite comparativa completa (automatizada)
sudo ./scripts/test_benchmarks.sh
# Gera: docs/benchmark-comparison.md
```

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PROJECT_ROOT` | Auto-detectado | Raiz do projeto (para scripts) |
| `DATA_DIR` | `$PROJECT_ROOT/data` | Diretório de outputs |

## Persistência do Tuning (Opcional)

```bash
# systemd service para performance.sh (edite ExecStart para seu caminho real)
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

# Para optimize_memory.sh, use a flag --cron:
sudo ./scripts/optimize_memory.sh --cron daily
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

# Remover cron jobs do memory optimizer
sudo ./scripts/optimize_memory.sh --remove-cron
```

## Segurança

> ⚠️ `performance.sh` desabilita proteções térmicas (C-states, energy-aware scheduling). **Use por sua conta e risco**. Monitore temperaturas constantemente. Não use em laptops sem refrigeração adequada.

> ⚠️ `optimize_memory.sh` executa `sync` + `vm.drop_caches=3` — pode causar latência temporária se houver muita memória suja. Use com cautela em produção.

## Resultados de Benchmark (Intel i5-3470S @ 2.90GHz, 4 cores, 5.7GiB RAM)

### Cenários Testados

| Cenário | Governor | Descrição |
|---------|----------|-----------|
| **Baseline** | schedutil | Sistema padrão |
| **Performance** | performance | Após `performance.sh` |
| **Memory** | schedutil | Após `optimize_memory.sh` (drop_caches + compaction) |

---

### 1. Baseline (schedutil — sistema padrão)

#### CPU Compute (stress-ng bogo ops/s)
| Métrica | Valor |
|---------|-------|
| **Single Thread** | 1,372.67 |
| **All Cores (4)** | 3,832.83 |

#### sysbench CPU (events/sec - prime numbers)
| Métrica | Valor |
|---------|-------|
| **Single Thread** | 37.78 |
| **Multi-Thread (4)** | 136.53 |
| **Latência p95 (ms)** | 38.25 |

#### Memória e Context Switching
| Métrica | Valor |
|---------|-------|
| **Memory BW (ops/s)** | 193,172 |
| **Context Switch (ops/s)** | N/A |

#### Frequência
| Cenário | Frequência |
|---------|------------|
| Baseline | Variável (1.8–3.6 GHz) |

---

### 2. Performance (governor=performance — após `performance.sh`)

#### CPU Compute (stress-ng bogo ops/s)
| Métrica | Valor | Δ vs Baseline |
|---------|-------|---------------|
| **Single Thread** | 1,287.90 | -6.2% ⬇️ |
| **All Cores (4)** | **5,108.14** | **+33.3%** ⬆️ |

#### sysbench CPU (events/sec - prime numbers)
| Métrica | Valor | Δ vs Baseline |
|---------|-------|---------------|
| **Single Thread** | 36.62 | -3.1% ⬇️ |
| **Multi-Thread (4)** | **145.32** | **+6.4%** ⬆️ |
| **Latência p95 (ms)** | **28.67** | **-25%** ⬆️ (melhor) |

#### Memória e Context Switching
| Métrica | Valor | Δ vs Baseline |
|---------|-------|---------------|
| **Memory BW (ops/s)** | 182,681 | -5.4% ⬇️ |
| **Context Switch (ops/s)** | 965,161 | — |

#### Frequência
| Cenário | Frequência |
|---------|------------|
| Performance | **3,200–3,300 MHz** (fixo) |

---

### 3. Memory (schedutil — após `optimize_memory.sh`)

#### CPU Compute (stress-ng bogo ops/s)
| Métrica | Valor | Δ vs Baseline |
|---------|-------|---------------|
| **Single Thread** | **1,396.94** | **+1.8%** ⬆️ |
| **All Cores (4)** | **5,004.28** | **+30.6%** ⬆️ |

#### sysbench CPU (events/sec - prime numbers)
| Métrica | Valor | Δ vs Baseline |
|---------|-------|---------------|
| **Single Thread** | **39.58** | **+4.8%** ⬆️ |
| **Multi-Thread (4)** | **140.66** | **+3.0%** ⬆️ |
| **Latência p95 (ms)** | **27.17** | **-29%** ⬆️ (melhor de todos) |

#### Memória e Context Switching
| Métrica | Valor | Δ vs Baseline |
|---------|-------|---------------|
| **Memory BW (ops/s)** | **101,704** | **-47.3%** ⬇️ ⚠️ |
| **Context Switch (ops/s)** | 955,830 | — |

#### Frequência
| Cenário | Frequência |
|---------|------------|
| Memory | **schedutil** (variável 1.8–3.6 GHz) |

### Análise Comparativa

| Aspecto | Baseline | Performance | Memory |
|---------|----------|-------------|--------|
| **Multi-thread (stress-ng)** | 3,832.83 (ref) | **+33.3%** ⬆️ | **+30.6%** ⬆️ |
| **Multi-thread (sysbench)** | 136.53 (ref) | **+6.4%** ⬆️ | **+3.0%** ⬆️ |
| **Single-thread** | 1,372.67 / 37.78 (ref) | -6.2% / -3.1% ⬇️ | **+1.8% / +4.8%** ⬆️ |
| **Latência p95** | 38.25ms (ref) | **-25%** ⬆️ | **-29%** ⬆️ (melhor) |
| **Memory BW** | 193,172 (ref) | -5.4% ⬇️ | **-47.3%** ⬇️ ⚠️ |
| **Frequência** | Variável 1.8–3.6 GHz | **Fixa 3.2–3.3 GHz** | Variável 1.8–3.6 GHz |
| **Consumo/Temp** | Baixo | **Alto (+30–50W, +15–25°C)** | Baixo |

### Trade-offs por Cenário

| Cenário | Prós | Contras | Ideal Para |
|---------|------|---------|------------|
| **Baseline** | Equilibrado, baixo consumo, estável | Throughput MT limitado, latência variável | Uso geral, laptops, bateria |
| **Performance** | ✅ MT +33% (stress-ng), +6% (sysbench)<br>✅ Latência p95 -25%<br>✅ Frequência fixa, zero throttling<br>✅ Previsibilidade total | ❌ ST -6%<br>❌ **Consumo +30–50W, temp +15–25°C**<br>❌ Requer cooling robusto<br>❌ Não use em bateria | Compilação, rendering, VMs, servidores de alta carga, gaming competitivo |
| **Memory** | ✅ ST +1.8% (melhor que baseline)<br>✅ **Latência p95 -29% (melhor de todos)**<br>✅ MT +30.6% (próximo do Performance)<br>✅ Baixo consumo/Temp (schedutil)<br>✅ Simples, reversível | ❌ **Memory BW -47%** ⚠️<br>❌ Bit errors detectados no stress-ng<br>❌ Compaction não ativada (kernel limitation)<br>❌ Pagecache limpo = I/O extra subsequente | Sistemas com memory pressure, workloads com alocações grandes, latência crítica sem overhead térmico |

## Execução da Suite Comparativa

```bash
# Suite completa (baseline + performance + memory + combined)
sudo ./scripts/test_benchmarks.sh

# Apenas baseline
sudo ./scripts/test_benchmarks.sh --baseline-only

# Apenas performance mode
sudo ./scripts/test_benchmarks.sh --performance-only

# Apenas memory optimization
sudo ./scripts/test_benchmarks.sh --memory-only

# Modo rápido (benchmark reduzido)
sudo ./scripts/test_benchmarks.sh --quick

# Simular sem executar (dry-run)
sudo ./scripts/test_benchmarks.sh --dry-run

# Gerar relatório a partir de logs existentes
./scripts/generate_comparison_report.sh
```

## Memory Optimization Details

O script `optimize_memory.sh` executa:

1. **`sync`** — Garante buffers de disco escritos
2. **`vm.drop_caches=3`** — Libera pagecache, dentries, inodes
3. **Verifica `CONFIG_COMPACTION=y`** — Procura em:
   - `/usr/src/linux/.config`
   - `/boot/config-$(uname -r)`
   - `/lib/modules/$(uname -r)/build/.config`
   - `/proc/config.gz`
4. **Ativa `vm.compaction_memory=1`** — Se suportado pelo kernel
5. **Instala CronJob opcional** — Daily (03:00), Hourly, Weekly — idempotente

### Flags

```bash
sudo ./scripts/optimize_memory.sh --no-cron       # Execução única
sudo ./scripts/optimize_memory.sh --cron daily    # Cron diário (03:00)
sudo ./scripts/optimize_memory.sh --cron hourly   # Cron horário
sudo ./scripts/optimize_memory.sh --cron weekly   # Cron semanal (Dom 03:00)
sudo ./scripts/optimize_memory.sh --remove-cron   # Remove cron jobs
sudo ./scripts/optimize_memory.sh --dry-run       # Simula
```

### Logs

- Console (colorido) + `/var/log/memory_optimizer.log`

## Licença

MIT — Use, modifique, distribua livremente.

## Referências

- [Arch Wiki - CPU frequency scaling](https://wiki.archlinux.org/title/CPU_frequency_scaling)
- [Arch Wiki - Improving performance](https://wiki.archlinux.org/title/Improving_performance)
- [systemd-analyze](https://www.freedesktop.org/software/systemd/man/systemd-analyze.html)
- [stress-ng](https://kernel.ubuntu.com/~cking/stress-ng/)
- [sysbench](https://github.com/akopytov/sysbench)
- [Kernel Memory Compaction](https://www.kernel.org/doc/html/latest/mm/page_migration.html)