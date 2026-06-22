from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse

from argos_nt.tools.tool_executor import ToolExecutor, ToolResult


PUBLIC_EMAIL_DOMAINS: set[str] = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "yahoo.com.br",
    "icloud.com",
    "me.com",
    "mac.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "gmx.com",
    "gmx.de",
    "aol.com",
    "yandex.com",
    "yandex.ru",
    "mail.com",
    "zoho.com",
    "uol.com.br",
    "bol.com.br",
    "terra.com.br",
    "qq.com",
}


class ScoutAgent:
    """Runs OSINT tools for extracted entities."""

    def __init__(self, executor: ToolExecutor | None = None) -> None:
        self.executor = executor or ToolExecutor()

    def run(
        self,
        entities: dict[str, list[str]],
        full_scan: bool = False,
        progress_callback: Callable[[str], None] | None = None,
        tool_filter: list[str] | None = None,
    ) -> list[ToolResult]:
        """
        Run OSINT tools for the given entities.

        Args:
            entities: Extracted entity dict (emails, phones, usernames, …).
            full_scan: When True, activates full-scan-scope tools.
            progress_callback: Optional callback for progress messages.
            tool_filter: When provided, only tools whose canonical name appears
                         in this list will run.  Pass None to run all.
        """
        results: list[ToolResult] = []

        def _allowed(tool_name: str) -> bool:
            return tool_filter is None or tool_name in tool_filter

        def emit(message: str) -> None:
            if progress_callback is not None:
                progress_callback(message)

        emails = entities.get("emails", [])
        phones = entities.get("phones", [])
        persons = entities.get("persons", [])
        usernames = entities.get("usernames", [])
        urls = entities.get("urls", [])

        dork_plan = self._build_dork_plan(persons=persons, emails=emails, usernames=usernames)
        dork_queries = [item["query"] for item in dork_plan]
        if dork_plan:
            emit(f"Generated {len(dork_queries)} dork queries from extracted people/emails/usernames")
            for item in dork_plan:
                emit(f"Dork query [{item['category']}]: {item['query']}")
            artifact_prefix = self._build_dork_artifact_prefix(persons=persons, emails=emails, usernames=usernames)
            artifact_path = self.executor.write_text_artifact(
                prefix=artifact_prefix,
                content="\n".join(dork_queries),
            )
            json_artifact_path = self.executor.write_json_artifact(
                prefix=f"{artifact_prefix}_structured",
                payload={
                    "queries": dork_plan,
                    "inputs": {
                        "persons": persons,
                        "emails": emails,
                        "usernames": usernames,
                    },
                },
            )
            emit(f"Dork plan written to {artifact_path}")
            emit(f"Structured dork plan written to {json_artifact_path}")
            results.append(
                self.executor.build_virtual_result(
                    tool="dork-queries",
                    target="generated-plan",
                    output=(
                        f"Saved TXT plan to {artifact_path}\n"
                        f"Saved JSON plan to {json_artifact_path}\n\n" + "\n".join(dork_queries)
                    ),
                )
            )
            if _allowed("google-dorks") and self.executor.has_tool("google_dorks", "google-dorks"):
                for query in dork_queries:
                    emit(f"Dispatching google-dorks for query '{query}'")
                    results.append(self.executor.run_google_dorks(query, progress_callback=progress_callback))
            else:
                emit("google-dorks: tool not available, keeping generated query plan only")

            if (full_scan or _allowed("pagodo")) and _allowed("pagodo") and self.executor.has_tool("pagodo"):
                for query in dork_queries:
                    emit(f"Dispatching pagodo for query '{query}'")
                    results.append(self.executor.run_pagodo(query, progress_callback=progress_callback))
            elif full_scan and _allowed("pagodo"):
                emit("pagodo: tool not available, skipping execution")

            if (full_scan or _allowed("dork-cli")) and _allowed("dork-cli") and self.executor.has_tool("dork-cli", "dork_cli"):
                for query in dork_queries:
                    emit(f"Dispatching dork-cli for query '{query}'")
                    results.append(self.executor.run_dork_cli(query, progress_callback=progress_callback))
            elif full_scan and _allowed("dork-cli"):
                emit("dork-cli: tool not available, skipping execution")

        domain_targets = self._collect_domain_targets(emails=emails, urls=urls)
        if domain_targets and (full_scan or _allowed("s3scanner")) and _allowed("s3scanner"):
            if self.executor.has_tool("s3scanner"):
                for domain in domain_targets:
                    emit(f"Dispatching s3scanner for domain '{domain}'")
                    results.append(self.executor.run_s3scanner(domain, progress_callback=progress_callback))
            else:
                emit("s3scanner: tool not available, skipping execution")

        for email in emails:
            if _allowed("holehe"):
                emit(f"Dispatching holehe for email '{email}'")
                results.append(self.executor.run_holehe(email, progress_callback=progress_callback))
            if _allowed("leaker"):
                emit(f"Dispatching leaker for email '{email}'")
                results.append(self.executor.run_leaker_email(email, progress_callback=progress_callback))
            if self.executor.has_tool("ghunt") and self.executor.has_ghunt_session():
                if _allowed("ghunt"):
                    emit(f"Dispatching ghunt for email '{email}'")
                    results.append(self.executor.run_ghunt_email(email, progress_callback=progress_callback))
            elif self.executor.has_tool("ghunt"):
                emit("ghunt: installed but no active session; run 'ghunt login' to enable")
            else:
                emit("ghunt: tool not available, skipping execution")
            if (full_scan or _allowed("h8mail")) and _allowed("h8mail"):
                emit(f"Dispatching h8mail for email '{email}'")
                results.append(self.executor.run_h8mail(email, progress_callback=progress_callback))

        for username in usernames:
            if _allowed("sherlock"):
                emit(f"Dispatching sherlock for username '{username}'")
                results.append(self.executor.run_sherlock(username, progress_callback=progress_callback))
            if _allowed("leaker"):
                emit(f"Dispatching leaker for username '{username}'")
                results.append(self.executor.run_leaker_username(username, progress_callback=progress_callback))
            if _allowed("maigret") and self.executor.has_tool("maigret"):
                emit(f"Dispatching maigret for username '{username}'")
                results.append(self.executor.run_maigret(username, progress_callback=progress_callback))
            elif not _allowed("maigret"):
                pass
            else:
                emit("maigret: tool not available, skipping execution")

            if _allowed("toutatis") and self.executor.has_tool("toutatis"):
                emit(f"Dispatching toutatis for username '{username}'")
                results.append(self.executor.run_toutatis(username, progress_callback=progress_callback))
            elif _allowed("toutatis"):
                emit("toutatis: tool not available, skipping execution")

            if (full_scan or _allowed("socialscan")) and _allowed("socialscan"):
                emit(f"Dispatching socialscan for username '{username}'")
                results.append(self.executor.run_socialscan(username, progress_callback=progress_callback))

        for phone in phones:
            if _allowed("leaker"):
                emit(f"Dispatching leaker for phone '{phone}'")
                results.append(self.executor.run_leaker_phone(phone, progress_callback=progress_callback))

            if _allowed("ignorant") and self.executor.has_tool("ignorant"):
                emit(f"Dispatching ignorant for phone '{phone}'")
                results.append(self.executor.run_ignorant(phone, progress_callback=progress_callback))
            elif _allowed("ignorant"):
                emit("ignorant: tool not available, skipping execution")

            if _allowed("whatspy") and self.executor.has_tool("whatspy", "whatsspy", "whats-spy"):
                emit(f"Dispatching whatspy for phone '{phone}'")
                results.append(self.executor.run_whatspy(phone, progress_callback=progress_callback))
            elif _allowed("whatspy"):
                emit("whatspy: tool not available, skipping execution")

        return results

    def _build_dork_plan(self, persons: list[str], emails: list[str], usernames: list[str]) -> list[dict[str, Any]]:
        plan: list[dict[str, Any]] = []

        for person in persons:
            normalized_person = person.strip()
            if not normalized_person:
                continue
            plan.append({
                "category": "professional-profile",
                "entity_type": "person",
                "value": normalized_person,
                "query": f'site:linkedin.com/in/ OR site:drive.google.com "{normalized_person}" filetype:pdf',
            })
            plan.append({
                "category": "identifiers-leak",
                "entity_type": "person",
                "value": normalized_person,
                "query": f'"{normalized_person}" ("CPF" OR "RG" OR "passaporte") (filetype:pdf OR filetype:xlsx)',
            })
            plan.append({
                "category": "legal-mentions",
                "entity_type": "person",
                "value": normalized_person,
                "query": f'(site:jusbrasil.com.br OR site:jus.br) "{normalized_person}"',
            })

        for email in emails:
            normalized_email = email.strip()
            if not normalized_email:
                continue
            plan.append({
                "category": "email-exposure",
                "entity_type": "email",
                "value": normalized_email,
                "query": f'intext:"{normalized_email}" (site:pastebin.com OR site:github.com)',
            })
            plan.append({
                "category": "document-exposure",
                "entity_type": "email",
                "value": normalized_email,
                "query": f'intext:"{normalized_email}" (site:scribd.com OR site:drive.google.com)',
            })

        for username in usernames:
            normalized_username = username.strip()
            if not normalized_username:
                continue
            plan.append({
                "category": "social-presence",
                "entity_type": "username",
                "value": normalized_username,
                "query": f'(site:github.com OR site:x.com OR site:reddit.com OR site:instagram.com) "{normalized_username}"',
            })
            plan.append({
                "category": "username-exposure",
                "entity_type": "username",
                "value": normalized_username,
                "query": f'intext:"{normalized_username}" (site:pastebin.com OR site:github.com)',
            })

        deduplicated: list[dict[str, Any]] = []
        seen_queries: set[str] = set()
        for item in plan:
            query = str(item["query"])
            if query in seen_queries:
                continue
            seen_queries.add(query)
            deduplicated.append(item)
        return deduplicated

    def _build_dork_artifact_prefix(self, persons: list[str], emails: list[str], usernames: list[str]) -> str:
        if persons:
            return f"dorks_{persons[0]}"
        if usernames:
            return f"dorks_{usernames[0]}"
        if emails:
            return f"dorks_{emails[0].split('@', 1)[0]}"
        return "dorks_plan"

    def _collect_domain_targets(self, emails: list[str], urls: list[str]) -> list[str]:
        domains: list[str] = []

        for email in emails:
            if "@" in email:
                domain = email.split("@", 1)[1].strip().lower()
                if domain and domain not in PUBLIC_EMAIL_DOMAINS:
                    domains.append(domain)

        for url in urls:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").strip().lower()
            if hostname:
                domains.append(hostname)

        return list(dict.fromkeys(domain for domain in domains if domain))
