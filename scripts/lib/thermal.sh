#!/usr/bin/env bash
# thermal.sh — Monitoramento térmico, alertas e proteção

# ========== CONSTANTES TÉRMICAS ==========
readonly THERMAL_WARN_IDLE=50      # °C idle warning
readonly THERMAL_WARN_LOAD=70      # °C load warning
readonly THERMAL_CRITICAL=85       # °C critical - auto throttle
readonly THERMAL_EMERGENCY=95      # °C emergency - shutdown
readonly THERMAL_CHECK_INTERVAL=2  # segundos entre checks

# ========== LEITURA DE TEMPERATURAS ==========
get_cpu_temps() {
    local temps=()
    
    # Via sensors (lm_sensors) - mais preciso
    if command -v sensors &>/dev/null; then
        while IFS= read -r line; do
            if [[ "$line" =~ (Core|Package).*\+?([0-9]+\.?[0-9]*)°C ]]; then
                temps+=("${BASH_REMATCH[2]}")
            fi
        done < <(sensors 2>/dev/null)
    fi
    
    # Fallback: zonas térmicas do kernel
    if [[ ${#temps[@]} -eq 0 ]]; then
        for zone in /sys/class/thermal/thermal_zone*/temp; do
            [[ -r "$zone" ]] || continue
            local temp
            temp=$(cat "$zone" 2>/dev/null)
            if [[ "$temp" =~ ^[0-9]+$ ]]; then
                temps+=("$((temp / 1000))")
            fi
        done
    fi
    
    printf '%s\n' "${temps[@]}"
}

get_max_temp() {
    local temps
    mapfile -t temps < <(get_cpu_temps)
    if [[ ${#temps[@]} -gt 0 ]]; then
        printf '%s\n' "${temps[@]}" | sort -nr | head -1
    else
        echo 0
    fi
}

get_avg_temp() {
    local temps
    mapfile -t temps < <(get_cpu_temps)
    if [[ ${#temps[@]} -gt 0 ]]; then
        local sum=0
        for t in "${temps[@]}"; do sum=$((sum + t)); done
        echo $((sum / ${#temps[@]}))
    else
        echo 0
    fi
}

# ========== MONITORAMENTO CONTÍNUO ==========
thermal_monitor_loop() {
    local duration="${1:-0}"  # 0 = infinito
    local callback="${2:-}"   # função chamada a cada check
    local start_time
    start_time=$(date +%s)
    
    log_info "Iniciando monitoramento térmico (intervalo: ${THERMAL_CHECK_INTERVAL}s)..."
    
    while true; do
        local max_temp avg_temp
        max_temp=$(get_max_temp)
        avg_temp=$(get_avg_temp)
        
        # Callback se fornecido
        if [[ -n "$callback" ]]; then
            "$callback" "$max_temp" "$avg_temp"
        fi
        
        # Log periódico
        log_debug "Thermal: max=${max_temp}°C avg=${avg_temp}°C"
        
        # Verifica thresholds
        if [[ $max_temp -ge $THERMAL_EMERGENCY ]]; then
            log_err "EMERGÊNCIA TÉRMICA: ${max_temp}°C >= ${THERMAL_EMERGENCY}°C"
            return 2
        elif [[ $max_temp -ge $THERMAL_CRITICAL ]]; then
            log_warn "CRÍTICO: ${max_temp}°C >= ${THERMAL_CRITICAL}°C"
        elif [[ $max_temp -ge $THERMAL_WARN_LOAD ]]; then
            log_warn "Atenção: ${max_temp}°C >= ${THERMAL_WARN_LOAD}°C"
        fi
        
        # Timeout check
        if [[ $duration -gt 0 ]]; then
            local elapsed=$(($(date +%s) - start_time))
            if [[ $elapsed -ge $duration ]]; then
                log_info "Monitoramento térmico concluído (${duration}s)"
                return 0
            fi
        fi
        
        sleep "$THERMAL_CHECK_INTERVAL"
    done
}

# ========== PROTEÇÃO AUTOMÁTICA ==========
thermal_auto_protect() {
    local pid_to_kill="${1:-}"
    
    log_info "Proteção térmica automática ativada (max: ${THERMAL_CRITICAL}°C)"
    
    thermal_monitor_loop 0 "thermal_protect_callback"
}

thermal_protect_callback() {
    local max_temp="$1" avg_temp="$2"
    local pid_to_kill="${THERMAL_PID_TO_KILL:-}"
    
    if [[ $max_temp -ge $THERMAL_CRITICAL ]] && [[ -n "$pid_to_kill" ]]; then
        log_warn "Temperatura crítica (${max_temp}°C) - enviando SIGTERM para PID $pid_to_kill"
        kill -TERM "$pid_to_kill" 2>/dev/null || true
        sleep 2
        kill -KILL "$pid_to_kill" 2>/dev/null || true
        return 2
    fi
}

# ========== ESTADO TÉRMICO PARA JSON ==========
thermal_state_json() {
    local max_temp avg_temp
    max_temp=$(get_max_temp)
    avg_temp=$(get_avg_temp)
    
    local status="ok"
    if [[ $max_temp -ge $THERMAL_CRITICAL ]]; then status="critical";
    elif [[ $max_temp -ge $THERMAL_WARN_LOAD ]]; then status="warn";
    elif [[ $max_temp -ge $THERMAL_WARN_IDLE ]]; then status="caution"; fi
    
    jq -n \
        --argjson max "$max_temp" \
        --argjson avg "$avg_temp" \
        --arg status "$status" \
        --argjson warn_idle "$THERMAL_WARN_IDLE" \
        --argjson warn_load "$THERMAL_WARN_LOAD" \
        --argjson critical "$THERMAL_CRITICAL" \
        --argjson emergency "$THERMAL_EMERGENCY" \
        '{
            max_temp_c: $max,
            avg_temp_c: $avg,
            status: $status,
            thresholds: {
                warn_idle: $warn_idle,
                warn_load: $warn_load,
                critical: $critical,
                emergency: $emergency
            }
        }'
}

# ========== FAN CONTROL ==========
get_fan_speeds() {
    local fans=()
    for fan in /sys/class/hwmon/hwmon*/fan*_input; do
        [[ -r "$fan" ]] || continue
        local label rpm
        label=$(cat "${fan%_input}_label" 2>/dev/null || basename "$fan")
        rpm=$(cat "$fan" 2>/dev/null)
        [[ -n "$rpm" ]] && fans+=("$label: $rpm RPM")
    done
    printf '%s\n' "${fans[@]}"
}

set_fan_speed() {
    local fan_path="$1" speed="$2"  # speed em PWM (0-255) ou RPM
    local pwm_path="${fan_path%_input}_pwm"
    
    if [[ -w "$pwm_path" ]]; then
        echo "$speed" > "$pwm_path"
        log_ok "Fan $fan_path definido para $speed"
    else
        log_err "Não é possível controlar fan: $pwm_path não acessível"
        return 1
    fi
}

# ========== THROTTLING DETECTION ==========
check_throttling() {
    local throttled=0
    
    # Intel: MSR IA32_THERM_STATUS
    if command -v rdmsr &>/dev/null && [[ $EUID -eq 0 ]]; then
        local msr
        msr=$(rdmsr -p 0 0x19c 2>/dev/null) || return 0
        # Bit 0 = thermal status, bit 1 = thermal status log
        if [[ $((msr & 1)) -eq 1 ]]; then throttled=1; fi
    fi
    
    # Kernel: /sys/devices/system/cpu/cpu*/thermal_throttle
    for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
        local throttle_file="$cpu/thermal_throttle/package_throttle_count"
        if [[ -r "$throttle_file" ]]; then
            local count
            count=$(cat "$throttle_file" 2>/dev/null)
            [[ $count -gt 0 ]] && throttled=1
        fi
    done
    
    echo $throttled
}

# Export
export -f get_cpu_temps get_max_temp get_avg_temp thermal_monitor_loop thermal_auto_protect thermal_protect_callback thermal_state_json get_fan_speeds set_fan_speed check_throttling
export THERMAL_WARN_IDLE THERMAL_WARN_LOAD THERMAL_CRITICAL THERMAL_EMERGENCY THERMAL_CHECK_INTERVAL