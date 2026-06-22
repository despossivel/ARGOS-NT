from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase


@dataclass(slots=True)
class Neo4jConnectionParams:
    uri: str
    username: str
    password: str
    database: str = "neo4j"


class Neo4jDriver:
    """Light wrapper around the official Neo4j driver for graph operations."""

    def __init__(self, params: Neo4jConnectionParams) -> None:
        self._database = params.database
        self._driver = GraphDatabase.driver(
            params.uri,
            auth=(params.username, params.password),
        )

    def close(self) -> None:
        self._driver.close()

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def create_case(self, case_name: str, source_file: str) -> str:
        case_id = f"case::{case_name}::{int(datetime.now(tz=timezone.utc).timestamp())}"
        query = """
        MERGE (c:Case {id: $case_id})
        ON CREATE SET c.name = $case_name, c.source_file = $source_file, c.created_at = datetime()
        ON MATCH SET c.last_seen_at = datetime()
        RETURN c.id AS case_id
        """
        record = self._execute_write(query, case_id=case_id, case_name=case_name, source_file=source_file)
        return str(record["case_id"])

    def ensure_case(self, case_id: str, case_name: str, source_file: str) -> str:
        query = """
        MERGE (c:Case {id: $case_id})
        ON CREATE SET c.name = $case_name, c.source_file = $source_file, c.created_at = datetime()
        ON MATCH SET c.name = $case_name, c.source_file = $source_file, c.last_seen_at = datetime()
        RETURN c.id AS case_id
        """
        record = self._execute_write(query, case_id=case_id, case_name=case_name, source_file=source_file)
        return str(record["case_id"])

    def upsert_entity(
        self,
        entity_type: str,
        properties: dict[str, Any],
        unique_key: str = "value",
    ) -> dict[str, Any]:
        if unique_key not in properties:
            raise ValueError(f"Missing unique key '{unique_key}' for {entity_type}")

        query = f"""
        MERGE (e:{entity_type} {{{unique_key}: $unique_value}})
        ON CREATE SET e += $all_props, e.created_at = datetime()
        ON MATCH SET e += $all_props, e.last_seen_at = datetime()
        RETURN e
        """
        record = self._execute_write(
            query,
            unique_value=properties[unique_key],
            all_props=properties,
        )
        return dict(record["e"])

    def link_case_to_entity(self, case_id: str, entity_type: str, unique_key: str, unique_value: str) -> None:
        query = f"""
        MATCH (c:Case {{id: $case_id}})
        MATCH (e:{entity_type} {{{unique_key}: $unique_value}})
        MERGE (c)-[:HAS_ENTITY]->(e)
        """
        self._execute_write(query, case_id=case_id, unique_value=unique_value)

    def create_relation(
        self,
        source_type: str,
        source_key: str,
        source_value: str,
        target_type: str,
        target_key: str,
        target_value: str,
        relation_type: str,
    ) -> None:
        query = f"""
        MATCH (s:{source_type} {{{source_key}: $source_value}})
        MATCH (t:{target_type} {{{target_key}: $target_value}})
        MERGE (s)-[r:{relation_type}]->(t)
        ON CREATE SET r.created_at = datetime()
        """
        self._execute_write(
            query,
            source_value=source_value,
            target_value=target_value,
        )

    def _finding_fingerprint(
        self,
        case_id: str,
        tool: str,
        summary: str,
        structured_json: str | None = None,
    ) -> str:
        payload = {
            "case_id": case_id,
            "tool": tool,
            "summary": summary,
            "structured_data": structured_json or "",
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def create_finding(self, case_id: str, tool: str, summary: str) -> None:
        fingerprint = self._finding_fingerprint(case_id, tool, summary)
        query = """
        MATCH (c:Case {id: $case_id})
        MERGE (f:Finding {fingerprint: $fingerprint})
        ON CREATE SET
          f.id = randomUUID(),
          f.tool = $tool,
          f.summary = $summary,
          f.created_at = datetime()
        ON MATCH SET
          f.last_seen_at = datetime()
        MERGE (c)-[:HAS_FINDING]->(f)
        """
        self._execute_write(
            query,
            case_id=case_id,
            tool=tool,
            summary=summary,
            fingerprint=fingerprint,
        )

    def create_structured_finding(
        self,
        case_id: str,
        tool: str,
        summary: str,
        structured_data: dict[str, Any],
    ) -> None:
        """Persist a Finding node with deduplication by case/tool/structured payload."""
        structured_json = json.dumps(structured_data, ensure_ascii=False, sort_keys=True)
        fingerprint = self._finding_fingerprint(case_id, tool, summary, structured_json)
        query = """
        MATCH (c:Case {id: $case_id})
        MERGE (f:Finding {fingerprint: $fingerprint})
        ON CREATE SET
          f.id = randomUUID(),
          f.tool = $tool,
          f.summary = $summary,
          f.structured_data = $structured_json,
          f.created_at = datetime()
        ON MATCH SET
          f.summary = $summary,
          f.last_seen_at = datetime()
        MERGE (c)-[:HAS_FINDING]->(f)
        """
        self._execute_write(
            query,
            case_id=case_id,
            tool=tool,
            summary=summary,
            structured_json=structured_json,
            fingerprint=fingerprint,
        )

    def get_case_map(self, case_id: str) -> dict[str, Any]:
        query = """
        MATCH (c:Case {id: $case_id})
        OPTIONAL MATCH (c)-[:HAS_ENTITY]->(e)
        OPTIONAL MATCH (c)-[:HAS_FINDING]->(f)
        RETURN c, collect(DISTINCT e) AS entities, collect(DISTINCT f) AS findings
        """
        record = self._execute_read(query, case_id=case_id)
        if record is None:
            return {"case": None, "entities": [], "findings": []}

        findings_raw = [dict(item) for item in record["findings"] if item]
        # Deserialise structured_data JSON stored as string
        findings: list[dict[str, Any]] = []
        for f in findings_raw:
            sd = f.get("structured_data")
            if isinstance(sd, str):
                try:
                    f["structured_data"] = json.loads(sd)
                except Exception:
                    f["structured_data"] = {}
            else:
                f.setdefault("structured_data", {})
            findings.append(f)

        return {
            "case": dict(record["c"]) if record["c"] else None,
            "entities": [dict(item) for item in record["entities"] if item],
            "findings": findings,
        }

    def list_cases(self, limit: int = 200) -> list[dict[str, Any]]:
        query = """
        MATCH (c:Case)
        RETURN c
        ORDER BY coalesce(c.created_at, c.last_seen_at) DESC
        LIMIT $limit
        """
        records = self._execute_read_all(query, limit=limit)
        items: list[dict[str, Any]] = []
        for record in records:
            case_obj = record.get("c")
            if not case_obj:
                continue
            case = dict(case_obj)
            items.append(
                {
                    "case_id": str(case.get("id", "")),
                    "name": str(case.get("name", "")),
                    "source_file": str(case.get("source_file", "")),
                    "created_at": str(case.get("created_at", "")),
                    "last_seen_at": str(case.get("last_seen_at", "")),
                }
            )
        return items

    def update_case_source_file(self, case_id: str, source_file: str) -> bool:
        query = """
        MATCH (c:Case {id: $case_id})
        SET c.source_file = $source_file,
            c.last_seen_at = datetime()
        RETURN c.id AS case_id
        """
        record = self._execute_write(query, case_id=case_id, source_file=source_file)
        return record is not None

    def delete_case(self, case_id: str) -> bool:
        query = """
        MATCH (c:Case {id: $case_id})
        OPTIONAL MATCH (c)-[:HAS_FINDING]->(f:Finding)
        WITH c, collect(f) AS findings
        FOREACH (item IN findings | DETACH DELETE item)
        DETACH DELETE c
        RETURN true AS deleted
        """
        record = self._execute_write(query, case_id=case_id)
        return bool(record and record.get("deleted"))

    def _execute_write(self, query: str, **params: Any):
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return result.single()

    def _execute_read(self, query: str, **params: Any):
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return result.single()

    def _execute_read_all(self, query: str, **params: Any) -> list[Any]:
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return list(result)
