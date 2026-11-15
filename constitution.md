# CONSTITUTION.md — Lei Fundamental do System Optimization Toolkit

> **Este documento é a autoridade suprema do projeto.** Toda decisão técnica, arquitetural ou de processo deve estar alinhada com o aqui disposto. Se houver conflito entre esta constituição e qualquer outra documentação, **esta prevalece**.

---

## 1. FILOSOFIA CORE

### 1.1 Princípio Zero: **Respeito ao Hardware e ao Usuário**
- O software serve ao hardware, não o contrário.
- Nenhuma otimização deve comprometer a integridade física do equipamento.
- O usuário **sempre** tem a palavra final — ferramentas sugerem, não impõem.

### 1.2 Separação Estrita de Responsabilidades (SoC)
| Camada | Responsabilidade | Permissão | Linguagem |
|--------|------------------|-----------|-----------|
| **Auditor** | Diagnóstico passivo, coleta de dados, relatórios | **Read-only** (nunca escreve) | Python 3.11+ |
| **Tuning** | Modificações de runtime (governor, C-states, THP, scheduler) | **Root / Write** | Bash (POSIX + Bash 4+) |
| **Memory** | Limpeza de caches, compactação, cron jobs | **Root / Write** | Bash |
| **Benchmarks** | Carga de trabalho sintética, medição | **User / Read-only** | Bash + stress-ng + sysbench |
| **Reporting** | Agregação, análise, geração de Markdown | **User / Read-only** | Bash (awk/sed) |

> **Regra de Ouro:** Código Python **nunca** toca sysfs/procfs para escrita. Código Bash **nunca** faz lógica complexa de parsing — delega ao Python ou usa awk/sed simples.

### 1.3 Modo Operacional Padrão: **Defensive by Default**
- Todo script perigoso requer `--dry-run` funcional e avisos visuais.
- Toda ação destrutiva é **idempotente** e **reversível** (com comando de rollback documentado).
- Logs estruturados + timestamps em **todos** os outputs.

### 1.4 Transparência Radical
- Métricas brutas sempre salvas (logs timestampados).
- Relatórios gerados automaticamente, não editados à mão.
- Código legível > código esperto. Comentários explicam **porquê**, não **o quê**.

---

## 2. REGRAS DE NEGÓCIO (INVIOLÁVEIS)

### 2.1 Segurança Térmica (Non-Negotiable)
```bash
# SEMPRE presente em scripts de tuning:
# 1. Verificação de sensors antes de aplicar
# 2. Aviso visual se temp > 70°C idle
# 3. Rollback automático se temp > 90°C sob carga
# 4. Documentação de TjMax do CPU alvo
```

### 2.2 Compatibilidade de Distro
- **Alvo primário:** Arch / Manjaro / CachyOS (systemd, pacman, kernels recentes)
- **Suporte secundário:** Fedora, openSUSE, Debian testing (via detecção de gerenciador de pacotes)
- **Não suportado:** Ubuntu LTS (kernel antigo), distros sem systemd, BSDs

### 2.3 Versionamento e Compatibilidade
- **SemVer** para releases públicos: `MAJOR.MINOR.PATCH`
- **Breaking changes** só em MAJOR (ex: remover `performance.sh` → `tuning/cpu.sh`)
- Scripts mantêm retrocompatibilidade de flags por 2 ciclos MAJOR

### 2.4 Dados de Usuário
- **Zero telemetria.** Zero phoning home. Zero coleta de dados.
- Logs ficam **local** em `data/` (gitignored).
- Relatórios Markdown são **propriedade do usuário** — pode compartilhar, apagar, modificar.

---

## 3. ESTRUTURA CANÔNICA DO REPOSITÓRIO

```
system-optimization/
├── constitution.md          ← ESTE ARQUIVO (versionado, imutável sem RFC)
├── README.md                ← Entry point humano
├── pyproject.toml           ← Metadados Python (build, deps, tool config)
├── .gitignore               ← Padrão do projeto
├── mem.md                   ← Memória persistente (NÃO versionado)
│
├── src/
│   └── auditor/
│       ├── __init__.py
│       ├── audit.py         ← Classe LinuxAuditor (entry point: python -m src.auditor.audit)
│       ├── models.py        ← Dataclasses/TypedDicts para relatório (futuro)
│       └── collectors/      ← Módulos de coleta isolados (futuro)
│           ├── __init__.py
│           ├── packages.py
│           ├── boot.py
│           ├── hardware.py
│           └── overclock.py
│
├── scripts/
│   ├── lib/
│   │   ├── common.sh        ← Funções compartilhadas (log, colors, root_check, dry_run)
│   │   ├── hardware.sh      ← Detecção CPU/GPU/RAM unificada
│   │   └── thermal.sh       ← Monitoramento térmico + alerts
│   │
│   ├── performance.sh       ← Tuning CPU (governor, turbo, C-states, scheduler, THP)
│   ├── optimize_memory.sh   ← Memory (drop_caches, compaction, cron)
│   ├── benchmark.sh         ← Suite única (stress-ng + sysbench)
│   ├── test_benchmarks.sh   ← Suite comparativa automatizada
│   └── generate_comparison_report.sh  ← Agregador de logs → Markdown
│
├── docs/
│   ├── PRD.md               ← Product Requirements (auditoria)
│   ├── benchmark-analysis.md
│   ├── benchmark-comparison.md  ← Gerado (pode versionar se release)
│   └── architecture.md      ← Diagramas Mermaid, decisões arquiteturais (futuro)
│
├── data/                    ← GITIGNORED (runtime outputs)
│   ├── diagnostico_sistema.md
│   └── benchmarks/
│       ├── benchmark_YYYYMMDD_HHMMSS_{scenario}.log
│       └── .gitkeep
│
└── tests/                   ← Futuro: pytest + shellcheck + bats
    ├── unit/
    ├── integration/
    └── fixtures/
```

> **Regra:** Nenhum arquivo solto na raiz além dos listados. Novos diretórios só com RFC aprovado.

---

## 4. COMO AGIR — WORKFLOWS OBRIGATÓRIOS

### 4.1 Ciclo de Desenvolvimento (Feature → Release)

```mermaid
graph LR
    A[Issue/RFC no mem.md] --> B[Branch feature/xxx]
    B --> C[Implementação + Testes Locais]
    C --> D[ShellCheck + Ruff + Type Check]
    D --> E[Execução Real em Hardware Alvo]
    E --> F[Atualiza mem.md + docs]
    F --> G[PR/Commit convencional]
    G --> H[Tag SemVer se release]
```

**Commit Convention:** `type(scope): subject` — ex: `fix(audit): normalize lscpu locale PT-BR`

### 4.2 Adição de Novo Script/Modulo

1. **RFC no `mem.md`** — Justificativa, escopo, impacto térmico/segurança
2. **Criar em `scripts/` ou `src/auditor/collectors/`** seguindo nomenclatura
3. **Implementar `--dry-run`, `--help`, logging colorido, root check**
4. **Adicionar entry no `scripts/lib/common.sh`** se reutilizável
5. **Documentar no `README.md`** (seção Uso Rápido + variáveis de ambiente)
6. **Testar em 3 cenários:** dry-run, execução real, rollback
7. **Atualizar `constitution.md`** se nova camada/padrão

### 4.3 Modificação de Script Existente

| Tipo | Processo |
|------|----------|
| **Bugfix** | Branch `fix/`, teste de regressão, commit `fix(scope):` |
| **Melhoria** | Branch `feat/`, `--dry-run` preservado, commit `feat(scope):` |
| **Breaking** | Branch `breaking/`, RFC obrigatório, migração documentada, commit `BREAKING(scope):` |
| **Refatoração** | Branch `refactor/`, zero mudança comportamental, commit `refactor(scope):` |

### 4.4 Validação Obrigatória Antes de Commit

```bash
# 1. Lint shell (todos scripts .sh)
shellcheck scripts/**/*.sh scripts/*.sh

# 2. Lint Python (auditor)
ruff check src/
mypy src/  # se type hints completos

# 3. Teste funcional mínimo
./scripts/benchmark.sh --dry-run   # ou flag equivalente
python -m src.auditor.audit        # auditoria completa

# 4. Verificar se mem.md atualizado
grep -q "$(date +%Y-%m-%d)" mem.md || echo "⚠️  ATUALIZE mem.md!"
```

---

## 5. BOAS PRÁTICAS TÉCNICAS

### 5.1 Python (Auditor)

```python
# OBRIGATÓRIO
- Type hints completos (mypy --strict passa)
- Dataclasses/Pydantic para estruturas de dados
- subprocess.run com timeout, capture_output, text=True
- Tratamento de erro silencioso (retorna string "ERRO:..." não exceção)
- Zero dependências externas além de stdlib (até decisão contrária)
- Funções < 50 linhas, classes < 200 linhas
- Docstring Google-style em funções públicas

# PROIBIDO
- exec/eval, pickle, shelve
- Threading/multiprocessing (auditoria é sequencial e rápida)
- Escrita em disco exceto relatório final
- Imports dinâmicos
```

### 5.2 Bash (Scripts de Tuning/Benchmark)

```bash
# SHEBANG E HEADER OBRIGATÓRIOS
#!/usr/bin/env bash
set -euo pipefail
# script.sh — Descrição curta
# Uso: script.sh [opções]
# Requer: root (ou não), dependências

# FUNÇÕES COMUNS (source scripts/lib/common.sh)
log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_err()   { echo -e "${RED}[ERR]${NC} $*"; }
root_check() { [[ $EUID -eq 0 ]] || { log_err "Requer root"; exit 1; } }
dry_run_check() { [[ "${DRY_RUN:-false}" == "true" ]] && log_warn "DRY-RUN: $*"; }

# PADRÕES
- Variáveis UPPER_SNAKE_CASE
- Funções lower_snake_case
- Flags: --dry-run, --help, --verbose, --force (quando aplicável)
- Temporários em mktemp -d, cleanup em trap
- Parsing de args com case/getopts (sem getopt externo)
- Zero dependências além de coreutils, util-linux, procps, sysfsutils
```

### 5.3 Logs e Outputs

| Tipo | Formato | Local |
|------|---------|-------|
| **Benchmark raw** | Texto estruturado (chave: valor) | `data/benchmarks/benchmark_YYYYMMDD_HHMMSS_{tag}.log` |
| **Auditoria** | Markdown | `data/diagnostico_sistema.md` |
| **Relatório comparativo** | Markdown (tabelas GFM) | `docs/benchmark-comparison.md` |
| **Memory optimizer** | Console colorido + syslog | `/var/log/memory_optimizer.log` |
| **Erros** | stderr + log file | Conforme script |

**Timestamp padrão:** `ISO 8601` (`date -Iseconds`) em headers de log.

### 5.4 Documentação

- `README.md` = **única** porta de entrada para usuários
- `constitution.md` = **única** autoridade para contribuidores
- `mem.md` = **única** memória operacional (não versionada)
- `docs/*.md` = técnicos, gerados ou versionados por release
- **Comentários no código** explicam decisões não-óbvias, não o óbvio

---

## 6. DEPENDÊNCIAS — POLÍTICA RÍGIDA

### 6.1 Runtime (Sistema Alvo)

| Categoria | Pacotes | Obrigatório? | Notas |
|-----------|---------|--------------|-------|
| **Base** | `python`, `lm_sensors`, `dmidecode`, `util-linux` | ✅ Sim | Auditor + hardware detection |
| **CPU Tuning** | `cpupower` | ⚠️ Opcional | Verificação pós-tuning |
| **Benchmarks** | `stress-ng`, `sysbench`, `bc` | ✅ Sim | Core da suite |
| **Cron** | `cronie` | ⚠️ Opcional | Apenas se `--cron` usado |
| **Kernel** | `linux-headers` (para compaction check) | ⚠️ Opcional | `/usr/src/linux/.config` |

> **Regra:** Scripts **devem degradar graciosamente** se dependência opcional ausente (log_warn + continua).

### 6.2 Desenvolvimento (Local)

```toml
# pyproject.toml — fonte da verdade
[project]
requires-python = ">=3.11"
dependencies = []  # Zero deps runtime para auditor

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
strict = true
warn_unused_ignores = true

# ShellCheck config via .shellcheckrc
# shellcheck shell=bash
# exclude=SC2034,SC2155  # aceitáveis no projeto
```

### 6.3 Proibido Adicionar Sem RFC
- Qualquer dependência Python (requests, click, rich, etc.)
- Qualquer binary externo não presente em base Arch/Manjaro
- Systemd units no repo (gerar via script, não versionar)

---

## 7. COMO SEGUIR A PROGRAMAÇÃO DO CÓDIGO

### 7.1 Padrões de Nomenclatura

| Entidade | Convenção | Exemplo |
|----------|-----------|---------|
| Arquivos Python | `snake_case.py` | `audit.py`, `collectors/packages.py` |
| Classes Python | `PascalCase` | `LinuxAuditor`, `PackageCollector` |
| Funções Python | `snake_case` | `audit_packages()`, `get_cpu_temps()` |
| Variáveis Python | `snake_case` | `core_temps`, `max_temp_c` |
| Constantes Python | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT = 30` |
| Scripts Bash | `snake_case.sh` | `performance.sh`, `test_benchmarks.sh` |
| Funções Bash | `snake_case` | `tune_governor()`, `run_stress_ng()` |
| Variáveis Bash | `UPPER_SNAKE_CASE` | `DRY_RUN`, `CPU_COUNT` |
| Logs | `benchmark_YYYYMMDD_HHMMSS_{tag}.log` | `benchmark_20261114_160725_schedutil.log` |
| Branches Git | `type/short-desc` | `feat/amd-pstate-support`, `fix/thermal-alert` |

### 7.2 Estrutura de Função Padrão (Python)

```python
def collect_cpu_data(self) -> Dict[str, Any]:
    """Coleta dados de CPU via lscpu -J.
    
    Returns:
        Dict com chaves normalizadas (EN): Architecture, Model name, CPU(s), etc.
    """
    raw = self.run_cmd(["lscpu", "-J"])
    if not raw or "ERRO" in raw:
        return {}
    
    try:
        data = json.loads(raw)
        return self._normalize_lscpu(data)
    except json.JSONDecodeError:
        log_warn("Falha ao parsear lscpu JSON")
        return {}
```

### 7.3 Estrutura de Função Padrão (Bash)

```bash
tune_cpu_governor() {
    local target_governor="${1:-performance}"
    local cpus
    cpus=$(ls /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor 2>/dev/null)
    
    [[ -n "$cpus" ]] || { log_err "Nenhum CPU com scaling_governor"; return 1; }
    
    for gov_path in $cpus; do
        dry_run_check "echo $target_governor > $gov_path"
        [[ "${DRY_RUN:-false}" == "true" ]] || echo "$target_governor" > "$gov_path"
    done
    
    log_ok "Governor definido para $target_governor em $(echo "$cpus" | wc -w) CPUs"
}
```

### 7.4 Testabilidade

- **Python:** Funções puras (sem side effects) → testáveis com pytest + mock `run_cmd`
- **Bash:** Funções pequenas, inputs via args, outputs via stdout → testáveis com `bats`
- **Integração:** `test_benchmarks.sh --dry-run` valida fluxo completo sem side effects

### 7.5 Extensibilidade (Open/Closed Principle)

| Ponto de Extensão | Como Adicionar |
|-------------------|----------------|
| Novo coletor de auditoria | Criar `src/auditor/collectors/novo.py` + registrar em `audit.py` |
| Novo benchmark | Adicionar função `run_novo_benchmark()` em `benchmark.sh` + chamar no `main` |
| Novo cenário de teste | Adicionar case em `test_benchmarks.sh` + flag `--novo-only` |
| Nova métrica no relatório | Estender `generate_comparison_report.sh` + parser correspondente |
| Novo governor/tuning | Função em `scripts/lib/hardware.sh` + chamada em `performance.sh` |

---

## 8. GOVERNANÇA E EVOLUÇÃO

### 8.1 Processo de Emenda à Constituição

1. **Proposta** no `mem.md` com tag `#CONSTITUTION-AMENDMENT`
2. **Discussão** mínima 48h (se colaborativo) ou decisão solo (mantenedor único)
3. **Aprovação** → Editar `constitution.md` + commit `chore(constitution): descrição`
4. **Versão** → Incrementar `CONSTITUTION_VERSION` no header deste arquivo

### 8.2 Versionamento da Constituição

```
CONSTITUTION_VERSION = "1.0.0"  # MAJOR: quebra workflow | MINOR: nova regra | PATCH: correção textual
```

### 8.3 Código de Conduta (Mínimo)

- **Respeito** — Técnico, direto, sem ataques pessoais
- **Evidência** — Opiniões com dados (logs, benchmarks, specs)
- **Reversibilidade** — Toda mudança deve ter plano de rollback
- **Documentação** — Se não está documentado, não existe

---

## 9. CHECKLIST DE CONFORMIDADE (Pre-Commit)

```bash
# Execute antes de TODO commit:
□ shellcheck scripts/**/*.sh scripts/*.sh  (zero warnings novos)
□ ruff check src/                          (zero errors)
□ mypy src/                                (zero errors se strict)
□ ./scripts/benchmark.sh --dry-run         (executa sem erro)
□ python -m src.auditor.audit              (gera relatório válido)
□ grep -q "$(date +%Y-%m-%d)" mem.md       (mem.md atualizado hoje)
□ README.md reflete flags/comandos atuais
□ Nenhum arquivo .pyc, __pycache__, *.swp, *.tmp no git status
```

---

## 10. REFERÊNCIAS RÁPIDAS

| Documento | Finalidade | Atualização |
|-----------|------------|-------------|
| `constitution.md` | Lei suprema | RFC apenas |
| `README.md` | Manual do usuário | Cada release |
| `mem.md` | Diário de bordo | **Diária** durante desenvolvimento |
| `docs/PRD.md` | Spec da auditoria | Quando escopo muda |
| `docs/benchmark-comparison.md` | Resultados reais | Após cada suite completa |
| `pyproject.toml` | Config tooling | Quando tooling muda |

---

## HISTÓRICO DE VERSÕES DA CONSTITUIÇÃO

| Versão | Data | Autor | Resumo |
|--------|------|-------|--------|
| 1.0.0 | 2026-11-14 | pereira | Criação inicial — filosofia, estrutura, regras, workflows, padrões |

---

> **FIM DA CONSTITUIÇÃO**  
> *Este documento vive em `constitution.md` na raiz do repositório.*  
> *Violações são bugs de processo — trate com a mesma seriedade de bugs de código.*