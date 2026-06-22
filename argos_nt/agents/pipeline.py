from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from argos_nt.agents.analyst_agent import AnalystAgent
from argos_nt.agents.architect_agent import ArchitectAgent
from argos_nt.agents.parser_agent import ModuleParser
from argos_nt.agents.scout_agent import ScoutAgent
from argos_nt.agents.sifter_agent import SifterAgent
from argos_nt.config_manager import ConfigManager
from argos_nt.core.provider_service import check_active_provider
from argos_nt.drivers.neo4j_driver import Neo4jConnectionParams, Neo4jDriver
from argos_nt.drivers.provider_manager import ProviderManager


class InvestigationPipeline:
    """End-to-end ingestion pipeline: file -> entities -> tools -> graph."""

    def ingest_text(
        self,
        content: str,
        case_name: str = "manual_case",
        full_scan: bool = False,
        progress_callback: Callable[[str], None] | None = None,
        tool_filter: list[str] | None = None,
        existing_case_id: str | None = None,
    ) -> dict[str, Any]:
        def emit(message: str) -> None:
            if progress_callback is not None:
                progress_callback(message)

        emit("Validating active AI provider...")
        provider_status, provider_detail = check_active_provider(self.config)
        if provider_status == "ERR":
            raise RuntimeError(
                "Active provider is not ready for scanning: "
                f"{provider_detail}. Update provider settings and try again."
            )

        emit("Extracting entities...")
        entities_obj = self.sifter.extract(content)
        entities = self.sifter.as_dict(entities_obj)

        emit("Creating case node in Neo4j...")
        if existing_case_id:
            case_id = self.graph.ensure_case(
                case_id=existing_case_id,
                case_name=case_name,
                source_file="manual_input",
            )
        else:
            case_id = self.graph.create_case(case_name=case_name, source_file="manual_input")

        emit("Persisting entities in Neo4j...")
        entity_stats = self.analyst.persist_entities(case_id, entities)

        emit("Running OSINT tools...")
        tool_results = self.scout.run(
            entities,
            full_scan=full_scan,
            progress_callback=progress_callback,
            tool_filter=tool_filter,
        )

        emit("Persisting tool findings in Neo4j...")
        self.analyst.persist_tool_results(case_id, tool_results, parser=self.parser)

        emit("Planning next investigation steps...")
        next_steps = self.architect.plan_next_steps(entities, tool_results)

        emit("Collecting case graph snapshot...")
        case_map = self.graph.get_case_map(case_id)

        emit("Pipeline completed.")

        return {
            "case_id": case_id,
            "source": "manual_input",
            "entities": entities,
            "entity_stats": entity_stats,
            "tool_results": [
                {
                    "tool": item.tool,
                    "target": item.target,
                    "ok": item.ok,
                    "output": item.output,
                }
                for item in tool_results
            ],
            "next_steps": next_steps,
            "graph_snapshot": case_map,
        }

    def __init__(self, config_manager: ConfigManager | None = None) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.config = self.config_manager.load()

        self.provider_manager = ProviderManager(self.config)

        params = Neo4jConnectionParams(
            uri=self.config.neo4j.uri,
            username=self.config.neo4j.username,
            password=self.config.neo4j.password,
            database=self.config.neo4j.database,
        )
        self.graph = Neo4jDriver(params)

        self.sifter = SifterAgent(self.provider_manager, prefer_llm=False)
        self.scout = ScoutAgent()
        self.analyst = AnalystAgent(self.graph)
        self.architect = ArchitectAgent()
        # ModuleParser: use_llm=False keeps it fast; set True to enable LLM enrichment
        self.parser = ModuleParser(provider_manager=self.provider_manager, use_llm=False)

    def close(self) -> None:
        self.graph.close()

    def ingest_file(
        self,
        file_path: str | Path,
        full_scan: bool = False,
        progress_callback: Callable[[str], None] | None = None,
        tool_filter: list[str] | None = None,
        existing_case_id: str | None = None,
    ) -> dict[str, Any]:
        def emit(message: str) -> None:
            if progress_callback is not None:
                progress_callback(message)

        path = Path(file_path)
        emit("Validating input path...")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        emit("Validating active AI provider...")
        provider_status, provider_detail = check_active_provider(self.config)
        if provider_status == "ERR":
            raise RuntimeError(
                "Active provider is not ready for scanning: "
                f"{provider_detail}. Update provider settings and try again."
            )

        emit("Reading input file...")
        content = path.read_text(encoding="utf-8")

        emit("Extracting entities...")
        entities_obj = self.sifter.extract(content)
        entities = self.sifter.as_dict(entities_obj)

        emit("Creating case node in Neo4j...")
        if existing_case_id:
            case_id = self.graph.ensure_case(
                case_id=existing_case_id,
                case_name=path.stem,
                source_file=str(path),
            )
        else:
            case_id = self.graph.create_case(case_name=path.stem, source_file=str(path))

        emit("Persisting entities in Neo4j...")
        entity_stats = self.analyst.persist_entities(case_id, entities)

        emit("Running OSINT tools...")
        tool_results = self.scout.run(
            entities,
            full_scan=full_scan,
            progress_callback=progress_callback,
            tool_filter=tool_filter,
        )

        emit("Persisting tool findings in Neo4j...")
        self.analyst.persist_tool_results(case_id, tool_results, parser=self.parser)

        emit("Planning next investigation steps...")
        next_steps = self.architect.plan_next_steps(entities, tool_results)

        emit("Collecting case graph snapshot...")
        case_map = self.graph.get_case_map(case_id)

        emit("Pipeline completed.")

        return {
            "case_id": case_id,
            "source": str(path),
            "entities": entities,
            "entity_stats": entity_stats,
            "tool_results": [
                {
                    "tool": item.tool,
                    "target": item.target,
                    "ok": item.ok,
                    "output": item.output,
                }
                for item in tool_results
            ],
            "next_steps": next_steps,
            "graph_snapshot": case_map,
        }
