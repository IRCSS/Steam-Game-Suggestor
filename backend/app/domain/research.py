"""LLM research: the standardized findings schema and the deterministic economics derived from it.

Research runs in two separate steps, matching how studies are made:
* "budget": web research only (team size, development time) - quick, decides whether a game fits.
* "reviews": summarizes the supplied reviews (why it worked / what held it back), no web access.
Runs saved before the split did both at once ("full"). Cost and break-even are CALCULATED here
from the estimates and the user's cost model, so they are reproducible and follow settings changes.
Pure module - no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROMPT_VERSION = "3"
SCHEMA_VERSION = "1"

Confidence = Literal["high", "medium", "low", "unknown"]
ResearchKind = Literal["budget", "reviews"]
RunKind = Literal["full", "budget", "reviews"]  # "full": both at once (runs before the split)
KIND_COVERS: dict[ResearchKind, tuple[RunKind, ...]] = {
    "budget": ("full", "budget"),
    "reviews": ("full", "reviews"),
}
CONFIDENCE_ORDER: dict[str, int] = {"unknown": 0, "low": 1, "medium": 2, "high": 3}


class Source(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(max_length=300)
    url: str = Field(max_length=1000)


class Estimate(BaseModel):
    """A researched quantity: range + best guess, with how sure we are and why."""

    model_config = ConfigDict(extra="ignore")

    low: float | None = Field(default=None, ge=0)
    high: float | None = Field(default=None, ge=0)
    best: float | None = Field(default=None, ge=0)
    confidence: Confidence = "unknown"
    basis: str = Field(default="", max_length=2000)
    sources: list[Source] = Field(default_factory=list[Source], max_length=12)

    def central(self) -> float | None:
        if self.best is not None:
            return self.best
        if self.low is not None and self.high is not None:
            return (self.low + self.high) / 2
        return self.low if self.low is not None else self.high


class Insight(BaseModel):
    model_config = ConfigDict(extra="ignore")

    point: str = Field(max_length=300)
    evidence: str = Field(default="", max_length=600)
    confidence: Confidence = "medium"


class ResearchFindings(BaseModel):
    """What the LLM returns. Each run kind fills its own part (see ``findings_json_schema``);
    the other part keeps its empty defaults."""

    model_config = ConfigDict(extra="ignore")

    studio: str = Field(default="", max_length=200)
    # people who worked on the game during its development
    team_size: Estimate = Field(default_factory=Estimate)
    # start of development to full (1.0) release
    development_months: Estimate = Field(default_factory=Estimate)
    why_it_worked: list[Insight] = Field(default_factory=list[Insight], max_length=6)
    what_held_it_back: list[Insight] = Field(default_factory=list[Insight], max_length=6)
    notes: str = Field(default="", max_length=2000)


def findings_json_schema(kind: ResearchKind) -> dict[str, object]:
    """JSON schema for the CLI's --json-schema (strict: no extra keys), per run kind."""

    def estimate(unit: str) -> dict[str, object]:
        number = {"type": ["number", "null"], "minimum": 0}
        return {
            "type": "object",
            "description": (
                f"Estimate in {unit}. Null numbers and confidence 'unknown' if no evidence."
            ),
            "properties": {
                "low": number,
                "high": number,
                "best": number,
                "confidence": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
                "basis": {
                    "type": "string",
                    "description": "How the estimate was derived, briefly.",
                },
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                        "required": ["title", "url"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["low", "high", "best", "confidence", "basis", "sources"],
            "additionalProperties": False,
        }

    insight = {
        "type": "object",
        "properties": {
            "point": {"type": "string"},
            "evidence": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["point", "evidence", "confidence"],
        "additionalProperties": False,
    }
    properties: dict[str, object] = (
        {
            "studio": {"type": "string"},
            "team_size": estimate("people"),
            "development_months": estimate("months"),
        }
        if kind == "budget"
        else {
            "why_it_worked": {"type": "array", "items": insight, "minItems": 1, "maxItems": 5},
            "what_held_it_back": {"type": "array", "items": insight, "minItems": 1, "maxItems": 5},
        }
    )
    properties["notes"] = {"type": "string"}
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def sanitize(findings: ResearchFindings) -> tuple[ResearchFindings, list[str]]:
    """Guardrails on LLM output: a number without any source cannot be more than 'low'
    confidence; 'unknown' never carries numbers; ranges are ordered. Returns warnings."""
    warnings: list[str] = []
    fixed = findings.model_copy(deep=True)
    for label, est in (
        ("team size", fixed.team_size),
        ("development time", fixed.development_months),
    ):
        if est.confidence == "unknown":
            est.low = est.high = est.best = None
        has_number = est.central() is not None
        if has_number and not est.sources and est.confidence in ("high", "medium"):
            est.confidence = "low"
            warnings.append(f"{label}: no source given, confidence lowered to low")
        if est.low is not None and est.high is not None and est.low > est.high:
            est.low, est.high = est.high, est.low
        est.sources = [s for s in est.sources if s.url.startswith(("http://", "https://"))]
    return fixed, warnings


# --- economics (deterministic) -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostModel:
    salary_per_person_year: float = 50_000.0
    salary_currency: str = "EUR"
    usd_per_salary_unit: float = 1.08  # EUR -> USD rate used to compare with USD revenue
    comparison_team_size: int = 3
    platform_cut: float = 0.30


@dataclass(frozen=True, slots=True)
class Range:
    low: float | None
    best: float | None
    high: float | None


@dataclass(frozen=True, slots=True)
class Economics:
    person_years: Range
    cost: Range  # in salary currency
    cost_usd: Range
    comparison_team_years: Range  # how long a team of N (cost model) would need
    break_even_gross_usd: Range  # gross revenue at which net (after platform cut) = cost
    break_even_copies: Range | None  # at the current price; None for free games
    revenue_multiple: float | None  # estimated gross revenue / break-even (best case)
    confidence: Confidence  # the weaker of team size and development time


def weakest(*levels: Confidence) -> Confidence:
    return min(levels, key=lambda c: CONFIDENCE_ORDER[c])


def _mul(a: float | None, b: float | None) -> float | None:
    return a * b if a is not None and b is not None else None


def compute_economics(
    findings: ResearchFindings, model: CostModel, price_usd: float, estimated_revenue_usd: float
) -> Economics:
    team, months = findings.team_size, findings.development_months

    def end(est: Estimate, which: Literal["low", "high"]) -> float | None:
        value = est.low if which == "low" else est.high
        return value if value is not None else est.central()

    # Lowest effort pairs the low ends, highest the high ends; months -> years.
    person_months = (
        _mul(end(team, "low"), end(months, "low")),
        _mul(team.central(), months.central()),
        _mul(end(team, "high"), end(months, "high")),
    )
    person_years = Range(*(v / 12 if v is not None else None for v in person_months))

    def scale(r: Range, factor: float) -> Range:
        return Range(*(v * factor if v is not None else None for v in (r.low, r.best, r.high)))

    cost = scale(person_years, model.salary_per_person_year)
    cost_usd = scale(cost, model.usd_per_salary_unit)
    team_years = scale(person_years, 1 / max(1, model.comparison_team_size))
    keep = 1 - model.platform_cut
    break_even = scale(cost_usd, 1 / keep if keep > 0 else float("inf"))
    copies = scale(break_even, 1 / price_usd) if price_usd > 0 else None
    multiple = (
        estimated_revenue_usd / break_even.best
        if break_even.best and estimated_revenue_usd > 0
        else None
    )
    return Economics(
        person_years=person_years,
        cost=cost,
        cost_usd=cost_usd,
        comparison_team_years=team_years,
        break_even_gross_usd=break_even,
        break_even_copies=copies,
        revenue_multiple=multiple,
        confidence=weakest(team.confidence, months.confidence),
    )
