import json
import sys
import urllib.error
import urllib.request

from bson import ObjectId

from app.api.v1._live import db_live
from app.core.f29 import scheduler
from scripts.f29.qa.edit_flow import BE, SHOP, login
from scripts.f29.register.learn import ROOT

OUT = ROOT / "notes/f29/qa/be_access.json"
DENIED = {403, 404}
CALLS = (("GET", "/seller/analytics/listings/{}/health", None),
         ("POST", "/seller/analytics/listings/{}/health/preview", {}))


def status(method, path, token, body):
    req = urllib.request.Request(BE + path, method=method, data=None if body is None else json.dumps(body).encode())
    req.add_header("content-type", "application/json")
    req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def leaked(text):
    try:
        data = json.loads(text).get("data")
    except (ValueError, AttributeError):
        return False
    return isinstance(data, dict) and "score" in data


def run():
    token = login()
    rows = list(db_live()["products"].find(scheduler.LOC_SP_THAT, {"shop_id": 1}))
    own = [str(p["_id"]) for p in rows if p.get("shop_id") == ObjectId(SHOP)]
    others = [str(p["_id"]) for p in rows if p.get("shop_id") != ObjectId(SHOP)]
    problems, seen = [], {}
    for pid in others + [str(ObjectId())]:
        for method, path, body in CALLS:
            code, text = status(method, path.format(pid), token, body)
            seen[code] = seen.get(code, 0) + 1
            if code not in DENIED or leaked(text):
                problems.append({"product_id": pid, "call": f"{method} {path}", "status": code})
    for pid in own:
        code, text = status("GET", f"/seller/analytics/listings/{pid}/health", token, None)
        if code != 200 or not leaked(text):
            problems.append({"product_id": pid, "call": "GET own health", "status": code})
    report = {"own": len(own), "others": len(others), "status_counts": seen, "problems": problems}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "problems"}), "problems", len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(run())
