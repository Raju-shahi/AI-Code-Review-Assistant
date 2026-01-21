from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class ReviewCommentBase(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    message: str
    severity: str = Field(default="info")


class ReviewCommentCreate(ReviewCommentBase):
    pass


class ReviewComment(ReviewCommentBase):
    id: int

    class Config:
        from_attributes = True


class ReviewBase(BaseModel):
    repo: str
    pr_number: int
    summary: str
    status: str = "pending"


class ReviewCreate(ReviewBase):
    comments: List[ReviewCommentCreate] = Field(default_factory=list)


class Review(ReviewBase):
    id: str
    created_at: datetime
    comments: List[ReviewComment] = Field(default_factory=list)

    class Config:
        from_attributes = True
