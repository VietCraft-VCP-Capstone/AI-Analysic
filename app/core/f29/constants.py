"""Hằng số công thức health-1.0 (PLAN_SELLER_AI_LISTING_HEALTH.md §4)."""

MODEL_VERSION = "health-1.0"

WEIGHTS = {
    "conversion": 0.30,
    "rating": 0.25,
    "content": 0.20,
    "inventory": 0.15,
    "freshness": 0.10,
}

# Mục tiêu nội dung (quyết định D3)
MIN_IMAGES = 5
MIN_DESCRIPTION_LENGTH = 150
MIN_TAGS_APPROVED = 3

MIN_TITLE_LENGTH = 20
MAX_TITLE_LENGTH = 120

# m=50 ổn định nhất trong 10/20/50 khi chia đôi review Olist theo thời gian.
# Xem docs/BAYES_M_SELECTION.md.
K_BAYESIAN_SHRINKAGE = 50

FRESHNESS_FULL_SCORE_DAYS = 90
FRESHNESS_ZERO_SCORE_DAYS = 365

# Tỉ lệ mua trên vài chục lượt xem dao động quá mạnh, nên chỉ chấm listing đủ lượt xem.
CONVERSION_WINDOW_DAYS = 30
MIN_VIEWS_CONVERSION = 100
# Danh mục thiếu bạn so sánh thì lùi về toàn sàn; toàn sàn cũng thiếu thì trục chưa tính.
MIN_CONVERSION_PEERS = 5
CR_INDEX_CAP = 2.0

# Danh mục ít hơn ngần này listing thì dùng trung vị toàn sàn làm mốc.
MIN_CATEGORY_SAMPLE = 8

# Giữ đúng mốc 80% của build_marts._viec_can_lam() để live và offline cùng một
# định nghĩa "đủ tồn kho".
MIN_STOCK_RATIO_PCT = 80.0

# Công sức sửa từng loại todo — sắp theo expected_gain / effort.
EFFORT = {"images": 1, "description": 2, "tags": 1, "stock": 3}
