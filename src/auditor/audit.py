#!/usr/bin/env python3
"""
Auditor de Sistema Linux - Diagnóstico Passivo
Executa varredura analítica sem modificações no sistema.
"""

import subprocess
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional


class LinuxAuditor:
    def __init__(self):
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "packages": {"orphans": [], "single_use": []},
            "boot": {"total_time": "", "bottlenecks": []},
            "hardware": {"cpu": {}, "gpu": {}, "ram": {}, "thermal": {}},
            "overclock": {"viability": "Indeterminado", "details": []},
            "action_plan": []
        }

    def run_cmd(self, cmd: List[str], timeout: int = 30) -> str:
        """Executa comando e retorna stdout."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            return f"TIMEOUT: {cmd}"
        except Exception as e:
            return f"ERRO: {e}"

    def audit_packages(self) -> None:
        """Audita pacões órfãos e uso único via pacman."""
        print("[*] Auditoria de pacotes (pacman)...")

        # Pacotes órfãos: instalados como dependência mas não requeridos
        orphans_out = self.run_cmd(["pacman", "-Qtdq"])
        if orphans_out and "ERRO" not in orphans_out:
            self.report["packages"]["orphans"] = orphans_out.splitlines()

        # Pacotes explicitamente instalados
        explicit_out = self.run_cmd(["pacman", "-Qeq"])
        explicit_pkgs = set(explicit_out.splitlines()) if explicit_out else set()

        # Verificar uso via logs do pacman (simplificado - pacotes sem arquivos executáveis recentes)
        # Nota: análise real de "uso único" requereria auditd ou logs de execução
        all_pkgs_out = self.run_cmd(["pacman", "-Q"])
        all_pkgs = {}
        if all_pkgs_out:
            for line in all_pkgs_out.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    all_pkgs[parts[0]] = parts[1]

        # Identificar pacotes sem binários (bibliotecas, docs) - candidatos a não uso direto
        for pkg in explicit_pkgs:
            files_out = self.run_cmd(["pacman", "-Ql", pkg])
            has_bin = any("/bin/" in f or "/sbin/" in f or "/usr/bin/" in f or "/usr/sbin/" in f
                          for f in files_out.splitlines())
            if not has_bin and pkg not in self.report["packages"]["orphans"]:
                self.report["packages"]["single_use"].append(f"{pkg} (sem binários executáveis)")

    def audit_boot(self) -> None:
        """Analisa tempo de boot e gargalos via systemd-analyze."""
        print("[*] Análise de inicialização (systemd-analyze)...")

        # Tempo total de boot
        time_out = self.run_cmd(["systemd-analyze"])
        match = re.search(r"Startup finished in (.+)", time_out)
        if match:
            self.report["boot"]["total_time"] = match.group(1)

        # Gargalos: serviços mais lentos
        blame_out = self.run_cmd(["systemd-analyze", "blame"])
        if blame_out:
            lines = blame_out.splitlines()
            for line in lines[:15]:  # Top 15
                parts = line.split()
                if len(parts) >= 2:
                    self.report["boot"]["bottlenecks"].append({
                        "service": parts[-1],
                        "time": " ".join(parts[:-1])
                    })

        # Critical chain
        chain_out = self.run_cmd(["systemd-analyze", "critical-chain"])
        if chain_out:
            self.report["boot"]["critical_chain"] = chain_out

    def audit_hardware(self) -> None:
        """Inspeciona hardware: CPU, GPU, RAM, térmica."""
        print("[*] Avaliação de hardware...")

        # CPU
        cpu_out = self.run_cmd(["lscpu", "-J"])
        if cpu_out and "ERRO" not in cpu_out:
            try:
                cpu_data = json.loads(cpu_out)
                for item in cpu_data.get("lscpu", []):
                    field = item.get("field", "").rstrip(":")
                    # Normalizar nomes de campo (PT-BR -> EN)
                    field_map = {
                        "Arquitetura": "Architecture",
                        "Modo(s) operacional da CPU": "CPU op-mode(s)",
                        "Tamanhos de endereço": "Address sizes",
                        "Ordem dos bytes": "Byte Order",
                        "CPU(s)": "CPU(s)",
                        "Lista de CPU(s) on-line": "On-line CPU(s) list",
                        "ID de fornecedor": "Vendor ID",
                        "Nome do modelo": "Model name",
                        "Família da CPU": "CPU family",
                        "Modelo": "Model",
                        "Thread(s) per núcleo": "Thread(s) per core",
                        "Núcleo(s) por soquete": "Core(s) per socket",
                        "Soquete(s)": "Socket(s)",
                        "Step": "Stepping",
                        "Versão do micro-código": "Microcode",
                        "CPU(s) MHz de escala": "CPU MHz scaling",
                        "CPU MHz": "CPU MHz",
                        "CPU MHz máx.": "CPU max MHz",
                        "CPU MHz mín.": "CPU min MHz",
                        "BogoMIPS": "BogoMIPS",
                        "Virtualização": "Virtualization",
                        "Cache L1d": "L1d cache",
                        "Cache L1i": "L1i cache",
                        "Cache L2": "L2 cache",
                        "Cache L3": "L3 cache",
                        "Flags": "Flags",
                    }
                    normalized = field_map.get(field, field)
                    self.report["hardware"]["cpu"][normalized] = item.get("data", "")
            except json.JSONDecodeError:
                pass

        # GPU
        gpu_out = self.run_cmd(["lspci", "-nn"])
        gpus = []
        for line in gpu_out.splitlines():
            if "VGA" in line or "3D" in line or "Display" in line:
                gpus.append(line.strip())
        self.report["hardware"]["gpu"]["devices"] = gpus

        # RAM
        mem_out = self.run_cmd(["free", "-h"])
        self.report["hardware"]["ram"]["summary"] = mem_out

        # Detalhes de memória via dmidecode (requer root para completo)
        dimm_out = self.run_cmd(["dmidecode", "-t", "memory"])
        self.report["hardware"]["ram"]["details"] = dimm_out[:5000]  # Limitar tamanho

        # Térmica - sensors
        sensors_out = self.run_cmd(["sensors"])
        self.report["hardware"]["thermal"]["sensors"] = sensors_out

        # Parse sensors for core temps
        core_temps = []
        for line in sensors_out.splitlines():
            if "Core" in line or "Package" in line:
                match = re.search(r'\+?(\d+\.?\d*)°C', line)
                if match:
                    core_temps.append(float(match.group(1)))

        # Temperaturas CPU via thermal zones
        thermal_out = self.run_cmd(["cat", "/sys/class/thermal/thermal_zone*/temp"])
        zone_temps = []
        for line in thermal_out.splitlines():
            try:
                zone_temps.append(int(line) / 1000)
            except ValueError:
                pass

        self.report["hardware"]["thermal"]["core_temps_c"] = core_temps
        self.report["hardware"]["thermal"]["zone_temps_c"] = zone_temps
        self.report["hardware"]["thermal"]["max_core_temp"] = max(core_temps) if core_temps else 0
        self.report["hardware"]["thermal"]["avg_core_temp"] = sum(core_temps) / len(core_temps) if core_temps else 0

    def evaluate_overclock(self) -> None:
        """Avalia viabilidade de overclock baseada em hardware e térmica."""
        print("[*] Avaliação de viabilidade de overclock...")

        cpu = self.report["hardware"]["cpu"]
        thermal = self.report["hardware"]["thermal"]

        details = []
        viable = "Inviável"

        # Verificar se CPU suporta overclock (K series Intel, X series AMD, ou unlocked)
        cpu_model = cpu.get("Model name", "").lower()
        cpu_flags = cpu.get("Flags", "").lower()

        if "intel" in cpu_model:
            if "k" in cpu_model or "x" in cpu_model or "unlocked" in cpu_flags:
                viable = "Viável (CPU unlocked Intel)"
            else:
                viable = "Inviável (CPU Intel locked - multiplicador travado)"
            details.append(f"Modelo: {cpu.get('Model name', 'Desconhecido')}")
        elif "amd" in cpu_model:
            if "ryzen" in cpu_model or "threadripper" in cpu_model or "epyc" in cpu_model:
                viable = "Viável (AMD Ryzen/Threadripper - unlocked por padrão)"
            else:
                viable = "Requer verificação (AMD - verificar modelo específico)"
            details.append(f"Modelo: {cpu.get('Model name', 'Desconhecido')}")

        # Frequências
        cpu_mhz = cpu.get("CPU MHz", "?")
        cpu_max_mhz = cpu.get("CPU max MHz", "?")
        if cpu_mhz != "?" and cpu_max_mhz != "?":
            details.append(f"Frequência atual: {cpu_mhz} MHz | Máx. turbo: {cpu_max_mhz} MHz")

        # Margem térmica - usar core_temps do sensors
        core_temps = thermal.get("core_temps_c", [])
        if core_temps:
            max_temp = max(core_temps)
            avg_temp = sum(core_temps) / len(core_temps)
            details.append(f"Temp. máx. núcleo (sensors): {max_temp}°C")
            details.append(f"Temp. média núcleos: {avg_temp:.1f}°C")

            if max_temp < 50:
                details.append("Margem térmica: EXCELENTE (muito espaço para OC)")
            elif max_temp < 60:
                details.append("Margem térmica: BOA (espaço moderado para OC)")
            elif max_temp < 70:
                details.append("Margem térmica: LIMITADA (OC conservador apenas)")
            elif max_temp < 80:
                details.append("Margem térmica: RESTRITA (undervolt recomendado)")
            else:
                details.append("Margem térmica: CRÍTICA (OC não recomendado)")
                if viable != "Inviável (CPU Intel locked - multiplicador travado)":
                    viable = "Inviável (temperaturas base elevadas)"

        # Verificar refrigeração
        sensors = thermal.get("sensors", "")
        if "fan" in sensors.lower() or "rpm" in sensors.lower():
            details.append("Ventoinhas detectadas via sensors")
        else:
            details.append("AVISO: Nenhuma ventoinha detectada em sensors")

        # RAM - verificar XMP/DOCP
        ram_details = self.report["hardware"]["ram"].get("details", "")
        if "XMP" in ram_details or "DOCP" in ram_details or "SPD" in ram_details:
            details.append("Perfis XMP/DOCP detectados na RAM")
        else:
            details.append("RAM: Verificar suporte XMP/DOCP no BIOS")

        self.report["overclock"]["viability"] = viable
        self.report["overclock"]["details"] = details

    def generate_action_plan(self) -> None:
        """Compila plano de ação baseado nos achados."""
        print("[*] Gerando plano de ação...")

        plan = []
        pkg = self.report["packages"]
        boot = self.report["boot"]
        hw = self.report["hardware"]
        oc = self.report["overclock"]

        # 1. Pacotes
        if pkg["orphans"]:
            plan.append(f"Remover {len(pkg['orphans'])} pacotes órfãos: `pacman -Rns {' '.join(pkg['orphans'][:5])}{'...' if len(pkg['orphans']) > 5 else ''}`")
        if pkg["single_use"]:
            plan.append(f"Revisar {len(pkg['single_use'])} pacotes sem binários executáveis (candidatos a remoção)")

        # 2. Boot
        if boot["bottlenecks"]:
            top = boot["bottlenecks"][0]
            plan.append(f"Otimizar serviço de boot mais lento: {top['service']} ({top['time']}) - analisar com `systemd-analyze plot > boot.svg`")
        if len(boot["bottlenecks"]) > 3:
            plan.append(f"Desabilitar/mascarar serviços não essenciais entre top 10 gargalos: {[b['service'] for b in boot['bottlenecks'][1:4]]}")

        # 3. Hardware/Overclock
        if oc["viability"] == "Viável":
            plan.append("Overclock viável: testar incrementos conservadores com stress test (prime95, memtest86) e monitorar térmicas")
        elif "Requer" in oc["viability"]:
            plan.append(f"Overclock: {oc['viability']} - avaliar refrigeração e BIOS antes de proceder")
        else:
            plan.append(f"Overclock: {oc['viability']} - focar em undervolt para reduzir temperaturas")

        # Térmicas
        zone_temps = hw.get("thermal", {}).get("zone_temps_c", [])
        if zone_temps and max(zone_temps) > 70:
            plan.append("CRÍTICO: Temperaturas base elevadas - limpar dissipadores, trocar pasta térmica, melhorar fluxo de ar")

        # RAM
        plan.append("Verificar se XMP/DOCP está ativo no BIOS para RAM operar na frequência nominal")

        # General
        plan.append("Executar `pacman -Sc` para limpar cache de pacotes antigos")
        plan.append("Configurar `systemd-oomd` ou `earlyoom` para gestão de memória sob pressão")

        self.report["action_plan"] = plan

    def get_project_root(self) -> Path:
        """Retorna o diretório raiz do projeto."""
        # __file__ = src/auditor/audit.py -> parent=src/auditor, parent.parent=src, parent.parent.parent=project_root
        return Path(__file__).parent.parent.parent

    def get_output_path(self) -> Path:
        """Retorna caminho para o arquivo de saída do relatório."""
        return self.get_project_root() / "data" / "diagnostico_sistema.md"

    def to_markdown(self) -> str:
        """Gera relatório final em Markdown."""
        r = self.report

        md = f"""# Relatório de Diagnóstico do Sistema Linux

**Data/Hora:** {r['timestamp']}
**Hostname:** {self.run_cmd(['hostname'])}

## 1. Auditoria de Pacotes

### Pacotes Órfãos / Não Utilizados
"""
        if r["packages"]["orphans"]:
            for pkg in r["packages"]["orphans"]:
                md += f"- {pkg}\n"
        else:
            md += "- Nenhum pacote órfão detectado\n"

        md += "\n### Uso Único / Sem Binários Executáveis\n"
        if r["packages"]["single_use"]:
            for pkg in r["packages"]["single_use"]:
                md += f"- {pkg}\n"
        else:
            md += "- Nenhum pacote suspeito identificado\n"

        md += f"""
## 2. Análise de Inicialização (Boot)

- **Tempo Total de Boot:** {r['boot']['total_time'] or 'Não disponível'}

### Serviços Gargalo (Top 15)
"""
        if r["boot"]["bottlenecks"]:
            for i, b in enumerate(r["boot"]["bottlenecks"], 1):
                md += f"{i}. **{b['service']}** — {b['time']}\n"
        else:
            md += "- Nenhum gargalo identificado\n"

        if "critical_chain" in r["boot"]:
            md += f"\n### Cadeia Crítica\n```\n{r['boot']['critical_chain']}\n```\n"

        md += """
## 3. Viabilidade de Overclock de Hardware
"""
        cpu = r["hardware"]["cpu"]
        md += f"""- **Componente Analisado:** CPU — {cpu.get('Model name', 'Desconhecido')}
- **Arquitetura:** {cpu.get('Architecture', 'Desconhecida')}
- **CPU(s):** {cpu.get('CPU(s)', '?')} | **Thread(s) por core:** {cpu.get('Thread(s) per core', '?')} | **Core(s) por socket:** {cpu.get('Core(s) per socket', '?')}
- **Frequência base:** {cpu.get('CPU MHz', '?')} MHz | **Máx.:** {cpu.get('CPU max MHz', '?')} MHz
"""
        gpu = r["hardware"]["gpu"]
        if gpu.get("devices"):
            md += f"- **GPU(s):**\n"
            for g in gpu["devices"]:
                md += f"  - {g}\n"

        ram = r["hardware"]["ram"]
        md += f"- **Memória:**\n{ram.get('summary', 'Indisponível')}\n"

        thermal = r["hardware"]["thermal"]
        if thermal.get("core_temps_c"):
            md += f"- **Temperaturas núcleos (sensors):** {', '.join(f'{t}°C' for t in thermal['core_temps_c'])}\n"
        if thermal.get("zone_temps_c"):
            md += f"- **Temperaturas (zonas térmicas):** {', '.join(f'{t}°C' for t in thermal['zone_temps_c'])}\n"

        md += f"""
### Margem Térmica e Estabilidade
"""
        for d in r["overclock"]["details"]:
            md += f"- {d}\n"

        md += f"""
### Viabilidade
- **{r['overclock']['viability']}**

## 4. Plano de Ação
"""
        for i, action in enumerate(r["action_plan"], 1):
            md += f"{i}. {action}\n"

        md += """
---
*Relatório gerado por Auditor de Sistema Linux - Modo Somente Leitura*
"""
        return md

    def run(self) -> str:
        """Executa auditoria completa."""
        print("=" * 50)
        print("AUDITOR DE SISTEMA LINUX - INICIANDO VARREDURA")
        print("=" * 50)

        self.audit_packages()
        self.audit_boot()
        self.audit_hardware()
        self.evaluate_overclock()
        self.generate_action_plan()

        print("=" * 50)
        print("VARREDURA CONCLUÍDA")
        print("=" * 50)

        return self.to_markdown()


def main():
    auditor = LinuxAuditor()
    report = auditor.run()

    # Salvar em arquivo
    output_path = auditor.get_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"\n[+] Relatório salvo em: {output_path}")

    # Exibir no terminal
    print("\n" + "=" * 50)
    print("RELATÓRIO FINAL")
    print("=" * 50)
    print(report)


if __name__ == "__main__":
    main()