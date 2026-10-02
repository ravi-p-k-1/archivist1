"""Validated data structures for the JSON transcript pipeline.

Two report shapes exist because Claude never sees speaker or timestamp
directly - it cites a compact-view entry id instead, and `finalize` copies
the real speaker and timestamp from that entry afterward.
"""

from pydantic import BaseModel, ConfigDict, Field

_ENTRY_PATTERN = r"^e[1-9][0-9]*$"


class ActionSubmission(BaseModel):
    """One action as submitted by Claude, citing a compact-view entry id."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: str = Field(min_length=1, description="A concrete, verifiable action.")
    owner: str = Field(
        default="Unassigned",
        min_length=1,
        description="The supported owner, or Unassigned.",
    )
    due_date: str = Field(
        default="Not specified",
        min_length=1,
        description="The supported due date, or Not specified.",
    )
    entry: str = Field(
        pattern=_ENTRY_PATTERN,
        description="The compact-view entry id this action is grounded in, for example e12.",
    )
    evidence_excerpt: str = Field(
        min_length=1,
        description="A short verbatim excerpt copied from the cited entry.",
    )


class ReportSubmission(BaseModel):
    """The complete structured output Claude submits for one transcript."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    actions: list[ActionSubmission] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ActionItem(BaseModel):
    """One transcript-grounded action item, with speaker and time resolved."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: str = Field(min_length=1, description="A concrete, verifiable action.")
    owner: str = Field(
        default="Unassigned",
        min_length=1,
        description="The supported owner, or Unassigned.",
    )
    due_date: str = Field(
        default="Not specified",
        min_length=1,
        description="The supported due date, or Not specified.",
    )
    evidence_excerpt: str = Field(
        min_length=1,
        description="A short verbatim excerpt from the transcript.",
    )
    speaker: str = Field(min_length=1, description="Speaker associated with the evidence.")
    timestamp: str = Field(
        min_length=1,
        description="Elapsed time from meeting start, HH:MM:SS.",
    )


class ActionReport(BaseModel):
    """The final, rendered extraction for one transcript."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    actions: list[ActionItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
