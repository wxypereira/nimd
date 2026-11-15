# Arquitetura Híbrida CLI + GUI — System Optimization Toolkit

## Princípio Fundamental

> **O Shell Script (`core.sh`) é a autoridade única da lógica de negócio.**
> O Rust/egui é **apenas uma interface** que invoca o script e exibe saída.
> Zero lógica de negócio no Rust. Zero dependência do Rust no Shell.

---

## Estrutura de Diretórios

```
system-optimization/
├── constitution.md              # Lei suprema do projeto (existente)
├── README.md                    # Documentação usuário (existente)
├── mem.md                       # Memória persistente (gitignored, existente)
├── .gitignore                   # Existente
├── pyproject.toml               # Python auditor (existente)
├── src/
│   └── auditor/                 # Python auditor (existente)
├── scripts/
│   ├── core.sh                  # ⭐ NOVO: Lógica única CLI (audit, tune, bench, memory)
│   ├── lib/
│   │   ├── common.sh            # Funções compartilhadas (log, colors, root_check)
│   │   ├── hardware.sh          # Detecção CPU/GPU/RAM unificada
│   │   └── thermal.sh           # Monitoramento térmico + alerts
│   ├── performance.sh           # Mantido: wrapper legacy → core.sh performance
│   ├── optimize_memory.sh       # Mantido: wrapper legacy → core.sh memory
│   ├── benchmark.sh             # Mantido: wrapper legacy → core.sh bench
│   ├── test_benchmarks.sh       # Mantido: wrapper legacy → core.sh test-suite
│   └── generate_comparison_report.sh  # Existente
├── data/                        # Outputs (gitignored)
│   ├── diagnostico_sistema.md
│   └── benchmarks/
└── gui/                         # ⭐ NOVO: Aplicação Rust/egui
    ├── Cargo.toml
    ├── Cargo.lock
    ├── build.rs                 # Opcional: embed assets, version info
    ├── src/
    │   ├── main.rs              # Entry point, setup eframe/egui
    │   ├── app.rs               # Struct App + trait eframe::App
    │   ├── tabs/
    │   │   ├── mod.rs
    │   │   ├── audit_tab.rs     # Tab: Auditoria do Sistema
    │   │   ├── tune_tab.rs      # Tab: Performance Tuning
    │   │   ├── bench_tab.rs     # Tab: Benchmarks
    │   │   ├── memory_tab.rs    # Tab: Memory Optimization
    │   │   └── logs_tab.rs      # Tab: Logs em tempo real (comum)
    │   ├── backend/
    │   │   ├── mod.rs
    │   │   ├── runner.rs        # Executa core.sh via std::process::Command + threads/canais
    │   │   ├── parser.rs        # Parseia saída do core.sh para structs Rust
    │   │   └── events.rs        # Eventos de comunicação GUI ↔ Backend (crossbeam-channel)
    │   └── widgets/
    │       ├── mod.rs
    │       ├── log_view.rs      # Widget: caixa de logs com auto-scroll, cores, filtros
    │       ├── progress_bar.rs  # Widget: barra de progresso com ETA
    │       └── param_input.rs   # Widget: inputs tipados (slider, dropdown, checkbox)
    └── assets/
        ├── icon.png
        └── fonts/
```

---

## Fluxo de Dados

```
┌─────────────────────────────────────────────────────────────────┐
│                        USUÁRIO                                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          ▼                                 ▼
┌─────────────────────┐           ┌─────────────────────┐
│     CLI (Terminal)  │           │     GUI (Rust)      │
│                     │           │                     │
│  ./scripts/core.sh  │           │  cargo run --release│
│  audit --json       │           │  ▼                  │
│  tune --apply       │           │  egui App           │
│  bench --quick      │           │  ▼                  │
│  memory --cron daily│           │  Backend Runner     │
└──────────┬──────────┘           │  (threads + channels)│
           │                      │  ▼                  │
           │               ┌──────┴──────┐             │
           │               ▼             ▼             │
           │        ┌─────────┐   ┌───────────┐        │
           │        │  stdout │   │  stderr   │        │
           │        └────┬────┘   └─────┬─────┘        │
           │             │             │                │
           └─────────────┼─────────────┼────────────────┘
                         ▼             ▼
              ┌─────────────────────────────────┐
              │        core.sh (Shell)          │
              │  ┌───────────────────────────┐  │
              │  │ Lógica de Negócio Pura    │  │
              │  │ - audit_packages()        │  │
              │  │ - audit_boot()            │  │
              │  │ - audit_hardware()        │  │
              │  │ - tune_cpu()              │  │
              │  │ - tune_memory()           │  │
              │  │ - run_benchmark()         │  │
              │  │ - run_test_suite()        │  │
              │  └───────────────────────────┘  │
              │  ┌───────────────────────────┐  │
              │  │ Output: JSON Lines (stdout)│ │
              │  │ Logs: Texto colorido (stderr)│ │
              │  └───────────────────────────┘  │
              └─────────────────────────────────┘
```

---

## Protocolo de Comunicação core.sh ↔ GUI

### stdout: JSON Lines (Structured Data)
```json
{"type":"progress","stage":"audit_packages","current":1,"total":5,"percent":20}
{"type":"result","section":"packages","data":{"orphans":["pkg1","pkg2"],"single_use":[]}}
{"type":"result","section":"boot","data":{"total_time":"2.345s","bottlenecks":[...]}}
{"type":"result","section":"hardware","data":{"cpu":{...},"gpu":[...],"ram":{...},"thermal":{...}}}
{"type":"result","section":"overclock","data":{"viability":"Viável","details":[...]}}
{"type":"complete","exit_code":0,"duration_ms":1234}
```

### stderr: Logs Humanos (Texto Colorido)
```
[INFO] Iniciando auditoria de pacotes...
[OK] 3 pacotes órfãos detectados
[WARN] dmidecode requer root para detalhes completos de RAM
[INFO] Benchmark CPU single-thread iniciado (60s)...
[PROGRESS] stress-ng: 45/60s elapsed
[OK] Benchmark concluído: 1396.94 bogo ops/s
```

### Códigos de Saída
| Código | Significado |
|--------|-------------|
| 0 | Sucesso |
| 1 | Erro genérico |
| 2 | Requer root (não executado como root) |
| 3 | Dependência faltando |
| 4 | Argumento inválido |
| 5 | Cancelado pelo usuário (SIGINT/SIGTERM) |
| 10+ | Erro específico de submódulo |

---

## core.sh — Interface CLI

```bash
#!/usr/bin/env bash
# core.sh — Lógica única do System Optimization Toolkit
# Uso: core.sh <comando> [opções]
# Modos: CLI direto | JSON output para GUI (--json)

set -euo pipefail

# ========== CONSTANTES ==========
readonly CORE_VERSION="2.0.0"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
readonly DATA_DIR="${PROJECT_ROOT}/data"
readonly LIB_DIR="${SCRIPT_DIR}/lib"

# ========== CARREGAR LIBS ==========
source "${LIB_DIR}/common.sh"
source "${LIB_DIR}/hardware.sh"
source "${LIB_DIR}/thermal.sh"

# ========== VARIÁVEIS GLOBAIS ==========
JSON_OUTPUT=false
DRY_RUN=false
VERBOSE=false
QUIET=false

# ========== HELP ==========
usage() {
    cat <<'EOF'
System Optimization Toolkit — Core Engine

USO:
    core.sh <comando> [opções]

COMANDOS:
    audit           Auditoria completa do sistema (read-only)
    tune            Aplicar tuning de performance (requer root)
    memory          Otimização de memória (requer root)
    bench           Executar benchmark (stress-ng + sysbench)
    test-suite      Suite comparativa automatizada
    report          Gerar relatório comparativo a partir de logs
    help            Exibir esta ajuda

OPÇÕES GLOBAIS:
    --json          Saída estruturada JSON Lines (stdout) + logs em stderr
    --dry-run       Simular sem aplicar mudanças
    --verbose       Logs detalhados
    --quiet         Apenas erros e resultados finais
    --help          Ajuda do comando específico

EXEMPLOS:
    core.sh audit --json                    # Auditoria para GUI
    core.sh tune --apply --dry-run          # Simular tuning
    core.sh memory --cron daily             # Otimização memória + cron diário
    core.sh bench --quick                   # Benchmark rápido
    core.sh test-suite --baseline-only      # Apenas baseline
    core.sh report                          # Gerar relatório markdown

EOF
}

# ========== PARSING GLOBAL ==========
parse_global_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --json) JSON_OUTPUT=true; shift ;;
            --dry-run) DRY_RUN=true; shift ;;
            --verbose) VERBOSE=true; shift ;;
            --quiet) QUIET=true; shift ;;
            --help) usage; exit 0 ;;
            *) break ;;
        esac
    done
}

# ========== JSON HELPERS ==========
json_emit() {
    [[ "$JSON_OUTPUT" == true ]] || return 0
    printf '%s\n' "$1"
}

json_progress() {
    local stage="$1" current="$2" total="$3" msg="${4:-}"
    local percent=$(( current * 100 / total ))
    json_emit "$(jq -n \
        --arg type "progress" \
        --arg stage "$stage" \
        --argjson current "$current" \
        --argjson total "$total" \
        --argjson percent "$percent" \
        --arg msg "$msg" \
        '{type:$type, stage:$stage, current:$current, total:$total, percent:$percent, message:$msg}')"
}

json_result() {
    local section="$1" data="$2"
    json_emit "$(jq -n --arg type "result" --arg section "$section" --argjson data "$data" \
        '{type:$type, section:$section, data:$data}')"
}

json_complete() {
    local exit_code="$1" duration_ms="$2" msg="${3:-}"
    json_emit "$(jq -n \
        --arg type "complete" \
        --argjson exit_code "$exit_code" \
        --argjson duration_ms "$duration_ms" \
        --arg msg "$msg" \
        '{type:$type, exit_code:$exit_code, duration_ms:$duration_ms, message:$msg}')"
}

# ========== COMANDO: AUDIT ==========
cmd_audit() {
    local start_ms=$(date +%s%3N)
    local stage=0 total=5

    log_info "Iniciando auditoria completa do sistema..."

    # 1. Pacotes
    ((stage++))
    json_progress "audit_packages" "$stage" "$total" "Coletando pacotes órfãos e uso único"
    local pkgs_orphans pkgs_single_use
    mapfile -t pkgs_orphans < <(audit_packages_orphans)
    mapfile -t pkgs_single_use < <(audit_packages_single_use)
    json_result "packages" "$(jq -n \
        --argjson orphans "$(printf '%s\n' "${pkgs_orphans[@]}" | jq -R . | jq -s .)" \
        --argjson single_use "$(printf '%s\n' "${pkgs_single_use[@]}" | jq -R . | jq -s .)" \
        '{orphans:$orphans, single_use:$single_use}')"

    # 2. Boot
    ((stage++))
    json_progress "audit_boot" "$stage" "$total" "Analisando inicialização via systemd-analyze"
    local boot_time boot_bottlenecks boot_critical_chain
    boot_time=$(audit_boot_time)
    mapfile -t boot_bottlenecks < <(audit_boot_bottlenecks)
    boot_critical_chain=$(audit_boot_critical_chain)
    json_result "boot" "$(jq -n \
        --arg time "$boot_time" \
        --argjson bottlenecks "$(printf '%s\n' "${boot_bottlenecks[@]}" | jq -R . | jq -s .)" \
        --arg critical_chain "$boot_critical_chain" \
        '{total_time:$time, bottlenecks:$bottlenecks, critical_chain:$critical_chain}')"

    # 3. Hardware
    ((stage++))
    json_progress "audit_hardware" "$stage" "$total" "Inspecionando CPU, GPU, RAM, térmica"
    local hw_cpu hw_gpu hw_ram hw_thermal
    hw_cpu=$(audit_hardware_cpu)
    hw_gpu=$(audit_hardware_gpu)
    hw_ram=$(audit_hardware_ram)
    hw_thermal=$(audit_hardware_thermal)
    json_result "hardware" "$(jq -n \
        --argjson cpu "$hw_cpu" \
        --argjson gpu "$hw_gpu" \
        --argjson ram "$hw_ram" \
        --argjson thermal "$hw_thermal" \
        '{cpu:$cpu, gpu:$gpu, ram:$ram, thermal:$thermal}')"

    # 4. Overclock
    ((stage++))
    json_progress "audit_overclock" "$stage" "$total" "Avaliando viabilidade de overclock"
    local oc_viability oc_details
    oc_viability=$(eval_overclock_viability)
    mapfile -t oc_details < <(eval_overclock_details)
    json_result "overclock" "$(jq -n \
        --arg viability "$oc_viability" \
        --argjson details "$(printf '%s\n' "${oc_details[@]}" | jq -R . | jq -s .)" \
        '{viability:$viability, details:$details}')"

    # 5. Action Plan
    ((stage++))
    json_progress "audit_plan" "$stage" "$total" "Gerando plano de ação"
    local plan
    mapfile -t plan < <(generate_action_plan)
    json_result "action_plan" "$(printf '%s\n' "${plan[@]}" | jq -R . | jq -s .)"

    local end_ms=$(date +%s%3N)
    json_complete 0 $((end_ms - start_ms)) "Auditoria concluída"
}

# ========== COMANDO: TUNE (Performance) ==========
cmd_tune() {
    local apply=false
    local restore=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --apply) apply=true; shift ;;
            --restore) restore=true; shift ;;
            *) log_err "Opção desconhecida: $1"; return 4 ;;
        esac
    done

    if [[ "$restore" == true ]]; then
        log_info "Restaurando configuração padrão..."
        tune_restore_defaults
        return 0
    fi

    if [[ "$apply" == false ]]; then
        log_err "Use --apply para confirmar ou --restore para reverter"
        return 4
    fi

    root_check || return 2

    local start_ms=$(date +%s%3N)
    local stage=0 total=6

    log_info "Aplicando tuning de performance (governor, turbo, C-states, scheduler, THP)..."

    # 1. Governor
    ((stage++))
    json_progress "tune_governor" "$stage" "$total" "Definindo governor=performance"
    [[ "$DRY_RUN" == true ]] || tune_set_governor "performance"
    json_result "governor" "$(jq -n --arg gov "performance" '{governor:$gov}')"

    # 2. Turbo / HWP
    ((stage++))
    json_progress "tune_turbo" "$stage" "$total" "Ativando turbo, desabilitando HWP"
    [[ "$DRY_RUN" == true ]] || tune_enable_turbo
    json_result "turbo" "$(jq -n --arg enabled "true" '{enabled:$enabled}')"

    # 3. C-States
    ((stage++))
    json_progress "tune_cstates" "$stage" "$total" "Desabilitando C-states profundos"
    [[ "$DRY_RUN" == true ]] || tune_disable_cstates
    json_result "cstates" "$(jq -n --arg disabled "true" '{disabled:$disabled}')"

    # 4. Scheduler
    ((stage++))
    json_progress "tune_scheduler" "$stage" "$total" "Ajustando scheduler (latency_ns, mig_cost_ns)"
    [[ "$DRY_RUN" == true ]] || tune_scheduler
    json_result "scheduler" "$(jq -n --arg latency "1000000" --arg mig_cost "5000000" '{latency_ns:$latency, migration_cost_ns:$mig_cost}')"

    # 5. THP
    ((stage++))
    json_progress "tune_thp" "$stage" "$total" "Configurando Transparent Huge Pages = always"
    [[ "$DRY_RUN" == true ]] || tune_thp_always
    json_result "thp" "$(jq -n --arg mode "always" '{mode:$mode}')"

    # 6. Services (mask thermald, tuned, power-profiles-daemon)
    ((stage++))
    json_progress "tune_services" "$stage" "$total" "Mascarando serviços de power management"
    [[ "$DRY_RUN" == true ]] || tune_mask_power_services
    json_result "services" "$(jq -n --argjson masked "$(jq -n '["thermald","tuned","power-profiles-daemon"]')" '{masked:$masked}')"

    local end_ms=$(date +%s%3N)
    json_complete 0 $((end_ms - start_ms)) "Performance tuning aplicado"
}

# ========== COMANDO: MEMORY ==========
cmd_memory() {
    local cron_mode="none"
    local remove_cron=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --cron) cron_mode="${2:-daily}"; shift 2 ;;
            --remove-cron) remove_cron=true; shift ;;
            *) log_err "Opção desconhecida: $1"; return 4 ;;
        esac
    done

    if [[ "$remove_cron" == true ]]; then
        log_info "Removendo cron jobs de memory optimizer..."
        memory_remove_cron
        return 0
    fi

    root_check || return 2

    local start_ms=$(date +%s%3N)
    local stage=0 total=4

    log_info "Executando otimização de memória..."

    # 1. Sync + Drop caches
    ((stage++))
    json_progress "memory_sync" "$stage" "$total" "Sincronizando buffers de disco"
    [[ "$DRY_RUN" == true ]] || sync
    json_progress "memory_drop_caches" "$stage" "$total" "Limpando pagecache, dentries, inodes"
    [[ "$DRY_RUN" == true ]] || memory_drop_caches
    json_result "drop_caches" "$(jq -n --arg status "ok" '{status:$status}')"

    # 2. Compaction check
    ((stage++))
    json_progress "memory_compaction_check" "$stage" "$total" "Verificando CONFIG_COMPACTION no kernel"
    local compaction_supported
    compaction_supported=$(memory_check_compaction)
    json_result "compaction_check" "$(jq -n --argjson supported "$compaction_supported" '{supported:$supported}')"

    # 3. Enable compaction (if supported)
    if [[ "$compaction_supported" == "true" ]]; then
        json_progress "memory_compaction_enable" "$stage" "$total" "Ativando vm.compaction_memory=1"
        [[ "$DRY_RUN" == true ]] || memory_enable_compaction
        json_result "compaction_enable" "$(jq -n --arg status "enabled" '{status:$status}')"
    fi

    # 4. Cron
    if [[ "$cron_mode" != "none" ]]; then
        ((stage++))
        json_progress "memory_cron" "$stage" "$total" "Instalando cron $cron_mode"
        [[ "$DRY_RUN" == true ]] || memory_install_cron "$cron_mode"
        json_result "cron" "$(jq -n --arg mode "$cron_mode" '{mode:$mode, installed:true}')"
    fi

    local end_ms=$(date +%s%3N)
    json_complete 0 $((end_ms - start_ms)) "Memory optimization concluída"
}

# ========== COMANDO: BENCH ==========
cmd_bench() {
    local quick=false
    local output_file=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick) quick=true; shift ;;
            --output) output_file="$2"; shift 2 ;;
            *) log_err "Opção desconhecida: $1"; return 4 ;;
        esac
    done

    local start_ms=$(date +%s%3N)
    local stage=0
    local total=7
    [[ "$quick" == true ]] && total=4

    log_info "Iniciando benchmark suite..."

    # Auto-generate output file if not provided
    [[ -n "$output_file" ]] || output_file="${DATA_DIR}/benchmarks/benchmark_$(date +%Y%m%d_%H%M%S)_$(get_current_governor).log"

    # Ensure directory exists
    mkdir -p "$(dirname "$output_file")"

    # Run benchmark with tee to file
    {
        # 1. stress-ng single thread
        ((stage++))
        json_progress "bench_stress_ng_st" "$stage" "$total" "stress-ng CPU single thread"
        run_stress_ng_single_thread "$quick"

        # 2. stress-ng multi thread
        ((stage++))
        json_progress "bench_stress_ng_mt" "$stage" "$total" "stress-ng CPU all cores"
        run_stress_ng_multi_thread "$quick"

        # 3. sysbench single thread
        ((stage++))
        json_progress "bench_sysbench_st" "$stage" "$total" "sysbench CPU single thread"
        run_sysbench_single_thread "$quick"

        # 4. sysbench multi thread
        ((stage++))
        json_progress "bench_sysbench_mt" "$stage" "$total" "sysbench CPU multi-thread"
        run_sysbench_multi_thread "$quick"

        if [[ "$quick" == false ]]; then
            # 5. Memory bandwidth
            ((stage++))
            json_progress "bench_mem_bw" "$stage" "$total" "stress-ng memory bandwidth"
            run_memory_bandwidth "$quick"

            # 6. Context switching
            ((stage++))
            json_progress "bench_ctx_switch" "$stage" "$total" "stress-ng context switching"
            run_context_switch "$quick"

            # 7. Frequencies
            ((stage++))
            json_progress "bench_freq" "$stage" "$total" "Coletando frequências sustentadas"
            run_frequency_sampling
        fi
    } 2>&1 | tee "$output_file"

    local end_ms=$(date +%s%3N)
    json_result "benchmark_log" "$(jq -n --arg file "$output_file" '{file:$file}')"
    json_complete 0 $((end_ms - start_ms)) "Benchmark concluído: $output_file"
}

# ========== COMANDO: TEST-SUITE ==========
cmd_test_suite() {
    local run_baseline=true
    local run_performance=true
    local run_memory=true
    local run_combined=true
    local quick=false
    local no_restore=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --baseline-only) run_performance=false; run_memory=false; run_combined=false; shift ;;
            --performance-only) run_baseline=false; run_memory=false; run_combined=false; shift ;;
            --memory-only) run_baseline=false; run_performance=false; run_combined=false; shift ;;
            --combined-only) run_baseline=false; run_performance=false; run_memory=false; shift ;;
            --quick) quick=true; shift ;;
            --no-restore) no_restore=true; shift ;;
            *) log_err "Opção desconhecida: $1"; return 4 ;;
        esac
    done

    root_check || return 2

    local start_ms=$(date +%s%3N)
    local logs=()

    # Baseline
    if [[ "$run_baseline" == true ]]; then
        log_info "=== CENÁRIO 1: BASELINE (schedutil) ==="
        tune_restore_defaults
        sleep 3
        local log_file
        log_file=$(cmd_bench --quick="$quick" --output="${DATA_DIR}/benchmarks/benchmark_baseline_$(date +%Y%m%d_%H%M%S).log")
        logs+=("baseline:$log_file")
    fi

    # Performance
    if [[ "$run_performance" == true ]]; then
        log_info "=== CENÁRIO 2: PERFORMANCE MODE ==="
        cmd_tune --apply
        sleep 3
        local log_file
        log_file=$(cmd_bench --quick="$quick" --output="${DATA_DIR}/benchmarks/benchmark_performance_$(date +%Y%m%d_%H%M%S).log")
        logs+=("performance:$log_file")
    fi

    # Memory
    if [[ "$run_memory" == true ]]; then
        log_info "=== CENÁRIO 3: MEMORY OPTIMIZATION ==="
        tune_restore_defaults
        sleep 2
        cmd_memory --cron daily
        sleep 2
        local log_file
        log_file=$(cmd_bench --quick="$quick" --output="${DATA_DIR}/benchmarks/benchmark_memory_$(date +%Y%m%d_%H%M%S).log")
        logs+=("memory:$log_file")
    fi

    # Combined
    if [[ "$run_combined" == true ]]; then
        log_info "=== CENÁRIO 4: COMBINED (Performance + Memory) ==="
        cmd_tune --apply
        sleep 2
        cmd_memory --cron daily
        sleep 2
        local log_file
        log_file=$(cmd_bench --quick="$quick" --output="${DATA_DIR}/benchmarks/benchmark_combined_$(date +%Y%m%d_%H%M%S).log")
        logs+=("combined:$log_file")
    fi

    # Restore
    if [[ "$no_restore" == false ]]; then
        log_info "Restaurando configuração original..."
        tune_restore_defaults
    fi

    # Generate report
    if [[ ${#logs[@]} -ge 2 ]]; then
        log_info "Gerando relatório comparativo..."
        "${SCRIPT_DIR}/generate_comparison_report.sh"
    fi

    local end_ms=$(date +%s%3N)
    json_result "test_suite_logs" "$(printf '%s\n' "${logs[@]}" | jq -R . | jq -s .)"
    json_complete 0 $((end_ms - start_ms)) "Test suite concluída"
}

# ========== COMANDO: REPORT ==========
cmd_report() {
    "${SCRIPT_DIR}/generate_comparison_report.sh"
}

# ========== MAIN ==========
main() {
    parse_global_args "$@"
    shift $((OPTIND - 1)) 2>/dev/null || true

    local cmd="${1:-help}"
    shift || true

    case $cmd in
        audit) cmd_audit "$@" ;;
        tune) cmd_tune "$@" ;;
        memory) cmd_memory "$@" ;;
        bench) cmd_bench "$@" ;;
        test-suite) cmd_test_suite "$@" ;;
        report) cmd_report "$@" ;;
        help|--help|-h) usage ;;
        *) log_err "Comando desconhecido: $cmd"; usage; exit 4 ;;
    esac
}

# Executa se chamado diretamente (não sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

---

## gui/Cargo.toml

```toml
[package]
name = "sysopt-gui"
version = "2.0.0"
edition = "2021"
description = "GUI for System Optimization Toolkit (egui/eframe)"
license = "MIT"
repository = "https://github.com/wxypereira/nimd"
authors = ["pereira <wxypereira@domain>"]
categories = ["gui", "system-tools", "command-line-utilities"]
keywords = ["egui", "eframe", "system-optimization", "benchmark", "linux"]

[workspace]
resolver = "2"

[dependencies]
# GUI Framework
eframe = { version = "0.29", features = ["persistence", "accesskit", "wgpu", "default_fonts"] }
egui = { version = "0.29", features = ["accesskit", "default_fonts"] }
egui_extras = "0.29"

# Async Runtime
tokio = { version = "1.40", features = ["rt-multi-thread", "macros", "sync", "process", "signal"] }

# Process Management
async-process = "1.8"      # Async Command execution
tokio-util = { version = "0.7", features = ["codec"] }  # Framing stdout/stderr

# Channels
crossbeam-channel = "0.5"  # Thread-safe channels for GUI ↔ Backend

# Serialization
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
simd-json = "0.10"         # Faster JSON parsing

# Logging
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter", "fmt"] }

# Utilities
anyhow = "1.0"             # Error handling
thiserror = "1.0"          # Derive Error
dirs = "5.0"               # Config/cache directories
chrono = { version = "0.4", features = ["serde"] }  # Timestamps
color-eyre = "0.6"         # Pretty error reports

# System Info
sysinfo = "0.30"           # For displaying current system stats in GUI

[build-dependencies]
vergen = "8.0"             # Embed git version info
embedded-resource = { version = "1.8", optional = true }  # Windows icon embedding

[features]
default = ["persistence"]
persistence = ["eframe/persistence"]
wayland = ["eframe/wayland"]

[profile.release]
opt-level = 3
lto = "fat"
codegen-units = 1
strip = "symbols"
panic = "abort"

[profile.dev]
opt-level = 0
debug = true
```

---

## gui/src/main.rs

```rust
//! System Optimization Toolkit — GUI Entry Point
//! 
//! Inicializa eframe/egui, configura logging, carrega app state.

use std::sync::Arc;
use color_eyre::Result;
use eframe::egui;
use tracing_subscriber::{EnvFilter, fmt};

mod app;
mod backend;
mod tabs;
mod widgets;

use app::SysOptApp;

fn main() -> Result<()> {
    // Instala panic handler colorido
    color_eyre::install()?;

    // Setup tracing (logs para arquivo + stdout)
    let file_appender = tracing_appender::rolling::daily("/tmp", "sysopt-gui.log");
    let (non_blocking, _guard) = tracing_appender::non_blocking(file_appender);
    
    fmt()
        .with_env_filter(EnvFilter::from_default_env()
            .add_directive("sysopt_gui=debug".parse()?)
            .add_directive("eframe=warn".parse()?))
        .with_writer(non_blocking)
        .with_ansi(false)
        .init();

    // Configuração nativa da janela
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1200.0, 800.0])
            .with_min_inner_size([900.0, 600.0])
            .with_title("System Optimization Toolkit")
            .with_window_icon(load_icon()),
        centered: true,
        persist_window: true,
        follow_system_theme: true,
        default_theme: eframe::Theme::Dark,
        renderer: eframe::Renderer::Wgpu,
        multisampling: 4,
        depth_buffer: 0,
        stencil_buffer: 0,
        hardware_acceleration: eframe::HardwareAcceleration::Preferred,
        ..Default::default()
    };

    // Run app
    eframe::run_native(
        "System Optimization Toolkit",
        native_options,
        Box::new(|cc| {
            // Configura fontes customizadas
            setup_fonts(&cc.egui_ctx);
            
            // Carrega estado persistido (tamanho janela, últimas abas, etc.)
            let mut app = SysOptApp::new(cc);
            app.load_persisted_state(&cc.egui_ctx);
            
            Ok(Box::new(app))
        }),
    )?;

    Ok(())
}

/// Carrega ícone da aplicação
fn load_icon() -> Option<egui::IconData> {
    let icon_bytes = include_bytes!("../assets/icon.png");
    let image = image::load_from_memory(icon_bytes).ok()?.into_rgba8();
    let (width, height) = image.dimensions();
    Some(egui::IconData {
        rgba: image.into_raw(),
        width,
        height,
    })
}

/// Configura fontes (JetBrains Mono para logs, Inter para UI)
fn setup_fonts(ctx: &egui::Context) {
    let mut fonts = egui::FontDefinitions::default();
    
    // Fonte monoespaçada para logs
    fonts.font_data.insert(
        "jetbrains_mono".to_owned(),
        egui::FontData::from_static(include_bytes!("../assets/fonts/JetBrainsMono-Regular.ttf"))
    );
    
    // Fonte principal UI
    fonts.font_data.insert(
        "inter".to_owned(),
        egui::FontData::from_static(include_bytes!("../assets/fonts/Inter-Regular.ttf"))
    );
    
    fonts.families.insert(
        egui::FontFamily::Monospace,
        vec!["jetbrains_mono".to_owned()]
    );
    fonts.families.insert(
        egui::FontFamily::Proportional,
        vec!["inter".to_owned()]
    );
    
    ctx.set_fonts(fonts);
}
```

---

## gui/src/app.rs

```rust
//! Aplicação principal — Estado global, tabs, persistência.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use eframe::egui::{self, ViewportId};
use egui::Context;
use serde::{Deserialize, Serialize};
use tracing::{debug, info, warn};

use crate::backend::{Backend, BackendEvent, BackendCommand};
use crate::tabs::{Tab, AuditTab, TuneTab, BenchTab, MemoryTab, LogsTab};
use crate::widgets::LogView;

/// Estado persistido entre sessões
#[derive(Debug, Default, Serialize, Deserialize)]
struct PersistedState {
    window_size: Option<[f32; 2]>,
    active_tab: usize,
    last_core_path: String,
    benchmark_quick: bool,
    auto_scroll_logs: bool,
}

/// Eventos internos da GUI
#[derive(Debug, Clone)]
enum GuiEvent {
    BackendEvent(BackendEvent),
    TabChanged(usize),
    RequestShutdown,
}

/// Aplicação principal
pub struct SysOptApp {
    // Estado persistido
    persisted: PersistedState,
    
    // Backend runner (executa core.sh)
    backend: Backend,
    
    // Tabs
    tabs: Vec<Box<dyn Tab>>,
    active_tab: usize,
    
    // Logs globais (compartilhados por todas as tabs)
    global_logs: Arc<Mutex<VecDeque<LogEntry>>>,
    auto_scroll: bool,
    
    // Status da operação atual
    operation_running: bool,
    operation_start: Option<Instant>,
    progress: Option<ProgressInfo>,
    
    // Canal para eventos internos
    event_tx: crossbeam_channel::Sender<GuiEvent>,
    event_rx: crossbeam_channel::Receiver<GuiEvent>,
}

#[derive(Debug, Clone)]
struct LogEntry {
    timestamp: chrono::DateTime<chrono::Local>,
    level: LogLevel,
    message: String,
    source: LogSource,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LogLevel {
    Info,
    Warn,
    Error,
    Debug,
    Success,
    Progress,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LogSource {
    Gui,
    BackendStdout,
    BackendStderr,
}

#[derive(Debug, Clone)]
struct ProgressInfo {
    stage: String,
    current: u32,
    total: u32,
    percent: u32,
    message: String,
}

impl SysOptApp {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        // Carrega estado persistido
        let persisted: PersistedState = cc.storage
            .and_then(|s| eframe::get_value(s, "sysopt_state"))
            .unwrap_or_default();
        
        let (event_tx, event_rx) = crossbeam_channel::unbounded();
        let global_logs = Arc::new(Mutex::new(VecDeque::with_capacity(5000)));
        
        // Inicializa backend
        let core_path = persisted.last_core_path.clone()
            .unwrap_or_else(|| "./scripts/core.sh".to_string());
        let backend = Backend::new(core_path, event_tx.clone(), global_logs.clone());
        
        // Cria tabs
        let tabs: Vec<Box<dyn Tab>> = vec![
            Box::new(AuditTab::new(global_logs.clone(), event_tx.clone())),
            Box::new(TuneTab::new(global_logs.clone(), event_tx.clone())),
            Box::new(BenchTab::new(global_logs.clone(), event_tx.clone())),
            Box::new(MemoryTab::new(global_logs.clone(), event_tx.clone())),
            Box::new(LogsTab::new(global_logs.clone())),
        ];
        
        Self {
            persisted,
            backend,
            tabs,
            active_tab: persisted.active_tab.min(4),
            global_logs,
            auto_scroll: persisted.auto_scroll_logs,
            operation_running: false,
            operation_start: None,
            progress: None,
            event_tx,
            event_rx,
        }
    }
    
    fn load_persisted_state(&mut self, ctx: &Context) {
        if let Some(size) = self.persisted.window_size {
            ctx.send_viewport_cmd(egui::ViewportCommand::InnerSize(egui::Vec2::new(size[0], size[1])));
        }
    }
    
    fn save_persisted_state(&mut self, ctx: &Context) {
        self.persisted.window_size = Some([
            ctx.input(|i| i.viewport().outer_rect.unwrap_or_default().width()),
            ctx.input(|i| i.viewport().outer_rect.unwrap_or_default().height()),
        ]);
        self.persisted.active_tab = self.active_tab;
        self.persisted.auto_scroll_logs = self.auto_scroll;
        
        if let Some(storage) = ctx.storage_mut() {
            eframe::set_value(storage, "sysopt_state", &self.persisted);
        }
    }
}

impl eframe::App for SysOptApp {
    fn update(&mut self, ctx: &Context, _frame: &mut eframe::Frame) {
        // Processa eventos do backend
        while let Ok(event) = self.event_rx.try_recv() {
            match event {
                GuiEvent::BackendEvent(be) => self.handle_backend_event(be),
                GuiEvent::TabChanged(idx) => self.active_tab = idx,
                GuiEvent::RequestShutdown => ctx.send_viewport_cmd(egui::ViewportCommand::Close),
            }
        }
        
        // Atualiza backend (poll processos)
        self.backend.poll();
        
        // Menu bar
        egui::TopBottomPanel::top("menu_bar").show(ctx, |ui| {
            self.show_menu_bar(ui);
        });
        
        // Status bar
        egui::TopBottomPanel::bottom("status_bar").show(ctx, |ui| {
            self.show_status_bar(ui);
        });
        
        // Tab bar
        egui::TopBottomPanel::top("tab_bar").show(ctx, |ui| {
            self.show_tab_bar(ui);
        });
        
        // Área central - tab ativa
        egui::CentralPanel::default().show(ctx, |ui| {
            if let Some(tab) = self.tabs.get_mut(self.active_tab) {
                tab.draw(ui, &mut self.backend, &mut self.operation_running);
            }
        });
        
        // Salva estado periodicamente
        self.save_persisted_state(ctx);
        
        // Request repaint se operação rodando
        if self.operation_running {
            ctx.request_repaint_after(Duration::from_millis(100));
        }
    }
    
    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        // Para backend graciosamente
        self.backend.shutdown();
        info!("Application exiting");
    }
}

impl SysOptApp {
    fn show_menu_bar(&mut self, ui: &mut egui::Ui) {
        egui::menu::bar(ui, |ui| {
            ui.menu_button("Arquivo", |ui| {
                if ui.button("Abrir pasta de logs").clicked() {
                    let _ = opener::open(&self.persisted.last_core_path.replace("core.sh", "../data"));
                    ui.close_menu();
                }
                ui.separator();
                if ui.button("Sair").clicked() {
                    self.event_tx.send(GuiEvent::RequestShutdown).ok();
                }
            });
            
            ui.menu_button("Configurações", |ui| {
                ui.checkbox(&mut self.auto_scroll, "Auto-scroll logs");
                if ui.button("Limpar logs globais").clicked() {
                    self.global_logs.lock().unwrap().clear();
                }
            });
            
            ui.menu_button("Ajuda", |ui| {
                if ui.button("Sobre").clicked() {
                    // TODO: About dialog
                }
            });
            
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                // Indicador de operação rodando
                if self.operation_running {
                    ui.spinner();
                    ui.label("Processando...");
                }
            });
        });
    }
    
    fn show_tab_bar(&mut self, ui: &mut egui::Ui) {
        let tab_names = ["🔍 Auditoria", "⚡ Tuning", "📊 Benchmark", "🧠 Memória", "📋 Logs"];
        
        ui.horizontal(|ui| {
            for (idx, name) in tab_names.iter().enumerate() {
                let selected = self.active_tab == idx;
                let btn = egui::SelectableLabel::new(selected, *name)
                    .with_sense(egui::Sense::click());
                if ui.add(btn).clicked() {
                    self.active_tab = idx;
                    self.event_tx.send(GuiEvent::TabChanged(idx)).ok();
                }
            }
            
            ui.separator();
            
            // Quick status do core.sh
            let core_exists = std::path::Path::new(&self.backend.core_path).exists();
            let color = if core_exists { egui::Color32::GREEN } else { egui::Color32::RED };
            ui.colored_label(color, format!("core.sh: {}", 
                if core_exists { "✓ Encontrado" } else { "✗ Não encontrado" }));
        });
    }
    
    fn show_status_bar(&mut self, ui: &mut egui::Ui) {
        ui.horizontal(|ui| {
            if let Some(progress) = &self.progress {
                ui.label(&progress.stage);
                ui.add(egui::ProgressBar::new(progress.percent as f32 / 100.0)
                    .show_percentage()
                    .animate(true));
                ui.label(format!("{}/{}", progress.current, progress.total));
            } else if self.operation_running {
                ui.spinner();
                ui.label("Executando...");
                if let Some(start) = self.operation_start {
                    let elapsed = start.elapsed().as_secs();
                    ui.label(format!("{}s", elapsed));
                }
            } else {
                ui.label("Pronto");
            }
            
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                // System info rápido
                if let Ok(sys) = sysinfo::System::new_all() {
                    let cpu_usage = sys.global_cpu_usage() as u32;
                    let mem_used = sys.used_memory() / 1024 / 1024;
                    let mem_total = sys.total_memory() / 1024 / 1024;
                    ui.label(format!("CPU: {}% | RAM: {}/{} MB", cpu_usage, mem_used, mem_total));
                }
            });
        });
    }
    
    fn handle_backend_event(&mut self, event: BackendEvent) {
        use BackendEvent::*;
        match event {
            Progress { stage, current, total, percent, message } => {
                self.progress = Some(ProgressInfo { stage, current, total, percent, message });
                self.add_log(LogLevel::Progress, &format!("{}: {}% ({}/{})", 
                    self.progress.as_ref().unwrap().stage, percent, current, total), LogSource::BackendStdout);
            }
            Result { section, data } => {
                self.add_log(LogLevel::Success, &format!("Resultado: {} → {}", section, data), LogSource::BackendStdout);
                // Repassa para tab ativa processar
                if let Some(tab) = self.tabs.get_mut(self.active_tab) {
                    tab.on_backend_result(&section, &data);
                }
            }
            Complete { exit_code, duration_ms, message } => {
                self.operation_running = false;
                self.operation_start = None;
                self.progress = None;
                
                let level = if exit_code == 0 { LogLevel::Success } else { LogLevel::Error };
                self.add_log(level, &format!("Concluído (código {}) em {}ms: {}", 
                    exit_code, duration_ms, message), LogSource::BackendStdout);
            }
            Log { level, message } => {
                let log_level = match level.as_str() {
                    "INFO" => LogLevel::Info,
                    "WARN" => LogLevel::Warn,
                    "ERROR" => LogLevel::Error,
                    "DEBUG" => LogLevel::Debug,
                    "OK" => LogLevel::Success,
                    _ => LogLevel::Info,
                };
                self.add_log(log_level, &message, LogSource::BackendStderr);
            }
            Error { message } => {
                self.add_log(LogLevel::Error, &message, LogSource::BackendStderr);
            }
        }
    }
    
    fn add_log(&self, level: LogLevel, message: &str, source: LogSource) {
        let mut logs = self.global_logs.lock().unwrap();
        logs.push_back(LogEntry {
            timestamp: chrono::Local::now(),
            level,
            message: message.to_string(),
            source,
        });
        // Limita tamanho
        if logs.len() > 5000 {
            logs.pop_front();
        }
    }
}
```

---

## gui/src/backend/runner.rs

```rust
//! Backend Runner — Executa core.sh em background com streaming de stdout/stderr
//! 
//! Usa tokio::process::Command + threads para não bloquear a GUI.
//! Comunica via crossbeam-channel com a thread principal.

use std::path::PathBuf;
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;
use std::time::Duration;

use anyhow::Result;
use crossbeam_channel::{Sender, Receiver, unbounded};
use serde_json::Value;
use tokio::process::Command as AsyncCommand;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::sync::mpsc;
use tracing::{debug, error, info, warn};

use super::events::{BackendEvent, BackendCommand};

/// Runner do backend — gerencia processo core.sh
pub struct Backend {
    core_path: PathBuf,
    event_tx: Sender<BackendEvent>,
    global_logs: Arc<Mutex<VecDeque<super::app::LogEntry>>>,
    
    // Processo atual
    current_child: Arc<Mutex<Option<tokio::process::Child>>>,
    
    // Canal interno para comandos
    cmd_tx: mpsc::UnboundedSender<BackendCommand>,
    cmd_rx: Arc<Mutex<Option<mpsc::UnboundedReceiver<BackendCommand>>>>,
    
    // Handle da task de polling
    poll_handle: Arc<Mutex<Option<tokio::task::JoinHandle<()>>>>,
}

impl Backend {
    pub fn new(
        core_path: impl Into<PathBuf>,
        event_tx: Sender<BackendEvent>,
        global_logs: Arc<Mutex<VecDeque<super::app::LogEntry>>>,
    ) -> Self {
        let (cmd_tx, cmd_rx) = mpsc::unbounded_channel();
        
        Self {
            core_path: core_path.into(),
            event_tx,
            global_logs,
            current_child: Arc::new(Mutex::new(None)),
            cmd_tx,
            cmd_rx: Arc::new(Mutex::new(Some(cmd_rx))),
            poll_handle: Arc::new(Mutex::new(None)),
        }
    }
    
    /// Envia comando para execução assíncrona
    pub fn execute(&self, command: BackendCommand) -> Result<()> {
        self.cmd_tx.send(command)?;
        Ok(())
    }
    
    /// Poll periódico (chamado da thread principal da GUI)
    pub fn poll(&self) {
        // Processa comandos pendentes
        if let Ok(mut rx_guard) = self.cmd_rx.lock() {
            if let Some(rx) = rx_guard.as_mut() {
                while let Ok(cmd) = rx.try_recv() {
                    self.spawn_command(cmd);
                }
            }
        }
    }
    
    /// Spawna comando core.sh como processo filho
    fn spawn_command(&self, cmd: BackendCommand) {
        let core_path = self.core_path.clone();
        let event_tx = self.event_tx.clone();
        let global_logs = self.global_logs.clone();
        let current_child = self.current_child.clone();
        
        let handle = tokio::spawn(async move {
            // Converte comando em args
            let args = cmd.to_args();
            
            info!("Executando: {} {}", core_path.display(), args.join(" "));
            
            let mut child = match AsyncCommand::new(&core_path)
                .args(&args)
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
            {
                Ok(c) => c,
                Err(e) => {
                    let _ = event_tx.send(BackendEvent::Error {
                        message: format!("Falha ao iniciar core.sh: {}", e),
                    });
                    return;
                }
            };
            
            // Armazena handle do processo
            *current_child.lock().unwrap() = Some(child);
            
            // Pega stdout/stderr
            let stdout = child.stdout.take().expect("stdout piped");
            let stderr = child.stderr.take().expect("stderr piped");
            let event_tx_stdout = event_tx.clone();
            let event_tx_stderr = event_tx.clone();
            let global_logs_stdout = global_logs.clone();
            let global_logs_stderr = global_logs.clone();
            
            // Task para ler stdout (JSON Lines)
            let stdout_handle = tokio::spawn(async move {
                let mut reader = BufReader::new(stdout).lines();
                while let Ok(Some(line)) = reader.next_line().await {
                    // Tenta parsear JSON
                    if let Ok(json) = serde_json::from_str::<Value>(&line) {
                        if let Some(event) = parse_json_event(json) {
                            let _ = event_tx_stdout.send(event);
                        }
                    } else {
                        // Não é JSON, trata como log
                        let _ = event_tx_stdout.send(BackendEvent::Log {
                            level: "INFO".to_string(),
                            message: line,
                        });
                    }
                }
            });
            
            // Task para ler stderr (logs humanos)
            let stderr_handle = tokio::spawn(async move {
                let mut reader = BufReader::new(stderr).lines();
                while let Ok(Some(line)) = reader.next_line().await {
                    // Extrai level se presente: [LEVEL] mensagem
                    let (level, msg) = parse_log_line(&line);
                    let _ = event_tx_stderr.send(BackendEvent::Log {
                        level,
                        message: msg,
                    });
                }
            });
            
            // Aguarda conclusão
            let exit_status = child.wait().await;
            
            // Aguarda leitores terminarem
            let _ = tokio::join!(stdout_handle, stderr_handle);
            
            // Limpa handle
            *current_child.lock().unwrap() = None;
            
            // Emite evento de conclusão
            let (exit_code, duration_ms) = match exit_status {
                Ok(status) => (status.code().unwrap_or(-1), 0), // TODO: track duration
                Err(e) => {
                    let _ = event_tx.send(BackendEvent::Error {
                        message: format!("Erro no processo: {}", e),
                    });
                    return;
                }
            };
            
            let _ = event_tx.send(BackendEvent::Complete {
                exit_code,
                duration_ms,
                message: if exit_code == 0 { "Sucesso".to_string() } else { "Falha".to_string() },
            });
        });
        
        *self.poll_handle.lock().unwrap() = Some(handle);
    }
    
    /// Para processo atual graciosamente
    pub fn shutdown(&self) {
        if let Ok(mut child_guard) = self.current_child.lock() {
            if let Some(mut child) = child_guard.take() {
                info!("Enviando SIGTERM para processo core.sh");
                let _ = child.start_kill(); // SIGTERM
                
                // Aguarda um pouco, depois SIGKILL
                tokio::spawn(async move {
                    tokio::time::sleep(Duration::from_secs(2)).await;
                    let _ = child.kill().await; // SIGKILL
                });
            }
        }
    }
}

/// Parses log line like "[LEVEL] message" -> (level, message)
fn parse_log_line(line: &str) -> (String, String) {
    if let Some(end_bracket) = line.find(']') {
        if line.starts_with('[') {
            let level = line[1..end_bracket].trim().to_string();
            let message = line[end_bracket + 1..].trim().to_string();
            return (level, message);
        }
    }
    ("INFO".to_string(), line.to_string())
}

/// Parses JSON event from core.sh stdout
fn parse_json_event(json: Value) -> Option<BackendEvent> {
    let event_type = json.get("type")?.as_str()?;
    
    match event_type {
        "progress" => Some(BackendEvent::Progress {
            stage: json.get("stage")?.as_str()?.to_string(),
            current: json.get("current")?.as_u64()? as u32,
            total: json.get("total")?.as_u64()? as u32,
            percent: json.get("percent")?.as_u64()? as u32,
            message: json.get("message")?.as_str().unwrap_or("").to_string(),
        }),
        "result" => Some(BackendEvent::Result {
            section: json.get("section")?.as_str()?.to_string(),
            data: json.get("data")?.clone(),
        }),
        "complete" => Some(BackendEvent::Complete {
            exit_code: json.get("exit_code")?.as_i64()? as i32,
            duration_ms: json.get("duration_ms")?.as_u64()? as u64,
            message: json.get("message")?.as_str().unwrap_or("").to_string(),
        }),
        _ => None,
    }
}
```

---

## gui/src/backend/events.rs

```rust
//! Eventos de comunicação Backend ↔ GUI

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Comandos que a GUI envia para o Backend
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "cmd")]
pub enum BackendCommand {
    Audit { json: bool },
    Tune { apply: bool, restore: bool, dry_run: bool },
    Memory { cron: Option<String>, remove_cron: bool, dry_run: bool },
    Bench { quick: bool, output: Option<String> },
    TestSuite { 
        baseline_only: bool,
        performance_only: bool,
        memory_only: bool,
        combined_only: bool,
        quick: bool,
        no_restore: bool,
    },
    Report,
}

impl BackendCommand {
    /// Converte comando em argumentos para core.sh
    pub fn to_args(&self) -> Vec<String> {
        let mut args = vec![];
        
        match self {
            BackendCommand::Audit { json } => {
                args.push("audit".to_string());
                if *json { args.push("--json".to_string()); }
            }
            BackendCommand::Tune { apply, restore, dry_run } => {
                args.push("tune".to_string());
                if *apply { args.push("--apply".to_string()); }
                if *restore { args.push("--restore".to_string()); }
                if *dry_run { args.push("--dry-run".to_string()); }
            }
            BackendCommand::Memory { cron, remove_cron, dry_run } => {
                args.push("memory".to_string());
                if let Some(c) = cron { 
                    args.push("--cron".to_string()); 
                    args.push(c.clone()); 
                }
                if *remove_cron { args.push("--remove-cron".to_string()); }
                if *dry_run { args.push("--dry-run".to_string()); }
            }
            BackendCommand::Bench { quick, output } => {
                args.push("bench".to_string());
                if *quick { args.push("--quick".to_string()); }
                if let Some(o) = output { 
                    args.push("--output".to_string()); 
                    args.push(o.clone()); 
                }
            }
            BackendCommand::TestSuite { 
                baseline_only, performance_only, memory_only, combined_only, 
                quick, no_restore 
            } => {
                args.push("test-suite".to_string());
                if *baseline_only { args.push("--baseline-only".to_string()); }
                if *performance_only { args.push("--performance-only".to_string()); }
                if *memory_only { args.push("--memory-only".to_string()); }
                if *combined_only { args.push("--combined-only".to_string()); }
                if *quick { args.push("--quick".to_string()); }
                if *no_restore { args.push("--no-restore".to_string()); }
            }
            BackendCommand::Report => {
                args.push("report".to_string());
            }
        }
        
        args
    }
}

/// Eventos que o Backend envia para a GUI
#[derive(Debug, Clone)]
pub enum BackendEvent {
    /// Progresso de etapa (para progress bar)
    Progress {
        stage: String,
        current: u32,
        total: u32,
        percent: u32,
        message: String,
    },
    /// Resultado estruturado de uma seção
    Result {
        section: String,
        data: Value,
    },
    /// Log humano (stderr do core.sh)
    Log {
        level: String,  // INFO, WARN, ERROR, OK, DEBUG
        message: String,
    },
    /// Conclusão do comando
    Complete {
        exit_code: i32,
        duration_ms: u64,
        message: String,
    },
    /// Erro fatal
    Error {
        message: String,
    },
}
```

---

## gui/src/tabs/mod.rs

```rust
//! Trait comum para todas as tabs

use crate::backend::Backend;
use crate::widgets::LogView;
use eframe::egui::{self, Ui};

pub trait Tab: Send + Sync {
    fn name(&self) -> &str;
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool);
    fn on_backend_result(&mut self, section: &str, data: &serde_json::Value) {}
}

// Re-export tabs
pub mod audit_tab;
pub mod tune_tab;
pub mod bench_tab;
pub mod memory_tab;
pub mod logs_tab;

pub use audit_tab::AuditTab;
pub use tune_tab::TuneTab;
pub use bench_tab::BenchTab;
pub use memory_tab::MemoryTab;
pub use logs_tab::LogsTab;
```

---

## gui/src/tabs/audit_tab.rs

```rust
//! Tab: Auditoria do Sistema

use std::sync::{Arc, Mutex};
use eframe::egui::{self, Ui, RichText, Color32};
use serde_json::Value;
use crossbeam_channel::Sender;
use crate::backend::Backend;
use crate::backend::events::BackendCommand;
use crate::widgets::LogView;
use crate::tabs::Tab;

pub struct AuditTab {
    logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
    event_tx: Sender<crate::app::GuiEvent>,
    
    // Resultados da auditoria
    packages: Option<Value>,
    boot: Option<Value>,
    hardware: Option<Value>,
    overclock: Option<Value>,
    action_plan: Option<Value>,
    
    // UI state
    show_json: bool,
}

impl AuditTab {
    pub fn new(
        logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
        event_tx: Sender<crate::app::GuiEvent>,
    ) -> Self {
        Self {
            logs,
            event_tx,
            packages: None,
            boot: None,
            hardware: None,
            overclock: None,
            action_plan: None,
            show_json: false,
        }
    }
}

impl Tab for AuditTab {
    fn name(&self) -> &str { "Auditoria" }
    
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool) {
        ui.horizontal(|ui| {
            ui.heading("🔍 Auditoria do Sistema");
            ui.separator();
            if ui.button("Executar Auditoria").clicked() && !*running {
                *running = true;
                let _ = backend.execute(BackendCommand::Audit { json: true });
            }
            ui.checkbox(&mut self.show_json, "Mostrar JSON bruto");
        });
        
        ui.separator();
        
        // Resultados em painéis colapsáveis
        egui::ScrollArea::vertical().show(ui, |ui| {
            self.render_section(ui, "📦 Pacotes", &self.packages, |ui, data| {
                self.render_packages(ui, data);
            });
            
            self.render_section(ui, "🚀 Inicialização (Boot)", &self.boot, |ui, data| {
                self.render_boot(ui, data);
            });
            
            self.render_section(ui, "🖥️ Hardware", &self.hardware, |ui, data| {
                self.render_hardware(ui, data);
            });
            
            self.render_section(ui, "⚡ Overclock", &self.overclock, |ui, data| {
                self.render_overclock(ui, data);
            });
            
            self.render_section(ui, "📋 Plano de Ação", &self.action_plan, |ui, data| {
                self.render_action_plan(ui, data);
            });
        });
    }
    
    fn on_backend_result(&mut self, section: &str, data: &Value) {
        match section {
            "packages" => self.packages = Some(data.clone()),
            "boot" => self.boot = Some(data.clone()),
            "hardware" => self.hardware = Some(data.clone()),
            "overclock" => self.overclock = Some(data.clone()),
            "action_plan" => self.action_plan = Some(data.clone()),
            _ => {}
        }
    }
}

impl AuditTab {
    fn render_section<F>(&self, ui: &mut Ui, title: &str, data: &Option<Value>, render: F)
    where F: FnOnce(&mut Ui, &Value) {
        egui::CollapsingHeader::new(title)
            .default_open(true)
            .show(ui, |ui| {
                if let Some(data) = data {
                    if self.show_json {
                        ui.code(format!("{}", serde_json::to_string_pretty(data).unwrap()));
                    } else {
                        render(ui, data);
                    }
                } else {
                    ui.label(RichText::new("Nenhum dado — execute a auditoria").color(Color32::GRAY));
                }
            });
    }
    
    fn render_packages(&self, ui: &mut Ui, data: &Value) {
        if let Some(orphans) = data.get("orphans").and_then(|v| v.as_array()) {
            ui.label(RichText::new(format!("Pacotes órfãos: {}", orphans.len())).strong());
            for pkg in orphans {
                ui.label(format!("  • {}", pkg.as_str().unwrap_or("")));
            }
        }
        if let Some(single) = data.get("single_use").and_then(|v| v.as_array()) {
            ui.label(RichText::new(format!("Uso único/sem binários: {}", single.len())).strong());
            for pkg in single {
                ui.label(format!("  • {}", pkg.as_str().unwrap_or("")));
            }
        }
    }
    
    fn render_boot(&self, ui: &mut Ui, data: &Value) {
        if let Some(time) = data.get("total_time").and_then(|v| v.as_str()) {
            ui.label(format!("Tempo total: {}", time));
        }
        if let Some(bottlenecks) = data.get("bottlenecks").and_then(|v| v.as_array()) {
            ui.label("Serviços mais lentos:");
            for (i, svc) in bottlenecks.iter().enumerate() {
                ui.label(format!("  {}. {}", i + 1, svc.as_str().unwrap_or("")));
            }
        }
        if let Some(chain) = data.get("critical_chain").and_then(|v| v.as_str()) {
            ui.separator();
            ui.label("Cadeia crítica:");
            ui.code(chain);
        }
    }
    
    fn render_hardware(&self, ui: &mut Ui, data: &Value) {
        if let Some(cpu) = data.get("cpu").and_then(|v| v.as_object()) {
            ui.label(RichText::new("CPU").strong());
            for (k, v) in cpu {
                ui.label(format!("  {}: {}", k, v.as_str().unwrap_or("")));
            }
        }
        if let Some(gpu) = data.get("gpu").and_then(|v| v.as_array()) {
            ui.label(RichText::new("GPU").strong());
            for g in gpu { ui.label(format!("  • {}", g.as_str().unwrap_or(""))); }
        }
        if let Some(ram) = data.get("ram").and_then(|v| v.as_object()) {
            ui.label(RichText::new("Memória").strong());
            for (k, v) in ram { ui.label(format!("  {}: {}", k, v.as_str().unwrap_or(""))); }
        }
        if let Some(thermal) = data.get("thermal").and_then(|v| v.as_object()) {
            ui.label(RichText::new("Térmica").strong());
            for (k, v) in thermal { ui.label(format!("  {}: {}", k, v)); }
        }
    }
    
    fn render_overclock(&self, ui: &mut Ui, data: &Value) {
        if let Some(viability) = data.get("viability").and_then(|v| v.as_str()) {
            let color = match viability {
                v if v.contains("Viável") => Color32::GREEN,
                v if v.contains("Requer") => Color32::YELLOW,
                _ => Color32::RED,
            };
            ui.label(RichText::new(format!("Viabilidade: {}", viability)).color(color).strong());
        }
        if let Some(details) = data.get("details").and_then(|v| v.as_array()) {
            for d in details { ui.label(format!("  • {}", d.as_str().unwrap_or(""))); }
        }
    }
    
    fn render_action_plan(&self, ui: &mut Ui, data: &Value) {
        if let Some(plan) = data.as_array() {
            for (i, action) in plan.iter().enumerate() {
                ui.label(format!("{}. {}", i + 1, action.as_str().unwrap_or("")));
            }
        }
    }
}
```

---

## gui/src/tabs/tune_tab.rs

```rust
//! Tab: Performance Tuning

use eframe::egui::{self, Ui, RichText, Color32, Button};
use crate::backend::Backend;
use crate::backend::events::BackendCommand;
use crate::tabs::Tab;

pub struct TuneTab {
    logs: std::sync::Arc<std::sync::Mutex<VecDeque<crate::app::LogEntry>>>,
    event_tx: crossbeam_channel::Sender<crate::app::GuiEvent>,
    
    // Estado UI
    dry_run: bool,
    show_advanced: bool,
    governor_options: Vec<String>,
    selected_governor: usize,
}

impl TuneTab {
    pub fn new(
        logs: std::sync::Arc<std::sync::Mutex<VecDeque<crate::app::LogEntry>>>,
        event_tx: crossbeam_channel::Sender<crate::app::GuiEvent>,
    ) -> Self {
        Self {
            logs,
            event_tx,
            dry_run: true,
            show_advanced: false,
            governor_options: vec![
                "performance".to_string(),
                "powersave".to_string(),
                "schedutil".to_string(),
                "ondemand".to_string(),
                "conservative".to_string(),
            ],
            selected_governor: 0,
        }
    }
}

impl Tab for TuneTab {
    fn name(&self) -> &str { "Tuning" }
    
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool) {
        ui.heading("⚡ Performance Tuning");
        ui.label("⚠️ Requer root. Desabilita C-states, ativa turbo, fixa governor=performance.");
        ui.separator();
        
        // Opções
        ui.horizontal(|ui| {
            ui.checkbox(&mut self.dry_run, "🔍 Dry-run (simular apenas)");
            ui.checkbox(&mut self.show_advanced, "⚙️ Opções avançadas");
        });
        
        if self.show_advanced {
            ui.horizontal(|ui| {
                ui.label("Governor:");
                egui::ComboBox::from_id_salt("governor")
                    .selected_text(&self.governor_options[self.selected_governor])
                    .show_ui(ui, |ui| {
                        for (i, gov) in self.governor_options.iter().enumerate() {
                            ui.selectable_value(&mut self.selected_governor, i, gov);
                        }
                    });
            });
        }
        
        ui.separator();
        
        // Botões de ação
        ui.horizontal(|ui| {
            let apply_btn = ui.add_enabled(
                !*running,
                Button::new(if self.dry_run { "▶ Simular Tuning" } else { "⚡ Aplicar Tuning" })
                    .fill(if self.dry_run { Color32::from_rgb(70, 130, 180) } else { Color32::from_rgb(180, 70, 70) })
            );
            if apply_btn.clicked() {
                *running = true;
                let _ = backend.execute(BackendCommand::Tune {
                    apply: !self.dry_run,
                    restore: false,
                    dry_run: self.dry_run,
                });
            }
            
            let restore_btn = ui.add_enabled(
                !*running,
                Button::new("🔄 Restaurar Padrão").fill(Color32::from_rgb(100, 100, 180))
            );
            if restore_btn.clicked() {
                *running = true;
                let _ = backend.execute(BackendCommand::Tune {
                    apply: false,
                    restore: true,
                    dry_run: false,
                });
            }
        });
        
        ui.separator();
        
        // O que será feito
        egui::CollapsingHeader::new("📋 O que o tuning faz")
            .default_open(true)
            .show(ui, |ui| {
                ui.label("1. CPU Governor → performance (frequência fixa no máximo)");
                ui.label("2. Intel PState → no_hwp + turbo ativado");
                ui.label("3. C-States → desabilitados (latência zero, consumo alto)");
                ui.label("4. Scheduler → latency_ns=1ms, migration_cost_ns=5ms");
                ui.label("5. THP → always (Transparent Huge Pages)");
                ui.label("6. Serviços → thermald, tuned, power-profiles-daemon mascarados");
                ui.label("7. IRQBalance → desabilitado");
            });
        
        // Aviso térmico
        ui.separator();
        ui.colored_label(Color32::YELLOW, "⚠️ MONITORE TEMPERATURAS: watch -n1 sensors");
        ui.colored_label(Color32::RED, "❌ NÃO USE EM LAPTOPS SEM REFRIGERAÇÃO ADEQUADA");
    }
}
```

---

## gui/src/tabs/bench_tab.rs

```rust
//! Tab: Benchmarks

use eframe::egui::{self, Ui, RichText, Color32, Button, ProgressBar};
use crate::backend::Backend;
use crate::backend::events::BackendCommand;
use crate::tabs::Tab;
use std::sync::{Arc, Mutex};
use std::collections::VecDeque;

pub struct BenchTab {
    logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
    event_tx: crossbeam_channel::Sender<crate::app::GuiEvent>,
    
    quick: bool,
    output_path: String,
    last_result: Option<serde_json::Value>,
}

impl BenchTab {
    pub fn new(
        logs: Arc<Mutex<VecDeque<crate::app::LogEntry>>>,
        event_tx: crossbeam_channel::Sender<crate::app::GuiEvent>,
    ) -> Self {
        Self {
            logs,
            event_tx,
            quick: false,
            output_path: "".to_string(),
            last_result: None,
        }
    }
}

impl Tab for BenchTab {
    fn name(&self) -> &str { "Benchmark" }
    
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool) {
        ui.heading("📊 Benchmark Suite");
        ui.separator();
        
        // Configurações
        ui.horizontal(|ui| {
            ui.checkbox(&mut self.quick, "⚡ Quick mode (30s por teste, sem memory/ctx)");
            if self.output_path.is_empty() {
                ui.label("Output: auto (data/benchmarks/benchmark_<timestamp>_<governor>.log)");
            } else {
                ui.label(format!("Output: {}", self.output_path));
            }
        });
        
        ui.separator();
        
        // Botões
        ui.horizontal(|ui| {
            let bench_btn = ui.add_enabled(
                !*running,
                Button::new("▶ Executar Benchmark").fill(Color32::from_rgb(70, 130, 180))
            );
            if bench_btn.clicked() {
                *running = true;
                let output = if self.output_path.is_empty() { None } else { Some(self.output_path.clone()) };
                let _ = backend.execute(BackendCommand::Bench { quick: self.quick, output });
            }
            
            let suite_btn = ui.add_enabled(
                !*running,
                Button::new("🧪 Suite Comparativa Completa").fill(Color32::from_rgb(100, 150, 100))
            );
            if suite_btn.clicked() {
                *running = true;
                let _ = backend.execute(BackendCommand::TestSuite {
                    baseline_only: false,
                    performance_only: false,
                    memory_only: false,
                    combined_only: false,
                    quick: self.quick,
                    no_restore: false,
                });
            }
        });
        
        ui.separator();
        
        // Último resultado
        if let Some(result) = &self.last_result {
            egui::CollapsingHeader::new("📈 Último Resultado")
                .default_open(true)
                .show(ui, |ui| {
                    if let Some(file) = result.get("benchmark_log").and_then(|v| v.get("file")).and_then(|v| v.as_str()) {
                        ui.label(format!("Log: {}", file));
                    }
                    // TODO: Parse log e mostrar métricas principais
                    ui.label("Use 'Gerar Relatório' para análise completa");
                });
        }
        
        ui.separator();
        
        // Botão gerar relatório
        if ui.button("📄 Gerar Relatório Comparativo").clicked() {
            let _ = backend.execute(BackendCommand::Report);
        }
    }
    
    fn on_backend_result(&mut self, section: &str, data: &serde_json::Value) {
        if section == "benchmark_log" {
            self.last_result = Some(data.clone());
        }
    }
}
```

---

## gui/src/tabs/memory_tab.rs

```rust
//! Tab: Memory Optimization

use eframe::egui::{self, Ui, RichText, Color32, Button};
use crate::backend::Backend;
use crate::backend::events::BackendCommand;
use crate::tabs::Tab;

pub struct MemoryTab {
    logs: std::sync::Arc<std::sync::Mutex<VecDeque<crate::app::LogEntry>>>,
    event_tx: crossbeam_channel::Sender<crate::app::GuiEvent>,
    
    cron_mode: String,
    remove_cron: bool,
    dry_run: bool,
}

impl MemoryTab {
    pub fn new(
        logs: std::sync::Arc<std::sync::Mutex<VecDeque<crate::app::LogEntry>>>,
        event_tx: crossbeam_channel::Sender<crate::app::GuiEvent>,
    ) -> Self {
        Self {
            logs,
            event_tx,
            cron_mode: "daily".to_string(),
            remove_cron: false,
            dry_run: true,
        }
    }
}

impl Tab for MemoryTab {
    fn name(&self) -> &str { "Memória" }
    
    fn draw(&mut self, ui: &mut Ui, backend: &mut Backend, running: &mut bool) {
        ui.heading("🧠 Memory Optimization");
        ui.label("Executa: sync → drop_caches=3 → verifica CONFIG_COMPACTION → ativa vm.compaction_memory");
        ui.separator();
        
        // Opções
        ui.horizontal(|ui| {
            ui.checkbox(&mut self.dry_run, "🔍 Dry-run");
            ui.checkbox(&mut self.remove_cron, "🗑️ Remover cron jobs existentes");
        });
        
        if !self.remove_cron {
            ui.horizontal(|ui| {
                ui.label("Cron:");
                egui::ComboBox::from_id_salt("memory_cron")
                    .selected_text(&self.cron_mode)
                    .show_ui(ui, |ui| {
                        ui.selectable_value(&mut self.cron_mode, "none".to_string(), "Nenhum (execução única)");
                        ui.selectable_value(&mut self.cron_mode, "hourly".to_string(), "Horário");
                        ui.selectable_value(&mut self.cron_mode, "daily".to_string(), "Diário (03:00)");
                        ui.selectable_value(&mut self.cron_mode, "weekly".to_string(), "Semanal (Dom 03:00)");
                    });
            });
        }
        
        ui.separator();
        
        // Botão executar
        let btn_text = if self.remove_cron { "🗑️ Remover Crons" } 
            else if self.dry_run { "▶ Simular" } 
            else { "⚡ Aplicar" };
        let btn_color = if self.remove_cron { Color32::from_rgb(180, 70, 70) }
            else if self.dry_run { Color32::from_rgb(70, 130, 180) }
            else { Color32::from_rgb(100, 150, 100) };
        
        let btn = ui.add_enabled(!*running, Button::new(btn_text).fill(btn_color));
        if btn.clicked() {
            *running = true;
            let cron = if self.cron_mode == "none" { None } else { Some(self.cron_mode.clone()) };
            let _ = backend.execute(BackendCommand::Memory { 
                cron, 
                remove_cron: self.remove_cron, 
                dry_run: self.dry_run 
            });
        }
        
        ui.separator();
        
        // Detalhes
        egui::CollapsingHeader::new("ℹ️ O que faz")
            .default_open(true)
            .show(ui, |ui| {
                ui.label("1. sync — Garante buffers de disco escritos");
                ui.label("2. echo 3 > /proc/sys/vm/drop_caches — Libera pagecache, dentries, inodes");
                ui.label("3. Verifica CONFIG_COMPACTION=y em múltiplos locais do kernel");
                ui.label("4. Se suportado: echo 1 > /proc/sys/vm/compaction_memory");
                ui.label("5. Opcional: Instala cron job idempotente (remove antes de adicionar)");
            });
        
        ui.separator();
        ui.colored_label(Color32::YELLOW, "⚠️ drop_caches=3 pode causar latência temporária se muita memória suja");
        ui.colored_label(Color32::YELLOW, "⚠️ Bit errors detectados em testes — verifique hardware RAM");
    }
}
```

---

## gui/src/tabs/logs_tab.rs

```rust
//! Tab: Logs em Tempo Real

use eframe::egui::{self, Ui, RichText, Color32, TextStyle};
use crate::widgets::LogView;
use crate::app::LogLevel;

pub struct LogsTab {
    logs: std::sync::Arc<std::sync::Mutex<VecDeque<crate::app::LogEntry>>>,
    log_view: LogView,
}

impl LogsTab {
    pub fn new(logs: std::sync::Arc<std::sync::Mutex<VecDeque<crate::app::LogEntry>>>) -> Self {
        Self {
            logs,
            log_view: LogView::new(),
        }
    }
}

impl crate::tabs::Tab for LogsTab {
    fn name(&self) -> &str { "Logs" }
    
    fn draw(&mut self, ui: &mut Ui, _backend: &mut crate::backend::Backend, _running: &mut bool) {
        ui.heading("📋 Logs em Tempo Real");
        ui.separator();
        
        // Filtros
        ui.horizontal(|ui| {
            self.log_view.draw_filters(ui);
            ui.separator();
            if ui.button("🗑️ Limpar").clicked() {
                self.logs.lock().unwrap().clear();
            }
        });
        
        ui.separator();
        
        // View de logs
        let logs = self.logs.lock().unwrap();
        self.log_view.draw(ui, &logs);
    }
}
```

---

## gui/src/widgets/log_view.rs

```rust
//! Widget: Caixa de logs com cores, filtros, auto-scroll, busca

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use eframe::egui::{self, Ui, RichText, Color32, TextStyle, ScrollArea, TextEdit};
use crate::app::{LogEntry, LogLevel, LogSource};

pub struct LogView {
    filter_level: Option<LogLevel>,
    filter_source: Option<LogSource>,
    search_text: String,
    auto_scroll: bool,
    max_lines: usize,
}

impl LogView {
    pub fn new() -> Self {
        Self {
            filter_level: None,
            filter_source: None,
            search_text: String::new(),
            auto_scroll: true,
            max_lines: 5000,
        }
    }
    
    pub fn draw_filters(&mut self, ui: &mut Ui) {
        ui.label("Filtros:");
        
        // Level filter
        egui::ComboBox::from_id_salt("log_level_filter")
            .selected_text(match self.filter_level {
                Some(l) => format!("{:?}", l),
                None => "Todos",
            })
            .show_ui(ui, |ui| {
                ui.selectable_value(&mut self.filter_level, None, "Todos");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Info), "Info");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Warn), "Warn");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Error), "Error");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Debug), "Debug");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Success), "Success");
                ui.selectable_value(&mut self.filter_level, Some(LogLevel::Progress), "Progress");
            });
        
        // Source filter
        egui::ComboBox::from_id_salt("log_source_filter")
            .selected_text(match self.filter_source {
                Some(s) => format!("{:?}", s),
                None => "Todas",
            })
            .show_ui(ui, |ui| {
                ui.selectable_value(&mut self.filter_source, None, "Todas");
                ui.selectable_value(&mut self.filter_source, Some(LogSource::Gui), "GUI");
                ui.selectable_value(&mut self.filter_source, Some(LogSource::BackendStdout), "Backend Stdout");
                ui.selectable_value(&mut self.filter_source, Some(LogSource::BackendStderr), "Backend Stderr");
            });
        
        // Search
        ui.add(TextEdit::singleline(&mut self.search_text)
            .hint_text("🔍 Buscar...")
            .desired_width(200.0));
        
        ui.checkbox(&mut self.auto_scroll, "📜 Auto-scroll");
    }
    
    pub fn draw(&mut self, ui: &mut Ui, logs: &VecDeque<LogEntry>) {
        let available_height = ui.available_height();
        
        ScrollArea::vertical()
            .auto_shrink([false, false])
            .stick_to_bottom(self.auto_scroll)
            .max_height(available_height)
            .show_rows(ui, 18.0, logs.len(), |ui, row_range| {
                for idx in row_range.start..row_range.end {
                    if let Some(entry) = logs.get(idx) {
                        // Aplica filtros
                        if let Some(f) = self.filter_level {
                            if entry.level != f { continue; }
                        }
                        if let Some(f) = self.filter_source {
                            if entry.source != f { continue; }
                        }
                        if !self.search_text.is_empty() {
                            if !entry.message.to_lowercase().contains(&self.search_text.to_lowercase()) {
                                continue;
                            }
                        }
                        
                        self.draw_log_entry(ui, entry);
                    }
                }
            });
    }
    
    fn draw_log_entry(&self, ui: &mut Ui, entry: &LogEntry) {
        let time_str = entry.timestamp.format("%H:%M:%S%.3f").to_string();
        
        let (level_color, level_prefix) = match entry.level {
            LogLevel::Info => (Color32::LIGHT_BLUE, "[INFO]"),
            LogLevel::Warn => (Color32::YELLOW, "[WARN]"),
            LogLevel::Error => (Color32::RED, "[ERROR]"),
            LogLevel::Debug => (Color32::GRAY, "[DEBUG]"),
            LogLevel::Success => (Color32::GREEN, "[OK]"),
            LogLevel::Progress => (Color32::from_rgb(70, 130, 180), "[PROG]"),
        };
        
        let source_str = match entry.source {
            LogSource::Gui => "GUI",
            LogSource::BackendStdout => "OUT",
            LogSource::BackendStderr => "ERR",
        };
        
        ui.horizontal(|ui| {
            ui.label(RichText::new(time_str).monospace().size(11.0).color(Color32::GRAY));
            ui.label(RichText::new(format!("{:<4}", source_str)).monospace().size(11.0).color(Color32::DARK_GRAY));
            ui.label(RichText::new(level_prefix).monospace().size(11.0).color(level_color));
            
            // Mensagem com wrap
            let msg = RichText::new(&entry.message).monospace().size(11.0);
            ui.label(msg);
        });
    }
}
```

---

## gui/src/widgets/progress_bar.rs

```rust
//! Widget: Barra de progresso customizada com ETA

use eframe::egui::{self, Ui, Color32, RichText};
use std::time::{Duration, Instant};

pub struct ProgressWidget {
    start_time: Option<Instant>,
    last_update: Instant,
}

impl ProgressWidget {
    pub fn new() -> Self {
        Self {
            start_time: None,
            last_update: Instant::now(),
        }
    }
    
    pub fn draw(&mut self, ui: &mut Ui, stage: &str, current: u32, total: u32, message: &str) {
        if self.start_time.is_none() {
            self.start_time = Some(Instant::now());
        }
        
        let percent = if total > 0 { current as f32 / total as f32 } else { 0.0 };
        let elapsed = self.start_time.unwrap().elapsed();
        
        // ETA
        let eta = if current > 0 && percent > 0.0 {
            let total_estimated = elapsed.as_secs_f32() / percent;
            let remaining = total_estimated - elapsed.as_secs_f32();
            Some(Duration::from_secs_f32(remaining.max(0.0)))
        } else { None };
        
        ui.horizontal(|ui| {
            ui.label(RichText::new(stage).strong());
            ui.add(egui::ProgressBar::new(percent)
                .show_percentage()
                .animate(true)
                .desired_width(200.0));
            ui.label(format!("{}/{}", current, total));
            
            if let Some(eta) = eta {
                ui.label(RichText::new(format!("ETA: {:.0}s", eta.as_secs())).color(Color32::GRAY));
            }
            ui.label(RichText::new(format!("({:.0}s)", elapsed.as_secs())).color(Color32::GRAY));
        });
        
        if !message.is_empty() {
            ui.label(RichText::new(message).italics().color(Color32::GRAY));
        }
    }
    
    pub fn reset(&mut self) {
        self.start_time = None;
        self.last_update = Instant::now();
    }
}
```

---

## gui/src/widgets/param_input.rs

```rust
//! Widgets: Inputs tipados reutilizáveis

use eframe::egui::{self, Ui, Slider, DragValue, ComboBox, Checkbox, TextEdit};

/// Slider com label e valor
pub fn slider_param(ui: &mut Ui, label: &str, value: &mut f32, range: std::ops::RangeInclusive<f32>, suffix: &str) {
    ui.horizontal(|ui| {
        ui.label(label);
        ui.add(Slider::new(value, range).suffix(suffix).clamp_to_range(true));
    });
}

/// Dropdown para enum
pub fn enum_param<T: Clone + PartialEq + std::fmt::Display>(
    ui: &mut Ui,
    label: &str,
    value: &mut T,
    options: &[(T, &str)],
) {
    ui.horizontal(|ui| {
        ui.label(label);
        ComboBox::from_id_salt(label)
            .selected_text(options.iter().find(|(v, _)| *v == *value).map(|(_, l)| *l).unwrap_or(""))
            .show_ui(ui, |ui| {
                for (v, l) in options {
                    ui.selectable_value(value, v.clone(), *l);
                }
            });
    });
}

/// Checkbox com label
pub fn bool_param(ui: &mut Ui, label: &str, value: &mut bool) {
    ui.checkbox(value, label);
}

/// Text input
pub fn text_param(ui: &mut Ui, label: &str, value: &mut String, hint: &str) {
    ui.horizontal(|ui| {
        ui.label(label);
        ui.add(TextEdit::singleline(value).hint_text(hint).desired_width(200.0));
    });
}

/// Path input com botão browse
pub fn path_param(ui: &mut Ui, label: &str, value: &mut String) {
    ui.horizontal(|ui| {
        ui.label(label);
        ui.add(TextEdit::singleline(value).desired_width(300.0));
        if ui.button("📁").clicked() {
            if let Some(path) = rfd::FileDialog::new().pick_file() {
                *value = path.display().to_string();
            }
        }
    });
}
```

---

## Resumo dos Arquivos Principais

| Arquivo | Responsabilidade |
|---------|------------------|
| `scripts/core.sh` | **Lógica única** — audit, tune, memory, bench, test-suite, report. CLI + JSON output |
| `scripts/lib/*.sh` | Funções compartilhadas (common, hardware, thermal) |
| `gui/Cargo.toml` | Dependências Rust (eframe, tokio, crossbeam-channel, serde, tracing) |
| `gui/src/main.rs` | Entry point, setup eframe, fonts, icon |
| `gui/src/app.rs` | Estado global, tabs, event loop, persistência |
| `gui/src/backend/runner.rs` | Executa core.sh via tokio::process, streaming stdout/stderr |
| `gui/src/backend/events.rs` | Protocolos BackendCommand / BackendEvent |
| `gui/src/tabs/*.rs` | 5 tabs: Audit, Tune, Bench, Memory, Logs |
| `gui/src/widgets/*.rs` | LogView, ProgressWidget, ParamInputs |

---

## Como Compilar e Executar

```bash
# 1. Garante que core.sh é executável
chmod +x scripts/core.sh scripts/lib/*.sh

# 2. Testa CLI direto
./scripts/core.sh audit --json
./scripts/core.sh bench --quick --dry-run
./scripts/core.sh tune --apply --dry-run

# 3. Compila GUI (release)
cd gui
cargo build --release

# 4. Executa GUI
./target/release/sysopt-gui
# ou em dev:
cargo run --release
```

---

## Princípios Mantidos

✅ **Separação total**: core.sh não sabe da GUI. GUI só invoca core.sh.  
✅ **CLI funcional**: Todos os comandos funcionam no terminal sem GUI.  
✅ **JSON Lines**: Comunicação estruturada para GUI parsear.  
✅ **Logs humanos**: stderr colorido para debug visual.  
✅ **Non-blocking**: tokio + threads + channels = GUI nunca congela.  
✅ **Dry-run first**: Segurança por padrão.  
✅ **Persistência**: Tamanho janela, última aba, configurações salvas.