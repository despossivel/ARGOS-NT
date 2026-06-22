from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from argos_nt.core.constants import EXPORT_FORMATS, REPORTS_DIR
from argos_nt.core.history_service import connect_graph


def slugify(value: str) -> str:
    sanitized = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip()
    )
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")
    return sanitized.strip("_") or "report"


def load_case_snapshot(case_id: str) -> dict[str, Any] | None:
    graph = connect_graph()
    try:
        return graph.get_case_map(case_id)
    finally:
        graph.close()


def render_report_text(entry: dict[str, str | int], snapshot: dict[str, Any]) -> str:
    case_id = str(entry["case_id"])
    target_file = str(entry["target_file"])
    case_data = snapshot.get("case") if isinstance(snapshot, dict) else None
    entities = snapshot.get("entities", []) if isinstance(snapshot, dict) else []
    findings = snapshot.get("findings", []) if isinstance(snapshot, dict) else []

    entity_list = [item for item in entities if isinstance(item, dict)]
    finding_list = [item for item in findings if isinstance(item, dict)]

    lines: list[str] = []
    lines.append("ARGOS-NT Case Report")
    lines.append("=" * 60)
    lines.append(f"Case ID: {case_id}")
    lines.append(f"Target file: {target_file}")
    if isinstance(case_data, dict):
        if case_data.get("source_file"):
            lines.append(f"Source: {case_data['source_file']}")
        if case_data.get("created_at"):
            lines.append(f"Created at: {case_data['created_at']}")
    lines.append(f"Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------
    lines.append("Entities")
    lines.append("-" * 60)
    if not entity_list:
        lines.append("No entities registered for this case.")
    else:
        type_counts: dict[str, list[str]] = {}
        for entity in entity_list:
            labels = entity.get("labels")
            entity_type = "Entity"
            if isinstance(labels, list) and labels:
                entity_type = str(labels[0])
            elif isinstance(entity.get("type"), str):
                entity_type = str(entity["type"])
            value = str(entity.get("value", entity.get("id", "?")))
            type_counts.setdefault(entity_type, []).append(value)
        for etype in sorted(type_counts):
            vals = type_counts[etype]
            lines.append(f"  {etype} ({len(vals)}):")
            for v in vals:
                lines.append(f"    • {v}")
    lines.append("")

    # ------------------------------------------------------------------
    # Findings - structured only (sanitised parser output)
    # ------------------------------------------------------------------
    lines.append("Findings")
    lines.append("-" * 60)
    if not finding_list:
        lines.append("No findings registered for this case.")
    else:
        for idx, finding in enumerate(finding_list, start=1):
            tool = str(finding.get("tool", "unknown"))
            summary = str(finding.get("summary", ""))
            sd = finding.get("structured_data")

            lines.append(f"\n[{idx}] Tool: {tool}")
            lines.append(f"    Summary: {summary}")

            if isinstance(sd, dict) and sd:
                lines.extend(_render_structured_data(sd))
            else:
                lines.append("    No structured findings available.")

    lines.append("")
    lines.append("=" * 60)
    lines.append("End of report — ARGOS-NT")
    return "\n".join(lines)


def _render_structured_data(sd: dict[str, Any]) -> list[str]:
    """
    Convert a structured_data dict into human-readable report lines.
    Every concrete finding is listed — nothing is omitted.
    """
    dtype = sd.get("type", "generic")
    lines: list[str] = []

    if dtype == "account_check":
        accounts = sd.get("accounts", [])
        if accounts:
            lines.append(f"    Registered accounts ({len(accounts)}):")
            for item in accounts:
                site = item.get("site", "unknown")
                status = item.get("status", "exists")
                lines.append(f"      ✓ {site} [{status}]")
        else:
            lines.append("    No registered accounts found.")

    elif dtype == "credential_leak":
        leaks = sd.get("leaks", [])
        if leaks:
            lines.append(f"    Credential leaks ({len(leaks)}):")
            for leak in leaks:
                src = leak.get("source", "unknown")
                pwd = leak.get("password", "")
                pwd_info = f" | password: {pwd}" if pwd else ""
                lines.append(f"      Source: {src}{pwd_info}")
        else:
            lines.append("    No credential breaches found.")

    elif dtype in ("username_search", "username_availability"):
        found = sd.get("profiles", [])
        registered_sites = sd.get("registered_sites", [])
        if found:
            lines.append(f"    Profiles found ({len(found)}):")
            for p in found:
                url = p.get("url", "")
                status = p.get("status", "found")
                lines.append(f"      ✓ {url} [{status}]")
        elif registered_sites:
            lines.append(f"    Registered sites ({len(registered_sites)}):")
            for s in registered_sites:
                lines.append(f"      ✓ {s}")
        else:
            lines.append("    No profiles found.")

    elif dtype == "phone_check":
        wa = sd.get("whatsapp_registered")
        sites = sd.get("registered_sites", [])
        profile_name = sd.get("profile_name")
        if wa is not None:
            lines.append(f"    WhatsApp registered: {'YES' if wa else 'NO'}")
        if profile_name:
            lines.append(f"    Profile name: {profile_name}")
        if sites:
            lines.append(f"    Services registered ({len(sites)}):")
            for s in sites:
                lines.append(f"      ✓ {s}")

    elif dtype == "google_account":
        name = sd.get("name")
        photo = sd.get("photo_url")
        services = sd.get("linked_services", [])
        if name:
            lines.append(f"    Name: {name}")
        if photo:
            lines.append(f"    Photo: {photo}")
        if services:
            lines.append(f"    Linked Google services: {', '.join(services)}")

    elif dtype == "instagram_account":
        name = sd.get("name")
        followers = sd.get("followers")
        following = sd.get("following")
        if name:
            lines.append(f"    Name: {name}")
        if followers is not None:
            lines.append(f"    Followers: {followers}")
        if following is not None:
            lines.append(f"    Following: {following}")

    elif dtype == "google_dork_search":
        urls = sd.get("urls_found", [])
        total = sd.get("total_results", 0)
        if urls:
            lines.append(f"    URLs found ({total}):")
            for url in urls[:20]:
                lines.append(f"      • {url}")
            if len(urls) > 20:
                lines.append(f"      ... and {len(urls) - 20} more URL(s)")
        else:
            lines.append("    No URLs found.")

    else:  # generic
        urls = sd.get("urls_found", [])
        emails = sd.get("emails_found", [])
        if urls:
            lines.append(f"    URLs found ({len(urls)}):")
            for u in urls:
                lines.append(f"      {u}")
        if emails:
            lines.append(f"    Emails found ({len(emails)}):")
            for e in emails:
                lines.append(f"      {e}")
        # Dump any other keys as-is
        skip = {"type", "target", "urls_found", "emails_found"}
        for k, v in sd.items():
            if k not in skip:
                lines.append(f"    {k}: {json.dumps(v, ensure_ascii=False)}")

    return lines


def render_report_html(entry: dict[str, str | int], report_text: str) -> str:
    case_id = escape(str(entry["case_id"]))
    target_file = escape(str(entry["target_file"]))
    generated_at = escape(datetime.now().isoformat(timespec="seconds"))
    body = escape(report_text)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ARGOS-NT Report - {case_id}</title>
  <style>
    :root {{
      --bg: #0b1220; --panel: #111b2f; --fg: #d7e2f0;
      --muted: #8aa1bc; --accent: #4dd0e1; --line: #1e2b45;
    }}
    body {{
      margin: 0;
      background: radial-gradient(circle at top right, #132445, var(--bg) 45%);
      color: var(--fg);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      padding: 24px;
    }}
    .card {{
      max-width: 1100px; margin: 0 auto;
      background: linear-gradient(160deg, rgba(77,208,225,0.08), rgba(17,27,47,0.96));
      border: 1px solid var(--line); border-radius: 14px;
      overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.35);
    }}
    .header {{
      padding: 18px 20px; border-bottom: 1px solid var(--line);
      background: rgba(9,15,28,0.7);
    }}
    .title {{ margin: 0; font-size: 20px; color: var(--accent); }}
    .meta {{ margin-top: 8px; font-size: 12px; color: var(--muted); line-height: 1.6; }}
    pre {{
      margin: 0; padding: 20px; white-space: pre-wrap;
      word-wrap: break-word; line-height: 1.5; font-size: 13px;
    }}
  </style>
</head>
<body>
  <section class="card">
    <header class="header">
      <h1 class="title">ARGOS-NT Case Report</h1>
      <div class="meta">
        Case ID: {case_id}<br/>
        Target: {target_file}<br/>
        Generated: {generated_at}
      </div>
    </header>
    <pre>{body}</pre>
  </section>
</body>
</html>"""


def export_report_pdf(output_path: Path, report_text: str) -> tuple[bool, str]:
    try:
        from fpdf import FPDF  # type: ignore
    except Exception:
        return False, "PDF export requires 'fpdf2'. Install with: pip install fpdf2"

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in report_text.splitlines():
        safe = line.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 6, safe)
    pdf.output(str(output_path))
    return True, "ok"


def export_case_report(
    entry: dict[str, str | int], fmt: str
) -> tuple[bool, Path | str]:
    """
    Export report for the given history entry.

    fmt: one of 'md', 'txt', 'html', 'pdf'
    Returns (True, output_path) on success, (False, error_message) on failure.
    """
    case_id = str(entry["case_id"])
    snapshot = load_case_snapshot(case_id)
    if not snapshot or snapshot.get("case") is None:
        return False, f"No case data found for case ID: {case_id}"

    extension = EXPORT_FORMATS.get(fmt, ".txt")
    report_text = render_report_text(entry, snapshot)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = REPORTS_DIR / f"report_{slugify(case_id)}_{timestamp}{extension}"

    if fmt in ("md", "txt"):
        output_path.write_text(report_text, encoding="utf-8")
    elif fmt == "html":
        output_path.write_text(render_report_html(entry, report_text), encoding="utf-8")
    elif fmt == "pdf":
        ok, detail = export_report_pdf(output_path, report_text)
        if not ok:
            return False, detail

    return True, output_path
