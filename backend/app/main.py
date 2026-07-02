from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db, init_db
from app.models import Notification, ScanRun, Signal, Stock, User
from app.notifications import dispatch_queued_discord_notifications
from app.schemas import (
    LoginRequest,
    MockTradeCreate,
    MockTradeResponse,
    NotificationResponse,
    PortfolioResponse,
    RecommendationResponse,
    ScanRunResponse,
    SessionResponse,
    StockPerformanceResponse,
    StockResponse,
)
from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    check_login_allowed,
    clear_login_failures,
    clear_session,
    create_session,
    ensure_admin_user,
    normalize_login_identifier,
    record_login_failure,
    require_csrf,
    require_user,
    revoke_session,
    verify_value,
)
from app.seed import seed_reference_data
from app.services import (
    create_mock_trade,
    list_mock_trades,
    list_recommendations,
    portfolio_summary,
    run_scan,
    stock_performance,
)

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    with SessionLocal() as db:
        ensure_admin_user(db)
        seed_reference_data(db)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/login", response_model=SessionResponse)
def login(
    payload: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> SessionResponse:
    identifier = normalize_login_identifier(payload.email)
    check_login_allowed(identifier)
    user = db.scalar(select(User).where(User.email == identifier))
    if not user or not verify_value(payload.password, user.password_hash):
        record_login_failure(identifier)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    clear_login_failures(identifier)
    csrf_token = create_session(db, user, response)
    return SessionResponse(email=user.email, csrf_token=csrf_token)


@app.post(
    "/auth/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
def logout(
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> None:
    revoke_session(db, session_cookie)
    clear_session(response)


@app.get("/auth/session", response_model=SessionResponse)
def session(
    user: User = Depends(require_user),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
) -> SessionResponse:
    return SessionResponse(email=user.email, csrf_token=csrf_cookie or "")


@app.get("/stocks", response_model=list[StockResponse], dependencies=[Depends(require_user)])
def stocks(db: Session = Depends(get_db)) -> list[Stock]:
    return db.scalars(select(Stock).where(Stock.active.is_(True)).order_by(Stock.ticker)).all()


@app.get(
    "/recommendations",
    response_model=list[RecommendationResponse],
    dependencies=[Depends(require_user)],
)
def recommendations(
    signal: Signal | None = None,
    db: Session = Depends(get_db),
) -> list:
    return list_recommendations(db, signal)


@app.post(
    "/scan-runs",
    response_model=ScanRunResponse,
    dependencies=[Depends(require_user), Depends(require_csrf)],
)
def create_scan(db: Session = Depends(get_db)) -> ScanRun:
    return run_scan(db)


@app.get("/scan-runs", response_model=list[ScanRunResponse], dependencies=[Depends(require_user)])
def scan_runs(db: Session = Depends(get_db)) -> list[ScanRun]:
    return db.scalars(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(20)).all()


@app.post(
    "/mock-trades",
    response_model=MockTradeResponse,
    dependencies=[Depends(require_user), Depends(require_csrf)],
)
def add_trade(payload: MockTradeCreate, db: Session = Depends(get_db)) -> MockTradeResponse:
    try:
        trade = create_mock_trade(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    stock = db.get(Stock, trade.stock_id)
    assert stock is not None
    return MockTradeResponse(
        id=trade.id,
        ticker=stock.ticker,
        side=trade.side,
        quantity=trade.quantity,
        price=trade.price,
        executed_at=trade.executed_at,
        note=trade.note,
    )


@app.get(
    "/mock-trades", response_model=list[MockTradeResponse], dependencies=[Depends(require_user)]
)
def mock_trades(db: Session = Depends(get_db)) -> list[MockTradeResponse]:
    return list_mock_trades(db)


@app.get("/portfolio", response_model=PortfolioResponse, dependencies=[Depends(require_user)])
def portfolio(db: Session = Depends(get_db)) -> PortfolioResponse:
    return portfolio_summary(db)


@app.get(
    "/stocks/{ticker}/performance",
    response_model=StockPerformanceResponse,
    dependencies=[Depends(require_user)],
)
def performance(ticker: str, db: Session = Depends(get_db)) -> StockPerformanceResponse:
    try:
        return stock_performance(db, ticker)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get(
    "/notifications",
    response_model=list[NotificationResponse],
    dependencies=[Depends(require_user)],
)
def notifications(db: Session = Depends(get_db)) -> list[Notification]:
    return db.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(50)).all()


@app.post(
    "/notifications/dispatch",
    dependencies=[Depends(require_user), Depends(require_csrf)],
)
async def dispatch_notifications(db: Session = Depends(get_db)) -> dict[str, int]:
    return {"processed": await dispatch_queued_discord_notifications(db)}
