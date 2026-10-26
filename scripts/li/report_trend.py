from scripts.li.report_parts import f3, pct, peaks_table, season_table

MOST = 0.5


def _met(v):
    return "—" if v is None else ("đạt" if v > MOST else "**không đạt**")


def criterion4_rows(bt):
    roll = bt["rolling"]
    return [("STL", bt["share_mase_lt_1"], roll["share_kw_mean_stl_lt_1"], roll["share_pairs_stl_lt_1"]),
            ("Seasonal naive", bt["share_naive_mase_lt_1"], roll["share_kw_mean_naive_lt_1"], roll["share_pairs_naive_lt_1"]),
            ("Chọn theo backtest 8 tuần trước (luật chọn của spec §5, runtime không dùng)", bt["share_selected_lt_1"],
             roll.get("share_kw_mean_selected_lt_1"), roll.get("share_pairs_selected_lt_1"))]


def criterion4_line(bt):
    _, last, mean, _ = criterion4_rows(bt)[2]
    return (f"tiêu chí 4 (MASE < 1 trên phần lớn từ khoá) với luật chọn của spec §5: mốc cuối {pct(last)} ({_met(last)}), "
            f"trung bình {bt['rolling']['origins']} mốc trượt {pct(mean)} ({_met(mean)}); runtime không dùng dự báo này "
            "mà dùng hệ số mùa × đà tăng (mục 8).")


def criterion4(bt):
    roll = bt["rolling"]
    head = ["| Phương pháp dự báo 8 tuần | Mốc cuối: tỉ lệ từ khoá MASE < 1 | "
            f"{roll['origins']} mốc trượt: tỉ lệ từ khoá có MASE trung bình < 1 | Tỉ lệ cặp từ khoá–mốc MASE < 1 |",
            "|---|---|---|---|"]
    body = [f"| {n} | {pct(a)} | {pct(b)} | {pct(c)} |" for n, a, b, c in criterion4_rows(bt)]
    return "\n".join([
        "Tiêu chí 4 (spec §1): dự báo 8 tuần có MASE < 1 so với seasonal naive trên phần lớn (> 50%) từ khoá đủ "
        "điều kiện. MASE chia sai số dự báo cho MAE của seasonal naive (chu kỳ 52) trong phần học.", "", *head, *body, "",
        f"- Luật chọn so với seasonal naive ngoài mẫu: tốt hơn hẳn ở {pct(bt.get('share_selected_beats_naive'))} "
        f"từ khoá (mốc cuối) và {pct(roll.get('share_pairs_selected_beats_naive'))} cặp từ khoá–mốc; khi luật chọn "
        "naive thì hai bên bằng nhau.",
        f"- Kết luận: mốc cuối {_met(criterion4_rows(bt)[2][1])}; trung bình nhiều mốc {_met(criterion4_rows(bt)[2][2])}.",
        "- Runtime (`trend_axis.demand_factor`) không dùng phương pháp nào trong bảng: `h(d)` = chỉ số mùa theo tuần "
        "(thành phần mùa STL khi chuỗi ≥ 104 tuần, nếu ngắn hơn thì trung bình theo tuần) × (1 + đà tăng 4 tuần so với "
        "4 tuần trước, cắt ±0,5), lấy trung bình theo các từ khoá khớp rồi cắt [0,5; 1,5]; không khớp từ khoá nào thì "
        "dùng mùa vụ nhóm từ `tikireviews` hoặc 1,0. Không có dự báo mức và không chọn STL hay naive. Bảng này chỉ "
        "đánh giá dự báo chuỗi từ khoá; `h(d)` được kiểm ở phần \"Đỉnh trước dịp\"."])


def _backtest(bt):
    roll = bt["rolling"]
    miss = bt["missing_keywords"]
    return "\n".join([
        f"- Một mốc (8 tuần cuối), {bt['n']}/{bt['n_keywords']} từ khoá đủ dài: MASE trung vị STL "
        f"{f3(bt['median_mase_stl'])}, naive {f3(bt['median_mase_naive'])}; STL tốt hơn naive ở "
        f"{pct(bt['share_stl_beats_naive'])}. Nếu chọn bằng chính tập chấm (lạc quan, chỉ để đối chiếu): "
        f"{pct(bt['share_oracle_lt_1'])}.",
        f"- {roll['origins']} mốc trượt không chồng nhau ({roll['weeks_covered']} tuần, {roll['pairs']} cặp); STL thắng "
        f"naive ở {pct(roll['share_pairs_stl_beats_naive'])} cặp.",
        f"- {len(miss)} từ khoá trong danh sách chưa có chuỗi tuần trong Mongo local: {', '.join(miss) or '—'}.",
    ])


def calib(c):
    if not c:
        return "_Chưa chạy `scripts/li/trend_calib.py`._"
    head = ["| Ngưỡng cos | Dòng không khớp chữ nhưng khớp vector | … và có chung token riêng của từ khoá | "
            "Số từ khoá khớp trung bình |", "|---|---|---|---|"]
    body = [f"| ≥ {t} | {pct(v['rows_vector_only'])} | {pct(v['rows_vector_overlap'])} | {v['mean_matches']} |"
            for t, v in c["thresholds"].items()]
    q = c["cos_quantiles"]
    return "\n".join([
        f"Hiệu chỉnh trên {c['n_titles']} tiêu đề tiki26 và {c['n_keywords']} từ khoá có chuỗi: khớp chữ đã bỏ dấu ở "
        f"{pct(c['literal_rows'])} dòng; cos tiêu đề–từ khoá trung vị {q['p50']}, p90 {q['p90']}, p99 {q['p99']}. "
        f"Token chung của nhiều từ khoá (bị bỏ khi xét chung token): {', '.join(c['generic_tokens'])}.", "",
        *head, *body, "", _judged(c.get("judged"))])


def _judged(j):
    if not j:
        return "Chưa có nhãn chấm tay."
    bands = "; ".join(f"{b}: {v['strict']}/{v['n']} (nới {v['lenient']})" for b, v in j["by_band"].items())
    return (f"Mẫu chấm tay {j['n']} cặp, có nhãn từng cặp trong `{j['file']}` (không bị `evaluate` ghi đè): đúng chặt "
            f"{j['strict']}/{j['n']}, nới {j['lenient']}/{j['n']}; theo dải {bands}.")


def trend(t, c=None):
    pk = t["peaks"]
    lo, hi = pk["window_weeks"]
    a, b = pk.get("search_weeks", [None, None])
    return "\n\n".join([
        "### Tiêu chí 4", criterion4(t["backtest"]), "### Backtest chi tiết", _backtest(t["backtest"]),
        "### Mùa vụ Google Trends so với `tikireviews_monthly`",
        "Hồ sơ 12 tháng trung bình của các từ khoá trong nhóm (gán nhóm bằng regex trên từ khoá, còn lại vào "
        "`home`) so với chỉ số tháng của review Tiki.", season_table(t["season_corr"]),
        "### Đỉnh trước dịp",
        f"Hệ số `mùa × (1 + đà tăng cắt ±0,5)` tính chỉ bằng dữ liệu trước từng tuần, chưa cắt [0,5; 1,5] như "
        f"`h(d)` (để thấy vị trí đỉnh khi hệ số chạm trần); tìm đỉnh trong độ lệch "
        f"{a:+d} … {b:+d} tuần quanh dịp (0 là tuần có dịp). {pk['n_pairs']} cặp (từ khoá, năm); đỉnh rơi vào độ lệch "
        f"{lo:+d} … {hi:+d} tuần ở {pct(pk['share_peak_before'])}.", peaks_table(pk),
        "### Hiệu chỉnh ngưỡng khớp vector", calib(c),
    ])
