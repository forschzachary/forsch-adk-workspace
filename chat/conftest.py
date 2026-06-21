import os
# tests import http.py -> mount_chainlit, which reads CHAINLIT_AUTH_SECRET at import time.
os.environ.setdefault("CHAINLIT_AUTH_SECRET", "test")
