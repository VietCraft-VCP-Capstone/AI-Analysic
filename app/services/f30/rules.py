Z_THRESHOLD = 2.0
WINDOW = 28                 # ngày baseline trước t
MIN_HISTORY_DAYS = 28       # ngày kể từ ngày đầu có view/đơn
MIN_EXPECTED = {"views": 5.0, "revenue": 1.0}   # revenue: đơn tương đương
MIN_ACTUAL_SPIKE = {"views": 10.0, "revenue": 2.0}
MIN_CHANGE_PCT = 30.0
MIN_CHANGE_VND = 100_000
MAX_ZERO_RUN = 14
TOP_LISTINGS = 3
MODEL_VERSION = "f30-nb-1.0"


def passes_gates(metric: str, direction: str, mu: float, actual: float,
                 expected_vnd: float, actual_vnd: float) -> bool:
    if direction == "drop" and mu < MIN_EXPECTED[metric]:
        return False
    if direction == "spike" and actual < MIN_ACTUAL_SPIKE[metric]:
        return False
    if abs(actual - mu) < MIN_CHANGE_PCT / 100 * mu:
        return False
    if metric == "revenue" and abs(actual_vnd - expected_vnd) < MIN_CHANGE_VND:
        return False
    return True
