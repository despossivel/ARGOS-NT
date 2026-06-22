from __future__ import annotations

from argos_nt.tools.tool_executor import ToolResult


class ArchitectAgent:
    """Decides next investigation tasks based on graph inputs and tool outcomes."""

    def plan_next_steps(self, entities: dict[str, list[str]], tool_results: list[ToolResult]) -> list[str]:
        tasks: list[str] = []

        if entities.get("emails"):
            tasks.append("Executar correlacao de dominio de email com organizacoes conhecidas.")
        if entities.get("usernames"):
            tasks.append("Buscar reutilizacao de username em plataformas adicionais.")
        if entities.get("urls"):
            tasks.append("Extrair metadados e infraestrutura das URLs encontradas.")

        failures = [item for item in tool_results if not item.ok]
        if failures:
            tasks.append("Reexecutar ferramentas com falha apos validar instalacao e argumentos.")

        if not tasks:
            tasks.append("Sem novos gatilhos: gerar relatorio preliminar e aguardar novos dados.")

        return tasks
