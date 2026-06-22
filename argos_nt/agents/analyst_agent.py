from __future__ import annotations

from typing import TYPE_CHECKING, Any

from argos_nt.drivers.neo4j_driver import Neo4jDriver
from argos_nt.tools.tool_executor import ToolResult

if TYPE_CHECKING:
    from argos_nt.agents.parser_agent import ModuleParser


class AnalystAgent:
    """Correlates extracted data and persists it into Neo4j."""

    def __init__(self, graph: Neo4jDriver) -> None:
        self.graph = graph

    def persist_entities(self, case_id: str, entities: dict[str, list[str]]) -> dict[str, int]:
        counters: dict[str, int] = {}

        mapping = {
            "emails": ("Email", "value"),
            "usernames": ("Username", "value"),
            "persons": ("Person", "value"),
            "organizations": ("Organization", "value"),
            "phones": ("Phone", "value"),
            "urls": ("Url", "value"),
            "locations": ("Location", "value"),
        }

        for key, values in entities.items():
            node_type, unique_key = mapping.get(key, (None, None))
            if node_type is None:
                continue

            count = 0
            for value in values:
                if not str(value).strip():
                    continue
                self.graph.upsert_entity(node_type, {unique_key: str(value).strip()})
                self.graph.link_case_to_entity(case_id, node_type, unique_key, str(value).strip())
                count += 1
            counters[key] = count

        self._connect_related_entities(entities)
        return counters

    def persist_tool_results(
        self,
        case_id: str,
        results: list[ToolResult],
        parser: ModuleParser | None = None,
    ) -> None:
        """
        Persist tool findings in Neo4j.

        When a ModuleParser is provided, each raw output is parsed into a
        structured dict and saved with create_structured_finding so that the
        report layer can display concrete findings (passwords, accounts, etc.)
        without losing data to 300-char truncation.
        """
        for result in results:
            if parser and result.output:
                structured = parser.parse(result.tool, result.output, target=result.target)
                summary = parser.human_summary(structured)
                self.graph.create_structured_finding(
                    case_id=case_id,
                    tool=result.tool,
                    summary=summary,
                    structured_data=structured,
                )
                continue

            summary = f"{result.tool} em {result.target}: {'OK' if result.ok else 'FAIL'}"
            # Fallback still avoids raw terminal persistence.
            self.graph.create_finding(case_id, result.tool, summary)

    def _connect_related_entities(self, entities: dict[str, list[str]]) -> None:
        emails = entities.get("emails", [])
        usernames = entities.get("usernames", [])

        for email in emails:
            for username in usernames:
                self.graph.create_relation(
                    source_type="Email",
                    source_key="value",
                    source_value=email,
                    target_type="Username",
                    target_key="value",
                    target_value=username,
                    relation_type="POSSIBLY_LINKED",
                )
