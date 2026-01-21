from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

from .database import AsyncSessionLocal, get_session, init_db
from .models import Review as ReviewModel
from .models import ReviewComment as ReviewCommentModel
from .schemas import Review, ReviewCreate
from .services.github_app import (
    fetch_pull_files,
    fetch_pull_request,
    get_installation_token,
    get_webhook_secret,
    post_review_summary,
    verify_github_signature,
)
from .services.llm import generate_review

load_dotenv()

app = FastAPI(title="AI Code Review Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}


@app.get("/api/reviews", response_model=List[Review])
async def list_reviews(session: AsyncSession = Depends(get_session)) -> List[Review]:
    result = await session.execute(select(ReviewModel).order_by(ReviewModel.created_at.desc()))
    reviews = result.scalars().unique().all()
    return reviews


@app.post("/api/reviews", response_model=Review)
async def create_review(
    payload: ReviewCreate, session: AsyncSession = Depends(get_session)
) -> Review:
    review = ReviewModel(
        repo=payload.repo,
        pr_number=payload.pr_number,
        status=payload.status,
        summary=payload.summary,
    )
    session.add(review)
    await session.flush()

    for comment in payload.comments:
        session.add(
            ReviewCommentModel(
                review_id=review.id,
                file_path=comment.file_path,
                line_start=comment.line_start,
                line_end=comment.line_end,
                message=comment.message,
                severity=comment.severity,
            )
        )

    await session.commit()
    await session.refresh(review)
    return review


@app.post("/api/reviews/seed", response_model=Review)
async def seed_review(session: AsyncSession = Depends(get_session)) -> Review:
    existing = await session.execute(select(ReviewModel).limit(1))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Reviews already exist")

    review = ReviewModel(
        repo="octo-org/example-repo",
        pr_number=42,
        status="completed",
        summary="Sample AI review: Checked diff for issues.",
    )
    session.add(review)
    await session.flush()

    session.add_all(
        [
            ReviewCommentModel(
                review_id=review.id,
                file_path="src/api/service.py",
                line_start=18,
                line_end=22,
                message="Potential null dereference when user is None.",
                severity="warning",
            ),
            ReviewCommentModel(
                review_id=review.id,
                file_path="src/utils/date.ts",
                line_start=4,
                line_end=4,
                message="Consider UTC parsing to avoid timezone issues.",
                severity="info",
            ),
        ]
    )

    await session.commit()
    await session.refresh(review)
    return review


async def process_pull_request_review(
    review_id: str,
    repo_full_name: str,
    pr_number: int,
    installation_id: int,
) -> None:
    async with AsyncSessionLocal() as session:
        review = await session.get(ReviewModel, review_id)
        if not review:
            return
        review.status = "in_progress"
        await session.commit()

    try:
        token = await get_installation_token(installation_id)
        pr = await fetch_pull_request(repo_full_name, pr_number, token)
        files = await fetch_pull_files(repo_full_name, pr_number, token)
        llm_result = await generate_review(pr, files)

        summary = llm_result.get("summary", "Review completed.")
        comments = llm_result.get("comments", [])
        summary_lines = ["## AI Code Review Summary", summary, "", "### Findings"]
        if comments:
            for comment in comments:
                summary_lines.append(
                    f"- **{comment.get('severity', 'info').upper()}** {comment.get('file_path')}: {comment.get('message')}"
                )
        else:
            summary_lines.append("- No blocking issues found.")

        review_body = "\n".join(summary_lines)
        await post_review_summary(repo_full_name, pr_number, token, review_body)

        async with AsyncSessionLocal() as session:
            review = await session.get(ReviewModel, review_id)
            if review:
                review.status = "completed"
                review.summary = summary
                for comment in comments:
                    session.add(
                        ReviewCommentModel(
                            review_id=review.id,
                            file_path=comment.get("file_path", "unknown"),
                            line_start=int(comment.get("line_start", 0)),
                            line_end=int(comment.get("line_end", 0)),
                            message=comment.get("message", ""),
                            severity=comment.get("severity", "info"),
                        )
                    )
                await session.commit()
    except Exception as exc:
        async with AsyncSessionLocal() as session:
            review = await session.get(ReviewModel, review_id)
            if review:
                review.status = "failed"
                review.summary = f"Review failed: {exc}"
                await session.commit()


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict:
    payload = await request.body()
    secret = get_webhook_secret() or ""
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_github_signature(secret, payload, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    body = await request.json()
    if event != "pull_request":
        return {"received": True, "skipped": True, "event": event}

    action = body.get("action")
    if action not in {"opened", "synchronize", "reopened"}:
        return {"received": True, "skipped": True, "event": event, "action": action}

    repo = body.get("repository", {}).get("full_name", "unknown")
    pr_number = body.get("pull_request", {}).get("number", 0)
    installation_id = body.get("installation", {}).get("id")
    if not installation_id:
        raise HTTPException(status_code=400, detail="Missing installation id")

    review = ReviewModel(
        repo=repo,
        pr_number=pr_number,
        status="queued",
        summary=f"Webhook event: {event} ({action})",
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)

    background_tasks.add_task(
        process_pull_request_review, review.id, repo, pr_number, installation_id
    )

    return {"received": True, "event": event, "review_id": review.id}
