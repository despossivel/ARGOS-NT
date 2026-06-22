"""ModuleParser - strict terminal-output sanitiser and structured extractor."""
from __future__ import annotations

import json
import re
from typing import Any

from argos_nt.drivers.provider_manager import ProviderManager


class ModuleParser:
    """
    Parses raw OSINT tool output into a structured dict.

    Usage:
        parser = ModuleParser()
        result = parser.parse("holehe", raw_output, target="victim@example.com")
    """

    def __init__(
        self,
        provider_manager: ProviderManager | None = None,
        use_llm: bool = False,
    ) -> None:
        self.provider_manager = provider_manager
        self.use_llm = use_llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, tool: str, raw_output: str, target: str = "") -> dict[str, Any]:
        """
        Parse raw tool output into a structured findings dict.

        The sanitiser and regex extractor always run first (deterministic, zero latency).
        If use_llm=True, a second pass tries to enrich anything the regex missed.
        """
        tool_key = tool.lower().replace("-", "_").replace(" ", "_")
        clean_output = self._sanitize_output(raw_output)

        structured = self._extract_regex(tool_key, clean_output, target)

        if self.use_llm and self.provider_manager:
            try:
                enriched = self._extract_llm(tool_key, clean_output, structured)
                # Only add keys not already present or that add new list items
                for k, v in enriched.items():
                    if k not in structured:
                        structured[k] = v
                    elif isinstance(v, list) and isinstance(structured[k], list):
                        existing = {json.dumps(i, sort_keys=True) for i in structured[k]}
                        for item in v:
                            if json.dumps(item, sort_keys=True) not in existing:
                                structured[k].append(item)
            except Exception:
                pass  # LLM failure must never block the pipeline

        return structured

    def _sanitize_output(self, raw_output: str) -> str:
        """Remove terminal UI noise and keep only data-candidate lines."""
        noise_patterns = (
            r"^\s*$",
            r"^\s*[\|/\\\-]{2,}\s*$",                    # spinners
            r"^\s*\[[#=\-\s>]{3,}\]\s*$",               # progress bars [###---]
            r"^\s*(loading|processing|initializing|starting)\b",
            r"^\s*(warning|warn|error|timeout|timed out|connection reset|network error)\b",
            r"^\s*traceback\b",
            r"^\s*\+[-=]{3,}\+\s*$",                      # ascii borders
            r"^\s*[=_\-*]{6,}\s*$",                        # separators
            r"^\s*\x1b\[[0-9;]*m",                         # ansi fragments
        )

        cleaned: list[str] = []
        for line in raw_output.splitlines():
            plain = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            if any(re.search(pat, plain, re.IGNORECASE) for pat in noise_patterns):
                continue
            cleaned.append(plain)
        return "\n".join(cleaned)

    def human_summary(self, structured: dict[str, Any]) -> str:
        """One-line human-readable summary for a Finding node."""
        dtype = structured.get("type", "generic")
        target = structured.get("target", "?")

        if dtype == "account_check":
            n = structured.get("total_found", 0)
            return f"Account check on {target}: {n} site(s) registered"

        if dtype == "credential_leak":
            n = structured.get("total_found", 0)
            has = structured.get("has_credentials", False)
            pwd_info = " (passwords exposed)" if has else ""
            return f"Credential leak on {target}: {n} breach(es) found{pwd_info}"

        if dtype == "username_search":
            n = structured.get("total_found", 0)
            return f"Username search for {target}: {n} profile(s) found"

        if dtype == "phone_check":
            sites = structured.get("registered_sites", [])
            wa = structured.get("whatsapp_registered")
            if wa is not None:
                return f"Phone check on {target}: WhatsApp={'yes' if wa else 'no'}"
            return f"Phone check on {target}: {len(sites)} service(s) registered"

        if dtype == "google_account":
            name = structured.get("name", "unknown")
            return f"Google account for {target}: name={name}"

        if dtype == "instagram_account":
            followers = structured.get("followers")
            name = structured.get("name", "unknown")
            return f"Instagram for {target}: {name}, {followers} followers"

        if dtype == "google_dork_search":
            n = structured.get("total_results", 0)
            return f"Google dork search '{target}': {n} URL(s) found"

        return f"Tool output for {target}"

    # ------------------------------------------------------------------
    # Regex extraction dispatcher
    # ------------------------------------------------------------------

    def _extract_regex(self, tool: str, raw: str, target: str) -> dict[str, Any]:
        parsers = {
            "holehe": self._parse_holehe,
            "h8mail": self._parse_h8mail,
            "leaker": self._parse_leaker,
            "leaker_email": self._parse_leaker,
            "leaker_username": self._parse_leaker,
            "sherlock": self._parse_sherlock,
            "maigret": self._parse_maigret,
            "ignorant": self._parse_ignorant,
            "whatspy": self._parse_whatspy,
            "whatsspy": self._parse_whatspy,
            "ghunt": self._parse_ghunt,
            "ghunt_email": self._parse_ghunt,
            "toutatis": self._parse_toutatis,
            "socialscan": self._parse_socialscan,
            "google_dorks": self._parse_google_dorks,
            "pagodo": self._parse_google_dorks,
            "dork_cli": self._parse_google_dorks,
        }
        fn = parsers.get(tool)
        if fn:
            return fn(raw, target)
        return self._parse_generic(raw, target)

    # ------------------------------------------------------------------
    # Tool-specific regex parsers
    # ------------------------------------------------------------------

    def _parse_holehe(self, raw: str, target: str) -> dict[str, Any]:
        accounts: list[dict[str, str]] = []

        for line in raw.splitlines():
            # Only explicit positives are accepted.
            if re.search(r"^\s*\[\+\]", line):
                m = re.search(r"\[\+\]\s+(.+?)(?:\s+\[|\s*$)", line)
                if m:
                    site = m.group(1).strip().lower()
                    if "." in site and not any(item["site"] == site for item in accounts):
                        accounts.append({"site": site, "status": "exists"})

        return {
            "type": "account_check",
            "target": target,
            "accounts": accounts,
            "total_found": len(accounts),
        }

    def _parse_h8mail(self, raw: str, target: str) -> dict[str, Any]:
        leaks: list[dict[str, str]] = []
        current_source: str = ""

        for line in raw.splitlines():
            if re.search(r"\b(starting|banner|version|usage|loaded|initiali[sz]ing)\b", line, re.IGNORECASE):
                continue

            # Detect source/breach name
            src_m = re.search(
                r"(?:source|breach|leak|from|database)[:\s]+([^\n\|]+)",
                line, re.IGNORECASE,
            )
            if src_m:
                current_source = src_m.group(1).strip()

            # Detect password field
            pwd_m = re.search(
                r"(?:password|pass|pwd|mdp|senha)[:\s]+([^\s\|,\n]{3,})",
                line, re.IGNORECASE,
            )
            if pwd_m:
                pwd = pwd_m.group(1).strip()
                if pwd.lower() not in ("n/a", "null", "none", "-", "empty", ""):
                    item = {
                        "source": current_source or "unknown",
                        "password": pwd,
                    }
                    if not any(x["source"] == item["source"] and x["password"] == item["password"] for x in leaks):
                        leaks.append(item)

            # Pipe-separated lines: email|hash|password|source
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                # h8mail sometimes outputs: email | password | hash | source
                for i, part in enumerate(parts):
                    if re.match(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", part):
                        # Next non-empty parts could be password
                        remaining = [p for p in parts[i + 1:] if p and len(p) >= 4]
                        if remaining:
                            pwd = remaining[0]
                            if pwd.lower() not in ("n/a", "null", "none", "-"):
                                if not any(b["password"] == pwd for b in leaks):
                                    leaks.append({
                                        "source": current_source or "pipe-separated",
                                        "password": pwd,
                                    })
                        break

        return {
            "type": "credential_leak",
            "target": target,
            "leaks": leaks,
            "total_found": len(leaks),
            "has_credentials": len(leaks) > 0,
        }

    def _parse_leaker(self, raw: str, target: str) -> dict[str, Any]:
        leaks: list[dict[str, str]] = []

        for line in raw.splitlines():
            pwd_m = re.search(
                r"(?:password|pass|pwd)[:\s]+([^\s\|,\n]{3,})", line, re.IGNORECASE
            )
            src_m = re.search(
                r"(?:source|from|database|db)[:\s]+([^\n\|,]{3,})", line, re.IGNORECASE
            )
            if pwd_m:
                leaks.append({
                    "password": pwd_m.group(1).strip(),
                    "source": src_m.group(1).strip() if src_m else "unknown",
                })

        return {
            "type": "credential_leak",
            "target": target,
            "leaks": leaks,
            "total_found": len(leaks),
            "has_credentials": len(leaks) > 0,
        }

    def _parse_sherlock(self, raw: str, target: str) -> dict[str, Any]:
        profiles: list[dict[str, str]] = []

        for line in raw.splitlines():
            if re.search(r"\[\+\]", line):
                url_m = re.search(r"https?://\S+", line)
                if url_m:
                    url = url_m.group(0)
                    if not any(p["url"] == url for p in profiles):
                        profiles.append({"url": url, "status": "found"})

        return {
            "type": "username_search",
            "target": target,
            "profiles": profiles,
            "total_found": len(profiles),
        }

    def _parse_maigret(self, raw: str, target: str) -> dict[str, Any]:
        profiles: list[dict[str, str]] = []

        for line in raw.splitlines():
            if re.search(r"\[\+\]", line):
                url_m = re.search(r"https?://\S+", line)
                if url_m:
                    url = url_m.group(0)
                    if not any(p["url"] == url for p in profiles):
                        profiles.append({"url": url, "status": "found"})

        # JSON/CSV output style
        json_hits = re.findall(r'"site":\s*"([^"]+)".*?"url":\s*"([^"]+)"', raw, re.DOTALL)
        for _site, url in json_hits:
            if not any(p["url"] == url for p in profiles):
                profiles.append({"url": url, "status": "found"})

        return {
            "type": "username_search",
            "target": target,
            "profiles": profiles,
            "total_found": len(profiles),
        }

    def _parse_ignorant(self, raw: str, target: str) -> dict[str, Any]:
        registered: list[str] = []

        for line in raw.splitlines():
            if re.search(r"\[\+\]", line):
                m = re.search(r"\[\+\]\s+(.+?)(?:\s+\[|\s*$)", line)
                if m:
                    registered.append(m.group(1).strip())

        return {
            "type": "phone_check",
            "target": target,
            "registered_sites": registered,
            "total_registered": len(registered),
        }

    def _parse_whatspy(self, raw: str, target: str) -> dict[str, Any]:
        registered = bool(re.search(
            r"(?:found|registered|active|exists|yes)", raw, re.IGNORECASE
        ))
        name_m = re.search(r"(?:name|profile|display)[:\s]+([^\n]+)", raw, re.IGNORECASE)

        return {
            "type": "phone_check",
            "target": target,
            "whatsapp_registered": registered,
            "profile_name": name_m.group(1).strip() if name_m else None,
        }

    def _parse_ghunt(self, raw: str, target: str) -> dict[str, Any]:
        name_m = re.search(r"(?:name|full.?name)[:\s]+([^\n]+)", raw, re.IGNORECASE)
        photo_m = re.search(r"https?://[^\s]+(?:photo|avatar|picture|ggpht)[^\s]*", raw, re.IGNORECASE)
        services: list[str] = []
        for svc in ("Gmail", "YouTube", "Maps", "Drive", "Photos", "Calendar", "Meet", "Play"):
            if re.search(svc, raw, re.IGNORECASE):
                services.append(svc)

        return {
            "type": "google_account",
            "target": target,
            "name": name_m.group(1).strip() if name_m else None,
            "photo_url": photo_m.group(0) if photo_m else None,
            "linked_services": services,
        }

    def _parse_toutatis(self, raw: str, target: str) -> dict[str, Any]:
        followers_m = re.search(r"followers[:\s]+(\d+)", raw, re.IGNORECASE)
        following_m = re.search(r"following[:\s]+(\d+)", raw, re.IGNORECASE)
        name_m = re.search(r"(?:full.?name|name|display)[:\s]+([^\n]+)", raw, re.IGNORECASE)

        return {
            "type": "instagram_account",
            "target": target,
            "name": name_m.group(1).strip() if name_m else None,
            "followers": int(followers_m.group(1)) if followers_m else None,
            "following": int(following_m.group(1)) if following_m else None,
        }

    def _parse_socialscan(self, raw: str, target: str) -> dict[str, Any]:
        registered: list[str] = []

        for line in raw.splitlines():
            if re.search(r"\[\+\]|claimed|registered|taken", line, re.IGNORECASE):
                m = re.search(r"(?:\[\+\]\s+)?(.+?)(?:\s*[-:]\s*|\s*$)", line)
                if m:
                    registered.append(m.group(1).strip())

        return {
            "type": "username_availability",
            "target": target,
            "registered_sites": registered,
            "total_registered": len(registered),
        }

    def _parse_google_dorks(self, raw: str, target: str) -> dict[str, Any]:
        """Parse Google dork search results (google-dorks, pagodo, dork-cli output)."""
        urls = list(set(re.findall(r"https?://[^\s\)\]\}\n]+", raw)))
        urls = [url.rstrip(",;'\".") for url in urls]
        urls = [u for u in urls if u.startswith("http")]
        urls = list(set(urls))
        
        return {
            "type": "google_dork_search",
            "target": target,
            "urls_found": urls,
            "total_results": len(urls),
        }

    def _parse_generic(self, raw: str, target: str) -> dict[str, Any]:
        urls = list(set(re.findall(r"https?://\S+", raw)))
        emails = list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", raw)))

        return {
            "type": "generic",
            "target": target,
            "urls_found": urls,
            "emails_found": emails,
        }

    # ------------------------------------------------------------------
    # Optional LLM enrichment pass
    # ------------------------------------------------------------------

    def _extract_llm(
        self, tool: str, raw: str, already_parsed: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Ask the LLM to extract anything the regex parser missed.
        Returns only ADDITIONAL data (caller decides what to merge).
        """
        system_prompt = (
            "You are a Raw Data Sanitizer for OSINT outputs. "
            "Sua unica funcao e ignorar todo o lixo de interface do terminal "
            "(como loaders, barras de progresso [###---], banners em ASCII, "
            "mensagens de erro de timeout ou avisos do sistema). "
            "Voce deve extrair exclusivamente dados validos e confirmados de inteligencia. "
            "Return ONLY a strict JSON object with clean findings. "
            "No markdown, no comments, no explanations."
        )

        already_json = json.dumps(already_parsed, ensure_ascii=False)
        user_prompt = (
            f"Tool: {tool}\n"
            f"Regex already extracted:\n{already_json}\n\n"
            f"Raw output (find anything missed):\n{raw[:4000]}\n\n"
            "Return a JSON object with ADDITIONAL findings not yet captured."
        )

        llm = self.provider_manager.get_chat_model()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)

        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return {}
