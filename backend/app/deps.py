from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import User


def current_user(x_user_id: int | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    """Demo sign-in: the browser sends the chosen demo customer's id. Replace with real auth before production."""
    if x_user_id is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    user = db.get(User, x_user_id)
    if user is None:
        raise HTTPException(401, "알 수 없는 사용자입니다.")
    return user
