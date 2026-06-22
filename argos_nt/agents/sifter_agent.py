from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from argos_nt.drivers.provider_manager import ProviderManager


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
AT_HANDLE_RE = re.compile(r"(?<![\w/])@([A-Za-z0-9_](?:[A-Za-z0-9_.-]{1,30}[A-Za-z0-9_])?)\b")
USERNAME_LABEL_RE = re.compile(
    r"(?im)^\s*(?:username|user|handle|nick|nickname|username associado|usuario associado)\s*[:=-]\s*(.+?)\s*$"
)
URL_RE = re.compile(r"https?://[^\s]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
PERSON_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b")


@dataclass(slots=True)
class EntityExtraction:
    emails: list[str] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)
    persons: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)


class SifterAgent:
    """Extract entities from raw reports using regex with optional LLM enrichment."""

    SYSTEM_PROMPT = (
        "Extract entities from text and return JSON with keys: "
        "emails,usernames,persons,organizations,phones,urls,locations. "
        "Return only JSON."
    )

    def __init__(self, provider_manager: ProviderManager | None = None, prefer_llm: bool = False) -> None:
        self.provider_manager = provider_manager
        self.prefer_llm = prefer_llm

    def extract(self, text: str) -> EntityExtraction:
        extracted = EntityExtraction(
            emails=sorted(set(EMAIL_RE.findall(text))),
            usernames=self._extract_usernames(text),
            persons=sorted(set(PERSON_RE.findall(text))),
            phones=sorted(set(PHONE_RE.findall(text))),
            urls=sorted(set(URL_RE.findall(text))),
        )

        if self.prefer_llm and self.provider_manager is not None:
            try:
                llm_payload = self.provider_manager.invoke_json(self.SYSTEM_PROMPT, text)
                extracted = self._merge(extracted, llm_payload)
            except Exception:
                pass

        return extracted

    def as_dict(self, extraction: EntityExtraction) -> dict[str, list[str]]:
        return asdict(extraction)

    def _extract_usernames(self, text: str) -> list[str]:
        candidates: list[str] = []

        for raw_value in USERNAME_LABEL_RE.findall(text):
            normalized = self._normalize_username_candidate(raw_value)
            if normalized is not None:
                candidates.append(normalized)

        for handle in AT_HANDLE_RE.findall(text):
            normalized = self._normalize_username_candidate(handle)
            if normalized is not None:
                candidates.append(normalized)

        return sorted(set(candidates))

    def _normalize_username_candidate(self, value: str) -> str | None:
        cleaned = value.strip().split()[0].strip(".,;:()[]{}<>'\"")
        cleaned = cleaned.lstrip("@").strip()

        if len(cleaned) < 3:
            return None
        if "@" in cleaned:
            return None
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            return None
        if "." in cleaned and cleaned.count(".") > 2:
            return None

        return cleaned

    def _merge(self, base: EntityExtraction, llm_payload: dict) -> EntityExtraction:
        data = asdict(base)
        for key in data:
            llm_values = llm_payload.get(key, [])
            if isinstance(llm_values, list):
                combined = sorted(set(data[key]) | {str(item) for item in llm_values if str(item).strip()})
                data[key] = combined
        return EntityExtraction(**data)
