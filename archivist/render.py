"""Plain-text rendering for validated action reports."""

from .evidence import normalize_whitespace
from .models import ActionReport


def _render_numbered(values: list[str]) -> list[str]:
    if not values:
        return ["None."]
    return [f"{index}. {normalize_whitespace(value)}" for index, value in enumerate(values, 1)]


def render_report(report: ActionReport) -> str:
    """Render the repository's stable, human-reviewable text format."""

    lines = ["ACTION ITEMS", ""]
    if report.actions:
        for index, item in enumerate(report.actions, start=1):
            lines.extend(
                [
                    f"{index}. Action: {normalize_whitespace(item.action)}",
                    f"   Owner: {normalize_whitespace(item.owner)}",
                    f"   Due date: {normalize_whitespace(item.due_date)}",
                    "   Evidence excerpt: "
                    f'"{normalize_whitespace(item.evidence_excerpt)}"',
                    f"   Speaker: {normalize_whitespace(item.speaker)}",
                    f"   Timestamp: {normalize_whitespace(item.timestamp)}",
                    "",
                ]
            )
    else:
        lines.extend(["None.", ""])

    lines.extend(["DECISIONS", "", *_render_numbered(report.decisions), ""])
    lines.extend(["OPEN QUESTIONS", "", *_render_numbered(report.open_questions), ""])
    return "\n".join(lines)


def render_report_json(report: ActionReport) -> str:
    """Render the same report as indented JSON, for later ingestion."""

    return report.model_dump_json(indent=2) + "\n"

