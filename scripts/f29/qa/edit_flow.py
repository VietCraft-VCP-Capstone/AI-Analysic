import json
import os
import signal
import sys
import time
import urllib.request
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReadPreference

from app.api.v1._live import db_live
from app.core.f29 import constants
from app.core.f29.score.calculator import HealthScoreCalculator
from scripts.f29.register.learn import ROOT

BE = os.environ.get("BE_URL", "http://localhost:8081/api")
SHOP = "6ad3c8198dcc4a925b5594a5"
PRODUCT = os.environ.get("QA_PRODUCT", "6af87bada91f9c179a63436c")
BACKUP = ROOT / ".overnight/qa/backup"
OUT = ROOT / "notes/f29/qa/edit_flow.json"
EXTRA = (" Chất liệu: vải canvas dày dặn, khoá hợp kim không gỉ. Kích thước: bản rộng 3,5 cm,"
         " dài 110 cm, phù hợp vòng eo 70 đến 95 cm. Hướng dẫn bảo quản: giặt tay nhẹ, phơi nơi thoáng mát.")
IGNORED = {"updated_at", "__v"}
TOL = 0.1


def call(method, path, token=None, body=None):
    req = urllib.request.Request(BE + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def login():
    return call("POST", "/auth/login", body={"email": os.environ["T_EMAIL"], "password": os.environ["T_PASS"]})["token"]


def live_doc():
    return db_live()["products"].with_options(read_preference=ReadPreference.PRIMARY).find_one({"_id": ObjectId(PRODUCT)})


def backup():
    path = BACKUP / f"{PRODUCT}.json"
    if not path.exists():
        doc = live_doc()
        if str(doc["shop_id"]) != SHOP or (doc.get("description") or "").endswith(EXTRA):
            sys.exit("tin không thuộc shop thử hoặc đang mang đoạn mô tả kiểm thử: không tạo bản sao lưu")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, default=str, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, path)
    return json.loads(path.read_text("utf-8"))


def summary(d):
    desc = next(f for f in d["factors"] if f["key"] == "description")
    return {"score": d["score"], "desc_sub": desc["sub_score"], "desc_words": (d.get("content_snapshot") or {}).get("desc_words")}


def health(token):
    return summary(call("GET", f"/seller/analytics/listings/{PRODUCT}/health", token)["data"])


def wait_sync(since, limit=90):
    scores = constants.store_db()["listing_health_scores"]
    end = time.time() + limit
    while time.time() < end:
        doc = scores.find_one({"product_id": ObjectId(PRODUCT)}, sort=[("updated_at", -1)])
        at = doc and doc.get("updated_at")
        if at and at.replace(tzinfo=timezone.utc) > since:
            return round(time.time() - since.timestamp(), 1)
        time.sleep(2)
    return None


def edit(token, description):
    since = datetime.now(timezone.utc)
    call("PUT", f"/products/{PRODUCT}", token, {"description": description})
    return wait_sync(since)


def restore(token, original):
    for attempt in range(3):
        try:
            sync = edit(token, original)
            if live_doc()["description"] == original:
                return sync
        except Exception as e:
            print(f"khôi phục lần {attempt + 1} lỗi: {type(e).__name__}", file=sys.stderr)
        time.sleep(5)
    print(f"CẢNH BÁO: tin {PRODUCT} CHƯA được khôi phục, xem {BACKUP}", file=sys.stderr)
    return False


def drift(original):
    now = json.loads(json.dumps(live_doc(), default=str))
    return sorted(k for k in set(original) | set(now) if k not in IGNORED and original.get(k) != now.get(k))


def check_edit(base, after, problems):
    if (after["desc_words"] or 0) <= (base["desc_words"] or 0):
        problems.append(f"số từ mô tả không tăng sau khi sửa: {base} -> {after}")
    if after["desc_sub"] < base["desc_sub"] - TOL or after["score"] < base["score"] - TOL:
        problems.append(f"điểm giảm sau khi thêm mô tả: {base} -> {after}")
    if base["desc_sub"] < 100 - TOL and after["desc_sub"] <= base["desc_sub"]:
        problems.append(f"điểm mô tả không tăng: {base} -> {after}")


def run():
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(143))
    original = backup()["description"]
    token = login()
    report: dict = {"product_id": PRODUCT, "shop_id": SHOP}
    problems: list = []
    live = live_doc()["description"]
    if live != original and live != original + EXTRA:
        sys.exit("mô tả trên sàn khác bản sao lưu và không phải bản kiểm thử: dừng, không ghi gì")
    if live != original:
        report["restored_leftover"] = restore(token, original) is not False
    report["stored_before"] = health(token)
    report["fresh_before"] = base = summary(HealthScoreCalculator().calculate(PRODUCT))
    try:
        report["sync_after_edit_s"] = edit(token, original + EXTRA)
        report["after_edit"] = after = health(token)
        if report["sync_after_edit_s"] is None:
            problems.append("không thấy điểm tự cập nhật sau khi sửa tin")
        check_edit(base, after, problems)
    finally:
        report["sync_after_restore_s"] = sync = restore(token, original)
        report["restored"] = sync is not False
        try:
            report["after_restore"] = restored = health(token)
            if abs(restored["score"] - base["score"]) > TOL or restored["desc_words"] != base["desc_words"]:
                problems.append(f"điểm không trở về như trước: {base} -> {restored}")
        except Exception as e:
            problems.append(f"không đọc được điểm sau khôi phục: {type(e).__name__}")
        report["fields_changed_vs_backup"] = changed = drift(backup())
        if changed or not report["restored"]:
            problems.append(f"tin khác bản sao lưu ở trường: {changed}")
        report["problems"] = problems
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(run())
