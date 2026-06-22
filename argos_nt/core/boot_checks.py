from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from argos_nt.config_manager import ConfigManager
from argos_nt.core.constants import (
    ANSI_BOLD,
    ANSI_RESET,
    ARGOS_NT_BANNER,
    APP_CODENAME,
    APP_VERSION,
    INPUT_DIR,
    MAINTAINER_LINE,
    OUTPUT_DIR,
    STATUS_COLORS,
    TOOL_REQUIREMENTS,
)
from argos_nt.core.provider_service import check_active_provider, get_provider_model
from argos_nt.drivers.neo4j_driver import Neo4jConnectionParams, Neo4jDriver


@dataclass
class CheckItem:
    status: str
    label: str
    detail: str


@dataclass
class BootResult:
    ok: bool = True
    checks: list[CheckItem] = field(default_factory=list)

    def add(self, status: str, label: str, detail: str) -> None:
        self.checks.append(CheckItem(status=status, label=label, detail=detail))

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"OK": 0, "WARN": 0, "ERR": 0}
        for check in self.checks:
            if check.label == "Summary":
                continue
            counts[check.status] = counts.get(check.status, 0) + 1
        return counts

    def issues(self) -> list[CheckItem]:
        return [check for check in self.checks if check.status != "OK" and check.label != "Summary"]


def boot_health_line(result: BootResult) -> str:
    """Return a compact one-line startup health summary."""
    counts = result.counts()
    return (
        f"boot health: {counts['OK']} ready | "
        f"{counts['WARN']} warnings | "
        f"{counts['ERR']} critical"
    )


def format_boot_issue(issue: CheckItem) -> str:
    """Normalize noisy boot issue text for compact CLI/TUI rendering."""
    label = issue.label
    detail = issue.detail.strip()

    if label.startswith("Tool ") and "not found in PATH" in detail:
        tool_name = label.replace("Tool ", "", 1)
        scope = ""
        if " for " in detail:
            after_for = detail.split(" for ", 1)[1]
            scope = after_for.split(" tool", 1)[0].strip()
        tried = ""
        if "(tried:" in detail:
            tried = detail.split("(tried:", 1)[1].rstrip(") ").strip()
        optional = "optional" in detail.lower()
        level = "optional" if optional else "required"
        suffix = f" ({scope})" if scope else ""
        if tried:
            return f"{tool_name}: {level}{suffix} tool missing [{tried}]"
        return f"{tool_name}: {level}{suffix} tool missing"

    if label == "Active Provider":
        if ". Menu remains available;" in detail:
            detail = detail.split(". Menu remains available;", 1)[0].strip()
        return f"Provider: {detail}"

    return f"{label}: {detail}"


def boot_health_formatted(result: BootResult) -> str:
    """Return a visually formatted boot health status block."""
    counts = result.counts()
    ready = counts["OK"]
    warnings = counts["WARN"]
    critical = counts["ERR"]
    
    line = (
        "  BOOT HEALTH  ::  "
        f"[ READY: {ready} ]  "
        f"[ WARNINGS: {warnings} ]  "
        f"[ CRITICAL: {critical} ]"
    )
    return line


def format_boot_issue_expanded(issue: CheckItem) -> str:
    """Return formatted boot issue with title, details, and recommendation."""
    label = issue.label
    detail = issue.detail.strip()
    
    lines = []
    
    if label.startswith("Tool ") and "not found in PATH" in detail:
        tool_name = label.replace("Tool ", "", 1)
        scope = ""
        tried = ""
        if " for " in detail:
            after_for = detail.split(" for ", 1)[1]
            scope = after_for.split(" tool", 1)[0].strip()
        if "(tried:" in detail:
            tried = detail.split("(tried:", 1)[1].rstrip(") ").strip()
        optional = "optional" in detail.lower()
        
        lines.append(f"[!] WARNING: Tool '{tool_name}' not found in PATH.")
        if scope:
            lines.append(f"    Scope: {scope.title()}")
        if tried:
            lines.append(f"    -> Recommendation: Install [{tried}]")
        else:
            lines.append(f"    -> Recommendation: Install this tool for expanded capabilities.")
        if optional:
            lines.append(f"    -> Impact: Optional; scan will continue without this tool.")
        return "\n".join(lines)
    
    if label == "Active Provider":
        lines.append("[!] WARNING: LLM Provider Configuration")
        if "not available" in detail.lower():
            model_match = detail.split("'") if "'" in detail else []
            if len(model_match) >= 2:
                model = model_match[1]
                lines.append(f"    -> Model '{model}' is not pulled in Ollama.")
            if "Available models:" in detail:
                available = detail.split("Available models:")[1].strip()
                lines.append(f"    -> Status: Reachable | Available Models: {available}")
        else:
            lines.append(f"    -> {detail}")
        return "\n".join(lines)
    
    return f"[!] {label}: {detail}"


def tool_scope_label(scope: str) -> str:
    return {
        "base-scan": "base scan",
        "full-scan": "full scan",
        "username-enrichment": "username enrichment",
        "email-enrichment": "email enrichment",
        "phone-enrichment": "phone enrichment",
    }.get(scope, scope)


def find_tool_path(executables: tuple[str, ...]) -> tuple[str, str] | None:
    for executable in executables:
        path = shutil.which(executable)
        if path:
            return executable, path
    return None


def run_startup_checks(print_output: bool = True) -> BootResult:
    """Run all boot checks. Returns BootResult; ok=True when no ERR recorded."""
    result = BootResult()
    counts: dict[str, int] = {"OK": 0, "WARN": 0, "ERR": 0}

    def record(status: str, label: str, detail: str) -> None:
        result.add(status, label, detail)
        counts[status] = counts.get(status, 0) + 1
        if print_output:
            color = STATUS_COLORS.get(status, "")
            print(f"{color}[{status}]{ANSI_RESET} {label}: {detail}")

    if print_output:
        print(f"\n{ANSI_BOLD}========================================{ANSI_RESET}")
        print(f"{ANSI_BOLD} ARGOS-NT Boot Sequence{ANSI_RESET}")
        print(f"{ANSI_BOLD}========================================{ANSI_RESET}")

    config_manager = ConfigManager()
    config = None
    try:
        config = config_manager.load()
        active_provider = str(config.ai.provider).lower().strip()
        active_model = get_provider_model(config, active_provider)
        record("OK", "Configuration", f"provider={active_provider} model={active_model}")
    except Exception as exc:
        record("ERR", "Configuration", str(exc))
        record("WARN", "Initialization", "continuing with limited checks")
        record("ERR", "Startup", "critical boot checks failed; menu startup blocked")
        if print_output:
            print(f"{ANSI_BOLD}========================================{ANSI_RESET}\n")
        result.ok = False
        return result

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    record("OK", "Directories", f"input={INPUT_DIR} output={OUTPUT_DIR}")

    for label, executables, required, scope in TOOL_REQUIREMENTS:
        found = find_tool_path(executables)
        if found is not None:
            executable, tool_path = found
            record(
                "OK",
                f"Tool {label}",
                f"{tool_scope_label(scope)} | {executable} -> {tool_path}",
            )
        elif required:
            record(
                "ERR",
                f"Tool {label}",
                f"required for {tool_scope_label(scope)} but not found in PATH "
                f"(tried: {', '.join(executables)})",
            )
        else:
            record(
                "WARN",
                f"Tool {label}",
                f"optional {tool_scope_label(scope)} tool not found in PATH "
                f"(tried: {', '.join(executables)})",
            )

    provider_status, provider_detail = check_active_provider(config)
    if provider_status == "ERR":
        record(
            "WARN",
            "Active Provider",
            f"{provider_detail}. Menu remains available; switch provider in settings before scanning.",
        )
    else:
        record(provider_status, "Active Provider", provider_detail)

    try:
        params = Neo4jConnectionParams(
            uri=config.neo4j.uri,
            username=config.neo4j.username,
            password=config.neo4j.password,
            database=config.neo4j.database,
        )
        graph = Neo4jDriver(params)
        try:
            graph.verify_connectivity()
            record("OK", "Neo4j", f"connected to {config.neo4j.uri} ({config.neo4j.database})")
        finally:
            graph.close()
    except Exception as exc:
        record("ERR", "Neo4j", str(exc))

    summary_status = "ERR" if counts["ERR"] else "WARN" if counts["WARN"] else "OK"
    record(
        summary_status,
        "Summary",
        f"ok={counts['OK']} warn={counts['WARN']} err={counts['ERR']}",
    )

    if counts["ERR"] and print_output:
        color = STATUS_COLORS.get("ERR", "")
        print(f"{color}[ERR]{ANSI_RESET} Startup: critical boot checks failed; menu startup blocked")

    if print_output:
        print(f"{ANSI_BOLD}========================================{ANSI_RESET}\n")

    result.ok = counts["ERR"] == 0
    return result


def render_system_status(
    boot_result: BootResult,
    provider_name: str | None = None,
    provider_model: str | None = None,
    total_cases: int = 0,
    active_modules: int = 0,
) -> str:
    """Render the full system status display with new visual design and colors."""
    lines = []
    
    # Color codes
    # CYAN removed
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    
    # Banner
    banner_lines = ARGOS_NT_BANNER.strip().split("\n")
    for line in banner_lines:
        lines.append(f"{line}{ANSI_RESET}")
    lines.append(" " + "-" * 75 + f"{ANSI_RESET}")
    lines.append(f"  AI OSINT / Investigation Console  |  {APP_VERSION} - \"{APP_CODENAME}\"{ANSI_RESET}")
    lines.append(f"  Maintainer: {MAINTAINER_LINE}{ANSI_RESET}")
    lines.append(" " + "-" * 75 + f"{ANSI_RESET}")
    lines.append("")
    
    # System Status
    lines.append(f"{BOLD}  [SYSTEM STATUS]{ANSI_RESET}")
    
    # LLM Core status
    provider_label = provider_name.title() if provider_name else "Unknown"
    model_label = provider_model or "unknown-model"
    llm_status = "REACHABLE" if provider_name else "UNCONFIGURED"
    llm_color = GREEN if provider_name else RED
    lines.append(f"  ● LLM CORE: {provider_label} ({model_label}) {'.' * (45 - len(provider_label) - len(model_label))} [ {llm_color}{llm_status}{ANSI_RESET} ]")
    
    # Database status
    db_color = GREEN
    lines.append(f"  ● DATABASE: Neo4j (Graph Engine) {'.' * 35} [ {db_color}CONNECTED{ANSI_RESET} ]")
    
    # Modules status
    module_label = f"{active_modules} Profiling Engines"
    module_color = GREEN if active_modules > 0 else YELLOW
    lines.append(f"  ● MODULES : {module_label} {'.' * (47 - len(module_label))} [ {module_color}LOADED{ANSI_RESET}    ]")
    
    # Data status
    dossier_str = f"{total_cases:02d} Active Dossier{'s' if total_cases != 1 else ''}"
    data_color = GREEN
    lines.append(f"  ● DATA    : {dossier_str} {'.' * (48 - len(dossier_str))} [ {data_color}SYNCED{ANSI_RESET}    ]")
    lines.append("")
    
    # Boot Health
    lines.append(f"{BOLD}  [BOOT HEALTH]{ANSI_RESET}")
    counts = boot_result.counts()
    total_components = counts["OK"] + counts["WARN"] + counts["ERR"]
    ready_color = GREEN
    warn_color = YELLOW if counts["WARN"] > 0 else GREEN
    crit_color = RED if counts["ERR"] > 0 else GREEN
    health_line = (
        f"  TOTAL: {total_components} Components  |  "
        f"{ready_color}✔ {counts['OK']} READY{ANSI_RESET}  |  "
        f"{warn_color}! {counts['WARN']} WARNINGS{ANSI_RESET}  |  "
        f"{crit_color}✘ {counts['ERR']} CRITICAL{ANSI_RESET}"
    )
    lines.append(health_line)
    lines.append("")
    
    # Startup Notices
    issues = boot_result.issues()
    if issues:
        lines.append(f"{BOLD}  [STARTUP NOTICES]{ANSI_RESET}")
        for issue in issues[:3]:
            is_critical = issue.status == "ERR" or "required" in issue.detail.lower()
            color = RED if is_critical else YELLOW
            expanded = format_boot_issue_expanded(issue)
            lines.append(f"{color}  {expanded}{ANSI_RESET}")
        if len(issues) > 3:
            lines.append(f"{YELLOW}  [i] {len(issues) - 3} additional startup notice(s) hidden{ANSI_RESET}")
        lines.append("")
    
    return "\n".join(lines)



def render_navigation_menu() -> str:
    """Render the navigation menu section with colors."""
    BOLD = "\033[1m"

    lines = []
    lines.append(" " + "-" * 75 + f"{ANSI_RESET}")
    lines.append(f"{BOLD}  [NAVIGATION]{ANSI_RESET}")
    lines.append(f"  (1) NEW SCAN       - Initialize intelligence gathering{ANSI_RESET}")
    lines.append(f"  (2) VIEW HISTORY   - Access graph-stored dossiers{ANSI_RESET}")
    lines.append(f"  (3) SETTINGS       - Configure providers & API keys{ANSI_RESET}")
    lines.append(f"  (4) EXIT           - Terminate secure session{ANSI_RESET}")
    lines.append(" " + "-" * 75 + f"{ANSI_RESET}")
    lines.append("")
    return "\n".join(lines)

