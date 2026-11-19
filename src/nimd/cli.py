#!/usr/bin/env python3
"""CLI Python que executa os otimizadores bash em scripts/optimizers/."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
STATE_DIR = Path("/var/lib/nimd/state")

OPTIMIZERS = {
    "fan": SCRIPTS_DIR / "optimize-fan",
    "gpu": SCRIPTS_DIR / "optimize-gpu",
    "ssd": SCRIPTS_DIR / "optimize-ssd",
    "hdd": SCRIPTS_DIR / "optimize-hdd",
}


def run_optimizer(domain: str, args: List[str], json_output: bool = True, dry_run: bool = False) -> List[Dict[str, Any]]:
    """Executa script bash e retorna linhas JSON parseadas."""
    script = OPTIMIZERS.get(domain)
    if not script or not script.exists():
        raise FileNotFoundError(f"Optimizer script not found: {domain}")

    cmd = [str(script)]
    if json_output:
        cmd.append("--json")
    if dry_run:
        cmd.append("--dry-run")
    
    # args[0] is the command (probe/apply/status/revert)
    # Global options (--json, --dry-run) must come BEFORE the command
    # Command-specific options come AFTER the command
    if args:
        cmd.append(args[0])  # command
        cmd.extend(args[1:])  # command-specific options

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0 and result.stderr:
        # Tenta extrair erro JSON do stderr
        for line in result.stderr.strip().split('\n'):
            try:
                err = json.loads(line)
                if err.get("type") == "error":
                    raise RuntimeError(f"{err.get('code', 'ERROR')}: {err.get('message', 'Unknown error')}")
            except json.JSONDecodeError:
                pass
        raise RuntimeError(f"Command failed (exit {result.returncode}): {result.stderr}")

    # Parse JSON array first (bash scripts output JSON array), fallback to JSON Lines
    outputs = []
    stdout = result.stdout.strip()
    if not stdout:
        return outputs
    
    # Try JSON array first (our bash scripts output this)
    try:
        parsed = json.loads(stdout)
        if isinstance(parsed, list):
            outputs = parsed
        else:
            outputs = [parsed]
        return outputs
    except json.JSONDecodeError:
        pass
    
    # Fallback: JSON Lines (for error responses etc)
    for line in stdout.split('\n'):
        line = line.strip()
        if line:
            try:
                outputs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    
    return outputs


def cmd_probe(domains: List[str], json_output: bool, dry_run: bool) -> None:
    for domain in domains:
        try:
            outputs = run_optimizer(domain, ["probe"], json_output, dry_run)
            for out in outputs:
                if json_output:
                    print(json.dumps(out))
                else:
                    if out.get("type") == "result":
                        data = out.get("data", [])
                        print(f"{domain}: OK — {len(data)} device(s)")
                    elif out.get("type") == "error":
                        print(f"{domain}: FAIL — {out.get('message')}")
        except Exception as e:
            if json_output:
                print(json.dumps({"type": "error", "code": "EXECUTION_ERROR", "message": str(e)}))
            else:
                print(f"{domain}: ERROR — {e}")


def cmd_apply(domain: str, profile: str, params: Dict[str, Any], dry_run: bool, json_output: bool) -> None:
    args = ["apply", "--profile", profile]
    # dry_run is now passed as parameter to run_optimizer, not as arg

    # Parâmetros específicos por domínio
    if domain == "fan" and profile == "custom":
        curve = params.get("curve")
        if curve:
            args.extend(["--curve", curve])
    elif domain == "gpu" and profile == "custom":
        for k, v in params.items():
            if k == "power_limit":
                args.extend(["--power-limit", str(v)])
            elif k == "core_offset":
                args.extend(["--core-offset", str(v)])
            elif k == "mem_offset":
                args.extend(["--mem-offset", str(v)])
            elif k == "perf_level":
                args.extend(["--perf-level", str(v)])
    elif domain == "ssd" and profile == "custom":
        for k, v in params.items():
            if k == "scheduler":
                args.extend(["--scheduler", str(v)])
            elif k == "nr_requests":
                args.extend(["--nr-requests", str(v)])
            elif k == "apst_enabled":
                args.extend(["--apst", "true" if v else "false"])
            elif k == "write_cache_enabled":
                args.extend(["--write-cache", "true" if v else "false"])
            elif k == "read_ahead_kb":
                args.extend(["--read-ahead", str(v)])
    elif domain == "hdd" and profile == "custom":
        for k, v in params.items():
            if k == "scheduler":
                args.extend(["--scheduler", str(v)])
            elif k == "read_ahead_kb":
                args.extend(["--read-ahead", str(v)])
            elif k == "apm_level":
                args.extend(["--apm", str(v)])
            elif k == "spindown_sec":
                args.extend(["--spindown", str(v)])

    try:
        outputs = run_optimizer(domain, args, json_output, dry_run)
        for out in outputs:
            if json_output:
                print(json.dumps(out))
            else:
                if out.get("type") == "complete":
                    print(f"{domain}: {'OK' if out.get('exit_code') == 0 else 'FAIL'} — {out.get('message')}")
                elif out.get("type") == "result" and out.get("section") == "warnings":
                    for w in out.get("data", []):
                        print(f"  WARN: {w}")
                elif out.get("type") == "error":
                    print(f"{domain}: ERROR — {out.get('message')}")
    except Exception as e:
        if json_output:
            print(json.dumps({"type": "error", "code": "EXECUTION_ERROR", "message": str(e)}))
        else:
            print(f"{domain}: ERROR — {e}")


def cmd_status(domains: List[str], json_output: bool, dry_run: bool) -> None:
    for domain in domains:
        try:
            outputs = run_optimizer(domain, ["status"], json_output, dry_run)
            for out in outputs:
                if json_output:
                    print(json.dumps(out))
                else:
                    if out.get("type") == "result" and out.get("section") == "status":
                        data = out.get("data", {})
                        profile = data.get("current_profile", "unknown")
                        devices = data.get("devices", [])
                        print(f"{domain}: profile={profile} devices={len(devices)}")
                        for d in devices:
                            print(f"  {d}")
        except Exception as e:
            if json_output:
                print(json.dumps({"type": "error", "code": "EXECUTION_ERROR", "message": str(e)}))
            else:
                print(f"{domain}: ERROR — {e}")


def cmd_revert(domain: str, json_output: bool) -> None:
    state_file = STATE_DIR / f"{domain}.json"
    if not state_file.exists():
        if json_output:
            print(json.dumps({"type": "error", "code": "HARDWARE_NOT_FOUND", "message": f"No saved state for {domain}"}))
        else:
            print(f"{domain}: FAIL — No saved state")
        return

    try:
        outputs = run_optimizer(domain, ["revert"], json_output, args.dry_run)
        for out in outputs:
            if json_output:
                print(json.dumps(out))
            else:
                if out.get("type") == "complete":
                    print(f"{domain}: {'OK' if out.get('exit_code') == 0 else 'FAIL'} — {out.get('message')}")
                elif out.get("type") == "result" and out.get("section") == "warnings":
                    for w in out.get("data", []):
                        print(f"  WARN: {w}")
                elif out.get("type") == "error":
                    print(f"{domain}: ERROR — {out.get('message')}")
    except Exception as e:
        if json_output:
            print(json.dumps({"type": "error", "code": "EXECUTION_ERROR", "message": str(e)}))
        else:
            print(f"{domain}: ERROR — {e}")


def main():
    parser = argparse.ArgumentParser(prog="nimd", description="Linux hardware optimization toolkit")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", help="JSON Lines output")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without applying")

    sub = parser.add_subparsers(dest="command", required=True)

    # probe
    p_probe = sub.add_parser("probe", help="Detect hardware")
    p_probe.add_argument("domain", choices=["fan", "gpu", "ssd", "hdd", "all"])

    # apply
    p_apply = sub.add_parser("apply", help="Apply optimization profile")
    p_apply.add_argument("domain", choices=["fan", "gpu", "ssd", "hdd"])
    p_apply.add_argument("profile", choices=["silent", "balanced", "performance", "custom"])
    p_apply.add_argument("--params", type=json.loads, default={}, help="Custom params as JSON")

    # status
    p_status = sub.add_parser("status", help="Show current status")
    p_status.add_argument("domain", choices=["fan", "gpu", "ssd", "hdd", "all"])

    # revert
    p_revert = sub.add_parser("revert", help="Restore previous state")
    p_revert.add_argument("domain", choices=["fan", "gpu", "ssd", "hdd"])

    args = parser.parse_args()

    domains = ["fan", "gpu", "ssd", "hdd"] if getattr(args, "domain", "") == "all" else [args.domain]

    if args.command == "probe":
        cmd_probe(domains, args.json, args.dry_run)
    elif args.command == "apply":
        cmd_apply(args.domain, args.profile, args.params, args.dry_run, args.json)
    elif args.command == "status":
        cmd_status(domains, args.json, args.dry_run)
    elif args.command == "revert":
        cmd_revert(args.domain, args.json)


if __name__ == "__main__":
    main()