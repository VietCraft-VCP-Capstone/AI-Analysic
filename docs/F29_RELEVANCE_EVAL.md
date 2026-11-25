Ảnh chụp số liệu ngày 2026-11-19 01:04 (Asia/Ho_Chi_Minh); số liệu thay đổi theo log mới.
# F29 — Đánh giá độ liên quan của từ khoá

> Nhãn: **weak supervision, not human-labelled**. Nhãn lấy từ click trong `search_logs`, không có người chấm.
> Sinh bởi `scripts/f29_health/eval_relevance.py`. Số liệu in nguyên từ script.

## Dữ liệu
- search_logs: 2837 lượt tìm, 1095 lượt có click, 1095 click tổng.
- Click dùng để đánh giá (sản phẩm thật, có danh mục): 1093.
- Từ khoá duy nhất (đã bỏ dấu): 93. Cặp (từ khoá, sản phẩm): 196.
- Khoảng thời gian: 2026-10-16 → 2026-11-18.
- Mốc tách: 2026-11-11 18:04. Tách theo thời gian: 7 ngày cuối làm test, trước đó làm train.
- Tách theo từ khoá chưa thấy: 1 trong 5 từ khoá (md5) làm test, các từ khoá còn lại làm train.

## Cách đo
- Ứng viên: mọi sản phẩm thật cùng danh mục chính (`categories[0]`) với sản phẩm được click.
- Lexical: tỉ lệ token của từ khoá có trong tên và tag sản phẩm.
- Model: token của từ khoá được tính điểm theo tần suất token trong tên sản phẩm đã click cho từ khoá đó, click ở vị trí p được tính trọng số 1/(p+1).
- Hoà điểm được tính bất lợi cho sản phẩm được click, với cả hai phương pháp.
- MRR và Recall@5 tính trên từng cặp (từ khoá, sản phẩm được click), lấy trung bình.

## Kết quả
| Tách | Train click | Test click | Test cặp | Test từ khoá | Ứng viên TB | MRR model | MRR lexical | Recall@5 model | Recall@5 lexical |
|---|---|---|---|---|---|---|---|---|---|
| temporal | 18 | 1075 | 185 | 88 | 14.1 | 0.534 | 0.537 | 0.751 | 0.751 |
| unseen_query | 725 | 368 | 42 | 22 | 11.2 | 0.630 | 0.682 | 0.809 | 0.881 |

## Quyết định
Model không thắng lexical trên mọi chỉ số ở cả hai cách tách, nên `enabled = false` và production dùng lexical. Không đạt: temporal mrr, temporal recall5, unseen_query mrr, unseen_query recall5.

## Giới hạn
- Dữ liệu nhỏ, và vài từ khoá chiếm phần lớn lượt tìm, nên số liệu dao động mạnh.
- Không có nhãn người chấm. Mọi số ở đây là weak supervision.
- Model trong `relevance_model.json` chỉ học từ dữ liệu trước mốc tách, không dùng 7 ngày test.
- Tách theo thời gian: 18 click để train, 1075 click để test. Khi train quá ít, kết quả tách này không đáng tin.
