"""Research job: helpful reviews (2 Steam requests) -> Claude Code CLI -> validated findings."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from app.db.connection import utc_now
from app.domain.models import Game
from app.domain.research import sanitize
from app.jobs.runner import JobContext, JobFailed
from app.providers.steam_reviews import ReviewSample, fetch_review_samples
from app.research.claude_cli import (
    ResearchError,
    Runner,
    build_prompt,
    run_claude_research,
    subprocess_runner,
)
from app.storage.files import machine_id
from app.storage.research import ResearchRun, ResearchStore

REVIEWS_PER_SIDE = 40


def make_research_task(
    game: Game,
    cli: Path,
    store: ResearchStore,
    *,
    model: str,
    max_budget_usd: float,
    timeout_seconds: float,
    runner: Runner = subprocess_runner,
) -> Callable[[JobContext], str]:
    def task(ctx: JobContext) -> str:
        ctx.set_total(3)
        ctx.log("Reading the most helpful Steam reviews")
        positives: list[ReviewSample] = (
            ctx.call(
                "reviews",
                "positive reviews",
                partial(
                    fetch_review_samples, appid=game.appid, side="positive", count=REVIEWS_PER_SIDE
                ),
            )
            or []
        )
        negatives: list[ReviewSample] = (
            ctx.call(
                "reviews",
                "negative reviews",
                partial(
                    fetch_review_samples, appid=game.appid, side="negative", count=REVIEWS_PER_SIDE
                ),
            )
            or []
        )
        ctx.advance()
        if ctx.cancelled:
            return "Stopped."
        ctx.log(
            f"Asking Claude Code: web research + {len(positives)} positive / {len(negatives)}"
            " negative reviews (usually 2-5 minutes)"
        )
        try:
            result = run_claude_research(
                cli,
                build_prompt(game, positives, negatives),
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
        if result.web_searches == 0:
            warnings.append("no web searches were made - team size and time are not sourced")
        store.add(
            ResearchRun(
                appid=game.appid,
                name=game.name,
                created_at=utc_now(),
                created_by=machine_id(),
                model=result.model,
                cost_usd=result.cost_usd,
                duration_seconds=result.duration_seconds,
                web_searches=result.web_searches,
                reviews_used={"positive": len(positives), "negative": len(negatives)},
                warnings=warnings,
                findings=findings,
            )
        )
        ctx.advance()
        cost = f", ${result.cost_usd:.2f}" if result.cost_usd is not None else ""
        return f"Research for {game.name} saved ({result.duration_seconds:.0f}s{cost})."

    return task
