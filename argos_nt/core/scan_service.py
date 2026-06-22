from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from argos_nt.agents.pipeline import InvestigationPipeline


def run_scan(
    target_file: str | Path,
    full_scan: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    tool_filter: list[str] | None = None,
    existing_case_id: str | None = None,
) -> dict[str, Any]:
    """
    Ingest a target file through the investigation pipeline.

    Creates its own InvestigationPipeline instance and closes it on exit.
    Returns the pipeline result dict (case_id, entity_stats, tool_results, next_steps, graph_snapshot).
    """
    pipeline = InvestigationPipeline()
    try:
        return pipeline.ingest_file(
            target_file,
            full_scan=full_scan,
            progress_callback=progress_callback,
            tool_filter=tool_filter,
            existing_case_id=existing_case_id,
        )
    finally:
        pipeline.close()
