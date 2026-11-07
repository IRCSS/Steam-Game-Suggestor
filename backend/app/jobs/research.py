"""Research jobs -> Claude Code CLI -> validated findings.

budget: web research only. reviews: helpful reviews (2 Steam requests), no web access."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Literal

from app.db.connection import utc_now
from app.domain.models import Game
from app.domain.research import ResearchKind, sanitize
from app.jobs.runner import JobContext, JobFailed
from app.providers.steam_reviews import ReviewSample, fetch_review_samples
from app.research.claude_cli import (
    ResearchError,
    Runner,
    build_budget_prompt,
    build_reviews_prompt,
    run_claude_research,
    subprocess_runner,
)
from app.storage.files import machine_id
from app.storage.research import ResearchRun, ResearchStore

REVIEWS_PER_SIDE = 40


def make_research_task(
    game: Game,
    kind: ResearchKind,
    cli: Path,
    store: ResearchStore,
    *,
    model: str,
    max_budget_usd: float,
    timeout_seconds: float,
    runner: Runner = subprocess_runner,
) -> Callable[[JobContext], str]:
    def fetch(ctx: JobContext, side: Literal["positive", "negative"]) -> list[ReviewSample]:
        return (
            ctx.call(
                "reviews",
                f"{side} reviews",
                partial(fetch_review_samples, appid=game.appid, side=side, count=REVIEWS_PER_SIDE),
            )
            or []
        )

    def task(ctx: JobContext) -> str:
        ctx.set_total(3)
        positives: list[ReviewSample] = []
        negatives: list[ReviewSample] = []
        if kind == "reviews":
            ctx.log("Reading the most helpful Steam reviews")
            positives, negatives = fetch(ctx, "positive"), fetch(ctx, "negative")
            ctx.advance()
            if ctx.cancelled:
                return "Stopped."
            ctx.log(
                f"Asking Claude Code to read {len(positives)} positive / {len(negatives)}"
                " negative reviews (usually 1-2 minutes)"
            )
            prompt = build_reviews_prompt(game, positives, negatives)
        else:
            ctx.advance()
            ctx.log("Asking Claude Code: team size and development time (usually about a minute)")
            prompt = build_budget_prompt(game)
        try:
            result = run_claude_research(
                cli,
                prompt,
                kind=kind,
                model=model,
                max_budget_usd=max_budget_usd,
                timeout_seconds=timeout_seconds,
                cancel=ctx.cancel_event,
                runner=runner,
            )
        except ResearchError as exc:
            raise JobFailed(str(exc)) from exc
        ctx.advance()
        findings, warnings = sanitize(result.findings)
        if result.permission_denials:
            warnings.append(
                f"{result.permission_denials} tool calls were refused - web research incomplete"
            )
        if kind == "budget" and result.web_searches == 0:
            warnings.append("no web searches were made - team size and time are not sourced")
        store.add(
            ResearchRun(
                kind=kind,
                appid=game.appid,
                name=game.name,
                created_at=utc_now(),
                created_by=machine_id(),
                model=result.model,
                cost_usd=result.cost_usd,
                duration_seconds=result.duration_seconds,
                web_searches=result.web_searches,
                reviews_used=(
                    {"positive": len(positives), "negative": len(negatives)}
                    if kind == "reviews"
                    else {}
                ),
                warnings=warnings,
                findings=findings,
            )
        )
        ctx.advance()
        cost = f", ${result.cost_usd:.2f}" if result.cost_usd is not None else ""
        what = "Budget estimate" if kind == "budget" else "Review analysis"
        return f"{what} for {game.name} saved ({result.duration_seconds:.0f}s{cost})."

    return task
