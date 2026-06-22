"""
ARGOS-NT Textual TUI — mirrors CLI flows via the argos_nt.core service layer.

Layout
------
 ┌─────────────────────────────────────────────────────────────────────┐
 │ Header (clock)                                                      │
 ├────────────── sidebar ─────────┬──────────── main panel ───────────┤
 │ [Targets] [History]            │  LOGS AND INSIGHTS  (RichLog)     │
 │  • file1.md                   │                                   │
 │  • file2.txt                  │                                   │
 │ ─────────────── History tab ─ │                                   │
 │  [1] case_id | 2025-01-01     │                                   │
 │  [View] [Export] [Delete]     │                                   │
 │  fmt: md / txt / html / pdf   │                                   │
 ├────────────────────────────────┴───────────────────────────────────┤
 │ Footer  F1 Help  F2 Providers  F3 Run  F4 Full  F5 Export  Q Quit  │
 └─────────────────────────────────────────────────────────────────────┘

Key bindings
------------
  F1  show_help         — notify keybinding cheatsheet
  F2  show_providers    — print all provider status to RichLog
  F3  run_scan          — run pipeline on selected target file (thread)
  F4  toggle_full_scan  — toggle full/base scan mode
  F5  export_report     — export selected case in chosen format (thread)
  F6  view_report       — render selected case report in RichLog (thread)
  q   quit
"""
from __future__ import annotations

import shutil
import traceback
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from argos_nt.config_manager import ConfigManager
from argos_nt.core.boot_checks import (
    boot_health_formatted,
    boot_health_line,
    format_boot_issue,
    format_boot_issue_expanded,
    run_startup_checks,
)
from argos_nt.core.constants import TOOL_REQUIREMENTS
from argos_nt.core.constants import EXPORT_FORMATS, INPUT_DIR
from argos_nt.core.history_service import delete_history_entry, load_history_entries
from argos_nt.core.provider_service import all_provider_status, get_provider_model
from argos_nt.core.report_service import export_case_report, load_case_snapshot, render_report_text
from argos_nt.core.scan_service import run_scan
from argos_nt.ui.banner_manager import ArgosBannerManager

_CSS = """
Screen {
    background: #0A0A0A;
    color: #E5E7EB;
}

#sidebar {
    width: 35%;
    min-width: 30;
    border: round #1E3A8A;
    padding: 1;
}

#main-panel {
    width: 65%;
    border: round #1E3A8A;
    padding: 1;
}

.title {
    color: #06B6D4;
    text-style: bold;
    margin-bottom: 1;
}

#insights-log {
    border: solid #06B6D4;
    height: 1fr;
}

#action-bar {
    height: auto;
    margin-top: 1;
    layout: horizontal;
}

#action-bar Button {
    margin-right: 1;
    min-width: 12;
}

#btn-delete {
    background: #7f1d1d;
    border: solid #ef4444;
}

#export-fmt {
    margin-top: 1;
    height: 3;
}
"""


class ArgosTUI(App):
    """ARGOS-NT TUI — delegates all heavy work to argos_nt.core."""

    CSS = _CSS

    BINDINGS = [
        ("f1", "show_help", "Help"),
        ("f2", "show_providers", "Providers"),
        ("f3", "run_scan", "Run Scan"),
        ("f4", "toggle_full_scan", "Full Scan"),
        ("f5", "export_report", "Export"),
        ("f6", "view_report", "View Report"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._full_scan: bool = False
        self._selected_entry: dict[str, Any] | None = None
        self._history_entries: list[dict[str, Any]] = []
        self._banner_manager = ArgosBannerManager()

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal():
            with Vertical(id="sidebar"):
                with TabbedContent(initial="tab-targets"):
                    with TabPane("Targets", id="tab-targets"):
                        yield ListView(id="target-list")

                    with TabPane("History", id="tab-history"):
                        yield ListView(id="history-list")
                        with Horizontal(id="action-bar"):
                            yield Button("View", id="btn-view", variant="primary")
                            yield Button("Export", id="btn-export", variant="success")
                            yield Button("Delete", id="btn-delete")
                        yield Input(
                            placeholder="fmt: md / txt / html / pdf",
                            id="export-fmt",
                        )

            with Vertical(id="main-panel"):
                yield Static("[ARGOS-NT] HOME / OPERATIONS", classes="title")
                yield RichLog(id="insights-log", wrap=True, highlight=True)

        yield Footer()

    # ------------------------------------------------------------------
    # Mount — boot checks + populate lists
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._populate_target_list()
        self._boot_and_load_history()

    def _populate_target_list(self) -> None:
        target_list = self.query_one("#target-list", ListView)
        target_list.clear()
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(INPUT_DIR.glob("*.md")) + sorted(INPUT_DIR.glob("*.txt"))
        for f in files:
            target_list.append(ListItem(Static(f.name)))
        if not files:
            target_list.append(ListItem(Static("(no files in data/input/)")))

    @work(thread=True)
    def _boot_and_load_history(self) -> None:
        log = self.query_one("#insights-log", RichLog)
        config = ConfigManager().load()
        provider = str(config.ai.provider).lower().strip()
        total_cases = 0
        try:
            total_cases = len(load_history_entries())
        except Exception:
            total_cases = 0

        active_modules = sum(
            1
            for _, executables, _, _ in TOOL_REQUIREMENTS
            if any(shutil.which(executable) for executable in executables)
        )

        self.call_from_thread(
            log.write,
            self._banner_manager.generate_startup_screen(
                total_cases=total_cases,
                active_modules=active_modules,
                provider_name=provider,
                provider_model=get_provider_model(config, provider),
            ),
        )

        boot = run_startup_checks(print_output=False)
        
        # Boot health header
        self.call_from_thread(log.write, "[bold bright_cyan]" + "-" * 70 + "[/bold bright_cyan]")
        self.call_from_thread(log.write, f"[bold bright_cyan]{boot_health_formatted(boot)}[/bold bright_cyan]")
        self.call_from_thread(log.write, "[bold bright_cyan]" + "-" * 70 + "[/bold bright_cyan]")
        
        issues = boot.issues()
        if issues:
            self.call_from_thread(log.write, "")
            self.call_from_thread(log.write, "[bold white]  (i) STARTUP NOTICES:[/bold white]")
            self.call_from_thread(log.write, "")
        
        for issue in issues[:4]:
            is_critical = issue.status == "ERR" or "required" in issue.detail.lower()
            text_style = "red" if is_critical else "yellow"
            expanded = format_boot_issue_expanded(issue)
            self.call_from_thread(log.write, f"[{text_style}]{expanded}[/{text_style}]")
            self.call_from_thread(log.write, "")
        
        if len(issues) > 4:
            self.call_from_thread(log.write, f"[dim]  note: {len(issues) - 4} additional startup notice(s) hidden[/dim]")
            self.call_from_thread(log.write, "")
        
        self.call_from_thread(log.write, "[bright_cyan]" + "-" * 70 + "[/bright_cyan]")
        self.call_from_thread(log.write, "")
        if boot.ok:
            self.call_from_thread(log.write, "[green]Console ready.[/green]")
        else:
            self.call_from_thread(log.write, "[red]Console started with critical startup issues.[/red]")

        self._refresh_history_data()

    # ------------------------------------------------------------------
    # History list management (thread-safe split)
    # ------------------------------------------------------------------

    def _refresh_history_data(self) -> None:
        """Fetch history from Neo4j (runs in a thread) then update UI."""
        try:
            entries = load_history_entries()
        except Exception as exc:
            entries = []
            log = self.query_one("#insights-log", RichLog)
            self.call_from_thread(log.write, f"[red]History load failed: {exc}[/red]")
        self._history_entries = entries
        self.call_from_thread(self._update_history_list_ui, entries)

    def _update_history_list_ui(self, entries: list[dict[str, Any]]) -> None:
        """Must be called on the main thread."""
        history_list = self.query_one("#history-list", ListView)
        history_list.clear()
        self._history_entries = entries
        if not entries:
            history_list.append(ListItem(Static("(no cases found)")))
            return
        for entry in entries:
            created_at = str(entry.get("created_at", "")).strip()[:19]
            label = f"[{entry['id']}] {entry['case_id']}"
            if created_at:
                label += f"  {created_at}"
            history_list.append(ListItem(Static(label)))

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "history-list":
            idx = event.list_view.index
            if idx is not None and 0 <= idx < len(self._history_entries):
                self._selected_entry = self._history_entries[idx]
            else:
                self._selected_entry = None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn == "btn-view":
            self._do_view_report()
        elif btn == "btn-export":
            self._do_export_report()
        elif btn == "btn-delete":
            self._do_delete_entry()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_show_help(self) -> None:
        self.notify(
            "F1 Help | F2 Providers | F3 Run Scan | F4 Full Scan | "
            "F5 Export | F6 View Report | Q Quit"
        )

    def action_show_providers(self) -> None:
        self._fetch_provider_status()

    @work(thread=True)
    def _fetch_provider_status(self) -> None:
        log = self.query_one("#insights-log", RichLog)
        try:
            config = ConfigManager().load()
            statuses = all_provider_status(config)
            self.call_from_thread(log.write, "[bold]Provider Status:[/bold]")
            for s in statuses:
                marker = " [active]" if s["active"] else ""
                color = "green" if s["status"] == "OK" else "red"
                self.call_from_thread(
                    log.write,
                    f"[{color}][{s['status']}][/{color}]{marker} "
                    f"{s['provider']} model={s['model']} — {s['detail']}",
                )
        except Exception as exc:
            self.call_from_thread(log.write, f"[red]Provider status error: {exc}[/red]")

    def action_run_scan(self) -> None:
        self._do_run_scan()

    @work(thread=True)
    def _do_run_scan(self) -> None:
        log = self.query_one("#insights-log", RichLog)
        target_list = self.query_one("#target-list", ListView)
        child = target_list.highlighted_child
        if child is None:
            self.call_from_thread(self.notify, "Select a target file in the Targets tab first.")
            return

        target_name = str(child.query_one(Static).renderable)
        if target_name.startswith("("):
            self.call_from_thread(self.notify, "No valid target file selected.")
            return

        target_path = str(INPUT_DIR / target_name)
        full = self._full_scan

        self.call_from_thread(
            log.write,
            f"[bold]Scanning:[/bold] {target_path}  (full_scan={full})",
        )

        def on_progress(msg: str) -> None:
            self.call_from_thread(log.write, f"[dim]{msg}[/dim]")

        try:
            result = run_scan(target_path, full_scan=full, progress_callback=on_progress)
            self.call_from_thread(
                log.write,
                f"[green]Scan completed.[/green]  Case: {result['case_id']}",
            )
            self.call_from_thread(log.write, f"Entities: {result['entity_stats']}")
            for step in result.get("next_steps", []):
                self.call_from_thread(log.write, f"  → {step}")
            # Reload history in background
            self._refresh_history_data()
        except Exception as exc:
            self.call_from_thread(log.write, f"[red]Scan failed:[/red] {exc}")
            self.call_from_thread(log.write, traceback.format_exc())

    def action_toggle_full_scan(self) -> None:
        self._full_scan = not self._full_scan
        label = "ON" if self._full_scan else "OFF"
        self.notify(f"Full scan mode: {label}")

    def action_view_report(self) -> None:
        self._do_view_report()

    @work(thread=True)
    def _do_view_report(self) -> None:
        log = self.query_one("#insights-log", RichLog)
        entry = self._selected_entry
        if entry is None:
            self.call_from_thread(self.notify, "Select a case in the History tab first.")
            return
        case_id = str(entry["case_id"])
        try:
            snapshot = load_case_snapshot(case_id)
        except Exception as exc:
            self.call_from_thread(log.write, f"[red]Failed to load case: {exc}[/red]")
            return
        if not snapshot or snapshot.get("case") is None:
            self.call_from_thread(
                log.write, f"[yellow]No case data found for: {case_id}[/yellow]"
            )
            return
        report = render_report_text(entry, snapshot)
        self.call_from_thread(log.write, f"[bold]Report — {case_id}:[/bold]")
        for line in report.splitlines():
            self.call_from_thread(log.write, line)

    def action_export_report(self) -> None:
        self._do_export_report()

    @work(thread=True)
    def _do_export_report(self) -> None:
        log = self.query_one("#insights-log", RichLog)
        entry = self._selected_entry
        if entry is None:
            self.call_from_thread(self.notify, "Select a case in the History tab first.")
            return
        fmt_widget = self.query_one("#export-fmt", Input)
        fmt = fmt_widget.value.strip().lower() or "md"
        if fmt not in EXPORT_FORMATS:
            self.call_from_thread(
                log.write,
                f"[yellow]Unknown format '{fmt}'. Use: {', '.join(EXPORT_FORMATS)}[/yellow]",
            )
            return
        try:
            ok, result = export_case_report(entry, fmt)
            if ok:
                self.call_from_thread(log.write, f"[green]Exported:[/green] {result}")
            else:
                self.call_from_thread(log.write, f"[red]Export failed:[/red] {result}")
        except Exception as exc:
            self.call_from_thread(log.write, f"[red]Export error:[/red] {exc}")

    @work(thread=True)
    def _do_delete_entry(self) -> None:
        log = self.query_one("#insights-log", RichLog)
        entry = self._selected_entry
        if entry is None:
            self.call_from_thread(self.notify, "Select a case in the History tab first.")
            return
        case_id = str(entry["case_id"])
        try:
            ok = delete_history_entry(entry)
            if ok:
                self.call_from_thread(log.write, f"[green]Deleted:[/green] {case_id}")
                self._selected_entry = None
                self._refresh_history_data()
            else:
                self.call_from_thread(log.write, f"[red]Could not delete:[/red] {case_id}")
        except Exception as exc:
            self.call_from_thread(log.write, f"[red]Delete error:[/red] {exc}")


def main() -> None:
    ArgosTUI().run()


if __name__ == "__main__":
    main()

