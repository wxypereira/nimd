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