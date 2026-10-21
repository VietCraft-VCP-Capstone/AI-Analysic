# Listing Intelligence (F29 v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chấm listing VietCraft theo 5 trục (ảnh, từ khoá, tag, thị hiếu và cạnh tranh, trend và mùa vụ), dùng model học trên dữ liệu Tiki Việt Nam; có endpoint, giao diện, job định kỳ và báo cáo đánh giá.

**Architecture:** Package `app/core/listing_intel/` gồm các hàm feature thuần, dùng chung cho script offline (`scripts/li/`) và runtime (router `f29_intel.py`). Ảnh và chữ được nhúng bằng SigLIP2 ONNX qua onnxruntime. Model gộp là HistGradientBoosting học trên bảng feature hợp nhất từ Tiki 2023 và Tiki 2026. BE proxy, FE có trang mới và thêm vào form tạo sản phẩm.

**Tech Stack:** Python 3.12, FastAPI, scikit-learn 1.9.1, onnxruntime, tokenizers, OpenCV, pandas, pymongo; Express + TypeScript + Mongoose; React 18 + Vite + recharts.

**Spec:** `vc-ai/AI-Analysic/docs/superpowers/specs/2026-10-21-listing-intelligence-design.md`

## Global Constraints

- Không viết comment trong code. File ngắn: mỗi file Python hoặc TSX mới nên dưới khoảng 150 dòng, tách file khi dài hơn.
- Không commit CSV, parquet, ảnh hay file ONNX. Dữ liệu nằm ở `/home/rio/Documents/CODE/nodejs/vietcraft/data-li/` (biến môi trường `LI_DATA_DIR`). Model ONNX nằm ở `~/.cache/vietcraft-li/` (biến `LI_MODEL_DIR`).
- Không import torch trong `app/core/listing_intel/` hay `scripts/li/`. Phụ thuộc runtime mới chỉ có `onnxruntime` và `tokenizers`.
- `scikit-learn==1.9.1`. Python của AI chạy bằng `vc-ai/AI-Analysic/.venv/bin/python`, từ thư mục `vc-ai/AI-Analysic`.
- Mongo: chỉ dùng local `mongodb://127.0.0.1:27017`. Dữ liệu nghiên cứu ở DB `li-research`. Runtime đọc DB live qua `db_live()` (chạy local với `MONGO_DB_LIVE=vietcraft-test`) và chỉ ghi 2 collection `listing_embeddings`, `listing_intel_scores`. Không bao giờ ghi vào Atlas.
- Model ONNX: repo HF `onnx-community/siglip2-base-patch16-224-ONNX`, file `onnx/vision_model_int8.onnx`, `onnx/text_model_int8.onnx`, `tokenizer.json`. Ảnh resize 224×224, chia 255, chuẩn hoá mean 0,5 std 0,5. Chữ được pad tới đúng 64 token.
- Nhóm danh mục (group key): `fashion`, `bags`, `shoes`, `accessories`, `home`, `sport`.
- Nhãn `top25`: listing thuộc 25% `quantity_sold` cao nhất trong cùng (source, group). Với `tiki23`, xếp hạng theo `quantity_sold / max(date_created, 30)`.
- Không bao giờ dùng làm feature: `review_count`, `rating_average`, `favourite_count`, `order_count`, `revenue_estimate`, `quantity_sold`, `inventory_status`, `badges`, `is_official_store`, `discount`, `discount_rate`, `has_video`, `fulfillment_type`, `brand`.
- Chia tập: `GroupShuffleSplit` theo seller (`current_seller` của `tiki23`, `seller_id` của `tiki26`), tỉ lệ 70/15/15, `random_state=42`.
- Ngưỡng: trùng gần `cos > 0,92`; khớp từ khoá trend bằng vector `cos ≥ 0,80`; "đã đo" khi lift ablation ≥ 0,005 và CI95 không chứa 0; hệ số nhu cầu `h(d)` cắt trong [0,5; 1,5]; `score(d) = clip(base × h(d), 0, 100)`.
- Ảnh chỉ tải từ `res.cloudinary.com`, `salt.tikicdn.com`; timeout 5 giây, tối đa 8 MB, content-type phải là `image/*`.
- Chuỗi hiển thị cho người dùng viết bằng tiếng Việt. FE dùng lại `InsightCard`, `InsightBlock`, `useInsight`, `Chip`, `InfoTip`, `Note` trong `FE/src/modules/analytics/components/ui.tsx`.
- Chỉ commit khi người dùng đồng ý; khi commit thì tạo nhánh `feat/listing-intel` trong từng repo.

## Review Focus

- Listing không có ảnh, hoặc mọi URL ảnh đều tải lỗi: trục ảnh trả `score=None` kèm lý do, điểm tổng vẫn tính từ các trục còn lại (test ở Task 11).
- Tiêu đề không dấu, viết hoa toàn bộ, có emoji hoặc chữ ở dạng tổ hợp (NFD): chuẩn hoá vẫn ra cùng token (test ở Task 2).
- Danh mục mới không có trong `category_map.json`: group là `None`, so sánh với toàn sàn, không crash (test ở Task 11).
- Bản nháp gửi URL ngoài danh sách cho phép, file quá lớn hoặc không phải ảnh: bị từ chối ở cả BE và AI (test ở Task 4 và Task 6).
- Từ khoá trend có chuỗi phẳng, toàn 0, hoặc không có trong Mongo: `h(d)` lấy mùa vụ của nhóm, nếu không có thì bằng 1,0 (test ở Task 5).

---

## Waves (chạy song song)

- Wave 1, độc lập: Task 1, 2, 3, 4, 5, 6, 7, 9.
- Wave 2: Task 8 (cần 1, 2, 3, 4, 5, 9) và Task 11 (cần 2, 3, 4, 5, 9; dùng bundle giả cho tới khi Task 10 xong).
- Wave 3: Task 10 (cần 8).
- Wave 4: Task 12 (cần tất cả).

---

### Task 1: Thu thập và làm sạch dữ liệu

**Files:**
- Create: `scripts/li/__init__.py`, `scripts/li/paths.py`, `scripts/li/ingest.py`, `scripts/li/labels.py`
- Create: `app/core/listing_intel/__init__.py`, `app/core/listing_intel/data/category_map.json`
- Test: `tests/listing_intel/__init__.py`, `tests/listing_intel/test_labels.py`

**Interfaces:**
- Produces:
  - `paths.DATA_DIR: Path` (từ env `LI_DATA_DIR`, mặc định `<vietcraft>/data-li`)
  - `paths.raw(name) -> Path`
  - `paths.clean(name) -> Path`
  - `labels.top25(df: DataFrame, score_col: str, by: list[str]) -> Series[int]`
  - `labels.split_by_seller(df, seller_col: str) -> Series[str]` (giá trị `train` / `val` / `test`)
  - `ingest.main()` ghi các file parquet:
    - `clean/tiki23.parquet`, cột `listing_id, source="tiki23", group, title, description, price, n_images, seller, age_days, sold, top25, split`
    - `clean/tiki26.parquet`, cột `listing_id, source="tiki26", group, title, description, price, image_url, seller, sold, top25, split, scraped_at`
    - `clean/tikifashion.parquet`, cột `listing_id, image_url, caption, category` (lấy mẫu 5.000 dòng, seed 42)
    - `clean/tikireviews_monthly.parquet`, cột `group, month (1–12), index` (trung bình bằng 1)
  - `category_map.json`:
    - `{"vietcraft": {"Áo thun": "fashion", ...}, "tiki23": {"men_bags": "bags", ...}, "tiki26": {"thoi-trang-nam": "fashion", "thoi-trang-nu": "fashion", "do-gia-dung": "home", "the-thao-da-ngoai": "sport"}}`
    - Phần VietCraft bao gồm: Trang trí, Ly tách, Nhà cửa, Tranh ảnh → home; Túi → bags; Giày dép → shoes; Phụ kiện, Trang sức → accessories; Áo quần bóng đá → sport; mọi danh mục áo, quần, váy, đầm, set, sweater, jacket, leather, vải len → fashion.

- [ ] **Step 1: Write failing tests** in `tests/listing_intel/test_labels.py`
  - `test_top25_marks_quarter_per_group`: 8 dòng thuộc 2 group, mỗi group 4 dòng → mỗi group đúng 1 dòng `top25==1`, là dòng có điểm cao nhất.
  - `test_split_keeps_each_seller_in_one_split`: 300 dòng, 60 seller → `df.groupby("seller")["split"].nunique().max() == 1`; cả 3 nhãn đều xuất hiện.
  - `test_split_is_deterministic`: gọi 2 lần ra cùng kết quả.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/listing_intel/test_labels.py -q`. Expected: FAIL (module chưa có).
- [ ] **Step 3: Implement `labels.py` and `paths.py`.** `top25` dùng `groupby(by)[score_col].rank(pct=True) > 0.75`.
- [ ] **Step 4: Implement `ingest.py`:**
  - **Nguồn:** copy file đã tải từ `/tmp/claude-1000/-home-rio-Documents-CODE-nodejs-vietcraft/a6de79fb-f4f8-4967-8a37-cf5641336562/scratchpad/dl/` (`tikifashion/*.csv` là `tiki23`; `huyhoang1308_tiki-csv/tiki_products_raw.csv` là `tiki26`; `giaphoangkim_tiki-fashion/filtered_cleaned_caption.csv` là `tikifashion`) vào `raw/`. Tải `farmingfree/vietnamese-e-commerce-suspicious-reviews-dataset` bằng `curl -L https://www.kaggle.com/api/v1/datasets/download/farmingfree/vietnamese-e-commerce-suspicious-reviews-dataset -o raw/tikireviews.zip`. Nếu tải lỗi thì ghi `tikireviews_monthly` rỗng và in cảnh báo.
  - **Lọc `tiki26`:** chỉ giữ 4 category có trong map.
  - **Làm sạch:** bỏ dòng thiếu `name` hoặc thiếu `price`, hoặc `price <= 0`.
  - **Mùa vụ từ `tikireviews`:** đếm review theo tháng; gán group bằng từ khoá trong tên sản phẩm (túi → bags, giày/dép → shoes, áo/quần/váy/đầm → fashion, còn lại → home); chia cho trung bình của group.
- [ ] **Step 5: Run `.venv/bin/python -m scripts.li.ingest`.** Expected: in số dòng mỗi file. `tiki23` khoảng 41,6 nghìn dòng; `tiki26` khoảng 4 nghìn dòng; tỉ lệ `top25` khoảng 0,25.
- [ ] **Step 6:** Run tests. Expected: PASS.

### Task 2: Chuẩn hoá tiếng Việt, bộ từ vựng, feature chữ

**Files:**
- Create: `app/core/listing_intel/types.py`, `normalize.py`, `lexicon.py`, `text_axis.py`
- Create: `app/core/listing_intel/data/lexicon.json`, `data/banned_vi.json`
- Test: `tests/listing_intel/test_text.py`

**Interfaces:**
- Produces:
  - `types.ListingInput` (dataclass):
    - `title: str`
    - `description: str = ""`
    - `tags: list[str]`
    - `materials: list[str]`
    - `category: str | None`
    - `group: str | None`
    - `price: float | None`
    - `image_urls: list[str]`
    - `product_id: str | None`
    - `seller_id: str | None`
  - `types.AxisResult` (dataclass):
    - `score: float | None`
    - `features: dict[str, float]`
    - `issues: list[dict]`, mỗi phần tử có khoá `code`, `message`, `field`
    - `missing_reason: str | None = None`
  - `normalize.norm(text) -> str`: NFC, chữ thường, bỏ emoji và ký hiệu, gộp khoảng trắng.
  - `normalize.fold(text) -> str`: như `norm` nhưng bỏ dấu, `đ` thành `d`.
  - `normalize.ngrams(text, n=(1, 2)) -> list[str]`: n-gram theo âm tiết trên `norm`.
  - `lexicon.attributes(text) -> dict[str, list[str]]`, khoá `material`, `color`, `size`, `occasion`, `use`, so khớp trên `fold`.
  - `lexicon.MATERIALS: list[str]`
  - `lexicon.banned_hits(text) -> list[str]`
  - `text_axis.text_features(inp: ListingInput, lift: dict[str, dict[str, float]] | None) -> dict[str, float]`, các khoá:
    - `title_len`, `title_words`, `title_upper_ratio`, `title_repeat_ratio`, `title_banned`
    - `attr_material`, `attr_color`, `attr_size`, `attr_occasion`, `attr_use`
    - `desc_len`, `desc_words`
    - `kw_lift_sum`, `kw_lift_max`, `kw_lift_terms`
    - `lift` là `{group: {term: log_lift}}`. Không có bảng lift thì 3 khoá `kw_*` bằng NaN.
  - `text_axis.text_issues(inp, feats) -> list[dict]`, các mã:
    - `title_short` (< 20 ký tự), `title_long` (> 120)
    - `keyword_stuffing` (repeat ratio > 0,3)
    - `banned_word`
    - `missing_material` (khi group ∈ {fashion, bags, shoes, accessories} và không có chất liệu khai báo lẫn phát hiện)
    - `missing_color`, `missing_size` (chỉ cho fashion và shoes)
    - `desc_short` (< 150 ký tự)
- **Nội dung `lexicon.json`:**
  - **material:** cotton, thun, linen, lanh, đũi, lụa, tơ tằm, len, nỉ, dạ, jean, denim, kaki, kate, voan, chiffon, ren, nhung, da bò, da thật, da pu, simili, canvas, cói, mây, tre, gỗ, gốm, sứ, thủy tinh, inox, bạc 925, đồng, thổ cẩm, vải bố, polyester, spandex.
  - **color:** khoảng 20 màu thường gặp.
  - **size:** S, M, L, XL, XXL, freesize, oversize, số size giày 35–45, cm.
  - **occasion:** lấy từ `OCCASIONS` trong `app/seed/catalog/name_generator.py:190-229`.
  - **use:** công sở, đi học, dạo phố, du lịch, dự tiệc, tập gym, đi biển, quà tặng.
  - **`banned_vi.json`:** chuyển 87 cụm và 16 từ đơn từ `BE/src/shared/services/content-moderation.service.ts`.

- [ ] **Step 1: Write failing tests** in `test_text.py`:
  - `test_norm_nfd_and_nfc_equal`: `norm(unicodedata.normalize("NFD","Áo Khoác Len")) == norm("Áo khoác len") == "áo khoác len"`
  - `test_fold_removes_diacritics`: `fold("Đầm Lụa Tơ Tằm") == "dam lua to tam"`
  - `test_emoji_and_caps_stripped`: `norm("ÁO THUN 🔥🔥 SALE!!!") == "áo thun sale"`
  - `test_attributes_detect_material_without_diacritics`: `attributes("ao khoac da bo nam")["material"] == ["da bò"]`
  - `test_missing_material_issue_only_for_fashion_groups`: group `fashion` không có chất liệu → có mã `missing_material`; group `home` thì không có.
  - `test_keyword_stuffing`: `"túi túi túi xách túi đẹp túi"` → có mã `keyword_stuffing`.
  - `test_kw_lift_nan_without_table`: `math.isnan(text_features(inp, None)["kw_lift_sum"])`
  - `test_kw_lift_uses_group_table`: `lift={"bags":{"túi da":1.2,"da":0.3}}`, title `"Túi da nữ"`, group bags → `kw_lift_sum == pytest.approx(1.5)`, `kw_lift_max == 1.2`, `kw_lift_terms == 2`
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/listing_intel/test_text.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the files.
- [ ] **Step 4:** Run tests. Expected: PASS.

### Task 3: Embedder SigLIP2 ONNX

**Files:**
- Create: `scripts/li/fetch_models.py`, `app/core/listing_intel/embedder.py`
- Modify: `requirements.txt` (thêm `onnxruntime==<bản pip cài>` và `tokenizers==<bản pip cài>`)
- Test: `tests/listing_intel/test_embedder.py`

**Interfaces:**
- Produces:
  - `embedder.MODEL_DIR: Path` (env `LI_MODEL_DIR`, mặc định `~/.cache/vietcraft-li/siglip2-base-patch16-224`)
  - `embedder.available() -> bool`
  - `embedder.embed_images(images: list[PIL.Image.Image]) -> np.ndarray` (shape `[n, d]`, float32, chuẩn hoá L2)
  - `embedder.embed_texts(texts: list[str]) -> np.ndarray`
  - `embedder.MODEL_ID = "onnx-community/siglip2-base-patch16-224-ONNX"`
  - Session nạp lười một lần, chạy batch 16.
  - Lấy output tên `pooler_output` nếu có, nếu không thì lấy output đầu tiên dạng 2D.

- [ ] **Step 1:** Cài gói: `.venv/bin/pip install onnxruntime tokenizers`, ghi đúng phiên bản vào `requirements.txt`.
- [ ] **Step 2:** Implement `fetch_models.py`: tải 3 file trong Global Constraints từ `https://huggingface.co/<MODEL_ID>/resolve/main/<path>` vào `MODEL_DIR`, bỏ qua file đã có. Run `.venv/bin/python -m scripts.li.fetch_models`. Expected: 3 file, tổng khoảng 410 MB.
- [ ] **Step 3: Write tests:**
  - `test_shapes_and_norm`: 2 ảnh màu đặc → shape `(2, d)`, `np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-3)`
  - `test_text_image_alignment`: ảnh đỏ đặc so với 2 câu `"một bức ảnh màu đỏ"`, `"một bức ảnh màu xanh lá"` → cos với câu đỏ lớn hơn.
  - `test_padding_fixed_64`: câu dài 500 ký tự vẫn chạy được.
  - Mọi test dùng `pytest.mark.skipif(not available(), ...)`.
- [ ] **Step 4:** Implement `embedder.py` (tokenizer qua `tokenizers.Tokenizer.from_file`, bật `enable_padding(length=64)` và `enable_truncation(64)`).
- [ ] **Step 5:** Run `.venv/bin/python -m pytest tests/listing_intel/test_embedder.py -q`. Expected: PASS. Đo thời gian 16 ảnh, in ra.

### Task 4: Vision, tải ảnh an toàn và số đo chất lượng

**Files:**
- Create: `app/core/listing_intel/vision.py`, `app/core/listing_intel/image_fetch.py`
- Test: `tests/listing_intel/test_vision.py`

**Interfaces:**
- Produces:
  - `image_fetch.ALLOWED_HOSTS = {"res.cloudinary.com", "salt.tikicdn.com"}`
  - `image_fetch.allowed(url) -> bool`: chỉ `https`, host nằm trong danh sách.
  - `image_fetch.fetch(url, timeout=5, max_bytes=8_000_000) -> PIL.Image.Image | None`: lỗi gì cũng trả `None`, không raise.
  - `vision.quality(img) -> dict[str, float]`, các khoá:
    - `img_w`, `img_h`, `img_aspect`
    - `img_sharpness`: log1p của phương sai Laplacian trên ảnh xám đã resize cạnh dài 512
    - `img_brightness`, `img_contrast`: trung bình và độ lệch chuẩn của ảnh xám, quy về 0–1
    - `img_border_uniform`: tỉ lệ pixel trong viền 5% có độ lệch < 12 so với trung vị của viền
    - `img_center_edges`: mật độ cạnh Canny trong 60% vùng giữa
    - `img_text_ratio`: tổng diện tích vùng MSER có tỉ lệ khung giống chữ, chia diện tích ảnh
  - `vision.dhash(img) -> int`: 64 bit
  - `vision.hamming(a, b) -> int`
  - `vision.quality_issues(q) -> list[dict]`, các mã:
    - `low_resolution` (cạnh ngắn < 500)
    - `blurry` (`img_sharpness < 4.0`)
    - `too_dark` (< 0,25), `too_bright` (> 0,9)
    - `busy_background` (`img_border_uniform < 0.4`)
    - `text_overlay` (`img_text_ratio > 0.08`)
    - `bad_aspect` (ngoài khoảng 0,75–1,34)

- [ ] **Step 1: Write failing tests:**
  - `test_allowed_rejects_http_and_other_hosts`: `allowed("http://res.cloudinary.com/x.jpg") is False`, `allowed("https://evil.com/a.jpg") is False`, `allowed("https://res.cloudinary.com/a/b.jpg") is True`
  - `test_fetch_rejects_non_image` dùng monkeypatch `urllib.request.urlopen` trả content-type `text/html` → `None`
  - `test_fetch_rejects_oversize` với header content-length 9.000.000 → `None`
  - `test_blur_detected`: ảnh bàn cờ so với cùng ảnh đó qua `cv2.GaussianBlur(… (21,21), 0)` → bản mờ có `img_sharpness` thấp hơn, và có mã `blurry`
  - `test_white_border_uniform`: nền trắng, hình vuông đen ở giữa → `img_border_uniform > 0.9`
  - `test_dhash_near_duplicate`: ảnh và chính nó tăng sáng 10% → `hamming <= 6`; ảnh nhiễu khác → `hamming > 20`
  - `test_brightness_invariance`: độ sáng ×1,1 → mọi khoá quality trừ `img_brightness` thay đổi < 15% tương đối
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/listing_intel/test_vision.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement bằng `cv2` và `numpy`. Tải ảnh bằng `urllib.request`, đọc theo từng chunk và dừng khi vượt `max_bytes`.
- [ ] **Step 4:** Run tests. Expected: PASS.

### Task 5: Lịch sự kiện và trend

**Files:**
- Modify: `app/core/calendar_vn.py` (thêm `MID_AUTUMN_DATES` 2021–2030, `SHOPPING_EVENTS`, `upcoming_events(d, weeks)`)
- Create: `app/core/listing_intel/trend_axis.py`, `app/core/listing_intel/trend_store.py`, `app/core/listing_intel/data/trend_keywords.json`
- Test: `tests/listing_intel/test_trend.py`

**Interfaces:**
- Produces:
  - `calendar_vn.SHOPPING_EVENTS: list[dict]`: `{"key", "name", "date_fn(year)->date", "prep_days", "groups": [...]}` cho Tết, Valentine 14/2, 8/3, 30/4, 1/6, khai giảng 5/9, Trung thu, 20/10, Halloween 31/10, 11/11, Black Friday, 20/11, 12/12, Noel 24/12.
  - `calendar_vn.upcoming_events(d: date, weeks: int = 12) -> list[dict]`, mỗi phần tử `{"key", "name", "date", "prep_start", "groups"}`.
  - `trend_store.weekly_series() -> dict[str, pd.Series]`: keyword → chuỗi tuần, đọc từ Mongo `data-collection.trend_interest` với granularity weekly (cột scaled), nếu không có thì đọc `vc-ai/vc-data/trends/trend_interest.parquet`. Cache trong bộ nhớ 1 giờ.
  - `trend_axis.seasonal_index(s: pd.Series) -> np.ndarray`: 52 giá trị, trung bình 1. Dùng STL `period=52` khi có ≥ 104 điểm, nếu không thì dùng trung bình theo tuần trong năm.
  - `trend_axis.momentum(s, at: date) -> float`: trung bình 4 tuần gần nhất chia trung bình 4 tuần trước đó, trừ 1. Chuỗi phẳng hoặc toàn 0 → 0,0.
  - `trend_axis.match_keywords(tokens: list[str], keywords: list[str], kw_vecs: np.ndarray | None, text_vec: np.ndarray | None) -> list[tuple[str, float]]`: so khớp chữ theo `fold` cho trọng số 1,0; nếu không, vector `cos ≥ 0.80` cho trọng số bằng cos.
  - `trend_axis.demand_factor(matches, series, at: date, group_season: np.ndarray | None) -> float`: theo công thức trong spec mục 5; không khớp được gì thì dùng `group_season`, nếu không có thì 1,0; cắt trong [0,5; 1,5].
  - `trend_axis.timeline(matches, series, start: date, weeks=8, group_season=None) -> list[dict]`, mỗi phần tử `{"week_start", "demand_factor", "events"}`.
  - `trend_axis.backtest(series_by_kw, horizon=8) -> pd.DataFrame`: cột `keyword, mase_stl, mase_naive, winner`; dùng `app/core/metrics.py` `mase`.
  - `trend_keywords.json`: 45 từ khoá đang có cộng các từ mới: áo khoác, đầm len, váy, túi tote, túi da, giày sneaker, gốm sứ, mây tre, thổ cẩm, lụa, quà trung thu, quà 11/11, black friday, quà khai giảng, halloween, trang trí trung thu.

- [ ] **Step 1: Write failing tests:**
  - `test_mid_autumn_2026`: Trung thu 2026 là `date(2026, 9, 25)`
  - `test_black_friday_2026`: `date(2026, 11, 27)`
  - `test_upcoming_events_window`: từ 2026-10-21, trong 6 tuần tới → có `20/11` và `halloween`, không có `tet`
  - `test_seasonal_index_peaks_at_season`: chuỗi tổng hợp 5 năm có đỉnh ở tuần 42 → `argmax` thuộc {41, 42, 43}, trung bình ≈ 1
  - `test_momentum_flat_zero`: chuỗi toàn 0 → 0,0
  - `test_demand_factor_bounds`: momentum cực lớn → 1,5; không khớp và không có mùa nhóm → 1,0
  - `test_timeline_peaks_before_event`: từ khoá theo mùa có đỉnh tháng 11 → trong timeline từ 2026-10-05, demand factor lớn nhất rơi vào một tuần thuộc tháng 10 hoặc tháng 11
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/listing_intel/test_trend.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. Ngày âm lịch Trung thu cố định 2021–2030: 2021-09-21, 2022-09-10, 2023-09-29, 2024-09-17, 2025-10-06, 2026-09-25, 2027-09-15, 2028-10-03, 2029-09-22, 2030-09-12.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Thu thêm dữ liệu trend:
  - `.venv/bin/pip install trendspy`.
  - Chạy `app/collectors/collect_trends.py --backfill weekly --mongo` với danh sách từ khoá mới, `request_delay` 6 giây, ghi vào Mongo local `data-collection`.
  - Gặp lỗi 429 thì dừng và ghi danh sách từ khoá chưa thu vào `data-li/clean/trend_missing.json`.

### Task 6: BE, trường chất liệu và proxy

**Files:**
- Modify: `BE/src/modules/product/infrastructure/models/product.model.ts` (thêm `materials: [String]`, mặc định `[]`)
- Modify: `BE/src/modules/product/application/product.dto.ts` (thêm `materials?: string[]` ở DTO tạo và sửa)
- Modify: `BE/src/modules/product/application/product.service.ts` (ghi `materials` ở mọi chỗ ghi `tags` khi tạo và sửa, sau khi chuẩn hoá)
- Create: `BE/src/modules/analytics/application/intel-preview.ts`
- Modify: `BE/src/modules/analytics/presentation/seller-analytics.router.ts` (ROUTES)

**Interfaces:**
- Produces:
  - `normalizeMaterials(raw: unknown): string[]`: trim, bỏ trùng không phân biệt hoa thường, tối đa 5 mục, mỗi mục tối đa 40 ký tự.
  - `parseIntelPreview(raw: unknown): PreviewBodyResult`: dùng lại kiểu `PreviewBodyResult` trong `health-preview.ts`. Giới hạn:
    - `title` 1–200 ký tự, `description` ≤ 5000
    - `tags` ≤ 20 mục, mỗi mục ≤ 40 ký tự
    - `materials` qua `normalizeMaterials`
    - `category` ≤ 80 ký tự
    - `price` từ 0 đến 1e9
    - `image_urls` ≤ 8, mỗi URL khớp `^https://res\.cloudinary\.com/`
  - Các dòng route:
    - `{ get '/listings/intel', ai: '/api/analytics/listings/intel' }`
    - `{ get '/listings/:id/intel', ai: p => '/api/analytics/listings/${p.id}/intel', query: ['date'] }`
    - `{ post '/listings/intel/preview', ai: '/api/analytics/listings/intel/preview', parseBody: parseIntelPreview }`
    - `{ get '/trends/calendar', ai: '/api/analytics/trends/calendar', query: ['category'] }`
    - Route `/listings/intel` phải đứng trước mọi route custom có thể bắt nhầm `/listings/:id`.

- [ ] **Step 1:** Implement `normalizeMaterials` và `parseIntelPreview`. Thêm self-check bằng `node:assert`: chạy `npx ts-node -e` gọi `parseIntelPreview({title:"a", image_urls:["https://evil.com/x.jpg"]})`, kết quả phải là lỗi; với `image_urls:["https://res.cloudinary.com/x/y.jpg"]` thì phải hợp lệ.
- [ ] **Step 2:** Thêm trường vào model, DTO, service; thêm các dòng route.
- [ ] **Step 3:** Run `cd BE && npx tsc --noEmit -p .`. Expected: exit 0.

### Task 7: FE, trang Phân tích listing, ô chất liệu và chấm thử

**Files:**
- Create: `FE/src/modules/analytics/intelTypes.ts`
- Create: `FE/src/modules/analytics/pages/ListingIntelPage.tsx`, `pages/ListingIntelDetailPage.tsx`
- Create: `FE/src/modules/analytics/components/intel/` gồm `IntelTable.tsx`, `AxisRadar.tsx`, `ImagePanel.tsx`, `KeywordPanel.tsx`, `TagPanel.tsx`, `MarketPanel.tsx`, `TrendTimeline.tsx`, `AdviceList.tsx`, `ModelCard.tsx`, `IntelReport.tsx` (ghép các panel, dùng chung cho trang chi tiết và modal chấm thử), `IntelPreviewModal.tsx`
- Create: `FE/src/modules/product/components/MaterialInput.tsx`
- Modify: `FE/src/modules/analytics/pages/InsightsPortal.tsx` (route `listing-intel` và `listing-intel/:id`), `FE/src/modules/analytics/nav.ts` (mục "Phân tích listing" trong nhóm "Nhìn vào trong", feature `F29 v2`), `FE/src/modules/analytics/services/analyticsApi.ts` (`intelPreview(body)`)
- Modify: `FE/src/modules/product/types/product.ts` (`materials?: string[]` trong `ProductFormData` và kiểu sản phẩm), `ProductFormBasicFields.tsx` hoặc `ProductFormModal.tsx` (gắn `MaterialInput`), `FE/src/modules/seller/components/create-product/Step4ProductDetails.tsx` (gắn `MaterialInput` và nút "Chấm thử trước khi đăng" mở `IntelPreviewModal`), `useProductFormState.ts` và `productsService.ts` (gửi `materials`)

**Interfaces:**
- Consumes (JSON từ AI, qua BE):
  - `GET /listings/:id/intel` và `POST /listings/intel/preview` trả `ListingIntel`:
    - `score`, `base`, `demand_factor`
    - `score_timeline[]`: `{week_start, score, demand_factor, events[]}`
    - `axes`: `{image|text|tags|market|trend: {score|null, evidence: 'measured'|'practice', metrics, issues[], missing_reason?}}`
    - `material`: `{declared[], detected[], required, missing}`
    - `keywords[]`: `{term, lift, trend: 'up'|'flat'|'down'|null, in_title}`
    - `tags[]`: `{tag, verdict: 'keep'|'weak'|'duplicate'|'pending', reason}`
    - `suggested_tags[]`: `{tag, reason}`
    - `images[]`: `{url, metrics, issues[], style, sim_title}`
    - `market`: `{price_pct, neighbors, near_duplicates, median_price}`
    - `advice[]`: `{axis, code, message, evidence, effort, impact|null}`
    - `peers`: `{group, size}`
    - `model`: `{version, auc, auc_ci95, best_baseline: {name, auc}, trained_on}`
    - `product_id?`, `date?`
  - `GET /listings/intel` trả `{items: [{product_id, title, thumbnail, score, axes: {image, text, tags, market, trend}, trend_direction, computed_at}], total}`.
  - `GET /trends/calendar` trả `{events: [{key, name, date, prep_start, groups, keywords: [{term, momentum}]}]}`.
- Produces: `MaterialInput({ value: string[], onChange(v: string[]) })`: gợi ý từ danh sách chất liệu như `lexicon.json` của Task 2, tối đa 5 chip, cho nhập thêm.

- [ ] **Step 1:** Viết `intelTypes.ts` đúng như Consumes.
- [ ] **Step 2:** Viết các component:
  - `AxisRadar` dùng recharts `RadarChart`, 5 trục, trục `null` hiện "thiếu dữ liệu".
  - `TrendTimeline` dùng recharts `LineChart` theo `score`, có `ReferenceLine` cho từng sự kiện.
  - `AdviceList` có chip `Đã đo` / `Thực hành tốt` theo `evidence`.
  - `ModelCard` hiện AUC, CI, baseline tốt nhất và nguồn dữ liệu.
  - Không component nào hiển thị xác suất.
- [ ] **Step 3:** Viết các trang. Trang danh sách dùng `useInsight('/listings/intel')`. Trang chi tiết dùng `useInsight('/listings/:id/intel', {date})`, có ô chọn ngày để xem điểm theo thời điểm khác.
- [ ] **Step 4:** Ô chất liệu và modal chấm thử: modal gọi `analyticsApi.intelPreview` với dữ liệu form hiện tại, chỉ gửi ảnh Cloudinary.
- [ ] **Step 5:** Run `cd FE && npx tsc --noEmit -p .`. Expected: exit 0.

### Task 8: Bảng feature cho dữ liệu nghiên cứu

**Files:**
- Create: `app/core/listing_intel/features.py`, `scripts/li/build_features.py`, `scripts/li/images.py`
- Test: `tests/listing_intel/test_features.py`

**Interfaces:**
- Consumes:
  - Task 1: các file parquet sạch.
  - Task 2: `text_features`.
  - Task 3: `embed_images`, `embed_texts`.
  - Task 4: `quality`, `dhash`.
  - Task 5: `demand_factor`, `match_keywords`.
  - Task 9: `knn_features`, `KnnIndex`, `lift_table`, `oof_centroid_margin`.
- Produces:
  - `features.IMAGE_COLS`, `TEXT_COLS`, `MARKET_COLS`, `TREND_COLS`, `META_COLS`:
    - meta = `log_price`, `price_rel`, `n_images`
    - image = 8 khoá quality, `sim_title`, `sim_category`, `style_white_bg`, `style_lifestyle`, `style_flatlay`, `style_closeup`, `emb_pca_0` … `emb_pca_15`
    - market = `knn_price_pct`, `knn_dup_count`, `top_centroid_margin`
    - trend = `trend_factor`, `trend_matches`, `trend_momentum_max`
  - `features.image_semantics(img_vec, title_vec, group, prompt_vecs) -> dict[str, float]`
  - `features.assemble(inp, img_feats: dict | None, ctx: FeatureContext) -> dict[str, float]`. `FeatureContext` gồm:
    - `lift`, `group_median_price: dict[str, float]`, `pca`
    - `prompt_vecs: dict[str, np.ndarray]`: câu mô tả danh mục và kiểu ảnh lấy từ `data/style_prompts.json`
    - `knn: dict[str, KnnIndex]`, `trend_series`, `trend_kw_vecs`, `group_season`, `at: date`
  - `scripts/li/images.py`:
    - tải thumbnail `tiki26` và ảnh mẫu `tikifashion` vào `data-li/images/<sha1>.jpg`, cạnh dài 256, JPEG quality 85;
    - 8 luồng song song, bỏ qua file đã có;
    - in tỉ lệ lỗi; nếu tỉ lệ lỗi > 20% thì dừng và báo.
  - `build_features.main()` ghi:
    - `data-li/features/table.parquet`: tất cả cột feature cộng `listing_id, source, group, seller, split, top25, sold`
    - `data-li/features/emb.npz`: vector ảnh và tiêu đề theo `listing_id`
  - `style_prompts.json`:
    - mỗi group 1 câu mô tả tiếng Việt;
    - kiểu ảnh: "ảnh sản phẩm trên nền trắng", "ảnh người mẫu mặc sản phẩm ngoài đời", "ảnh sản phẩm xếp phẳng chụp từ trên xuống", "ảnh chụp cận chất liệu sản phẩm".

- [ ] **Step 1: Write failing tests:**
  - `test_assemble_has_all_columns`: `ListingInput` tối thiểu, `img_feats=None` → kết quả có đủ mọi cột trong 5 danh sách; các cột ảnh là NaN.
  - `test_price_rel_uses_group_median`: price 200000, median nhóm 100000 → `price_rel == pytest.approx(math.log(2))`
  - `test_no_banned_columns`: không có tên cột nào thuộc danh sách cấm trong Global Constraints.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/listing_intel/test_features.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `features.py`.
- [ ] **Step 4:** Implement và chạy `.venv/bin/python -m scripts.li.images`.
- [ ] **Step 5:** Implement `build_features.py`:
  - PCA (16 chiều) chỉ fit trên vector ảnh của tập train.
  - Bảng lift chỉ tính từ tập train.
  - `top_centroid_margin` tính out-of-fold (5 fold theo seller) cho các dòng train; dòng val và test dùng tâm học từ toàn bộ train.
  - Mốc trend: `tiki26` dùng `scraped_at`, `tiki23` dùng `2023-09-15`.
  - Run `.venv/bin/python -m scripts.li.build_features`. Expected: in shape và tỉ lệ NaN theo từng nhóm cột.
- [ ] **Step 6:** Run tests. Expected: PASS.

### Task 9: Trục tag và trục thị trường (hàm thuần)

**Files:**
- Create: `app/core/listing_intel/lift.py`, `tags_axis.py`, `market_axis.py`
- Test: `tests/listing_intel/test_tags_market.py`

**Interfaces:**
- Produces:
  - `lift.lift_table(titles: list[str], groups: list[str], top: list[int], min_count=20, alpha=1.0) -> dict[str, dict[str, float]]`. Giá trị là log-lift có làm mượt: `log(((c_top+α)/(N_top+α·V)) / ((c_all+α)/(N_all+α·V)))`.
  - `market_axis.KnnIndex(vecs: np.ndarray, prices: np.ndarray, top: np.ndarray)`
  - `market_axis.knn_features(vec, price, index, k=20, dup_cos=0.92) -> dict`, khoá `knn_price_pct`, `knn_dup_count`, `knn_median_price`
  - `market_axis.oof_centroid_margin(vecs, top, folds) -> np.ndarray`
  - `market_axis.centroid_margin(vec, top_centroid, rest_centroid) -> float`
  - `tags_axis.tag_report(tags, title, group, lift, trend_terms: set[str], pending: set[str], tag_vecs, ref_vec) -> tuple[float, list[dict], list[dict]]`. Trả về điểm thô, danh sách `[{tag, verdict, reason}]`, gợi ý `[{tag, reason}]`.
  - Công thức điểm thô (minh bạch, không học):
    `0.35·mean(clip(lift_tag, 0, 2)/2) + 0.25·share_trending + 0.20·mean_cos(tag_vec, ref_vec) + 0.20·attr_coverage − 0.1·n_duplicate − 0.05·n_pending`, cắt trong [0, 1].
  - Gợi ý tag: top 3 term của bảng lift trong group, chưa có trong tag hay tiêu đề, độ dài 1–3 âm tiết.
  - Verdict: `duplicate` khi trùng sau `fold`; `pending` khi tag nằm trong `pending`; `weak` khi lift < 0 và không trending; còn lại `keep`.

- [ ] **Step 1: Write failing tests:**
  - `test_lift_positive_for_top_terms`: 40 tiêu đề, `"da bò"` chỉ xuất hiện ở các dòng top → `lift["bags"]["da bò"] > 0`
  - `test_lift_respects_min_count`: term xuất hiện 3 lần không có trong bảng
  - `test_knn_dup_count`: 5 vector trùng và 15 vector ngẫu nhiên → `knn_dup_count == 5` khi query bằng vector trùng
  - `test_knn_price_pct`: query giá cao nhất → `knn_price_pct == 100`
  - `test_oof_margin_excludes_own_fold`: thêm một dòng top cực đoan vào fold 0 thì margin của chính dòng đó không đổi
  - `test_tag_duplicate_and_pending`: `["Len", "len", "vintage"]`, pending={"vintage"} → verdict lần lượt `keep`, `duplicate`, `pending`
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/listing_intel/test_tags_market.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run tests. Expected: PASS.

### Task 10: Huấn luyện, đánh giá, model bundle, báo cáo tự sinh

**Files:**
- Create: `scripts/li/train.py`, `scripts/li/evaluate.py`, `scripts/li/report.py`, `scripts/li/sanity.py`
- Output: `app/core/listing_intel/model/` gồm:
  - `fusion.joblib`, `axis_image.joblib`, `axis_text.joblib`, `axis_market.joblib`
  - `meta.json`
  - `reference/`: `score_dist.parquet`, `axis_dist.parquet`, `lift.json`, `pca.joblib`, `group_median_price.json`, `knn_<group>.npz` (float16), `centroids.npz`, `group_season.json`
- Output: `docs/LISTING_INTEL_REPORT.md`, `docs/listing_intel_results.json`
- Test: `tests/listing_intel/test_bundle.py`

**Interfaces:**
- Consumes: Task 8 (`table.parquet`, `emb.npz`); `scripts/f29_ml/evaluate.py` (`score_all`, `delta_ci`, `auc_ci`, grouped bootstrap).
- Produces:
  - `train.fit_bundle(table: DataFrame, out_dir: Path) -> dict`: học model gộp và từng trục, ghi bundle cùng `meta.json`, trả về `meta`. Task 11 dùng hàm này để tạo bundle nhỏ cho test.
  - `meta.json` có các khoá:
    - `model_version: "li-1.0"`, `sklearn`, `onnx_model`
    - `features`, `axis_features {image, text, market}`, `groups`
    - `metrics {test: {...}, val: {...}}`, `baselines {name: metrics}`, `best_baseline {name, auc, delta, ci95}`
    - `ablation {image|text|market|trend: {lift, ci95}}`, `evidence {image|text|tags|market|trend: "measured"|"practice"}`
    - `thresholds {dup_cos: 0.92, trend_match_cos: 0.80}`
    - `trend_backtest {n, share_mase_lt_1}`, `trained_on`
  - Trục `tags` và `trend` luôn là `practice`, trừ khi ablation của trend đạt tiêu chí.
- **Model:** `HistGradientBoostingClassifier(learning_rate=0.05, max_iter=400, random_state=42)` dùng cho model gộp và từng trục. Học trên `split=="train"` của cả 2 nguồn, cột `group` dạng category. Chọn kết quả theo val, báo cáo trên test. Bundle là model học trên train.
- **Baseline:**
  - ngẫu nhiên;
  - `health-1.0` (điểm content tính từ `n_images` với mốc 5 ảnh, `desc_len` với mốc 150, không có tag);
  - chỉ `log_price`;
  - chỉ `n_images`;
  - TF-IDF tiêu đề (n-gram âm tiết 1–2, `min_df=3`) + `LogisticRegression(max_iter=2000)`.
- **Ablation:** bỏ từng nhóm cột rồi học lại; CI ghép cặp bằng `delta_ci`, lấy mẫu theo seller.
- **Test lệch thời gian:** model chỉ dùng `TEXT_COLS + META_COLS`, học trên toàn bộ `tiki23`, chấm trên `tiki26` test.
- **Sanity (`sanity.py`):**
  - xáo trộn nhãn train → AUC test trong [0,45; 0,55];
  - không seller nào nằm ở 2 tập;
  - không cột cấm nào lọt vào feature;
  - chạy lại 2 lần thì dự đoán giống hệt nhau;
  - ảnh tăng sáng ±10% và nén JPEG q70 trên 50 ảnh test → điểm trục ảnh lệch trung vị ≤ 5 điểm phân vị.
- **Retrieval check:** 200 cặp ảnh–caption của `tikifashion`, tỉ lệ top-1 so với ngẫu nhiên.
- **Trend:** `backtest` cho mọi từ khoá đủ điều kiện; tương quan giữa chỉ số mùa Google Trends và `tikireviews_monthly` theo group.

- [ ] **Step 1: Write failing tests** in `test_bundle.py` (skip nếu chưa có bundle):
  - `test_meta_has_required_keys`: đủ các khoá liệt kê ở trên.
  - `test_evidence_rule`: với mỗi trục là `measured` thì `ablation[axis]["lift"] >= 0.005` và `ablation[axis]["ci95"][0] > 0`.
  - `test_score_dist_monotone`: phân vị trong `score_dist.parquet` tăng dần theo từng group.
- [ ] **Step 2:** Implement `train.py`, `evaluate.py`, `sanity.py`, `report.py`. Báo cáo có các mục theo spec mục 8, cộng mục "Điểm yếu và ảnh hưởng" để Task 12 điền.
- [ ] **Step 3:** Run `.venv/bin/python -m scripts.li.train && .venv/bin/python -m scripts.li.evaluate`. Expected: tạo bundle và báo cáo; in bảng test và kết quả sanity.
- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/listing_intel/test_bundle.py -q`. Expected: PASS.

### Task 11: Runtime, đọc dữ liệu sàn, fusion, lời khuyên, endpoint, job

**Files:**
- Create: `app/core/listing_intel/live_data.py`, `fusion.py`, `advice.py`, `store.py`, `service.py`, `jobs.py`
- Create: `app/api/v1/f29_intel.py`
- Modify: `app/api/v1/analytics_routes.py` (đăng ký router như cách các router F khác đang làm), `app/core/f29_scheduler.py` hoặc nơi khởi động scheduler (đăng ký job từ `jobs.py`)
- Test: `tests/listing_intel/test_service.py`, `tests/listing_intel/test_router.py`

**Interfaces:**
- Consumes: Task 2–5, 8, 9; bundle của Task 10. Trước khi có bundle thật, test dùng fixture tạo bundle nhỏ từ dữ liệu tổng hợp qua chính `scripts/li/train.py`, hàm `fit_bundle(table: DataFrame, out_dir: Path)`.
- Produces:
  - `live_data.load_listing(product_id) -> ListingInput | None`
  - `live_data.shop_listings(shop_id) -> list[ListingInput]`
  - `live_data.peer_inputs(group) -> list[ListingInput]`
  - `live_data.pending_tags() -> set[str]`
  - Đọc: `products` (title, description, tags, materials, categories, images, shop_id, updated_at), giá trung vị của các `product_variants` đang hoạt động, `tags` (`status` hoặc `review_status` là `pending`).
  - `fusion.load_bundle() -> Bundle`: kiểm tra phiên bản sklearn, nạp lười. `fusion.base_score(feats, group) -> float` (phân vị 0–100). `fusion.axis_scores(feats, group) -> dict[str, float | None]`.
  - `advice.build(axes: dict[str, AxisResult], material: dict, evidence: dict, impacts: dict) -> list[dict]`: xếp theo `(evidence == "measured", impact, -effort)`, tối đa 6 mục.
  - `store.save_score(doc)`: upsert theo `(product_id, date, model_version)` vào `listing_intel_scores`. `store.get_embedding(url) / put_embedding(url, vec, metrics)` với `_id = sha1(url)` trong `listing_embeddings`, vector lưu dạng bytes float16.
  - `service.analyze(inp: ListingInput, at: date, persist: bool) -> dict`: trả đúng dạng `ListingIntel` như Task 7 Consumes.
  - `service.shop_summary(shop_id) -> dict`
  - `service.calendar(shop_id, category: str | None) -> dict`
  - Router:
    - `GET /api/analytics/listings/intel`
    - `GET /api/analytics/listings/{id}/intel?date=`
    - `POST /api/analytics/listings/intel/preview`
    - `GET /api/analytics/trends/calendar?category=`
    - Dùng `CurrentShop`, kiểm tra quyền như `_kiem_quyen_listing` trong `f29_health.py`, envelope `ok` / `insufficient`, meta có `model_version`.
    - Đăng ký `/listings/intel` trước `/listings/{id}/intel`.
  - `jobs.nightly()`: tính lại listing có `updated_at` mới hơn điểm cuối, chạy lúc 02:00.
  - `jobs.weekly_trends()`: thứ Hai 03:00, gọi collector với từ khoá mở rộng; lỗi thì chỉ ghi log.
  - Hàm `impacts`: với mỗi feature ảnh hoặc chữ sửa được, đặt feature đó bằng trung vị nhóm top25 trong reference, chấm lại phân vị; mức tăng chính là impact.

- [ ] **Step 1: Write failing tests:**
  - `test_analyze_without_images`: `image_urls=[]` → `axes.image.score is None`, `missing_reason` có chữ "ảnh", `score` không phải None.
  - `test_analyze_failed_downloads`: monkeypatch `image_fetch.fetch` luôn trả `None` → kết quả như test trên.
  - `test_unknown_category_falls_back`: `category="Danh mục mới"` → `peers.group is None`, có điểm.
  - `test_material_missing_for_fashion`: group fashion, không chất liệu → `material.missing is True`, advice có `missing_material` với evidence `practice`.
  - `test_timeline_has_8_weeks_and_bounds`: `len(score_timeline) == 8`, mọi score nằm trong [0, 100], mọi `demand_factor` trong [0,5; 1,5].
  - `test_preview_rejects_disallowed_url` (router): `image_urls=["https://evil.com/a.jpg"]` → 422 hoặc `insufficient`, không gọi fetch.
  - `test_other_shop_forbidden` (router): listing của shop khác → 403.
  - `test_persist_upserts_once`: `analyze(..., persist=True)` 2 lần cùng ngày → 1 document.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/listing_intel/test_service.py tests/listing_intel/test_router.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. Vector ảnh lấy từ cache trước, chưa có mới tải và nhúng. Ảnh tải song song tối đa 4 luồng.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Chạy thật: `MONGO_DB_LIVE=vietcraft-test .venv/bin/python -c "from app.core.listing_intel.service import analyze; ..."` cho 1 sản phẩm có ảnh. Expected: đủ 5 trục, thời gian in ra; lần chạy thứ 2 (đã có cache) dưới 1 giây.

### Task 12: Tích hợp đầu cuối, báo cáo, vòng sửa điểm yếu, review

**Files:**
- Modify: `docs/LISTING_INTEL_REPORT.md` (các mục viết tay)
- Modify: các file của Task 2–11 theo điểm yếu tìm ra

- [ ] **Step 1:** Chạy stack local:
  - AI: `MONGO_DB_LIVE=vietcraft-test` trên cổng 8010.
  - BE: `MONGO_URI=mongodb://127.0.0.1:27017/vietcraft-test`, `AI_ANALYTICS_URL=http://localhost:8010`, cổng 8080.
  - FE: `VITE_API_URL=http://localhost:8080/api` trên cổng 3000.
  - Gọi 4 endpoint qua BE bằng token seller local, xác nhận dạng JSON khớp `intelTypes.ts`.
- [ ] **Step 2:** Chụp màn hình bằng Chrome headless (theo script `shot.mjs` trong scratchpad): trang danh sách, trang chi tiết của sản phẩm có ảnh, modal chấm thử. Kiểm tra ở bề rộng 375px.
- [ ] **Step 3:** Chạy trên dữ liệu thật VietCraft: độ phủ từng trục, phân phối điểm, PSI giữa feature Tiki và VietCraft, 5 ví dụ. Điền vào báo cáo.
- [ ] **Step 4:** Viết mục "Drawback, điểm yếu và ảnh hưởng": mỗi điểm yếu gồm ảnh hưởng tới trục hoặc endpoint nào, cách sửa, và trạng thái (đã sửa hoặc giới hạn đã chấp nhận).
- [ ] **Step 5:** Sửa các điểm yếu sửa được. Chạy lại `scripts.li.train`, `scripts.li.evaluate` và toàn bộ test. Cập nhật báo cáo.
- [ ] **Step 6:** Hai agent review độc lập, một agent soi phương pháp và rò rỉ dữ liệu, một agent soi runtime, an toàn và FE. Sửa các lỗi được xác nhận.
- [ ] **Step 7:** Kiểm tra cuối:
  - `.venv/bin/python -m pytest tests -q`: chỉ còn 2 lỗi cũ của `test_api_contract`.
  - `npx tsc --noEmit -p .` ở BE và FE.
  - Dọn `scratchpad/venv` và `scratchpad/dl` sau khi Task 1 đã copy dữ liệu.
- [ ] **Step 8:** Commit, chỉ khi người dùng đồng ý: nhánh `feat/listing-intel` ở 3 repo, không có CSV, parquet, ảnh hay ONNX.
