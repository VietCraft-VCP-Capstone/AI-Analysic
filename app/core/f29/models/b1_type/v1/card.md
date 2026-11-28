# B1 · Loại hàng từ ảnh và chữ (v1)

- Việc làm: đoán loại hàng (27 loại) từ vector ảnh và chữ SigLIP2 đã đóng băng.
- Dữ liệu: emb_tikifashion.npz, 4962 mẫu (bỏ nhãn trung_nien_nu). Chỉ thời trang có dữ liệu train (15 loại). Còn 12 loại chạy zero-shot.
- Chia: cụm nối khi cos ảnh > 0,95 hoặc cos chữ > 0,999 (3942 cụm). group_split 70/15/15, seed 0. Train/val/test: 3473/745/744.
- Mẫu test theo loại: ao_khoac_vest 107, ao_so_mi_kieu 49, ao_thun 74, boot 3, dam_vay 84, do_lot_boi 95, do_ngu_do_bo 27, giay_cao_got 48, giay_tay_luoi 41, giay_the_thao 19, phu_kien_thoi_trang 15, quan 105, sandal_dep 42, set_do 25, sweater_hoodie 10. Loại dưới 10 mẫu làm macro-F1 nhiễu.
- Mô hình: LogisticRegression ảnh C=10, chữ C=10; gộp log p_ảnh + 1,25·log p_chữ; trộn zero-shot 0,5 (nhiệt độ 100).
- Từ chối: τ = 0,448, chọn trên val để độ đúng phần trả lời ≥ 0,95 (val 0,950). Trên test: từ chối 6,0%, độ đúng phần trả lời 0,940, macro-F1 phần trả lời 0,905.

| Nguồn | Macro-F1 [CI 95%] | Top-1 [CI 95%] | Fused trừ nguồn, top-1 [CI 95%] | McNemar p | Holm p |
|---|---|---|---|---|---|
| img | 0,721 [0,657; 0,770] | 0,778 [0,749; 0,810] | 0,133 [0,105; 0,161] | 3,07e-23 | 1,23e-22 |
| txt | 0,806 [0,761; 0,849] | 0,883 [0,857; 0,908] | 0,028 [0,006; 0,049] | 1,39e-02 | 2,79e-02 |
| probe | 0,874 [0,808; 0,904] | 0,914 [0,893; 0,933] | -0,003 [-0,011; 0,005] | 7,54e-01 | 7,54e-01 |
| fused | 0,871 [0,807; 0,901] | 0,911 [0,889; 0,931] | - | - | - |
| zeroshot_img | 0,552 [0,493; 0,600] | 0,605 [0,565; 0,644] | - | - | - |
| zeroshot_txt | 0,611 [0,539; 0,651] | 0,704 [0,665; 0,744] | - | - | - |
| zeroshot | 0,620 [0,579; 0,662] | 0,754 [0,719; 0,786] | 0,157 [0,127; 0,189] | 1,54e-27 | 7,72e-27 |
| tfidf | 0,789 [0,741; 0,833] | 0,875 [0,848; 0,899] | 0,036 [0,015; 0,059] | 1,82e-03 | 5,46e-03 |

- Trộn zero-shot không khác probe thuần có ý nghĩa thống kê (fused trừ probe, top-1 = -0,003, Holm p = 7,54e-01). Đổi lại, loại chưa có dữ liệu có xác suất.
- Giới hạn: dữ liệu là ảnh Tiki Fashion. Chưa đo trên tiki26 và VietCraft.
- Giới hạn: ảnh ngoài thời trang chưa đo. Probe không có lớp ngoài thời trang, nên có thể gán nhãn thời trang với p ≥ τ.
- Giới hạn: loại zero-shot có p tối đa 0,5, nên thường bị từ chối khi τ = 0,45.
- Giới hạn: 12 loại zero-shot không có nhãn test, nên không đo được độ đúng.
