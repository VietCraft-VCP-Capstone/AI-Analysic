#!/usr/bin/env python3
"""
run.py — Cài đặt và chạy dự án bằng MỘT lệnh. Windows, macOS, Linux như nhau.

    python run.py

Chạy đi chạy lại bao nhiêu lần cũng được: mỗi bước tự kiểm "đã xong chưa", xong
rồi thì bỏ qua. Lần đầu mất ~5 phút (cài thư viện + dựng dữ liệu), lần sau vài giây.

    python run.py                 cài những gì thiếu, rồi bật server
    python run.py --check         chỉ kiểm, không cài, không bật server
    python run.py --setup-only    cài xong thì dừng, không bật server
    python run.py --rebuild       dựng lại toàn bộ bảng mart (GHI lên Atlas)
    python run.py --port 8080     đổi cổng
    python run.py --no-dev-auth   KHÔNG tắt xác thực (mọi endpoint sẽ trả 401)

Script này chạy bằng Python HỆ THỐNG (chưa cần môi trường ảo) nên tuyệt đối không
import thư viện của dự án ở đầu file — nó phải chạy được trên máy trắng.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

GOC = Path(__file__).resolve().parent
VENV = GOC / ".venv"
PY_TOI_THIEU = (3, 10)

# Windows để python.exe trong .venv\Scripts\, Unix để trong .venv/bin/.
# Đây là khác biệt DUY NHẤT giữa hai hệ điều hành trong cả script này.
WIN = platform.system() == "Windows"
PY_VENV = VENV / ("Scripts" if WIN else "bin") / ("python.exe" if WIN else "python")

XANH, VANG, DO, XAM, HET = "\033[92m", "\033[93m", "\033[91m", "\033[90m", "\033[0m"
if WIN and not os.environ.get("WT_SESSION"):
    XANH = VANG = DO = XAM = HET = ""      # Command Prompt cũ không hiểu mã màu


def ok(msg):   print(f"  {XANH}[OK]{HET}   {msg}")
def bo(msg):   print(f"  {XAM}[BO QUA]{HET} {msg}")
def lam(msg):  print(f"  {VANG}[LAM]{HET}  {msg}")
def loi(msg):  print(f"  {DO}[LOI]{HET}  {msg}")
def muc(n, t): print(f"\n{'='*70}\n  BUOC {n} — {t}\n{'='*70}")


def chay(cmd, **kw):
    """Gọi lệnh con. Không dùng shell=True: đường dẫn có dấu cách trên Windows
    (vd. C:\\Users\\Nguyen Van A\\) sẽ bị tách sai."""
    return subprocess.run([str(c) for c in cmd], cwd=GOC, **kw)


# ---------------------------------------------------------------------------

def buoc_1_python():
    muc(1, "Kiem phien ban Python")
    if sys.version_info < PY_TOI_THIEU:
        loi(f"Can Python >= {'.'.join(map(str, PY_TOI_THIEU))}, dang co {platform.python_version()}")
        print("\n  Tai tai: https://www.python.org/downloads/")
        if WIN:
            print("  Luu y Windows: nho TICK 'Add Python to PATH' luc cai.")
        sys.exit(1)
    ok(f"Python {platform.python_version()} tren {platform.system()}")


def buoc_2_venv(chi_kiem):
    muc(2, "Moi truong ao (.venv)")
    if PY_VENV.exists():
        bo(f"Da co: {PY_VENV.relative_to(GOC)}")
    elif chi_kiem:
        loi("Chua co .venv"); return False
    else:
        lam("Dang tao .venv ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
        ok("Da tao .venv")

    # Thư viện: kiểm bằng cách import thật, không đọc pip list — pip list chậm và
    # không biết được thư viện có nạp nổi hay không.
    thu = chay([PY_VENV, "-c", "import fastapi, pymongo, pandas, statsmodels, uvicorn"],
               capture_output=True)
    if thu.returncode == 0:
        bo("Thu vien da day du")
        return True
    if chi_kiem:
        loi("Thieu thu vien"); return False

    lam("Dang cai thu vien (lan dau mat ~2-3 phut) ...")
    chay([PY_VENV, "-m", "pip", "install", "--upgrade", "-q", "pip"])
    r = chay([PY_VENV, "-m", "pip", "install", "-q", "-r", "requirements.txt"])
    if r.returncode != 0:
        loi("Cai thu vien that bai — xem thong bao o tren")
        sys.exit(1)
    ok("Da cai xong thu vien")
    return True


def buoc_3_env(chi_kiem):
    muc(3, "File cau hinh app/.env")
    env, mau = GOC / "app" / ".env", GOC / ".env.example"
    if not env.exists():
        if chi_kiem:
            loi("Chua co app/.env"); return False
        if not mau.exists():
            loi("Khong tim thay .env.example"); sys.exit(1)
        env.parent.mkdir(exist_ok=True)
        env.write_text(mau.read_text(encoding="utf-8"), encoding="utf-8")
        lam(f"Da tao app/.env tu .env.example")

    noi_dung = env.read_text(encoding="utf-8")
    # Kiểm có URI THẬT chưa, không chỉ kiểm dòng có tồn tại: bản mẫu cũng có dòng
    # MONGODB_URI nhưng giá trị là <user>:<password>, điền vậy thì vẫn hỏng.
    that = [d for d in noi_dung.splitlines()
            if d.strip().startswith("MONGODB_URI=") and "<" not in d and len(d.strip()) > 20]
    if not that:
        loi("app/.env chua co MONGODB_URI that")
        print(f"\n  Mo file nay ra va dien chuoi ket noi Atlas:\n    {env}")
        print("  Xin chuoi ket noi tu nguoi giu Atlas.\n")
        return False
    ok("app/.env da co MONGODB_URI")
    return True


def buoc_4_mart(chi_kiem, dung_lai):
    muc(4, "Bang mart — du lieu cho API doc")
    ma = ("import json,sys;"
          "sys.path.insert(0,'.');"
          "from pymongo import MongoClient;"
          "from app.config import settings;"
          "from app.core.writer import MART_SCHEMA as M;"
          "c=MongoClient(settings.MONGO_URI,serverSelectionTimeoutMS=8000);"
          "d=c[settings.MONGO_DB_SEED];"
          "print(json.dumps({t:d[t].estimated_document_count() for t in M}))")
    r = chay([PY_VENV, "-c", ma], capture_output=True, text=True)
    if r.returncode != 0:
        loi("Khong noi duoc MongoDB")
        print(f"  {(r.stderr or '').strip().splitlines()[-1] if r.stderr else ''}")
        print("  Kiem lai MONGODB_URI trong app/.env, va kiem mang.")
        return False

    dem = json.loads(r.stdout.strip().splitlines()[-1])
    rong = sorted(t for t, n in dem.items() if n == 0)

    if not rong and not dung_lai:
        bo(f"Ca {len(dem)} bang deu co du lieu ({sum(dem.values()):,} dong)")
        return True
    if chi_kiem:
        loi(f"{len(rong)} bang con rong: {', '.join(rong)}")
        print("  Khac phuc: python run.py   (hoac: python -m app.core.build_marts --all)")
        return False

    if dung_lai:
        lam("Dung LAI toan bo mart (--rebuild) ...")
    else:
        lam(f"{len(rong)} bang con rong, dang dung: {', '.join(rong)}")
    print(f"  {XAM}Job nay GHI len cum Atlas M0 512MB DUNG CHUNG ca nhom (~15MB). ~3 phut.{HET}")

    r = chay([PY_VENV, "-m", "app.core.build_marts", "--all"])
    if r.returncode != 0:
        loi("Dung mart that bai"); return False
    ok("Da dung xong mart")
    return True


def buoc_5_kiem():
    muc(5, "Chay bo kiem")
    tot = True
    for ten, cmd in [("Hop dong API (12 test)", [PY_VENV, "tests/test_api_contract.py"]),
                     ("Hop dong mart (9 bang)", [PY_VENV, "scripts/validate_mart.py", "--all", "--offline"])]:
        r = chay(cmd, capture_output=True, text=True)
        (ok if r.returncode == 0 else loi)(f"{ten}: {(r.stdout or '').strip().splitlines()[-1] if r.stdout else 'khong co ket qua'}")
        tot &= r.returncode == 0
    return tot


def buoc_6_server(cong, tat_xac_thuc):
    muc(6, "Bat server")
    moi = os.environ.copy()
    if tat_xac_thuc:
        moi.setdefault("DEV_SHOP_ID", "shp_00017")
        print(f"  {VANG}Xac thuc DANG TAT (DEV_SHOP_ID=shp_00017).{HET}")
        print(f"  {XAM}SPEC-04 (JWT) chua xong nen chua co token that. Dung --no-dev-auth de bat lai.{HET}")
    print(f"\n  Mo trinh duyet:  {XANH}http://localhost:{cong}/docs{HET}")
    print(f"  {XAM}Dung server: Ctrl+C{HET}\n")
    try:
        chay([PY_VENV, "-m", "uvicorn", "app.main:app", "--reload", "--port", str(cong)], env=moi)
    except KeyboardInterrupt:
        print("\n  Da dung server.")


def main():
    a = argparse.ArgumentParser(description="Cai dat va chay VietCraft AI Analytics")
    a.add_argument("--check", action="store_true", help="chi kiem, khong cai gi")
    a.add_argument("--setup-only", action="store_true", help="cai xong thi dung")
    a.add_argument("--rebuild", action="store_true", help="dung lai toan bo mart")
    a.add_argument("--port", type=int, default=8000)
    a.add_argument("--no-dev-auth", action="store_true", help="KHONG tat xac thuc")
    x = a.parse_args()

    print(f"\n{'='*70}\n  VietCraft AI Analytics — {'KIEM TRA' if x.check else 'CAI DAT & CHAY'}"
          f"\n  {GOC}\n{'='*70}")

    buoc_1_python()
    if not buoc_2_venv(x.check): sys.exit(1)
    if not buoc_3_env(x.check):  sys.exit(1)
    if not buoc_4_mart(x.check, x.rebuild): sys.exit(1)
    tot = buoc_5_kiem()

    if x.check:
        print(f"\n{'='*70}")
        print(f"  {XANH}SAN SANG{HET} — chay: python run.py" if tot else f"  {DO}CO BUOC CHUA DAT{HET}")
        print(f"{'='*70}\n")
        sys.exit(0 if tot else 1)

    if x.setup_only:
        print(f"\n{'='*70}\n  {XANH}CAI XONG{HET}. Bat server: python run.py\n{'='*70}\n")
        return

    buoc_6_server(x.port, not x.no_dev_auth)


if __name__ == "__main__":
    main()
