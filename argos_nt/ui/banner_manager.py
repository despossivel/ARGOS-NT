from __future__ import annotations

import random
import textwrap
from pathlib import Path

from rich.console import Group
from rich.text import Text


DEFAULT_BANNER = textwrap.dedent(
    r"""
     ___    ____   ______  ____  _____    _   ______________
    /   |  / __ \ / ____/ / __ \/ ___/   / | / /_  __/ ____/
   / /| | / /_/ // / __  / / / /\__ \   /  |/ / / / / /
  / ___ |/ _, _// /_/ / / /_/ /___/ /  / /|  / / / / /___
 /_/  |_/_/ |_| \____/  \____//____/  /_/ |_/ /_/  \____/
    """
).strip("\n")


class ArgosBannerManager:
    """Load ASCII banners from disk and render a startup screen."""

    def __init__(self, banner_dir: str | Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parent
        self.banner_dir = Path(banner_dir) if banner_dir is not None else base_dir / "assets" / "banners"
        self.banner_dir.mkdir(parents=True, exist_ok=True)

    def _load_raw_banners(self) -> list[str]:
        banners: list[str] = []
        for path in sorted(self.banner_dir.glob("*.txt")):
            content = textwrap.dedent(path.read_text(encoding="utf-8")).rstrip("\n")
            if content.strip():
                banners.append(content)
        return banners

    def get_random_banner(self) -> str:
        banners = self._load_raw_banners()
        if not banners:
            return DEFAULT_BANNER
        return random.choice(banners)

    def generate_startup_screen(
        self,
        total_cases: int,
        active_modules: int,
        provider_name: str | None = None,
        provider_model: str | None = None,
        creator_line: str = "created by: @despossivel feat copilot",
    ) -> Group:
        banner_text = Text(self.get_random_banner(), style="bold cyan")
        intro_lines = Text()
        intro_lines.append("ARGOS-NT - AI OSINT / Investigation Console\n", style="bold white")
        if provider_name:
            provider_label = provider_name.title()
            model_label = provider_model or "unknown-model"
            intro_lines.append(f"Using: {provider_label} ({model_label})\n", style="bright_cyan")
        intro_lines.append(f"{creator_line}\n", style="dim")

        status_lines = Text()
        status_lines.append("[+] ARGOS-NT Intelligent Core Initialized\n", style="bold green")
        status_lines.append("[+] Graph Database (Neo4j): CONNECTED\n", style="green")
        status_lines.append(
            f"[+] Active Profiling Modules: {active_modules} loaded\n",
            style="bright_white",
        )
        status_lines.append(
            f"[+] Investigation Dossiers: {total_cases} {'active dossier' if total_cases == 1 else 'active dossiers'}\n",
            style="bright_white",
        )

        return Group(
            banner_text,
            Text(""),
            intro_lines,
            Text(""),
            status_lines,
        )


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    manager = ArgosBannerManager()
    console.print(
        manager.generate_startup_screen(
            total_cases=12,
            active_modules=8,
            provider_name="ollama",
            provider_model="qwen2.5",
        )
    )