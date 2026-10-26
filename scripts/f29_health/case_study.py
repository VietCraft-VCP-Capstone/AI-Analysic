import argparse
import sys

from app.api.v1._live import LOC_SP_THAT
from app.core.f29.calculator import HealthScoreCalculator
from app.core.f29.preview import preview_health
from app.core.f29.todos import _vnd
from scripts.f29_health import report
from scripts.f29_health.report import CASE
from scripts.f29_health.run import REPORT

LEVER = {"image": "n_images", "description": "description_length", "tags": "n_tags"}
FIXED = ("Không có doanh số thật trên VietCraft; bảng chỉ cho thấy tính năng chạy đúng trên dữ liệu thật "
         "và lời khuyên làm điểm tăng đúng như hứa.")


def _lever_todo(result):
    return next((t for t in result["todos"] if t["code"] in (*LEVER, "price")), None)


def fix_top_todo(result):
    todo = _lever_todo(result)
    if todo is None:
        return {}
    if todo["code"] in LEVER:
        return {LEVER[todo["code"]]: todo["target"]}
    row = next(r for r in result["breakdown"] if r["key"] == "price")
    return {"price": row["reference"]["price"]}


def _action(todo, body):
    if todo is None:
        return "—"
    code = todo["code"]
    if code == "image":
        return f"Thêm ảnh lên {int(todo['target'])}"
    if code == "description":
        return f"Viết mô tả đủ {int(todo['target'])} ký tự"
    if code == "tags":
        return f"Chọn đủ {int(todo['target'])} tag"
    if code == "price" and body.get("price"):
        return f"Đặt giá bằng mức tham chiếu {_vnd(body['price'])}"
    return todo["message"]


def run(calc, product_ids, k=5):
    scored = [r for r in (calc.calculate(pid) for pid in product_ids) if r and "error" not in r]
    rows = []
    for cur in sorted(scored, key=lambda r: r["score"])[:k]:
        body = fix_top_todo(cur)
        todo = _lever_todo(cur)
        after = preview_health(calc, cur["product_id"], body)
        rows.append({"product_id": cur["product_id"], "title": cur["title"], "before": cur["score"],
                     "after": after["score"], "todo": todo, "action": _action(todo, body)})
    return rows


def _line(r):
    title = r["title"].replace("|", "\\|")
    return f"| {title} | {r['before']} | {r['action']} | {r['after']} |"


def markdown(rows, db):
    lines = [f"Dữ liệu: Mongo local, db `{db}` (chỉ đọc).", "", FIXED, "",
             "| Sản phẩm | Trước | Làm theo việc chỉnh được đầu tiên | Sau |", "|---|---|---|---|"]
    return "\n".join(lines + [_line(r) for r in rows])


def write(path, rows, db):
    section = f"{CASE}\n\n{markdown(rows, db)}"
    old = report._case_study(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace(old, section) if old else f"{text.rstrip()}\n\n{section}\n"
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    calc = HealthScoreCalculator()
    db = calc.live_db.name
    print(f"Đọc db: {db}")
    ids = [str(p["_id"]) for p in calc.live_db["products"].find(LOC_SP_THAT, {"_id": 1})]
    rows = run(calc, ids)
    if not rows:
        print("Không chấm được sản phẩm nào (kiểm tra trọng số và dữ liệu), không ghi báo cáo.", file=sys.stderr)
        sys.exit(2)
    if args.dry_run:
        print(markdown(rows, db))
        return
    write(REPORT, rows, db)
    print(f"Đã ghi {REPORT}")


if __name__ == "__main__":
    main()
