from contextlib import asynccontextmanager
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from . import tools
from .agent import run_agent
from .auth import authenticate, create_token, decode_token, validate_auth_config
from .config import settings
from .db import get_conn


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_auth_config()
    yield


app = FastAPI(title="SupportAssist", version="1.0.0", lifespan=lifespan)
OrderId = Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictRequest):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RefundRequest(StrictRequest):
    amount_cents: int = Field(ge=1, le=10_000_000)


class NoteRequest(StrictRequest):
    customer_note: str = Field(max_length=2_000)


class ChatRequest(StrictRequest):
    message: str = Field(min_length=1, max_length=4_000)


def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
        if not 1 <= user_id <= 9_223_372_036_854_775_807:
            raise ValueError("invalid subject")
        claimed_username = str(payload["username"])
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="authentication signing key is not configured",
        ) from exc
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username FROM users WHERE id = ? AND username = ?",
            (user_id, claimed_username),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return dict(row)


def _checked(result: dict) -> dict:
    if result.get("ok"):
        return result
    error = result.get("error", "request_rejected")
    if error == "order_not_found":
        raise HTTPException(status_code=404, detail="not found")
    if error in {"already_refunded", "order_not_refundable"}:
        raise HTTPException(status_code=409, detail=error)
    if error in {"invalid_amount", "amount_must_equal_order_total"}:
        raise HTTPException(status_code=422, detail=error)
    raise HTTPException(status_code=400, detail="request rejected")


@app.post("/login")
def login(req: LoginRequest):
    user = authenticate(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="bad credentials")
    try:
        token = create_token(user["id"], user["username"])
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="authentication signing key is not configured",
        ) from exc
    return {"access_token": token, "token_type": "bearer"}


@app.get("/orders")
def list_orders(user: dict = Depends(current_user)):
    return tools.list_my_orders(user["id"])


@app.get("/orders/{order_id}")
def read_order(order_id: OrderId, user: dict = Depends(current_user)):
    order = tools.get_order(order_id, user["id"])
    if order is None:
        raise HTTPException(status_code=404, detail="not found")
    return order


@app.get("/orders/{order_id}/refund-preview")
def refund_preview(order_id: OrderId, user: dict = Depends(current_user)):
    return _checked(tools.prepare_refund(order_id, user["id"]))


@app.post("/orders/{order_id}/refund")
def refund_order(
    order_id: OrderId,
    req: RefundRequest,
    user: dict = Depends(current_user),
):
    return _checked(tools.issue_refund(order_id, req.amount_cents, user["id"]))


@app.post("/orders/{order_id}/note")
def set_note(order_id: OrderId, req: NoteRequest, user: dict = Depends(current_user)):
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE orders SET customer_note = ? WHERE id = ? AND user_id = ?",
            (req.customer_note, order_id, user["id"]),
        )
    if cursor.rowcount != 1:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@app.get("/kb")
def kb_search(
    q: str = Query(min_length=1, max_length=200),
    user: dict = Depends(current_user),
):
    del user
    return tools.search_kb(q)


@app.post("/chat")
def chat(req: ChatRequest, user: dict = Depends(current_user)):
    try:
        return run_agent(
            req.message,
            user["id"],
            include_trace=settings.expose_debug_trace,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="local model timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="local model unavailable") from exc
