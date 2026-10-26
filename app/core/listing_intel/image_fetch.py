import io
import os
import re
import time
import urllib.request
from urllib.parse import unquote, urlparse

from PIL import Image, ImageOps

ALLOWED_HOSTS = {"res.cloudinary.com", "salt.tikicdn.com"}
CHUNK = 65536
MAX_PIXELS = 25_000_000
USER_AGENT = "vietcraft-listing-intel/1.0"
MAX_URL = 2048
CLOUDINARY = "res.cloudinary.com"
UPLOAD_PATH = re.compile(r"/([^/]+)/image/upload/.")
ENCODED = re.compile(r"%2e|%2f|%5c", re.I)


def _host(url):
    p = urlparse(url)
    if p.scheme != "https" or p.port not in (None, 443) or p.username is not None or "\\" in url:
        return None
    return p.hostname


def _path_ok(host, path) -> bool:
    plain = unquote(path)
    if ENCODED.search(path) or ".." in plain or "fetch:" in plain.lower():
        return False
    if host != CLOUDINARY:
        return True
    m = UPLOAD_PATH.match(path)
    cloud = os.environ.get("CLOUDINARY_CLOUD_NAME")
    return m is not None and (not cloud or m.group(1) == cloud)


def allowed(url) -> bool:
    try:
        host = _host(url)
        return len(url) <= MAX_URL and host in ALLOWED_HOSTS and _path_ok(host, urlparse(url).path)
    except (ValueError, TypeError, AttributeError):
        return False


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _Redirect)


def _open(req, timeout):
    return _OPENER.open(req, timeout=timeout)


def _read_capped(resp, max_bytes, deadline):
    buf = bytearray()
    while len(buf) <= max_bytes:
        if time.monotonic() >= deadline:
            return None
        chunk = resp.read(min(CHUNK, max_bytes + 1 - len(buf)))
        if not chunk:
            return bytes(buf)
        buf += chunk
    return None


def _decode(data):
    im = Image.open(io.BytesIO(data))
    if im.width * im.height > MAX_PIXELS:
        return None
    rgba = ImageOps.exif_transpose(im).convert("RGBA")
    out = Image.new("RGB", rgba.size, "white")
    out.paste(rgba, mask=rgba.getchannel("A"))
    return out


def fetch(url, timeout=5, max_bytes=8_000_000):
    try:
        if not allowed(url):
            return None
        deadline = time.monotonic() + timeout
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
        with _open(req, timeout) as resp:
            if not allowed(resp.geturl() if hasattr(resp, "geturl") else url):
                return None
            if not str(resp.headers.get("Content-Type", "")).lower().startswith("image/"):
                return None
            length = resp.headers.get("Content-Length")
            if length is not None and int(length) > max_bytes:
                return None
            data = _read_capped(resp, max_bytes, deadline)
        return None if data is None else _decode(data)
    except Exception:
        return None
