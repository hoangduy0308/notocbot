"""
Dashboard router - API endpoints for NoTocBot web dashboard.
"""

import os
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.config import AsyncSessionLocal
from src.database.models import User
from src.security.web_auth import (
    TelegramLoginData,
    SessionTokenError,
    verify_telegram_login,
    create_session_token,
    verify_session_token,
)
from src.services.dashboard_stats import (
    get_user_summary,
    get_debt_by_person,
    get_transaction_history_for_user,
    get_monthly_trends,
)
from src.services.user_service import get_or_create_user


JWT_SECRET = os.getenv("JWT_SECRET", "your-default-secret-key-change-in-production")

templates = Jinja2Templates(directory="src/web/templates")

router = APIRouter()


class TelegramLoginRequest(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str]
    full_name: str


class LoginResponse(BaseModel):
    success: bool
    user: UserResponse


class LogoutResponse(BaseModel):
    success: bool


class UserSummaryResponse(BaseModel):
    total_net_balance: Decimal
    total_positive: Decimal
    total_negative: Decimal
    debtor_count: int
    transaction_count: int

    class Config:
        from_attributes = True


class DebtByPersonResponse(BaseModel):
    debtor_id: int
    name: str
    balance: Decimal

    class Config:
        from_attributes = True


class TransactionResponse(BaseModel):
    id: int
    debtor_id: int
    debtor_name: str
    amount: Decimal
    type: str
    note: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class MonthlyTrendResponse(BaseModel):
    month: str
    net_change: Decimal

    class Config:
        from_attributes = True


async def get_db_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session)
) -> User:
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = verify_session_token(token, JWT_SECRET)
        user = await get_user_by_telegram_id(session, payload["user_id"])
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid session")


async def get_current_user_optional(
    request: Request,
    session: AsyncSession = Depends(get_db_session)
) -> Optional[User]:
    token = request.cookies.get("session_token")
    if not token:
        return None
    try:
        payload = verify_session_token(token, JWT_SECRET)
        return await get_user_by_telegram_id(session, payload["user_id"])
    except ValueError:
        return None


@router.post("/auth/telegram-login", response_model=LoginResponse)
async def telegram_login(
    data: TelegramLoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session)
):
    try:
        login_data = verify_telegram_login(data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    full_name = data.first_name
    if data.last_name:
        full_name = f"{data.first_name} {data.last_name}"

    user = await get_or_create_user(
        session=session,
        telegram_id=login_data.id,
        full_name=full_name,
        username=data.username
    )
    await session.commit()

    token = create_session_token(login_data, JWT_SECRET)

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )

    return LoginResponse(
        success=True,
        user=UserResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            full_name=user.full_name
        )
    )


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(response: Response):
    response.delete_cookie(key="session_token")
    return LogoutResponse(success=True)


@router.get("/api/dashboard/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        full_name=user.full_name
    )


@router.get("/api/dashboard/summary", response_model=UserSummaryResponse)
async def get_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    summary = await get_user_summary(session, user.id)
    return UserSummaryResponse(
        total_net_balance=summary.total_net_balance,
        total_positive=summary.total_positive,
        total_negative=summary.total_negative,
        debtor_count=summary.debtor_count,
        transaction_count=summary.transaction_count
    )


@router.get("/api/dashboard/debt-by-person", response_model=list[DebtByPersonResponse])
async def get_debt_by_person_endpoint(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    debts = await get_debt_by_person(session, user.id)
    return [
        DebtByPersonResponse(
            debtor_id=d.debtor_id,
            name=d.name,
            balance=d.balance
        )
        for d in debts
    ]


@router.get("/api/dashboard/history", response_model=list[TransactionResponse])
async def get_history(
    debtor_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    transactions = await get_transaction_history_for_user(
        session, user.id, debtor_id=debtor_id, limit=limit
    )
    return [
        TransactionResponse(
            id=t.id,
            debtor_id=t.debtor_id,
            debtor_name=t.debtor_name,
            amount=t.amount,
            type=t.type,
            note=t.note,
            created_at=t.created_at
        )
        for t in transactions
    ]


@router.get("/api/dashboard/monthly-trends", response_model=list[MonthlyTrendResponse])
async def get_monthly_trends_endpoint(
    months: int = Query(default=12, ge=1, le=36),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    trends = await get_monthly_trends(session, user.id, months=months)
    return [
        MonthlyTrendResponse(month=t.month, net_change=t.net_change)
        for t in trends
    ]


@router.get("/dashboard")
async def dashboard_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
):
    if not user:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user}
    )


@router.get("/dashboard/login")
async def login_page(request: Request):
    bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "NoTocBot")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "bot_username": bot_username}
    )
