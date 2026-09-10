"""The output contract: what the check runner returns.

``Aufgabe`` in, ``Flag[]`` + ``NotChecked[]`` out (tech doc 9).  The docx writer,
the HTML report, and any future Word add-in are all consumers of *this* and
never reach into the runner's internals.

Two rules from tech doc 4.1 are enforced structurally rather than by convention:

**No flag without evidence.**  ``evidence`` is required and must carry the rule's
quoted source text.  A check that cannot produce that does not ship.  This is
the entire difference between this tool and pasting an item into a chatbot.

**Deterministic first, model second.**  ``mechanism`` records which mechanism
produced the flag, so a report can distinguish "this violates a stated rule"
from "a model thinks this may be a problem".
"""
from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Grading vocabulary a flag must not use.  Flags advise; they never grade
# (tech doc 1.5.4).  Matched on word boundaries, not as substrings: "notieren"
# contains "note", and "verfaelscht" contains "falsch", so substring matching
# would reject legitimate findings.
#
# Deliberately narrow.  Factual words like "falsch" or "unzureichend" are not
# listed: "unzureichende Schmerzkontrolle" is clinical description, and the
# constraint is about the register of a *judgement*, not about vocabulary.
GRADING_WORDS = re.compile(
    r"\b(?:fehler|fehlerhaft|mangelhaft|ungenügend|ungenuegend|"
    r"note|noten|bewertung|punktabzug|mangel)\b",
    re.IGNORECASE,
)


class Severity(str, Enum):
    """A property of the *rule*, not a model judgement, so it stays deterministic
    and defensible (tech doc 4.2).

    Tone is a design constraint: these are qualified professionals who will
    reasonably resent software second-guessing their pedagogical judgement.
    ``hinweis`` is the default register; ``blocker`` is reserved strictly for
    violations of binding PflAPrV requirements (tech doc 1.5.4).
    """

    blocker = "blocker"  # violates a binding PflAPrV requirement
    pruefen = "pruefen"  # violates state guidance or a construction principle
    hinweis = "hinweis"  # advisory


class Mechanism(str, Enum):
    deterministic = "deterministic"
    llm = "llm"


class Evidence(BaseModel):
    """Why this flag is defensible.  ``rule_quote`` and ``source`` are mandatory."""

    model_config = ConfigDict(extra="forbid")

    rule_quote: str = Field(min_length=1, description="short quote from the rule's source")
    source: str = Field(min_length=1, description="citable locator, e.g. 'Anlage 2 (zu § 9 Absatz 1 Satz 2), Kompetenz I.1.h'")
    retrieved_passage: str | None = Field(
        default=None, description="populated for Family C, where the evidence is a retrieved passage"
    )
    retrieved_source: str | None = None


class Flag(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    flag_id: str
    rule_id: str
    anchor: str = Field(description="stable structural ID from the item schema, e.g. ta.2.eh.3")
    severity: Severity
    mechanism: Mechanism
    finding: str = Field(min_length=1, description="what is wrong, in one or two sentences")
    evidence: Evidence

    # For the primary user these carry most of the value, so a Family A rule
    # without a usable suggestion is an incomplete rule (tech doc 1.5.2).  Where
    # a rule admits two legitimate fixes, both are offered rather than picking
    # one: that choice is a pedagogical judgement belonging to the author.
    suggestions: list[str] = Field(default_factory=list)

    # Deliberately omitted as a number: a model-generated confidence would be
    # unfounded and reviewers would over-trust it.  `mechanism` carries the
    # honest version of the same information (tech doc 4.2).
    confidence: None = None

    @field_validator("finding")
    @classmethod
    def no_grading_language(cls, value: str) -> str:
        """Keep the advisory register the tone constraint requires.

        This is a development-time guard on prompt quality, not a runtime filter:
        a model asked to critique an exam item will reach for "Fehler" unprompted,
        and the fix is to correct the prompt, never to drop the flag.  The runner
        must therefore treat a rejection here as a defect in the rule's prompt
        rather than swallowing it (tech doc 1.5.4).
        """
        match = GRADING_WORDS.search(value)
        if match:
            raise ValueError(
                f"finding uses grading language {match.group(0)!r}; flags advise, they never "
                "grade (tech doc 1.5.4). Reword the rule's prompt, do not drop the flag."
            )
        return value


class NotChecked(BaseModel):
    """A check that did not run, and why.

    Mandatory in both outputs.  With the ``requires`` gate this is a routine
    occurrence on any draft, not an edge case, and for an author it is actively
    useful: "nicht prüfbar bis Erwartungshorizont vorliegt" is a to-do list.
    Silent skipping is a bug (tech doc 4.3, 9).
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    reason: str = Field(min_length=1)
    missing: list[str] = Field(
        default_factory=list, description="the unmet `requires` paths"
    )
    anchor: str | None = None


class CheckResult(BaseModel):
    """The complete result of one run over one Aufsichtsarbeit."""

    model_config = ConfigDict(extra="forbid")

    aufgabe_id: str | None = None
    flags: list[Flag] = Field(default_factory=list)
    not_checked: list[NotChecked] = Field(default_factory=list)
    run_id: str | None = None
    model: str | None = Field(default=None, description="null when no LLM check ran")

    def by_severity(self, severity: Severity | str) -> list[Flag]:
        value = severity.value if isinstance(severity, Severity) else severity
        return [f for f in self.flags if f.severity == value]

    @property
    def coverage(self) -> dict[str, int]:
        return {
            "flags": len(self.flags),
            "rules_not_checked": len(self.not_checked),
            "deterministic_flags": sum(1 for f in self.flags if f.mechanism == "deterministic"),
            "llm_flags": sum(1 for f in self.flags if f.mechanism == "llm"),
        }
