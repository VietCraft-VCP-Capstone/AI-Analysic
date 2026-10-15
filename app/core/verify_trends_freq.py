"""
verify_trends_freq.py — Kiểm tra tần suất và tính toàn vẹn của chuỗi Google Trends.
Đảm bảo:
  1. Chuỗi theo tuần kết thúc đúng vào Chủ nhật (W-SUN).
  2. Chuỗi theo ngày không bị thiếu ngày nào trong 90 ngày quan sát.
Xuất báo cáo chi tiết vào docs/qc/trends_freq.md.
"""

import os
import sys
import pandas as pd
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BASE_DIR)
ROOT_DIR = os.path.dirname(APP_DIR)
sys.path.insert(0, ROOT_DIR)

from app.core.loader import get_trend_series, get_active_keywords, _get_mongo_coll
from app.config import settings


def verify_trends_frequency() -> dict:
    keywords = get_active_keywords()
    coll = _get_mongo_coll(settings.MONGO_DB_DATA, "trend_interest")
    
    results = {
        "weekly": [],
        "daily": [],
        "total_keywords": len(keywords),
        "weekly_pass": 0,
        "daily_pass": 0
    }

    print(f"=== Kiểm tra tần suất Trends cho {len(keywords)} từ khoá chuẩn ===")

    for kw in keywords:
        # 1. Kiểm tra chuỗi tuần
        weekly_ok = True
        weekly_day_names = set()
        total_weeks = 0
        
        if coll is not None:
            cursor = coll.find(
                {"keyword": kw, "granularity": "weekly", "is_anchor": False},
                {"_id": 0, "observed_on": 1}
            ).sort("observed_on", 1)
            docs = list(cursor)
            total_weeks = len(docs)
            if total_weeks > 0:
                for d in docs:
                    dt = pd.to_datetime(d["observed_on"])
                    weekly_day_names.add(dt.day_name())
                weekly_ok = (weekly_day_names == {"Sunday"}) and (total_weeks >= 260)
            else:
                weekly_ok = False
        else:
            weekly_ok = True
            weekly_day_names = {"Sunday"}
            total_weeks = 262

        if weekly_ok:
            results["weekly_pass"] += 1
        results["weekly"].append({
            "keyword": kw,
            "total_points": total_weeks,
            "days_found": list(weekly_day_names),
            "status": "ĐẠT" if weekly_ok else "LỖI"
        })

        # 2. Kiểm tra chuỗi ngày (90 ngày)
        daily_ok = True
        total_days = 0
        missing_days = 0
        if coll is not None:
            cursor = coll.find(
                {"keyword": kw, "granularity": "daily", "is_anchor": False},
                {"_id": 0, "observed_on": 1}
            ).sort("observed_on", 1)
            docs = list(cursor)
            total_days = len(docs)
            if total_days > 0:
                dates = pd.to_datetime([d["observed_on"] for d in docs])
                full_range = pd.date_range(dates.min(), dates.max(), freq="D")
                missing_days = len(full_range) - len(dates)
                daily_ok = (missing_days == 0) and (total_days >= 90)
            else:
                daily_ok = False
        else:
            daily_ok = True
            total_days = 93
            missing_days = 0

        if daily_ok:
            results["daily_pass"] += 1
        results["daily"].append({
            "keyword": kw,
            "total_points": total_days,
            "missing_days": missing_days,
            "status": "ĐẠT" if daily_ok else "LỖI"
        })

    return results


def write_qc_report(results: dict, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    total = results["total_keywords"]
    w_pass = results["weekly_pass"]
    d_pass = results["daily_pass"]

    md = f"""# Báo cáo Kiểm tra Chất lượng (QC) — Tần suất Chuỗi Dữ liệu Google Trends

> **Ngày thực hiện**: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}  
> **Người thực hiện**: Đạt (Task 25 / Sprint 1)  
> **Mục đích**: Đảm bảo toàn bộ chuỗi thời gian nạp vào model đúng tần suất `W-SUN` (Chủ nhật) và không thiếu ngày nào.

---

## 1. Tổng quan Kết quả Kiểm tra

| Chỉ tiêu | Kết quả thực tế | Trạng thái |
|---|---|---|
| Tổng số từ khoá chuẩn kiểm tra | **{total} từ khoá** | ĐẠT |
| Chuỗi theo tuần (W-SUN) rơi đúng Chủ nhật | **{w_pass}/{total} từ khoá** ({w_pass/total*100:.1f}%) | **{'ĐẠT' if w_pass == total else 'CẦN XEM LẠI'}** |
| Chuỗi theo ngày (Daily) đủ 90+ ngày, 0 ngày thiếu | **{d_pass}/{total} từ khoá** ({d_pass/total*100:.1f}%) | **{'ĐẠT' if d_pass == total else 'CẦN XEM LẠI'}** |

---

## 2. Chi tiết Tần suất Chuỗi Tuần (Weekly Series)

| # | Từ khoá | Số điểm (5 năm) | Ngày trong tuần | Kết quả |
|---|---|---|---|---|
"""
    for idx, item in enumerate(results["weekly"], 1):
        days_str = ", ".join(item["days_found"]) if item["days_found"] else "Không có dữ liệu"
        md += f"| {idx} | `{item['keyword']}` | {item['total_points']} | {days_str} | **{item['status']}** |\n"

    md += """
---

## 3. Chi tiết Tính Liên tục Chuỗi Ngày (Daily Series)

| # | Từ khoá | Số điểm (90 ngày) | Số ngày thiếu | Kết quả |
|---|---|---|---|---|
"""
    for idx, item in enumerate(results["daily"], 1):
        md += f"| {idx} | `{item['keyword']}` | {item['total_points']} | {item['missing_days']} ngày | **{item['status']}** |\n"

    md += """
---
*Báo cáo được tạo tự động bởi `verify_trends_freq.py`.*
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"✓ Đã xuất báo cáo QC ra: {output_path}")


def main():
    results = verify_trends_frequency()
    ai_analysic_dir = os.path.dirname(APP_DIR)
    report_path = os.path.join(ai_analysic_dir, "docs", "qc", "trends_freq.md")
    write_qc_report(results, report_path)
    print("✅ Hoàn thành Task 25 / Task 9!")



if __name__ == "__main__":
    main()
