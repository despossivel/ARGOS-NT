from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


@dataclass(slots=True)
class ToolResult:
    tool: str
    target: str
    ok: bool
    output: str


class ToolExecutor:
    """Execute OSINT CLI tools with safe output normalization."""

    def __init__(self, timeout_seconds: int = 120, output_dir: str | Path = "data/output") -> None:
        self.timeout_seconds = timeout_seconds
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_holehe(self, email: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run("holehe", [email], target=email, progress_callback=progress_callback)

    def run_sherlock(self, username: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run("sherlock", [username, "--print-found"], target=username, progress_callback=progress_callback)

    def run_h8mail(self, email: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run("h8mail", ["-t", email], target=email, progress_callback=progress_callback)

    def run_socialscan(self, username: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run("socialscan", [username], target=username, progress_callback=progress_callback)

    def run_maigret(self, username: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run_first_available(
            ("maigret",),
            [username],
            target=username,
            progress_callback=progress_callback,
            tool_label="maigret",
        )

    def run_ignorant(self, phone: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        parsed = self._split_phone_for_ignorant(phone)
        if parsed is None:
            return ToolResult(
                tool="ignorant",
                target=phone,
                ok=False,
                output="Invalid phone format for Ignorant. Use E.164 format, e.g. +34604192904.",
            )

        country_code, local_number = parsed
        return self._run_first_available(
            ("ignorant",),
            [country_code, local_number],
            target=phone,
            progress_callback=progress_callback,
            tool_label="ignorant",
        )

    def run_whatspy(self, phone: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        command = self._first_available_command(("whatspy", "whatsspy", "whats-spy"))
        if command is None:
            return ToolResult(
                tool="whatspy",
                target=phone,
                ok=False,
                output="Tool 'whatspy' was not found in PATH (tried: whatspy, whatsspy, whats-spy).",
            )

        healthy, reason = self._check_command_health(command)
        if not healthy:
            if progress_callback is not None:
                progress_callback(f"whatspy: installation check failed: {reason}")
            return ToolResult(
                tool="whatspy",
                target=phone,
                ok=False,
                output=(
                    "WhatsSpy executable is present but appears broken. "
                    f"Reason: {reason}"
                ),
            )

        return self._run(
            command,
            [phone],
            target=phone,
            progress_callback=progress_callback,
        )

    def run_toutatis(self, username: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run_first_available(
            ("toutatis",),
            [username],
            target=username,
            progress_callback=progress_callback,
            tool_label="toutatis",
        )

    def run_google_dorks(self, query: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run_first_available(
            ("google_dorks", "google-dorks"),
            [query],
            target=query,
            progress_callback=progress_callback,
            tool_label="google-dorks",
        )

    def run_pagodo(self, query: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run_first_available(
            ("pagodo",),
            [query],
            target=query,
            progress_callback=progress_callback,
            tool_label="pagodo",
        )

    def run_dork_cli(self, query: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run_first_available(
            ("dork-cli", "dork_cli"),
            [query],
            target=query,
            progress_callback=progress_callback,
            tool_label="dork-cli",
        )

    def run_s3scanner(self, target: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run_first_available(
            ("s3scanner",),
            [target],
            target=target,
            progress_callback=progress_callback,
            tool_label="s3scanner",
        )

    def run_ghunt_email(self, email: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        creds_path = Path.home() / ".malfrats" / "ghunt" / "creds.m"
        if not creds_path.is_file():
            if progress_callback is not None:
                progress_callback("ghunt: no stored session found, run 'ghunt login' first")
            return ToolResult(
                tool="ghunt",
                target=email,
                ok=False,
                output="GHunt session not found. Run 'ghunt login' before using ghunt email mode.",
            )

        return self._run_first_available(
            ("ghunt",),
            ["email", email],
            target=email,
            progress_callback=progress_callback,
            tool_label="ghunt",
        )

    def run_leaker_email(self, email: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run("leaker", ["email", email, "--no-color"], target=email, progress_callback=progress_callback)

    def run_leaker_username(self, username: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run(
            "leaker",
            ["username", username, "--no-color"],
            target=username,
            progress_callback=progress_callback,
        )

    def run_leaker_phone(self, phone: str, progress_callback: Callable[[str], None] | None = None) -> ToolResult:
        return self._run(
            "leaker",
            ["phone", phone, "--no-color"],
            target=phone,
            progress_callback=progress_callback,
        )

    def has_tool(self, *commands: str) -> bool:
        return any(shutil.which(command) is not None for command in commands)

    def has_ghunt_session(self) -> bool:
        creds_path = Path.home() / ".malfrats" / "ghunt" / "creds.m"
        return creds_path.is_file()

    def build_virtual_result(self, tool: str, target: str, output: str, ok: bool = True) -> ToolResult:
        return ToolResult(tool=tool, target=target, ok=ok, output=output)

    def write_text_artifact(self, prefix: str, content: str, suffix: str = ".txt") -> Path:
        safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix).strip("_") or "artifact"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifact_path = self.output_dir / f"{safe_prefix}_{timestamp}{suffix}"
        artifact_path.write_text(content, encoding="utf-8")
        return artifact_path

    def write_json_artifact(self, prefix: str, payload: object) -> Path:
        safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix).strip("_") or "artifact"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifact_path = self.output_dir / f"{safe_prefix}_{timestamp}.json"
        artifact_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return artifact_path

    def _run(
        self,
        command: str,
        args: list[str],
        target: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> ToolResult:
        def emit(message: str) -> None:
            if progress_callback is not None:
                progress_callback(message)

        if shutil.which(command) is None:
            emit(f"{command}: tool not found in PATH")
            return ToolResult(
                tool=command,
                target=target,
                ok=False,
                output=f"Tool '{command}' was not found in PATH.",
            )

        try:
            emit(f"Starting {command} for target '{target}' in {self.output_dir}")
            process = subprocess.Popen(
                [command, *args],
                cwd=self.output_dir,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output_lines: list[str] = []

            try:
                stdout, _ = process.communicate(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, _ = process.communicate()
                clean_timeout_output = ANSI_RE.sub("", stdout or "").strip()
                if clean_timeout_output:
                    for line in clean_timeout_output.splitlines():
                        emit(f"{command} output: {line}")
                emit(f"{command}: execution timed out after {self.timeout_seconds}s")
                return ToolResult(
                    tool=command,
                    target=target,
                    ok=False,
                    output=f"Execution of '{command}' exceeded timeout ({self.timeout_seconds}s).",
                )

            clean_output = ANSI_RE.sub("", stdout or "").strip()
            if clean_output:
                output_lines.extend(clean_output.splitlines())
                for line in output_lines:
                    emit(f"{command} output: {line}")
            else:
                emit(f"{command}: no output returned")

            emit(f"Finished {command} for target '{target}' with exit code {process.returncode}")
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool=command,
                target=target,
                ok=False,
                output=f"Execution of '{command}' exceeded timeout ({self.timeout_seconds}s).",
            )

        clean = "\n".join(output_lines).strip()

        return ToolResult(
            tool=command,
            target=target,
            ok=process.returncode == 0,
            output=clean or "No output returned.",
        )

    def _run_first_available(
        self,
        commands: tuple[str, ...],
        args: list[str],
        target: str,
        progress_callback: Callable[[str], None] | None = None,
        tool_label: str | None = None,
    ) -> ToolResult:
        tool_name = tool_label or commands[0]

        command = self._first_available_command(commands)
        if command is not None:
            return self._run(command, args, target=target, progress_callback=progress_callback)

        if progress_callback is not None:
            progress_callback(f"{tool_name}: tool not found in PATH (tried: {', '.join(commands)})")

        return ToolResult(
            tool=tool_name,
            target=target,
            ok=False,
            output=f"Tool '{tool_name}' was not found in PATH (tried: {', '.join(commands)}).",
        )

    def _first_available_command(self, commands: tuple[str, ...]) -> str | None:
        for command in commands:
            if shutil.which(command) is not None:
                return command
        return None

    def _split_phone_for_ignorant(self, phone: str) -> tuple[str, str] | None:
        raw = phone.strip()
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 8:
            return None

        if raw.startswith("+"):
            for cc_len in (2, 1, 3):
                if len(digits) - cc_len >= 6:
                    return digits[:cc_len], digits[cc_len:]
            return None

        # Ignorant expects country code + local number; require explicit +CC format.
        return None

    def _check_command_health(self, command: str) -> tuple[bool, str]:
        try:
            completed = subprocess.run(
                [command, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception as exc:
            return False, str(exc)

        output = f"{completed.stdout}\n{completed.stderr}".strip()
        if "SyntaxError" in output:
            return False, "SyntaxError raised while running --help"

        # Some tools return non-zero on --help, so only treat clear interpreter errors as broken.
        return True, "ok"
