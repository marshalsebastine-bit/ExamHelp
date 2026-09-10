"""The rule catalogue schema.

The catalogue is **data, not code** (tech doc 3.3, 9): YAML files, one per
family, version-controlled, editable by a non-programmer.  A rule change must
never require a code change.

Three fields do most of the work:

``input_slice`` declares the minimum artifact fragment a check needs.  It is what
keeps prompts small enough for free-tier token budgets, and — more importantly —
it narrows the failure surface: a check that cannot see the Fallsituation cannot
produce a flag about the Fallsituation (tech doc 3.3.1).

``requires`` declares preconditions.  Unmet means skip visibly, never flag.  This
is what makes the tool usable on a work-in-progress draft (tech doc 1.5.1).

``mutation`` is the defect the rule must catch, so the evaluation harness is
generated from the catalogue rather than maintained separately.  A rule without a
mutation is not testable and does not ship (tech doc 3.3, 7.2).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.flag import Severity


class Family(str, Enum):
    A = "A"  # Form und Konstruktion
    B = "B"  # Kompetenzzuordnung
    C = "C"  # Quellenbindung


class CheckType(str, Enum):
    deterministic = "deterministic"
    llm = "llm"
    hybrid = "hybrid"


class Scope(str, Enum):
    aufgabe = "aufgabe"
    fallsituation = "fallsituation"
    teilaufgabe = "teilaufgabe"
    erwartungshorizont = "erwartungshorizont"
    aufgabenset = "aufgabenset"  # across sibling Aufsichtsarbeiten


class Authority(str, Enum):
    """How binding the rule's source is.  Severity derives from this rather than
    being hand-assigned per rule (repo review 2.3)."""

    binding_federal = "binding_federal"
    official_state = "official_state"
    third_party_advisory = "third_party_advisory"
    professional_normative = "professional_normative"
    # A construction principle the project states in its own words, with no
    # external authority behind it.  Named explicitly because the plan's severity
    # model does: `pruefen` covers "state guidance or a construction principle"
    # (tech doc 4.2).  Labelling these honestly is better than forcing a citation
    # onto a rule no source actually states -- that is the fabricated-citation
    # failure mode the evidence rule exists to prevent.
    construction_principle = "construction_principle"
    assessment_literature = "assessment_literature"


# The severity a rule may carry, given how binding its source is.  `blocker` is
# reserved for binding federal law: if PflAPrV does not require it, the tool does
# not get to call it a blocker.
MAX_SEVERITY = {
    Authority.binding_federal: Severity.blocker,
    Authority.official_state: Severity.pruefen,
    Authority.third_party_advisory: Severity.pruefen,
    Authority.professional_normative: Severity.pruefen,
    Authority.construction_principle: Severity.pruefen,
    Authority.assessment_literature: Severity.hinweis,
}
SEVERITY_RANK = {Severity.hinweis: 0, Severity.pruefen: 1, Severity.blocker: 2}


class RuleSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: str
    locator: str = Field(description="citable position within the document")
    url: str | None = None
    quote: str | None = Field(
        default=None,
        description="the source text this rule derives from, quoted into a flag's evidence",
    )


class Mutation(BaseModel):
    """The defect this rule must catch. Used only by the evaluation harness."""

    model_config = ConfigDict(extra="forbid")

    id: str
    operation: str = Field(description="the deterministic transformation the harness applies")
    description: str
    target: str | None = Field(default=None, description="which element the mutation acts on")


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    id: str
    family: Family
    title: str
    rule_text: str = Field(
        description="the team's own wording. Reproducing a copyrighted source's "
        "formulation is not permissible; citing it is (repo review 5)."
    )
    source: RuleSource
    authority: Authority
    jurisdiction: str = Field(default="federal", description="'federal' or a Land code, e.g. 'BY'")
    check_type: CheckType
    scope: Scope
    input_slice: list[str] = Field(min_length=1)
    requires: list[str] = Field(default_factory=list)
    severity_default: Severity
    mutation: Mutation
    suggestion_template: list[str] = Field(
        default_factory=list,
        description="expected for Family A: what the author can do about it (tech doc 1.5.2)",
    )
    # A rule whose evidence source is not yet in the corpus cannot produce a
    # citable flag, so it must not run.  Recording that here keeps the gap
    # visible in the catalogue instead of hiding it behind a placeholder quote
    # (tech doc 4.1: a check that cannot produce evidence does not ship).
    blocked_on: str | None = None
    notes: str | None = None

    @property
    def runnable(self) -> bool:
        return self.blocked_on is None

    @model_validator(mode="after")
    def severity_within_authority(self) -> "Rule":
        ceiling = MAX_SEVERITY[self.authority]
        if SEVERITY_RANK[self.severity_default] > SEVERITY_RANK[ceiling]:
            raise ValueError(
                f"{self.id}: severity {self.severity_default.value!r} exceeds what "
                f"authority {self.authority.value!r} supports (max {ceiling.value!r}). "
                "blocker is reserved for binding PflAPrV requirements (tech doc 4.2)."
            )
        return self

    @model_validator(mode="after")
    def requires_is_within_input_slice(self) -> "Rule":
        """A precondition on data the check never receives cannot be meaningful."""
        for path in self.requires:
            if not any(path == s or path.startswith(f"{s}.") or s.startswith(f"{path}.") for s in self.input_slice):
                raise ValueError(
                    f"{self.id}: requires {path!r} is not covered by input_slice {self.input_slice}"
                )
        return self

    @model_validator(mode="after")
    def family_a_offers_a_suggestion(self) -> "Rule":
        """For the author, suggestions carry most of the value (tech doc 1.5.2)."""
        if self.family == Family.A and not self.suggestion_template:
            raise ValueError(
                f"{self.id}: Family A rules must offer at least one suggestion; "
                "a Family A rule without a usable suggestion is an incomplete rule"
            )
        return self

    @model_validator(mode="after")
    def evidence_is_quotable(self) -> "Rule":
        """No flag without evidence: the rule must carry a quotable source.

        Family B's evidence is the competency text, looked up at runtime from
        rules/kompetenzen.yaml, so those rules legitimately have no static quote.
        """
        if self.family != Family.B and not self.source.quote and not self.blocked_on:
            raise ValueError(
                f"{self.id}: source.quote is required so a flag can carry evidence "
                "(tech doc 4.1). A check that cannot produce evidence does not ship. "
                "Set `blocked_on` if the source document is not yet acquired."
            )
        return self


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: dict = Field(default_factory=dict)
    rules: list[Rule]

    @model_validator(mode="after")
    def ids_are_unique(self) -> "RuleSet":
        seen = [r.id for r in self.rules]
        duplicates = sorted({i for i in seen if seen.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate rule ids: {duplicates}")
        mutation_ids = [r.mutation.id for r in self.rules]
        duplicate_mutations = sorted({i for i in mutation_ids if mutation_ids.count(i) > 1})
        if duplicate_mutations:
            raise ValueError(f"duplicate mutation ids: {duplicate_mutations}")
        return self

    def by_family(self, family: Family | str) -> list[Rule]:
        value = family if isinstance(family, Family) else Family(family)
        return [r for r in self.rules if r.family == value]

    @property
    def runnable(self) -> list[Rule]:
        return [r for r in self.rules if r.runnable]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.rules),
            "runnable": len(self.runnable),
            "blocked": sum(1 for r in self.rules if not r.runnable),
            "deterministic": sum(1 for r in self.rules if r.check_type == CheckType.deterministic),
            "llm": sum(1 for r in self.rules if r.check_type == CheckType.llm),
            "hybrid": sum(1 for r in self.rules if r.check_type == CheckType.hybrid),
            **{f"family_{f.value}": len(self.by_family(f)) for f in Family},
        }
