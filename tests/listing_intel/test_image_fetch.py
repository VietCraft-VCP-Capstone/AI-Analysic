import io
import time

import pytest
from PIL import Image

from app.core.listing_intel import image_fetch

URL = "https://res.cloudinary.com/a/image/upload/b.jpg"


def img_bytes(size=(200, 200), fmt="PNG", **kw):
    out = io.BytesIO()
    Image.new("RGB", size, (9, 9, 9)).save(out, format=fmt, **kw)
    return out.getvalue()


BODY = img_bytes()


class FakeResp:
    def __init__(self, ctype="image/png", body=b"", length=None, url=URL):
        self.headers = {"Content-Type": ctype}
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self._buf = io.BytesIO(body)
        self._url = url

    def read(self, n=-1):
        return self._buf.read(n)

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


class SlowResp(FakeResp):
    def read(self, n=-1):
        time.sleep(0.05)
        return b"0"


def patch_open(monkeypatch, resp):
    calls = []
    monkeypatch.setattr(image_fetch, "_open", lambda req, timeout: calls.append(req) or resp)
    return calls


def test_allowed_rejects_http_and_other_hosts():
    assert image_fetch.allowed("http://res.cloudinary.com/x.jpg") is False
    assert image_fetch.allowed("https://evil.com/a.jpg") is False
    assert image_fetch.allowed(URL) is True
    assert image_fetch.allowed("https://salt.tikicdn.com/a.jpg") is True


@pytest.mark.parametrize("url", [
    "https://res.cloudinary.com.evil.com/a.jpg",
    "https://evil.com/res.cloudinary.com/a.jpg",
    "https://res.cloudinary.com@evil.com/a.jpg",
    "https://u:p@res.cloudinary.com/x.jpg",
    "https://evil.com\\@res.cloudinary.com/x.jpg",
    "https://res.cloudinary.com:8443/a.jpg",
    "https://xres.cloudinary.com/a.jpg",
    "file:///etc/passwd", "", None,
])
def test_allowed_rejects_tricks(url):
    assert image_fetch.allowed(url) is False


def test_allowed_accepts_case_and_default_port():
    assert image_fetch.allowed("https://RES.Cloudinary.COM/a/image/upload/b.jpg") is True
    assert image_fetch.allowed("https://res.cloudinary.com:443/a/image/upload/b.jpg") is True


@pytest.mark.parametrize("path", [
    "/a/../other/image/upload/x.jpg", "/a/%2e%2e/other/image/upload/x.jpg", "/a/image/upload/..%2fx.jpg",
    "/a/image/fetch/https://evil.com/x.jpg", "/a/image/upload/l_fetch:aHR0cHM6Ly9ldmlsLmNvbQ==/x.jpg",
    "/a/image/private/x.jpg", "/a/video/upload/x.mp4", "/a/b.jpg", "/a/image/upload/",
])
def test_allowed_rejects_cloudinary_paths(path):
    assert image_fetch.allowed("https://res.cloudinary.com" + path) is False


def test_allowed_pins_cloud_name_and_length(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "a")
    assert image_fetch.allowed(URL) is True
    assert image_fetch.allowed("https://res.cloudinary.com/other/image/upload/b.jpg") is False
    assert image_fetch.allowed(URL + "x" * 2048) is False


@pytest.mark.parametrize("resp,kw", [
    (FakeResp("text/html", b"<html>"), {}),
    (FakeResp("image/png", b"x", length=9_000_000), {}),
    (FakeResp("image/png", BODY + b"0" * 5000), {"max_bytes": len(BODY)}),
    (FakeResp("image/png", BODY, url="https://evil.com/a.png"), {}),
    (SlowResp("image/png"), {"timeout": 0.2}),
])
def test_fetch_rejects(monkeypatch, resp, kw):
    patch_open(monkeypatch, resp)
    assert image_fetch.fetch(URL, **kw) is None


def test_fetch_stops_streaming_at_cap(monkeypatch):
    resp = FakeResp("image/png", BODY + b"0" * 5000)
    patch_open(monkeypatch, resp)
    image_fetch.fetch(URL, max_bytes=len(BODY))
    assert resp._buf.tell() == len(BODY) + 1


def test_fetch_accepts_exactly_max_bytes(monkeypatch):
    patch_open(monkeypatch, FakeResp("image/png", BODY))
    assert image_fetch.fetch(URL, max_bytes=len(BODY)).size == (200, 200)


def test_fetch_skips_network_for_disallowed_url(monkeypatch):
    calls = patch_open(monkeypatch, FakeResp())
    assert image_fetch.fetch("https://evil.com/a.jpg") is None
    assert calls == []


def test_fetch_never_raises(monkeypatch):
    def boom(*a, **kw):
        raise OSError("down")

    monkeypatch.setattr(image_fetch, "_open", boom)
    assert image_fetch.fetch(URL) is None
    patch_open(monkeypatch, FakeResp("image/png", b"not an image"))
    assert image_fetch.fetch(URL) is None


def test_fetch_returns_image_with_exif_orientation(monkeypatch):
    exif = Image.Exif()
    exif[0x0112] = 6
    patch_open(monkeypatch, FakeResp("image/jpeg", img_bytes((30, 20), "JPEG", exif=exif)))
    assert image_fetch.fetch(URL).size == (20, 30)
