from __future__ import annotations

from pathlib import Path

INPUT_DIR = Path("data/input")
OUTPUT_DIR = Path("data/output")
REPORTS_DIR = OUTPUT_DIR / "reports"

SUPPORTED_PROVIDERS: tuple[str, ...] = ("ollama", "openai", "anthropic", "deepseek")

# (label, executables, required, scope)
TOOL_REQUIREMENTS: tuple[tuple[str, tuple[str, ...], bool, str], ...] = (
    ("holehe", ("holehe",), True, "base-scan"),
    ("sherlock", ("sherlock",), True, "base-scan"),
    ("h8mail", ("h8mail",), False, "full-scan"),
    ("socialscan", ("socialscan",), False, "full-scan"),
    ("leaker", ("leaker",), False, "base-scan"),
    ("Google Dorks", ("google_dorks", "google-dorks"), False, "base-scan"),
    ("Toutatis", ("toutatis",), False, "username-enrichment"),
    ("Maigret", ("maigret",), False, "username-enrichment"),
    ("GHunt", ("ghunt",), False, "email-enrichment"),
    ("Ignorant", ("ignorant",), False, "phone-enrichment"),
    ("WhatsSpy", ("whatspy", "whatsspy", "whats-spy"), False, "phone-enrichment"),
    ("Pagodo", ("pagodo",), False, "full-scan"),
    ("Dork-Cli / S3Scanner", ("dork-cli", "dork_cli", "s3scanner"), False, "full-scan"),
)

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
STATUS_COLORS: dict[str, str] = {
    "OK": "\033[92m",
    "WARN": "\033[93m",
    "ERR": "\033[91m",
}

EXPORT_FORMATS: dict[str, str] = {
    "md": ".md",
    "txt": ".txt",
    "html": ".html",
    "pdf": ".pdf",
}

# New banner for full redesign
ARGOS_NT_BANNER = r"""
 ██╗ █████╗ ██████╗  ██████╗  ██████╗ ███████╗      ███╗   ██╗████████╗ ██████╗
 ██║██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗██╔════╝      ████╗  ██║╚══██╔══╝██╔════╝
 ██║███████║██████╔╝██║  ███╗██║   ██║███████╗█████╗██╔██╗ ██║   ██║   ██║     
 ██║██╔══██║██╔══██╗██║   ██║██║   ██║╚════██║╚════╝██║╚██╗██║   ██║   ██║     
 ██║██║  ██║██║  ██║╚██████╔╝╚██████╔╝███████║      ██║ ╚████║   ██║   ╚██████╗
 ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝      ╚═╝  ╚═══╝   ╚═╝    ╚═════╝
"""

APP_VERSION = "v1.0.4"
APP_CODENAME = "Panoptes"
MAINTAINER_LINE = "@despossivel feat. Copilot"

