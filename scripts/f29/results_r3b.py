from scripts.f29.eval_kit import md_table
from scripts.f29.results_base import num
from scripts.f29.results_register import LABEL, _ci


ROWS = [("health-5.1", "health-5.1 (học 3 bộ, thử)"), ("hand", "Đặt tay 30/30/15/10/15"),
        ("health-5.0", "health-5.0 (đang chạy)"), ("equal", "Đều nhau"), ("w_src", "Chỉ học Amazon"),
        ("tiki_only", "Chỉ học Tiki"), ("random", "Ngẫu nhiên")]
MARKETS = [("TK", "Tiki"), ("HM", "Handmade"), ("FA", "Fashion"), ("AMAZON", "Amazon gộp")]
INTRO = (
    "Ý tưởng: học trọng số từ 3 bộ dữ liệu thật thay cho bộ mô phỏng, rồi kéo về thị trường Việt Nam (Tiki). "
    "Dữ liệu gồm Tiki, Amazon Handmade và Amazon Fashion. Với Amazon, các yếu tố lấy từ trạng thái tin trước "
    "mốc 12/9/2022, còn nhãn là số đánh giá mới trong 12 tháng sau mốc (thước đo gần đúng, không phải doanh số), "
    "để không rò rỉ tương lai vào đầu vào. Mỗi bộ chia theo người bán. "
    "Mỗi tập test có file khoá và quy tắc ghi trước: test Amazon (Handmade, Fashion) mở lần đầu và duy nhất; "
    "test Tiki mở lần thứ ba; test mô phỏng mở lần thứ ba. "
    "AUC là xác suất chấm tin bán chạy cao hơn tin không bán chạy: 0,5 là đoán bừa, 1 là hoàn hảo.")
TIKI_NOTE = (
    "Số của health-5.0 trên Tiki là 0,571 ở đây vì R3b chấm Tiki bằng 4 yếu tố (thêm Tag, đo bằng độ phủ thuộc tính); "
    "mục R3 ở trên chấm bằng 3 yếu tố (Ảnh, Mô tả, Giá) nên ra 0,576.")
WHY = ("Trọng số không chuyển được giữa thị trường: Mô tả có ích trên Tiki nhưng ngược chiều trên Handmade, "
       "độ phủ thuộc tính có ích trên Amazon nhưng không có ích trên Tiki. ")


def _gate(ok) -> str:
    return "–" if ok is None else "đạt" if ok else "không đạt"


def _delta(block: dict, key: str) -> str:
    c = (block or {}).get(key)
    return f"chênh CI 95% {_ci(c)}" if c else "chưa có số"


def _cell(t: dict, k: str, key: str) -> str:
    return num(t.get(k, {}).get(key, {}).get("roc_auc"))


def _loo(m: dict) -> str | None:
    loo = (m.get("report_only") or {}).get("leave_one_out")
    if not loo:
        return None
    a, b = loo.get("HM_to_FA", {}), loo.get("FA_to_HM", {})
    ups = [x["delta_vs_hand"][1] for x in (a, b) if x.get("delta_vs_hand")]
    worse = " Cả hai đều kém đặt tay rõ rệt." if len(ups) == 2 and max(ups) < 0 else ""
    return (f"- Bỏ một nguồn: học Handmade đo Fashion AUC {num(a.get('auc'))}; "
            f"học Fashion đo Handmade AUC {num(b.get('auc'))}.{worse}")


def _r3(m: dict, r5) -> str:
    s, ok = m["test"].get("SIM"), (m.get("gates") or {}).get("R3")
    if not s:
        return "- R3 (mô phỏng 500 tin, r ≥ 0,65): chưa có số."
    old = f" (health-5.0: {num(r5)})" if r5 is not None else ""
    return f"- R3 (mô phỏng 500 tin, r ≥ 0,65): {_gate(ok)}; r của health-5.1 = {num(s['r'])} {_ci(s['ci95'])}{old}."


def _verdict(m: dict) -> str:
    k = m["test"].get("TK", {})
    adopt = m.get("adopt")
    head = "nhận health-5.1" if adopt else "không nhận health-5.1, giữ health-5.0"
    hand = (f"Trên Tiki, trọng số học hơn đặt tay {_ci(k['delta_vs_hand'])}, nhưng đây là lần mở test Tiki thứ ba."
            if k.get("delta_vs_hand") else "")
    return f"- Kết luận: {head}. {'' if adopt else WHY}{hand}"


def r3b_body(m: dict, r5=None) -> str:
    t, g = m["test"], m.get("gates") or {}
    rows = [{"Cách chấm": name, **{lab: _cell(t, k, key) for k, lab in MARKETS}} for key, name in ROWS]
    w, lam = (m.get("weights") or {}).get("health-5.1"), m.get("lambda") or {}
    wtxt = " · ".join(f"{LABEL[x]} {num(100 * w[x], 1)}" for x in LABEL) if w else "chưa có số"
    lines = [
        f"- Cổng G1 (Amazon test, health-5.1 hơn đặt tay, cận dưới > 0): {_gate(g.get('G1'))}; "
        f"{_delta(t.get('AMAZON'), 'delta_vs_hand')}.",
        f"- Cổng G2 (Tiki test, không kém health-5.0 quá 0,01): {_gate(g.get('G2'))}; "
        f"{_delta(t.get('TK'), 'delta_vs_health-5.0')}.",
        _r3(m, r5),
        _loo(m),
        f"- Trọng số thử (health-5.1, phương án {lam.get('design', '–')}, c = {num(lam.get('chosen'), 2)}): {wtxt}. "
        "Tag bằng 0 vì độ phủ thuộc tính không giúp đoán trên Tiki, không có nghĩa là Tag không quan trọng.",
        _verdict(m),
        "- Giới hạn: Tag chỉ đo gần đúng bằng độ phủ thuộc tính; nhãn Amazon là số đánh giá mới, không phải "
        "doanh số; Fashion thưa đánh giá sau 2022 (nhãn gần nghĩa còn bán).",
    ]
    table = md_table(rows, ["Cách chấm"] + [x[1] for x in MARKETS])
    return "\n\n".join([INTRO, "AUC trên tập test (Amazon mở lần đầu, Tiki và mô phỏng mở lần thứ ba):", table,
                        TIKI_NOTE, "\n".join(x for x in lines if x)])
