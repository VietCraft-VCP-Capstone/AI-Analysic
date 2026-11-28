import os
import re
import time
import urllib.request
from urllib.parse import unquote, urlparse


ALLOWED_HOSTS = {"res.cloudinary.com", "salt.tikicdn.com", "down-vn.img.susercontent.com", "bizweb.dktcdn.net"}
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
