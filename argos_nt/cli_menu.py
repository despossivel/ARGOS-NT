"""
ARGOS-NT interactive CLI menu.

All heavy logic lives in argos_nt/core/.  This module is the thin
interactive loop that drives the operator through the menu options.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import traceback
import tempfile
import json
from datetime import datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

from rich.console import Console

from argos_nt.config_manager import ConfigManager
from argos_nt.core.boot_checks import (
    boot_health_formatted,
    boot_health_line,
    format_boot_issue,
    format_boot_issue_expanded,
    render_navigation_menu,
    render_system_status,
    run_startup_checks,
)
from argos_nt.core.constants import (
    ANSI_RESET,
    EXPORT_FORMATS,
    INPUT_DIR,
    OUTPUT_DIR,
    STATUS_COLORS,
    SUPPORTED_PROVIDERS,
    TOOL_REQUIREMENTS,
)
from argos_nt.core.history_service import (
    delete_history_entry,
    find_history_entry,
    load_history_entries,
    render_history_dossier_view,
    render_history_options_menu,
    render_history_view,
    update_history_entry_source,
)
from argos_nt.core.provider_service import all_provider_status, check_active_provider, get_provider_model, mask_secret
from argos_nt.core.report_service import export_case_report, load_case_snapshot, render_report_text
from argos_nt.core.scan_service import run_scan
from argos_nt.ui.banner_manager import ArgosBannerManager

_console = Console()
_banner_manager = ArgosBannerManager()

_BASE_SCAN_TOOLS = ["holehe", "sherlock", "leaker"]
_BALANCED_SCAN_EXCLUDES = {"pagodo"}
# ---------------------------------------------------------------------------
# Small helpers kept in the CLI layer
# ---------------------------------------------------------------------------


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _vlog(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[VERBOSE {_ts()}] {message}")


def _count_active_modules() -> int:
    return sum(
        1
        for _, executables, _, _ in TOOL_REQUIREMENTS
        if any(shutil.which(executable) for executable in executables)
    )


def _render_home(boot) -> None:
    config = ConfigManager().load()
    provider = str(config.ai.provider).lower().strip()
    provider_model = get_provider_model(config, provider)
    try:
        total_cases = len(load_history_entries())
    except Exception:
        total_cases = 0

    active_modules = _count_active_modules()
    
    # Render complete system status with new design
    system_display = render_system_status(
        boot,
        provider_name=provider,
        provider_model=provider_model,
        total_cases=total_cases,
        active_modules=active_modules,
    )
    print(system_display)
    
    # Render navigation menu
    menu_display = render_navigation_menu()
    print(menu_display)


def _show_home(boot) -> None:
    print("\033[2J\033[H", end="")
    _render_home(boot)


def _prompt_with_default(label: str, current_value: str) -> str:
    typed = input(f"{label} [{current_value}]: ").strip()
    return typed if typed else current_value


def _prompt_optional_secret(label: str, current_value: str | None) -> str | None:
    print(f"{label}: {mask_secret(current_value)}")
    print("Type a new token and press Enter to update, '-' to clear, Enter to keep.")
    typed = input("New value: ").strip()
    if typed == "":
        return current_value
    if typed == "-":
        return None
    return typed


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("._") or "item"


def _select_target_file() -> str | None:
    input_files = sorted(path for path in INPUT_DIR.iterdir() if path.is_file())

    print("\n============================")
    print(" Input File")
    print("============================")
    if input_files:
        for index, path in enumerate(input_files, start=1):
            print(f"[{index}] {path}")
    else:
        print("No files found in data/input.")

    custom_index = len(input_files) + 1
    print(f"[{custom_index}] Custom path")
    print("[q] Cancel")

    choice = input("input-file> ").strip().lower()
    if choice == "q":
        return None

    if choice.isdigit():
        selected = int(choice)
        if 1 <= selected <= len(input_files):
            return str(input_files[selected - 1])
        if selected == custom_index:
            typed_path = input("Path to .md/.txt target file: ").strip()
            return typed_path or None

    print("Invalid option.")
    return None


def _run_scan_cli(
    target_file: str,
    verbose: bool,
    existing_case_id: str | None = None,
) -> None:
    start = perf_counter()
    input_path = Path(target_file)
    _vlog(verbose, f"Checking file: {input_path.resolve()}")
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"File not found: {input_path}")

    full_scan, tool_filter = _select_scan_mode()
    if tool_filter == []:
        print("Scan cancelled.")
        return

    result = run_scan(
        target_file,
        full_scan=full_scan,
        tool_filter=tool_filter,
        existing_case_id=existing_case_id,
        progress_callback=lambda msg: _vlog(verbose, f"Pipeline: {msg}"),
    )
    _vlog(verbose, f"Finished in {perf_counter() - start:.2f}s")

    print("\n[OK] Scan completed. Summary:")
    print(f"  Case:       {result['case_id']}")
    print(f"  Entities:   {result['entity_stats']}")
    print(f"  Next steps: {result['next_steps']}")

    if verbose:
        print("\n--- Tool results ---")
        for tool in result["tool_results"]:
            status = "OK" if tool["ok"] else "FAIL"
            print(f"  {tool['tool']} on {tool['target']}: {status}")
        print("\nGraph snapshot:")
        print(result["graph_snapshot"])


# ---------------------------------------------------------------------------
# History submenu
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Scan mode selection
# ---------------------------------------------------------------------------

# Canonical tool names used in ScoutAgent — must match the strings checked by
# _allowed() in scout_agent.py.
_TOOL_MENU: tuple[tuple[str, str, str], ...] = (
    # (display_label, canonical_name, scope)
    ("holehe            — account presence check per e-mail",       "holehe",      "email"),
    ("h8mail            — credential/breach search per e-mail",     "h8mail",      "email"),
    ("leaker            — credential lookup (e-mail, username, phone)", "leaker", "email/username/phone"),
    ("ghunt             — Google account OSINT",                     "ghunt",       "email"),
    ("sherlock          — username search across social networks",   "sherlock",    "username"),
    ("maigret           — deep username search",                     "maigret",     "username"),
    ("toutatis          — Instagram account OSINT",                  "toutatis",    "username"),
    ("socialscan        — username & e-mail availability check",     "socialscan",  "username"),
    ("ignorant          — phone number presence check",              "ignorant",    "phone"),
    ("whatspy           — WhatsApp profile OSINT",                   "whatspy",     "phone"),
    ("google-dorks      — automated Google dork search",             "google-dorks","dorks"),
    ("pagodo            — Google dork automation (full-scan)",       "pagodo",      "dorks"),
    ("dork-cli          — dork execution helper (full-scan)",        "dork-cli",    "dorks"),
    ("s3scanner         — S3 bucket enumeration (full-scan)",        "s3scanner",   "domain"),
)


def _select_scan_mode() -> tuple[bool, list[str] | None]:
    """
    Interactive menu that asks the operator which scan mode to run.

    Returns:
        (full_scan, tool_filter)
        full_scan=True  → all tools, tool_filter=None
        full_scan=False, tool_filter=[...]  → specific tools only
        full_scan=False, tool_filter=None   → base scan (default)
    """
    print("\n[ SELECT TOOLS TO RUN ]")
    print()
    for idx, (_, name, scope) in enumerate(_TOOL_MENU, start=1):
        print(f"  [{idx}] {name:<14} [{scope}]")
    print()
    print("  [q] Quick scan")
    print("  [a] Run all (except pagodo)")
    print("  [n] Run all (slow)")
    print("  [x] Cancel")
    print()

    choice = input("Choice(s) e.g. 1 2 4 or q: ").strip().lower()
    if not choice:
        return False, _BASE_SCAN_TOOLS.copy()

    if choice == "x":
        return False, []

    if choice == "q":
        return False, _BASE_SCAN_TOOLS.copy()

    if choice == "a":
        chosen = [name for _, name, _ in _TOOL_MENU if name not in _BALANCED_SCAN_EXCLUDES]
        return False, chosen

    if choice == "n":
        return True, None

    tokens = [token.strip() for token in choice.replace(",", " ").split() if token.strip()]
    chosen: list[str] = []
    for token in tokens:
        if not token.isdigit():
            continue
        index = int(token)
        if 1 <= index <= len(_TOOL_MENU):
            tool_name = _TOOL_MENU[index - 1][1]
            if tool_name not in chosen:
                chosen.append(tool_name)

    if chosen:
        return False, chosen

    print("Invalid selection — defaulting to quick scan.")
    return False, _BASE_SCAN_TOOLS.copy()

def _history_menu(verbose: bool) -> None:
    while True:
        print("\033[2J\033[H", end="")
        try:
            entries = load_history_entries()
        except Exception as exc:
            print(f"Failed to load history from Neo4j: {exc}")
            input("\nPress Enter to return to the main menu...")
            return
        # Render history view
        history_display = render_history_view(entries)
        print(history_display)
        if not entries:
            print("  No history found.")
            print()
            input("Press Enter to return to the main menu...")
            return
        else:
            raw_id = input("Select case ID (or 'q' to back): ").strip().lower()
            if raw_id == "q":
                return
            
            if not raw_id.isdigit():
                print("Invalid history ID.")
                input("\nPress Enter to continue...")
                continue

            history_id = int(raw_id)
            entry = find_history_entry(history_id, entries)
            if entry is None:
                print(f"Case [{history_id:02d}] not found.")
                input("\nPress Enter to continue...")
                continue

            # Render dossier detail and operational commands
            print("\033[2J\033[H", end="")
            config = ConfigManager().load()
            provider = str(config.ai.provider).lower().strip()
            provider_model = get_provider_model(config, provider)
            try:
                snapshot = load_case_snapshot(str(entry["case_id"]))
            except Exception:
                snapshot = None

            dossier_view = render_history_dossier_view(entry, snapshot, provider_model)
            print(dossier_view)
            
            options_menu = render_history_options_menu()
            print(options_menu)
            
            choice = input("dossier-mgt > ").strip()
            
            if choice == "1":
                try:
                    _run_scan_cli(
                        str(entry["target_file"]),
                        verbose,
                        existing_case_id=str(entry["case_id"]),
                    )
                except Exception as exc:
                    print(f"[ERROR] {exc}")
                    if verbose:
                        traceback.print_exc()
                input("\nPress Enter to continue...")
            elif choice == "2":
                _view_report_cli(entry)
                input("\nPress Enter to continue...")
            elif choice == "3":
                _export_report_cli(entry)
                input("\nPress Enter to continue...")
            elif choice == "4":
                new_target = input(f"New target file [{entry['target_file']}]: ").strip()
                if new_target:
                    if update_history_entry_source(entry, new_target):
                        entry["target_file"] = new_target
                        print("Updated.")
                    else:
                        print("Case not found in Neo4j.")
                else:
                    print("No changes made.")
                input("\nPress Enter to continue...")
            elif choice == "5":
                confirm = input(f"Delete case '{entry['case_id']}' from Neo4j? (y/N): ").strip().lower()
                if confirm == "y":
                    if delete_history_entry(entry):
                        print("Deleted.")
                        input("\nPress Enter to continue...")
                        break
                    else:
                        print("Deletion failed.")
                        input("\nPress Enter to continue...")
                else:
                    print("Deletion cancelled.")
                    input("\nPress Enter to continue...")
            elif choice == "6":
                break
            else:
                print("Invalid option.")
                input("\nPress Enter to continue...")



def _history_item_menu(entry: dict, verbose: bool) -> None:  # type: ignore[type-arg]
    while True:
        print(f"\n--- History Item [{entry['id']}] ---")
        print(f"Case ID: {entry['case_id']}")
        print(f"Target file: {entry['target_file']}")
        print("1. Run new scan")
        print("2. View report")
        print("3. Export report")
        print("4. Edit target file")
        print("5. Delete item")
        print("6. Back")

        item_choice = input("history-item> ").strip()
        if item_choice == "1":
            try:
                _run_scan_cli(
                    str(entry["target_file"]),
                    verbose,
                    existing_case_id=str(entry["case_id"]),
                )
            except Exception as exc:
                print(f"[ERROR] {exc}")
                if verbose:
                    traceback.print_exc()
            input("\nPress Enter to continue...")
        elif item_choice == "2":
            _view_report_cli(entry)
            input("\nPress Enter to continue...")
        elif item_choice == "3":
            _export_report_cli(entry)
            input("\nPress Enter to continue...")
        elif item_choice == "4":
            new_target = input(f"New target file [{entry['target_file']}]: ").strip()
            if new_target:
                if update_history_entry_source(entry, new_target):
                    entry["target_file"] = new_target
                    print("Updated.")
                else:
                    print("Case not found in Neo4j.")
            else:
                print("No changes made.")
        elif item_choice == "5":
            confirm = input(f"Delete case '{entry['case_id']}' from Neo4j? (y/N): ").strip().lower()
            if confirm == "y":
                if delete_history_entry(entry):
                    print("Deleted.")
                    return
            print("Deletion cancelled.")
        elif item_choice == "6":
            return
        else:
            print("Invalid option.")


def _view_report_cli(entry: dict) -> None:  # type: ignore[type-arg]
    case_id = str(entry["case_id"])
    try:
        snapshot = load_case_snapshot(case_id)
    except Exception as exc:
        print(f"Failed to load report: {exc}")
        return
    if not snapshot or snapshot.get("case") is None:
        print(f"No case data found for case ID: {case_id}")
        return
    print("\n" + render_report_text(entry, snapshot))


def _export_report_cli(entry: dict) -> None:  # type: ignore[type-arg]
    print("\nExport format:")
    for i, (key, ext) in enumerate(EXPORT_FORMATS.items(), start=1):
        print(f"  {i}. {key.upper()} ({ext})")
    fmt_map = {str(i): key for i, key in enumerate(EXPORT_FORMATS.keys(), start=1)}
    choice = input(f"Select format [1-{len(EXPORT_FORMATS)}] (default 1): ").strip() or "1"
    fmt = fmt_map.get(choice)
    if fmt is None:
        print("Invalid format option.")
        return
    ok, result = export_case_report(entry, fmt)
    if ok:
        print(f"Report exported to: {result}")
    else:
        print(f"Export failed: {result}")


def _change_provider(config_manager: ConfigManager) -> None:
    config = config_manager.load()
    current = str(config.ai.provider).lower().strip()
    print("\n--- Change Provider ---")
    print(f"Current provider: {current}")
    for i, provider in enumerate(SUPPORTED_PROVIDERS, start=1):
        marker = " *" if provider == current else ""
        print(f"  [{i}] {provider}{marker}")
    choice = input(f"Select provider (1-{len(SUPPORTED_PROVIDERS)}) or Enter to cancel: ").strip()
    if not choice or not choice.isdigit():
        print("No changes made.")
        return
    idx = int(choice)
    if not (1 <= idx <= len(SUPPORTED_PROVIDERS)):
        print("Invalid selection.")
        return
    config.ai.provider = SUPPORTED_PROVIDERS[idx - 1]
    config_manager.save(config)
    print(f"Active provider set to: {SUPPORTED_PROVIDERS[idx - 1]}")


def _configure_credentials(config_manager: ConfigManager) -> None:
    config = config_manager.load()
    provider = str(config.ai.provider).lower().strip()
    print(f"\n--- Configure {provider.upper()} ---")
    if provider == "ollama":
        config.ai.ollama_base_url = _prompt_with_default("Ollama URL", config.ai.ollama_base_url)
        config.ai.ollama_model = _prompt_with_default(
            "Model", get_provider_model(config, "ollama")
        )
    elif provider == "openai":
        config.api_keys.openai = _prompt_optional_secret("OPENAI_API_KEY", config.api_keys.openai)
        config.ai.openai_model = _prompt_with_default(
            "Model", get_provider_model(config, "openai")
        )
    elif provider == "anthropic":
        config.api_keys.anthropic = _prompt_optional_secret(
            "ANTHROPIC_API_KEY", config.api_keys.anthropic
        )
        config.ai.anthropic_model = _prompt_with_default(
            "Model", get_provider_model(config, "anthropic")
        )
    elif provider == "deepseek":
        config.api_keys.deepseek = _prompt_optional_secret(
            "DEEPSEEK_API_KEY", config.api_keys.deepseek
        )
        config.ai.deepseek_base_url = _prompt_with_default(
            "DeepSeek base URL", config.ai.deepseek_base_url
        )
        config.ai.deepseek_model = _prompt_with_default(
            "Model", get_provider_model(config, "deepseek")
        )
    config_manager.save(config)
    print("Configuration saved.")


def _show_provider_status_cli(config_manager: ConfigManager) -> None:
    config = config_manager.load()
    statuses = all_provider_status(config)
    print("\n--- Provider Status ---")
    for s in statuses:
        marker = " [active]" if s["active"] else ""
        print(f"[{s['status']}]{marker} {s['provider']} model={s['model']} — {s['detail']}")


def render_provider_diagnostic_screen(config) -> str:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = ANSI_RESET
    statuses = all_provider_status(config)
    provider_table = [
        ("01", "Ollama", config.ai.ollama_model, statuses[0]["status"], statuses[0]["detail"]),
        ("02", "OpenAI", config.ai.openai_model, statuses[1]["status"], statuses[1]["detail"]),
        ("03", "Anthropic", config.ai.anthropic_model, statuses[2]["status"], statuses[2]["detail"]),
        ("04", "DeepSeek", config.ai.deepseek_model, statuses[3]["status"], statuses[3]["detail"]),
    ]
    def status_icon(status):
        if status == "OK":
            return f"[✔] ACTIVE / ENGAGED"
        if status == "WARN":
            return f"[!] ERR: {YELLOW}Warning{RESET}"
        return f"[x] ERR: {RED}Error{RESET}"
    lines = []
    lines.append("-" * 75)
    lines.append("  CORE CONFIGURATION  |  Intelligence Layer  |  Mode: Diagnostic")
    lines.append("-" * 75)
    lines.append("")
    lines.append(" [ BRAIN MODULES & SYSTEM HEALTH ]")
    lines.append("")
    lines.append("  ID | PROVIDER  | MODEL/ENDPOINT          | STATUS & DIAGNOSTIC")
    lines.append("  ---|-----------|-------------------------|---------------------------------")
    for pid, name, model, status, detail in provider_table:
        if status == "OK":
            status_str = f"[✔] ACTIVE / ENGAGED"
        elif status == "WARN":
            status_str = f"[!] ERR: {detail}"
        else:
            status_str = f"[x] ERR: {detail}"
        lines.append(f"  {pid}  | {name:<9}| {str(model)[:23]:<23} | {status_str}")
    lines.append("")
    lines.append("-" * 75)
    lines.append(" [ LIVE DIAGNOSTIC LOG ]")
    for s in statuses:
        lines.append(f"  ▶ {s['detail']}")
    lines.append("-" * 75)
    lines.append("")
    lines.append(" [ COMMANDS ]")
    lines.append("  (1) SWITCH PROVIDER    - Change active intelligence core")
    lines.append("  (2) CONFIGURE MODEL    - Set API Keys, Model Names or Endpoints")
    lines.append("  (3) RE-SCAN STATUS     - Force a new diagnostic ping")
    lines.append("  (4) BACK               - Return to Command Core")
    lines.append("")
    return "\n".join(lines)


def _provider_settings_menu(config_manager: ConfigManager) -> None:
    while True:
        config = config_manager.load()
        print("\033[2J\033[H", end="")
        print(render_provider_diagnostic_screen(config))
        choice = input("settings > ").strip()
        if choice == "1":
            _change_provider(config_manager)
        elif choice == "2":
            _configure_credentials(config_manager)
        elif choice == "3":
            # Re-scan status (reloads screen)
            continue
        elif choice == "4":
            return
        else:
            print("Invalid option.")
            input("\nPress Enter to continue...")



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _prompt_case_metadata() -> dict:
    """Prompt the user for manual case data (in English)."""
    print("\n--- New Case (Manual Entry) ---")
    while True:
        case_name = input("1. Case name *: ").strip()
        if case_name:
            break
        print("  [!] Required field.")
    while True:
        email = input("2. Email *: ").strip()
        if email:
            break
        print("  [!] Required field.")
    username = input("3. Username (optional): ").strip()
    while True:
        target_name = input("4. Full or partial target name *: ").strip()
        if target_name:
            break
        print("  [!] Required field.")
    if len(target_name.split()) < 2:
        print("  [!] WARNING: Partial name may yield inconsistent results.")
    phone = input("5. Phone (optional): ").strip()
    location = input("6. Location (optional): ").strip()
    birthdate = input("7. Birthdate (optional): ").strip()
    return {
        "case_name": case_name,
        "email": email,
        "username": username,
        "target_name": target_name,
        "phone": phone,
        "location": location,
        "birthdate": birthdate,
    }

def _render_manual_case_and_scan_menu(meta: dict) -> str:
    """Render the redesigned manual entry + scan selection screen."""
    BOLD = "\033[1m"
    RESET = ANSI_RESET
    lines = []
    lines.append("-" * 75)
    lines.append("  TARGET ACQUISITION  |  Manual Entry Mode  |  Priority: High")
    lines.append("-" * 75)
    lines.append("")
    lines.append(" [1. IDENTITY VECTOR]")
    def show_field(idx, label, value):
        v = value if value else "[ NOT DEFINED ]"
        return f"  ({idx}) {label:<10}: {v}"
    lines.append(show_field(1, "CASE NAME", meta.get("case_name")))
    lines.append(show_field(2, "EMAIL", meta.get("email")))
    lines.append(show_field(3, "USERNAME", meta.get("username")))
    lines.append(show_field(4, "FULL NAME", meta.get("target_name")))
    lines.append(show_field(5, "PHONE", meta.get("phone")))
    lines.append(show_field(6, "LOCATION", meta.get("location")))
    lines.append(show_field(7, "BIRTHDATE", meta.get("birthdate")))
    lines.append("")
    lines.append("-" * 75)
    lines.append(" [2. ORDNANCE SELECTION - OSINT ARSENAL]")
    lines.append("")
    lines.append("   EMAIL MODULES          USERNAME MODULES        PHONE/DORK MODULES")
    lines.append("   -----------------      -----------------       ------------------")
    lines.append("   [01] holehe            [05] sherlock           [09] ignorant")
    lines.append("   [02] h8mail            [06] maigret            [10] whatspy")
    lines.append("   [03] leaker            [07] toutatis           [11] google-dorks")
    lines.append("   [04] ghunt             [08] socialscan         [12] pagodo")
    lines.append("                                                  [13] dork-cli")
    lines.append("-" * 75)
    lines.append(" [EXECUTION PRESETS]")
    lines.append("  (Q) QUICK SCAN  - Fast verification (Top 5 tools)")
    lines.append("  (A) FULL AUTO   - Run all optimized modules")
    lines.append("  (N) DEEP DIVE   - All tools + Slow scrapers (Pagodo/Dorks)")
    lines.append("  (X) ABORT       - Discard target data")
    lines.append("-" * 75)
    lines.append("")
    lines.append(" argos-ntc (loadout) > _")
    return "\n".join(lines)


def _render_scan_intake_menu() -> str:
    lines = []
    lines.append("-" * 75)
    lines.append("  SCAN INITIALIZATION  |  Intelligence Intake  |  Mode: Selection")
    lines.append("-" * 75)
    lines.append("")
    lines.append(" [ SELECT INJECTION METHOD ]")
    lines.append("")
    lines.append("  (1) DIRECT ENTRY      - Manual target profiling (Email, Name, Phone...)")
    lines.append("                          Best for specific, single-target investigations.")
    lines.append("")
    lines.append("  (2) BATCH INGESTION   - Load target seeds from local files (.md, .txt)")
    lines.append("                          Best for large-scale data harvesting and automation.")
    lines.append("")
    lines.append("-" * 75)
    lines.append(" [ SYSTEM STATUS ]")
    lines.append("  Ready to receive target coordinates. Select (1) to initialize terminal ")
    lines.append("  input or (2) to mount the local /data/input directory.")
    lines.append("-" * 75)
    lines.append("")
    lines.append(" argos-ntc (intake) > _")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ARGOS-NT interactive menu")
    parser.add_argument("--verbose", action="store_true", help="Show detailed processing logs")
    args = parser.parse_args()
    verbose = args.verbose

    boot = run_startup_checks(print_output=False)
    if not boot.ok:
        _render_home(boot)
        print("Critical startup checks failed. Resolve the issues above and restart ARGOS-NT.")
        sys.exit(1)

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        _show_home(boot)
        option = input("argos-ntc > ").strip()

        if option == "1":
            print(_render_scan_intake_menu())
            mode = input("Choose method (1 or 2): ").strip()
            if mode == "2":
                target_file = _select_target_file()
                if not target_file:
                    print("Scan cancelled.")
                    input("\nPress Enter to return to the menu...")
                    continue
                start = perf_counter()
                try:
                    input_path = Path(target_file)
                    _vlog(verbose, f"Checking file: {input_path.resolve()}")
                    if not input_path.exists() or not input_path.is_file():
                        raise FileNotFoundError(f"File not found: {input_path}")

                    full_scan, tool_filter = _select_scan_mode()
                    # Empty list means the user cancelled
                    if tool_filter == []:
                        print("Scan cancelled.")
                        input("\nPress Enter to return to the menu...")
                        continue

                    result = run_scan(
                        target_file,
                        full_scan=full_scan,
                        tool_filter=tool_filter,
                        progress_callback=lambda msg: _vlog(verbose, f"Pipeline: {msg}"),
                    )
                    _vlog(verbose, f"Finished in {perf_counter() - start:.2f}s")

                    print("\n[OK] Scan completed. Summary:")
                    print(f"  Case:       {result['case_id']}")
                    print(f"  Entities:   {result['entity_stats']}")
                    print(f"  Next steps: {result['next_steps']}")

                    if verbose:
                        print("\n--- Tool results ---")
                        for tool in result["tool_results"]:
                            status = "OK" if tool["ok"] else "FAIL"
                            print(f"  {tool['tool']} on {tool['target']}: {status}")
                        print("\nGraph snapshot:")
                        print(result["graph_snapshot"])

                except Exception as exc:
                    print(f"[ERROR] {exc}")
                    if verbose:
                        traceback.print_exc()

                input("\nPress Enter to return to the menu...")
            else:
                meta = _prompt_case_metadata()
                print(_render_manual_case_and_scan_menu(meta))
                full_scan, tool_filter = _select_scan_mode()
                if tool_filter == []:
                    print("Scan cancelled.")
                    input("\nPress Enter to return to the menu...")
                    continue
                # Write manual case data to a temporary file for scan compatibility
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
                    json.dump(meta, tf)
                    tf.flush()
                    temp_path = tf.name
                try:
                    result = run_scan(
                        temp_path,
                        full_scan=full_scan,
                        tool_filter=tool_filter,
                        progress_callback=lambda msg: _vlog(verbose, f"Pipeline: {msg}"),
                    )
                    print("\n[OK] Scan completed. Summary:")
                    print(f"  Case:       {result['case_id']}")
                    print(f"  Entities:   {result['entity_stats']}")
                    print(f"  Next steps: {result['next_steps']}")
                    if verbose:
                        print("\n--- Tool results ---")
                        for tool in result["tool_results"]:
                            status = "OK" if tool["ok"] else "FAIL"
                            print(f"  {tool['tool']} on {tool['target']}: {status}")
                        print("\nGraph snapshot:")
                        print(result["graph_snapshot"])
                except RuntimeError as exc:
                    msg = str(exc)
                    if "Active provider is not ready" in msg:
                        print("\n[ERROR] No provider is configured or the selected provider/model is unavailable.")
                        print("Please check your provider settings and ensure a model is available.")
                    else:
                        print(f"[ERROR] {msg}")
                    if verbose:
                        traceback.print_exc()
                except Exception as exc:
                    print(f"[ERROR] {exc}")
                    if verbose:
                        traceback.print_exc()
                input("\nPress Enter to return to the menu...")
                # Optionally, remove the temp file after scan
                try:
                    import os
                    os.unlink(temp_path)
                except Exception:
                    pass


        elif option == "2":
            _history_menu(verbose)

        elif option == "3":
            _provider_settings_menu(ConfigManager())

        elif option == "4":
            print("Exiting...")
            sys.exit(0)

        else:
            print("Invalid option.")
            input("\nPress Enter to return to the menu...")


if __name__ == "__main__":
    main()
