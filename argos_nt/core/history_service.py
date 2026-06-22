from __future__ import annotations

from pathlib import Path

from argos_nt.config_manager import ConfigManager
from argos_nt.core.constants import ANSI_RESET, REPORTS_DIR
from argos_nt.drivers.neo4j_driver import Neo4jConnectionParams, Neo4jDriver


def connect_graph() -> Neo4jDriver:
    config = ConfigManager().load()
    params = Neo4jConnectionParams(
        uri=config.neo4j.uri,
        username=config.neo4j.username,
        password=config.neo4j.password,
        database=config.neo4j.database,
    )
    return Neo4jDriver(params)


def load_history_entries() -> list[dict[str, str | int]]:
    graph = connect_graph()
    try:
        cases = graph.list_cases(limit=500)
    finally:
        graph.close()

    entries: list[dict[str, str | int]] = []
    for index, case in enumerate(cases, start=1):
        target_file = str(case.get("source_file", "")) or "(no source file)"
        created_at = str(case.get("created_at", ""))
        entries.append(
            {
                "id": index,
                "case_id": str(case.get("case_id", "")),
                "target_file": target_file,
                "created_at": created_at,
            }
        )
    return entries


def find_history_entry(
    history_id: int, entries: list[dict[str, str | int]]
) -> dict[str, str | int] | None:
    for entry in entries:
        if entry["id"] == history_id:
            return entry
    return None


def update_history_entry_source(entry: dict[str, str | int], new_source_file: str) -> bool:
    case_id = str(entry["case_id"])
    graph = connect_graph()
    try:
        return graph.update_case_source_file(case_id, new_source_file)
    finally:
        graph.close()


def delete_history_entry(entry: dict[str, str | int]) -> bool:
    case_id = str(entry["case_id"])
    graph = connect_graph()
    try:
        return graph.delete_case(case_id)
    finally:
        graph.close()


def render_history_view(entries: list[dict[str, str | int]]) -> str:
    """Render the archive explorer view with table of history entries."""
    # CYAN removed
    GREEN = "\033[92m"
    BOLD = "\033[1m"
    
    lines = []
    
    total_records = len(entries)
    lines.append("-" * 75 + f"{ANSI_RESET}")
    lines.append(f"{BOLD}  ARCHIVE EXPLORER  |  Total Records: {total_records:02d}  |  Storage: Local Graph{ANSI_RESET}")
    lines.append("-" * 75 + f"{ANSI_RESET}")
    lines.append("")
    
    # Table header
    lines.append(f"  {BOLD}ID   |  CASE IDENTIFIER           |  SOURCE FILE          |  TIMESTAMP{ANSI_RESET}")
    lines.append(f"  -----|----------------------------|-----------------------|----------------{ANSI_RESET}")
    
    # Table rows
    for entry in entries[:10]:  # Limit to 10 entries
        entry_id = str(entry["id"]).zfill(2)
        case_id = str(entry["case_id"])[:28].ljust(28)
        target_file = str(entry["target_file"])[:21].ljust(21)
        created_at = str(entry.get("created_at", ""))[:16] if entry.get("created_at") else "---"
        
        lines.append(f"  {GREEN}[{entry_id}]{ANSI_RESET} |  {case_id} |  {target_file} |  {created_at}")
    
    # Fill empty slots if less than 10 entries
    if total_records < 10:
        for i in range(10 - total_records):
            lines.append(f"  [..] |  <EMPTY_SLOT>              |  ---                  |  ---")
    
    lines.append("")
    
    return "\n".join(lines)


def render_history_dossier_view(
    entry: dict[str, str | int],
    snapshot: dict[str, object] | None,
    provider_model: str | None = None,
) -> str:
    """Render a dossier detail screen for a selected history entry."""
    # CYAN removed
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = ANSI_RESET

    entry_id = str(entry["id"]).zfill(2)
    case_id = str(entry["case_id"])
    target_file = str(entry["target_file"])
    created_at = str(entry.get("created_at", ""))
    case_data = snapshot.get("case") if isinstance(snapshot, dict) else None
    if isinstance(case_data, dict):
        created_at = str(case_data.get("created_at", created_at))
        target_file = str(case_data.get("source_file", target_file))

    # Entities
    entities = snapshot.get("entities", []) if isinstance(snapshot, dict) else []
    entities_count = len([item for item in entities if isinstance(item, dict)])
    # Compose entity table
    entity_table = []
    if entities:
        entity_table.append("  -------------------------------------------------------------------------")
        entity_table.append("  (ID) TYPE      | VALUE")
        entity_table.append("  -------------------------------------------------------------------------")
        for idx, ent in enumerate(entities, 1):
            if not isinstance(ent, dict):
                continue
            ent_type = ent.get("type", "?")[:10].ljust(10)
            ent_value = str(ent.get("value", "")).strip()
            ent_id = f"[{idx:02d}]"
            entity_table.append(f"  {ent_id}  {ent_type} | {ent_value}")
        entity_table.append("  -------------------------------------------------------------------------")

    # Findings
    findings = snapshot.get("findings", []) if isinstance(snapshot, dict) else []
    findings_blocks = []
    for idx, finding in enumerate(findings, 1):
        if not isinstance(finding, dict):
            continue
        title = finding.get("title", "FINDING")
        module = finding.get("module", "?")
        status = finding.get("status", "INFO").upper()
        summary = finding.get("summary", "")
        details = finding.get("details", "")
        # Status icon
        if status == "CRITICAL":
            status_icon = f"{RED}[!] CRITICAL:{RESET}"
        elif status == "SUCCESS":
            status_icon = f"{GREEN}[+] SUCCESS:{RESET}"
        elif status == "NEGATIVE":
            status_icon = f"{YELLOW}[-] NEGATIVE:{RESET}"
        else:
            status_icon = f"[i] INFO:"
        findings_blocks.append(f"  [FINDING {idx:02d}] :: {title.upper()} ({module})")
        findings_blocks.append(f"  {status_icon} {summary}")
        if details:
            for line in details.split("\n"):
                findings_blocks.append(f"      {line}")
        findings_blocks.append("")

    reports = list(REPORTS_DIR.glob(f"**/*{case_id}*.md")) if REPORTS_DIR.exists() else []
    last_action = "Exported to Markdown" if reports else "Analysis completed"

    lines = []
    lines.append("-" * 75)
    lines.append(f"  ARGOS-NTC INTELLIGENCE DOSSIER  |  CONFIDENTIAL  |  v1.0.4")
    lines.append("-" * 75)
    lines.append("")
    lines.append(f" [1. CASE IDENTIFICATION]")
    lines.append(f"  ● CASE ID    : {case_id}")
    lines.append(f"  ● TARGET     : {Path(target_file).stem}")
    lines.append(f"  ● TIMESTAMP  : {created_at}")
    lines.append(f"  ● STATUS     : COMPLETED - {entities_count} Findings Identified")
    lines.append("")
    lines.append(f" [2. CORE ENTITIES MAP]")
    if entity_table:
        lines.extend(entity_table)
    else:
        lines.append("  No entities mapped.")
    lines.append("")
    lines.append(f" [3. INTELLIGENCE FINDINGS]")
    if findings_blocks:
        lines.extend(findings_blocks)
    else:
        lines.append("  No findings available.")
    lines.append("-" * 75)
    lines.append(f" [END OF DOSSIER]")
    lines.append("-" * 75)
    lines.append(f" [ENTER] Return to Case Management | [P] Export PDF | [O] Obsidian Sync")
    lines.append("-" * 75)
    lines.append("")
    return "\n".join(lines)


def render_history_options_menu() -> str:
    """Render options menu for the dossier management screen."""
    CYAN = "\033[36m"
    BOLD = "\033[1m"
    
    lines = []
    
    lines.append(f"{BOLD}  [ OPERATIONAL COMMANDS ]{ANSI_RESET}")
    lines.append(f"  (1) RUN RE-SCAN    - Re-execute all OSINT modules for fresh data{ANSI_RESET}")
    lines.append(f"  (2) VIEW REPORT    - Display formatted intelligence summary (TUI){ANSI_RESET}")
    lines.append(f"  (3) EXPORT         - Generate Obsidian Vault or PDF Dossier{ANSI_RESET}")
    lines.append(f"  (4) EDIT TARGET    - Modify input parameters/seeds for this case{ANSI_RESET}")
    lines.append(f"  (5) WIPE CASE      - Permanent deletion from Graph and Disk{ANSI_RESET}")
    lines.append(f"  (6) BACK           - Return to Archive Explorer{ANSI_RESET}")
    lines.append("-" * 75 + f"{ANSI_RESET}")
    lines.append("")
    
    return "\n".join(lines)

