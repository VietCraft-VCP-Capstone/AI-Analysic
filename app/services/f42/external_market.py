import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import joblib
import numpy as np
import pandas as pd

from app.services.f42.vi_text import clean_tokens, normalize_nfc, strip_accents

# Đường dẫn đến bộ dữ liệu data-li Tiki & thư mục Model
TIKI_CLEAN_DIR = Path(__file__).resolve().parents[4] / "data-li" / "data-li" / "clean"
TIKI23_PATH = TIKI_CLEAN_DIR / "tiki23.parquet"
TIKI26_PATH = TIKI_CLEAN_DIR / "tiki26.parquet"

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "f42"
CAT_MODEL_PATH = MODEL_DIR / "category_classifier.joblib"
PRICE_MODEL_PATH = MODEL_DIR / "pricing_quantile_model.joblib"
LIFT_JSON_PATH = MODEL_DIR / "top_selling_lift.json"

# Ánh xạ tên danh mục tiếng Việt sang nhóm dữ liệu Tiki
GROUP_KEYWORDS: Dict[str, List[str]] = {
    "bags": ["túi", "balo", "ví", "bóp", "cặp", "tote", "bag", "leather"],
    "shoes": ["giày", "dép", "guốc", "sandal", "sneaker", "ủng"],
    "accessories": ["phụ kiện", "trang sức", "vòng", "nhẫn", "khuyên", "móc khóa", "dây chuyền"],
    "fashion": ["áo", "quần", "váy", "đầm", "thời trang", "hoodie", "jacket", "set"],
    "sport": ["thể thao", "bóng đá", "tập gym", "chạy bộ", "sport"],
    "home": ["nhà cửa", "trang trí", "nến", "ly", "cốc", "bình", "gốm", "decor", "gối"]
}


class ExternalMarketProvider:
    """
    Cung cấp dữ liệu thị trường bên ngoài và các mô hình Machine Learning
    (Category Classifier & Quantile Regressors) huấn luyện trên 45.000 sản phẩm TMĐT.
    """

    _cached_prices_by_group: Dict[str, List[float]] = {}
    _cached_top_titles_by_group: Dict[str, List[str]] = {}
    _is_loaded: bool = False

    # ML Artifacts
    _cat_artifact: Optional[Dict[str, Any]] = None
    _price_artifact: Optional[Dict[str, Any]] = None
    _lift_dict: Optional[Dict[str, List[Dict[str, Any]]]] = None

    @classmethod
    def _load_data_if_needed(cls):
        if cls._is_loaded:
            return

        cls._cached_prices_by_group = {g: [] for g in GROUP_KEYWORDS}
        cls._cached_top_titles_by_group = {g: [] for g in GROUP_KEYWORDS}

        try:
            # 1. Nạp tiki23 (accessories, bags, shoes)
            if TIKI23_PATH.exists():
                df23 = pd.read_parquet(TIKI23_PATH, columns=["group", "price", "title", "top25", "split"])
                df23_train = df23[df23["split"] == "train"] if "split" in df23.columns else df23
                for group, group_df in df23_train.groupby("group"):
                    if group in cls._cached_prices_by_group:
                        cls._cached_prices_by_group[group].extend(
                            group_df["price"].dropna().astype(float).tolist()
                        )
                    top_df = group_df[group_df["top25"] == 1] if "top25" in group_df.columns else group_df.head(50)
                    if group in cls._cached_top_titles_by_group:
                        cls._cached_top_titles_by_group[group].extend(
                            top_df["title"].dropna().astype(str).tolist()[:100]
                        )

            # 2. Nạp tiki26 (fashion, sport, home)
            if TIKI26_PATH.exists():
                df26 = pd.read_parquet(TIKI26_PATH, columns=["group", "price", "title", "top25", "split"])
                df26_train = df26[df26["split"] == "train"] if "split" in df26.columns else df26
                for group, group_df in df26_train.groupby("group"):
                    if group in cls._cached_prices_by_group:
                        cls._cached_prices_by_group[group].extend(
                            group_df["price"].dropna().astype(float).tolist()
                        )
                    top_df = group_df[group_df["top25"] == 1] if "top25" in group_df.columns else group_df.head(50)
                    if group in cls._cached_top_titles_by_group:
                        cls._cached_top_titles_by_group[group].extend(
                            top_df["title"].dropna().astype(str).tolist()[:100]
                        )

            # 3. Nạp ML models nếu tồn tại
            if CAT_MODEL_PATH.exists():
                cls._cat_artifact = joblib.load(CAT_MODEL_PATH)

            if PRICE_MODEL_PATH.exists():
                cls._price_artifact = joblib.load(PRICE_MODEL_PATH)

            if LIFT_JSON_PATH.exists():
                with open(LIFT_JSON_PATH, "r", encoding="utf-8") as f:
                    cls._lift_dict = json.load(f)

            cls._is_loaded = True
        except Exception:
            cls._is_loaded = True

    @classmethod
    def match_group(cls, category_name: str, title: str = "") -> str:
        """Nhận diện nhóm ngành hàng kết hợp ML Category Classifier + Quy tắc từ khóa."""
        cls._load_data_if_needed()

        # Thử bằng ML Classifier trước nếu có title
        if title and cls._cat_artifact:
            try:
                vec = cls._cat_artifact["vectorizer"]
                clf = cls._cat_artifact["classifier"]
                X = vec.transform([title])
                probs = clf.predict_proba(X)[0]
                best_idx = int(np.argmax(probs))
                if probs[best_idx] >= 0.40:
                    classes = cls._cat_artifact.get("classes")
                    if classes and best_idx < len(classes):
                        return str(classes[best_idx])
                    classes_attr = getattr(clf, "classes_", [])
                    if best_idx < len(classes_attr):
                        return str(classes_attr[best_idx])
            except Exception:
                pass

        # Fallback bằng từ khóa
        text = f"{normalize_nfc(category_name)} {normalize_nfc(title)}".lower()
        text_no_acc = strip_accents(text)

        for group, keywords in GROUP_KEYWORDS.items():
            for kw in keywords:
                kw_norm = strip_accents(kw)
                if re.search(rf"\b{re.escape(kw_norm)}\b", text_no_acc):
                    return group

        return "home"

    @classmethod
    def predict_price_band_ml(cls, title: str, category_name: str = "") -> Optional[Tuple[int, int, int]]:
        """
        Dự đoán dải giá P25 - P50 - P75 cá nhân hóa bằng Quantile Regressors đã huấn luyện.
        """
        cls._load_data_if_needed()
        if not cls._price_artifact or not title:
            return None

        try:
            p_vec = cls._price_artifact["vectorizer"]
            p_svd = cls._price_artifact["svd"]
            g_to_idx = cls._price_artifact["group_to_idx"]
            models = cls._price_artifact["models"]

            group = cls.match_group(category_name, title)

            X_t = p_vec.transform([title])
            X_s = p_svd.transform(X_t)

            X_g = np.zeros((1, len(g_to_idx)))
            if group in g_to_idx:
                X_g[0, g_to_idx[group]] = 1.0

            X_in = np.hstack([X_s, X_g])

            p25_raw = float(np.exp(models["p25"].predict(X_in)[0]))
            p50_raw = float(np.exp(models["p50"].predict(X_in)[0]))
            p75_raw = float(np.exp(models["p75"].predict(X_in)[0]))

            # Đảm bảo đơn điệu
            p25 = int(round(min(p25_raw, p50_raw) / 1000) * 1000)
            p50 = int(round(p50_raw / 1000) * 1000)
            p75 = int(round(max(p75_raw, p50_raw) / 1000) * 1000)

            return (p25, p50, p75)
        except Exception:
            return None

    @classmethod
    def get_market_prices(cls, category_name: str, title: str = "") -> List[float]:
        """Lấy danh sách giá thực tế từ tập Tiki train."""
        cls._load_data_if_needed()
        group = cls.match_group(category_name, title)
        return cls._cached_prices_by_group.get(group, [])

    @classmethod
    def get_top_selling_titles(cls, category_name: str, title: str = "", limit: int = 5) -> List[str]:
        """Lấy danh sách tiêu đề top 25 bán chạy nhất của nhóm ngành."""
        cls._load_data_if_needed()
        group = cls.match_group(category_name, title)
        titles = cls._cached_top_titles_by_group.get(group, [])
        return titles[:limit]

    @classmethod
    def get_lifted_keywords(cls, category_name: str, title: str = "", top_n: int = 8) -> List[Dict[str, Any]]:
        """Lấy danh sách từ khóa có Lift cao nhất từ nhóm bán chạy Top 25."""
        cls._load_data_if_needed()
        if not cls._lift_dict:
            return []
        group = cls.match_group(category_name, title)
        items = cls._lift_dict.get(group, [])
        return items[:top_n]
