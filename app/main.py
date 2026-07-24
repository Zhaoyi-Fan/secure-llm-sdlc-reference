from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import tools
from .agent import run_agent
from .auth import authenticate, create_token, decode_token
from .db import get_conn

app = FastAPI(title="SupportAssist", version="0.1.0")


class LoginRequest(BaseModel):
    username: str
    password: str


class RefundRequest(BaseModel):
    amount_cents: int


class NoteRequest(BaseModel):
    customer_note: str


class ChatRequest(BaseModel):
    message: str


def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")
    return {"id": int(payload["sub"]), "username": payload["username"]}


@app.post("/login")
def login(req: LoginRequest):
    user = authenticate(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="bad credentials")
    return {"access_token": create_token(user["id"], user["username"]), "token_type": "bearer"}


@app.get("/orders")
def list_orders(user: dict = Depends(current_user)):
    return tools.list_my_orders(user["id"])


@app.get("/orders/{order_id}")
def read_order(order_id: int, user: dict = Depends(current_user)):
    order = tools.get_order(order_id, user["id"])
    if order is None:
        raise HTTPException(status_code=404, detail="not found")
    return order


@app.post("/orders/{order_id}/refund")
def refund_order(order_id: int, req: RefundRequest, user: dict = Depends(current_user)):
    return tools.issue_refund(order_id, req.amount_cents, user["id"])


@app.post("/orders/{order_id}/note")
def set_note(order_id: int, req: NoteRequest, user: dict = Depends(current_user)):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET customer_note = ? WHERE id = ? AND user_id = ?",
            (req.customer_note, order_id, user["id"]),
        )
    return {"ok": True}


@app.get("/kb")
def kb_search(q: str, user: dict = Depends(current_user)):
    return tools.search_kb(q)


@app.post("/chat")
def chat(req: ChatRequest, user: dict = Depends(current_user)):
    return run_agent(req.message, user["id"])
