import os
from pathlib import Path
from fastapi import FastAPI
from chainlit.utils import mount_chainlit

_TOKEN = os.environ.get("CHAT_TOKEN", "")

class TokenBridge:
    """Accept ?chat_token= (or a chat_token cookie) and inject x-chat-token, so a plain
    iframe authenticates Chainlit's header_auth_callback (sets a cookie for the SPA's WS)."""
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            qs = dict(p.split("=", 1) for p in scope.get("query_string", b"").decode().split("&") if "=" in p)
            tok = qs.get("chat_token")
            if not tok:
                for k, v in scope.get("headers", []):
                    if k == b"cookie" and b"chat_token=" in v:
                        tok = v.decode().split("chat_token=", 1)[1].split(";", 1)[0]
            if tok:
                hdrs = [(k, v) for k, v in scope["headers"] if k != b"x-chat-token"]
                hdrs.append((b"x-chat-token", tok.encode()))
                scope = {**scope, "headers": hdrs}
                async def send2(m):
                    if m["type"] == "http.response.start" and tok:
                        m = {**m, "headers": [*m.get("headers", []), (b"set-cookie", f"chat_token={tok}; Path=/; HttpOnly; SameSite=None; Secure".encode())]}
                    await send(m)
                return await self.app(scope, receive, send2)
        return await self.app(scope, receive, send)

app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"ok": True}

_TARGET = str(Path(__file__).with_name("cl_app.py"))
mount_chainlit(app=app, target=_TARGET, path="/chat")
app.add_middleware(TokenBridge)

def main():
    import uvicorn
    uvicorn.run(app, host=os.environ.get("CHAT_HOST", "127.0.0.1"), port=int(os.environ.get("CHAT_PORT", "8801")))

if __name__ == "__main__":
    main()
