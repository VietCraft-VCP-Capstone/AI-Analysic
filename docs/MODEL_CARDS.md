# MODEL CARD: SigLIP2 ONNX (Listing Intelligence)

## Nguồn

- Repo ONNX: https://huggingface.co/onnx-community/siglip2-base-patch16-224-ONNX
- Revision ghim: `ba1f3b0843f24bc5417d38e19c37b287d719b2f4`
- Model gốc: https://huggingface.co/google/siglip2-base-patch16-224
- Thư mục cache: `~/.cache/vietcraft-li/siglip2-base-patch16-224` (đổi được bằng biến môi trường `LI_MODEL_DIR`)
- Tải lại: `cd AI-Analysic && .venv/bin/python -m scripts.li.fetch_models`

## Giấy phép

- Repo ONNX không khai báo license (trường `license` trống). README chỉ dẫn về model gốc.
- Model gốc `google/siglip2-base-patch16-224`: **Apache-2.0** (cardData `license: apache-2.0`). Nguyên văn: https://www.apache.org/licenses/LICENSE-2.0.txt
- Tóm tắt Apache-2.0: được dùng, sửa, phân phối, dùng thương mại. Phải giữ thông báo bản quyền và bản sao license. Có cấp quyền bằng sáng chế. Không có bảo đảm.
- Bản ONNX là bản chuyển đổi của model gốc. Coi như kế thừa Apache-2.0. Đây là suy luận, chưa được tác giả repo ONNX xác nhận.

## File đã tải (sha256 đã kiểm tra)

| File | Kích thước (byte) | sha256 |
|---|---|---|
| `onnx/vision_model_int8.onnx` | 94,553,333 | `0dd31785a2713f1113ef2272472165c69d580473dae38d7b47568ac587795e70` |
| `onnx/text_model_int8.onnx` | 283,438,275 | `3a0603d3a00c05a80a6ded4743c16aaac7b1e62cdcc7e362e7ce418659b96400` |
| `tokenizer.json` | 34,363,039 | `cb9140fae3ac5122c972d37adf83e1248471a38147ad76f8215c8872c6fd8322` |

- Tổng: 412,354,647 byte (khoảng 412 MB).
- Kích thước lấy bằng HEAD request trước khi tải (header `x-linked-size`).
- Kết quả kiểm tra: khớp cả ba sha256 ghim trong `scripts/li/fetch_models.py`, và khớp `x-linked-etag` của Hugging Face.
- `README.md` của revision (555 byte) được lưu cùng thư mục cache, sha256 `399820e83f2cb2fbca17a6bc76949aacf9ee1caf99e55e6f7f744b24cd23764a`.

## Phiên bản thư viện

- onnxruntime 1.31.0 (khớp `requirements.txt`)
- tokenizers 0.23.3

## Tốc độ đo trên máy này

Máy: Intel i7-11800H (8 nhân, 16 luồng), RAM 15 GB, chỉ dùng CPUExecutionProvider.

Phương pháp: một lần khởi động làm nóng, sau đó chạy 3 lần và lấy trung vị.

- Ảnh: 32 ảnh RGB ngẫu nhiên 300x300 qua `embed_images`. Gồm resize và chuẩn hóa, không gồm giải mã JPEG từ URL. Trung vị **23.65 ảnh/s** (1.35 s cho 32 ảnh).
- Text: 128 chuỗi tiếng Việt ngắn, đệm đến 64 token, qua `embed_texts`. Trung vị **81.30 text/s** (1.57 s cho 128 chuỗi).
- `embed_images` và `embed_texts` xử lý từng mục một, không gộp batch. Số trên là theo từng mục.
- Số liệu chỉ đúng cho máy này.

## Chất lượng

Chưa đo accuracy hay AUC trên dữ liệu VietCraft. Không có con số chất lượng nào trong tài liệu này.

## Kiểm thử

- `tests/listing_intel/test_siglip_smoke.py`: 2 passed khi có weights. Khi thiếu weights, cả 2 test được skip với lý do "model ONNX chua tai".
