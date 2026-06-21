import os
from pathlib import Path
from fastapi import FastAPI
from chainlit.utils import mount_chainlit

app = FastAPI()


@app.get("/healthz")
def healthz():
    return {"ok": True}


# (Phase 3: @app.post("/crm/events") goes HERE, before the mount.)

_TARGET = str(Path(__file__).with_name("cl_app.py"))
mount_chainlit(app=app, target=_TARGET, path="/chat")   # MUST be after the routes above


def main():
    import uvicorn
    uvicorn.run(app, host=os.environ.get("BRIDGE_HTTP_HOST", "127.0.0.1"),
                port=int(os.environ.get("BRIDGE_HTTP_PORT", "8800")))


if __name__ == "__main__":
    main()
