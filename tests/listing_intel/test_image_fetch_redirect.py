import http.server
import importlib
import io
import threading
import urllib.request

import pytest
from PIL import Image

from app.core.listing_intel import image_fetch

URL = "https://res.cloudinary.com/a/image/upload/b.jpg"
OUT = io.BytesIO()
Image.new("RGB", (200, 200), (9, 9, 9)).save(OUT, format="PNG")
BODY = OUT.getvalue()


def test_redirect_handler_only_follows_allowed():
    h, req = image_fetch._Redirect(), urllib.request.Request(URL)
    for bad in ("https://evil.com/a.jpg", "http://res.cloudinary.com/a.jpg", "ftp://res.cloudinary.com/a"):
        assert h.redirect_request(req, io.BytesIO(), 302, "Found", {}, bad) is None
    new = h.redirect_request(req, io.BytesIO(), 302, "Found", {}, "https://salt.tikicdn.com/a.jpg")
    assert isinstance(new, urllib.request.Request)


def test_opener_ignores_proxy_env(monkeypatch):
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:1")
    assert any(getattr(h, "proxies", None) for h in urllib.request.build_opener().handlers)
    fresh = importlib.reload(image_fetch)
    assert not any(getattr(h, "proxies", None) for h in fresh._OPENER.handlers)


class Handler(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):
        Handler.hits.append(self.server.server_port)
        if self.path == "/redir":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.other}/x.png")
            return self.end_headers()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *args):
        pass


@pytest.fixture
def local(monkeypatch):
    a, b = (http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) for _ in range(2))
    a.other, Handler.hits = b.server_port, []
    for s in (a, b):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{a.server_port}"
    monkeypatch.setattr(image_fetch, "allowed", lambda u: u.startswith(base))
    yield base, b.server_port
    for s in (a, b):
        s.shutdown()
        s.server_close()


def test_real_http_fetch_and_redirect_blocked(local):
    base, other = local
    assert image_fetch.fetch(base + "/img").size == (200, 200)
    assert image_fetch.fetch(base + "/redir") is None
    assert other not in Handler.hits
