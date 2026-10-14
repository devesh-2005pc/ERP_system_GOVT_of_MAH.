from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from app.auth.security import decode_token
from app.auth.deps import is_cross_department
from app.core.database import SessionLocal
from app.models.user import User
from app.ws.manager import manager

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4401)
        return

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == payload.get("sub"), User.is_active == True).first()  # noqa: E712
        if not user:
            await websocket.close(code=4401)
            return
        dept_code = user.department.code.value
        cross = is_cross_department(user)
    finally:
        db.close()

    await manager.connect(websocket, dept_code, cross)
    try:
        while True:
            await websocket.receive_text()  # client keepalive pings; we don't act on content
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
