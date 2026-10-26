LABELS = {
    "log_sales_90d": "Số món bán 90 ngày qua",
    "log_sales_180d": "Số món bán 180 ngày qua",
    "days_since_last": "Số ngày từ đơn gần nhất",
    "log_price": "Giá (tiền tệ gốc)",
    "log_price_rel": "Giá so với trung vị danh mục",
    "freight_ratio": "Phí ship / giá",
    "photos": "Số ảnh",
    "description_length": "Độ dài mô tả",
    "name_length": "Độ dài tên",
    "log_reviews": "Số đánh giá",
    "rating": "Điểm sao (đã co về trung bình)",
    "low_star_share": "Tỉ lệ đánh giá 1–2 sao",
    "log_seller_sales": "Số món shop bán (180 ngày)",
    "log_seller_listings": "Số sản phẩm đang bán của shop",
    "seller_rating": "Điểm sao của shop",
    "seller_late_rate": "Tỉ lệ giao trễ của shop",
    "seller_ship_days": "Số ngày giao hàng của shop",
    "log_weight": "Cân nặng",
    "log_volume": "Thể tích",
    "category": "Danh mục",
}
GROUP_LABELS = {
    "history": "Lịch sử bán", "price": "Giá và phí ship", "content": "Nội dung (ảnh, mô tả, tên)",
    "reviews": "Đánh giá", "seller": "Shop (uy tín, giao hàng)", "physical": "Kích thước, cân nặng",
}
METHOD = """## Cách làm

1. **Câu hỏi:** sản phẩm có ra ít nhất 1 đơn trong 90 ngày tới không. Đây là định nghĩa "khoẻ" đo được bằng kết quả bán thật, thay cho checklist.
2. **Dữ liệu:** Olist, sàn TMĐT thật của Brazil, khoảng 100 nghìn đơn từ 2017 đến 2018. Một sản phẩm của một shop được tính là một listing.
3. **Làm sạch:** bỏ đơn huỷ hoặc không giao được, bỏ giai đoạn quá thưa (trước 2017 và sau 08/2018), mỗi đơn chỉ giữ một đánh giá (bản trả lời sau cùng), dịch danh mục sang tiếng Anh. 610 sản phẩm thiếu thông tin nội dung được giữ lại dưới dạng giá trị trống.
4. **Chống nhìn trước tương lai:** tại mỗi mốc T, mọi feature chỉ dùng dữ liệu trước T: đơn đặt trước T, đánh giá có thời điểm khách trả lời trước T và thuộc đơn trước T, ngày giao trước T. Nhãn chỉ dùng đơn trong [T, T+90 ngày). Chỉ lấy listing có đơn trong 180 ngày trước T.
5. **Chia tập theo thời gian:** train, validation và test có cửa sổ nhãn không chồng lên nhau. Model triển khai được chọn theo AUC validation trong các model chạy được trên VietCraft, học trên train + validation, báo cáo trên test. File model triển khai chính là model được chấm trên test.
6. **Benchmark:** ngẫu nhiên, luật health-1.0 hiện tại (2 trục đo được trên Olist là nội dung và đánh giá, chiếm 45% trọng số của luật), luật "bán nhiều 90 ngày qua" và luật "đơn gần nhất".
7. **Khoảng tin cậy:** bootstrap 200 lần, lấy mẫu theo shop (một shop có nhiều listing nên không coi từng dòng là độc lập). So sánh model với baseline mạnh nhất bằng bootstrap ghép cặp trên cùng mẫu.
"""


def _table(scores):
    head = ["| Phương pháp | ROC-AUC (95% CI) | PR-AUC | AUC trong cùng danh mục | Tỉ lệ ra đơn ở top 20% |",
            "|---|---|---|---|---|"]
    rows = [f"| {n} | {m['roc_auc']:.3f} ({m['auc_ci95'][0]:.3f}–{m['auc_ci95'][1]:.3f}) | {m['pr_auc']:.3f} "
            f"| {m['within_cat_auc']:.3f} | {m['top20_hit']:.1%} |" for n, m in scores.items()]
    return "\n".join(head + rows)


def _importance(lift, imp):
    lines = ["| Nhóm yếu tố | AUC giảm khi bỏ cả nhóm và học lại |", "|---|---|"]
    lines += [f"| {GROUP_LABELS[g]} | {v:+.4f} |" for g, v in sorted(lift.items(), key=lambda kv: -kv[1])]
    lines += ["", "| Yếu tố | AUC giảm khi xáo trộn riêng yếu tố đó |", "|---|---|"]
    lines += [f"| {LABELS.get(f, f)} | {v:.4f} |" for f, v in list(imp.items())[:10]]
    return "\n".join(lines)


def render(r):
    splits = "\n".join(f"| {s['name']} | {', '.join(s['cutoffs'])} | {s['rows']:,} | {s['positive_rate']:.1%} |"
                       for s in r["splits"])
    clean = "\n".join(f"- `{k}`: {v:,}" for k, v in r["cleaning"].items())
    base = r["splits"][2]["positive_rate"]
    d = r["delta"]
    return f"""# F29: thí nghiệm ML cho sức khoẻ sản phẩm (Olist)

Sinh tự động bởi `python -m scripts.f29_ml.run`. Không sửa tay.

{METHOD}
## Làm sạch dữ liệu

{clean}

## Chia tập

| Tập | Mốc T | Số listing | Tỉ lệ ra đơn |
|---|---|---|---|
{splits}

## Kết quả trên validation

{_table(r['validation'])}

Model triển khai, chọn theo validation trong các bản chạy được trên VietCraft: **{r['deployed']}**.

## Kết quả trên test (chưa từng dùng khi học hay khi chọn model)

{_table(r['test'])}

Tỉ lệ ra đơn trung bình trên test là {base:.1%}. Cột "top 20%" cho biết trong 20% listing được chấm cao nhất có bao nhiêu phần trăm thực sự ra đơn.

**So với baseline mạnh nhất ({d['vs']}):** AUC chênh {d['auc']:+.3f}, khoảng tin cậy 95% bootstrap ghép cặp theo shop [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}].

## Yếu tố quan trọng của model triển khai ({r['deployed']})

Bảng đầu: bỏ hẳn một nhóm yếu tố, học lại rồi đo AUC trên test. Số gần 0 nghĩa là nhóm đó không thêm thông tin khi đã có các nhóm còn lại. Scorer chỉ đưa lời khuyên cho nhóm có mức giảm từ 0,005 trở lên.

{_importance(r['group_lift'], r['importance'])}

## Giới hạn

- Olist là sàn Brazil, không phải VietCraft. Bản triển khai bỏ giá tuyệt đối (khác tiền tệ), danh mục (khác cây danh mục) và tỉ lệ giao trễ (VietCraft chưa lưu ngày hẹn giao).
- Olist chỉ có sản phẩm đã từng bán được, nên model không chấm sản phẩm chưa có đơn nào trong 180 ngày.
- Nội dung sản phẩm (số ảnh, độ dài mô tả) là ảnh chụp tại thời điểm xuất dữ liệu, không theo từng mốc T.
- Trạng thái đơn là trạng thái lúc xuất dữ liệu: vài trăm đơn đặt trước T nhưng huỷ sau T bị loại khỏi feature.
- Một listing xuất hiện ở nhiều mốc train. Test chỉ có một mốc, nên kết quả phản ánh một giai đoạn.
- Xác suất dự đoán chưa hiệu chỉnh theo tỉ lệ nền (tỉ lệ nền giảm từ train sang test), nên sản phẩm chỉ hiển thị thứ hạng so với nhóm, không hiển thị xác suất.
- Chưa có kiểm chứng trên dữ liệu bán thật của VietCraft. Dữ liệu sàn hiện tại là lưu lượng mô phỏng.
"""
