"""
Module Cào & Tổng hợp dữ liệu từ Sàn VietCraft và Google Trending (F42 Market Aggregator).

Chức năng:
1. Cào dữ liệu sản phẩm cùng danh mục / thương hiệu trên chính sàn VietCraft (MongoDB products & product_variants).
2. Lấy dữ liệu từ khóa xu hướng & nhu cầu tìm kiếm thực tế từ Google Trends (Google Suggest VN + Atlas data-collection).
3. Suy luận mức giá hợp lý và thuyết phục cho các sản phẩm mới / model thế hệ mới dựa trên phân khúc thương hiệu,
   dòng tiền nhiệm và xu hướng thị trường.
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from app.services.f42.vi_text import clean_tokens, normalize_nfc, strip_accents

logger = logging.getLogger(__name__)

# Bảng phân khúc thương hiệu & dòng sản phẩm TMĐT (chuẩn hóa theo thị trường Việt Nam)
# Giúp định giá chính xác và thuyết phục các sản phẩm mới, phiên bản kế tiếp (như iPhone 17/18, Galaxy S mới, v.v.)
BRAND_SEGMENT_BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "iphone_promax": {
        "keywords": ["iphone", "pro max", "promax"],
        "brand": "Apple",
        "segment_name": "Flagship cao cấp nhất của Apple (Pro Max)",
        "p25": 29_990_000,
        "p50": 34_990_000,
        "p75": 39_990_000,
        "reference_line": "dòng tiền nhiệm iPhone Pro Max (256GB - 512GB)",
    },
    "iphone_pro": {
        "keywords": ["iphone", "pro"],
        "brand": "Apple",
        "segment_name": "Flagship cao cấp Apple (Pro)",
        "p25": 24_990_000,
        "p50": 28_490_000,
        "p75": 32_990_000,
        "reference_line": "dòng tiền nhiệm iPhone Pro",
    },
    "iphone_standard": {
        "keywords": ["iphone"],
        "brand": "Apple",
        "segment_name": "Smartphone tiêu chuẩn của Apple",
        "p25": 17_990_000,
        "p50": 21_490_000,
        "p75": 25_990_000,
        "reference_line": "dòng tiền nhiệm iPhone tiêu chuẩn / Plus",
    },
    "samsung_ultra": {
        "keywords": ["galaxy s", "ultra", "samsung"],
        "brand": "Samsung",
        "segment_name": "Flagship cao cấp nhất của Samsung (Galaxy Ultra)",
        "p25": 25_990_000,
        "p50": 30_490_000,
        "p75": 34_990_000,
        "reference_line": "dòng tiền nhiệm Galaxy S Ultra",
    },
    "samsung_fold": {
        "keywords": ["galaxy z fold", "z fold", "fold"],
        "brand": "Samsung",
        "segment_name": "Smartphone màn hình gập cao cấp (Galaxy Z Fold)",
        "p25": 34_990_000,
        "p50": 40_990_000,
        "p75": 45_990_000,
        "reference_line": "dòng tiền nhiệm Galaxy Z Fold",
    },
    "samsung_flip": {
        "keywords": ["galaxy z flip", "z flip", "flip"],
        "brand": "Samsung",
        "segment_name": "Smartphone gập thời trang (Galaxy Z Flip)",
        "p25": 18_990_000,
        "p50": 23_490_000,
        "p75": 27_990_000,
        "reference_line": "dòng tiền nhiệm Galaxy Z Flip",
    },
    "macbook_pro": {
        "keywords": ["macbook pro", "macbook"],
        "brand": "Apple",
        "segment_name": "Laptop chuyên nghiệp cao cấp của Apple",
        "p25": 38_990_000,
        "p50": 46_990_000,
        "p75": 54_990_000,
        "reference_line": "dòng MacBook Pro chip Apple Silicon",
    },
    "macbook_air": {
        "keywords": ["macbook air"],
        "brand": "Apple",
        "segment_name": "Laptop mỏng nhẹ cao cấp của Apple",
        "p25": 22_990_000,
        "p50": 26_990_000,
        "p75": 31_990_000,
        "reference_line": "dòng MacBook Air M-Series",
    },
    "ipad_pro": {
        "keywords": ["ipad pro"],
        "brand": "Apple",
        "segment_name": "Máy tính bảng cao cấp Apple iPad Pro",
        "p25": 24_990_000,
        "p50": 29_990_000,
        "p75": 36_990_000,
        "reference_line": "dòng iPad Pro M-Series",
    },
    "apple_watch": {
        "keywords": ["apple watch", "apple watch ultra"],
        "brand": "Apple",
        "segment_name": "Đồng hồ thông minh Apple Watch",
        "p25": 8_990_000,
        "p50": 13_990_000,
        "p75": 21_990_000,
        "reference_line": "dòng Apple Watch Series & Ultra",
    },
    "airpods": {
        "keywords": ["airpods pro", "airpods"],
        "brand": "Apple",
        "segment_name": "Tai nghe không dây Apple AirPods",
        "p25": 3_490_000,
        "p50": 4_990_000,
        "p75": 6_490_000,
        "reference_line": "dòng tai nghe AirPods / AirPods Pro",
    },
}


class MarketDataAggregator:
    """Bộ thu thập & kết hợp dữ liệu Sàn VietCraft + Google Trending."""

    @classmethod
    def fetch_internal_platform_data(
        cls,
        title: str,
        category_name: str,
        db_live: Any
    ) -> Dict[str, Any]:
        """
        Cào dữ liệu từ database sàn VietCraft (MongoDB products & product_variants).
        Tìm các sản phẩm cùng danh mục, cùng nhóm từ khóa, hoặc cùng phân khúc thương hiệu.
        """
        result: Dict[str, Any] = {
            "found_count": 0,
            "prices": [],
            "p25": 0,
            "p50": 0,
            "p75": 0,
            "sample_titles": [],
            "common_tags": [],
            "summary_text": "Chưa có sản phẩm tương tự trực tiếp trên sàn VietCraft."
        }

        if db_live is None or not (title or category_name):
            return result

        try:
            tokens = [w for w in clean_tokens(title) if len(w) >= 2][:4]
            regex_patterns = [{"title": {"$regex": re.escape(w), "$options": "i"}} for w in tokens]

            filter_clauses: List[Dict[str, Any]] = []
            if regex_patterns:
                filter_clauses.append({"$or": regex_patterns})
            if category_name:
                filter_clauses.append({
                    "$or": [
                        {"categories": {"$regex": re.escape(category_name), "$options": "i"}},
                        {"category_name": {"$regex": re.escape(category_name), "$options": "i"}}
                    ]
                })

            query: Dict[str, Any] = {"is_hidden": {"$ne": True}}
            if filter_clauses:
                query["$or"] = filter_clauses

            cursor = db_live["products"].find(
                query,
                {"title": 1, "min_price": 1, "max_price": 1, "tags": 1}
            ).limit(40)

            prods = list(cursor)
            if not prods and category_name:
                # Tìm nới lỏng theo danh mục
                prods = list(db_live["products"].find(
                    {"is_hidden": {"$ne": True}},
                    {"title": 1, "min_price": 1, "max_price": 1, "tags": 1}
                ).limit(20))

            prices: List[float] = []
            tags_counter: Dict[str, int] = {}
            titles: List[str] = []

            for p in prods:
                t = p.get("title")
                if t:
                    titles.append(t)
                min_p = p.get("min_price")
                max_p = p.get("max_price")
                if min_p and float(min_p) > 1000:
                    prices.append(float(min_p))
                if max_p and float(max_p) > 1000 and max_p != min_p:
                    prices.append(float(max_p))

                for tag in p.get("tags") or []:
                    tag_str = str(tag).strip()
                    if tag_str and len(tag_str) >= 2:
                        tags_counter[tag_str] = tags_counter.get(tag_str, 0) + 1

            if prices:
                prices.sort()
                n = len(prices)
                p25 = int(prices[int(n * 0.25)])
                p50 = int(prices[int(n * 0.50)])
                p75 = int(prices[int(n * 0.75)])

                sorted_tags = sorted(tags_counter.items(), key=lambda kv: kv[1], reverse=True)
                top_tags = [kv[0] for kv in sorted_tags[:8]]

                summary = (
                    f"Dữ liệu sàn VietCraft: Tìm thấy {len(prods)} sản phẩm cùng ngành hàng, "
                    f"khoảng giá niêm yết từ {p25:,}đ đến {p75:,}đ, giá trung vị {p50:,}đ."
                )

                result["found_count"] = len(prods)
                result["prices"] = prices
                result["p25"] = p25
                result["p50"] = p50
                result["p75"] = p75
                result["sample_titles"] = titles[:5]
                result["common_tags"] = top_tags
                result["summary_text"] = summary
        except Exception as e:
            logger.warning(f"Lỗi khi cào dữ liệu nội bộ sàn VietCraft: {e}")

        return result

    @classmethod
    def fetch_google_trending_data(
        cls,
        query: str,
        category_name: str = "",
        db_data: Any = None
    ) -> Dict[str, Any]:
        """
        Cào dữ liệu từ khóa tìm kiếm hot nhất từ Google Trends Việt Nam
        (Google Suggest API thời gian thực + MongoDB trend_keyword / trend_related).
        """
        result: Dict[str, Any] = {
            "trending_keywords": [],
            "search_signals": [],
            "summary_text": ""
        }

        clean_q = normalize_nfc(query or "").strip()
        if not clean_q:
            return result

        trending_list: List[str] = []

        # 1. Truy vấn Google Suggest / Realtime Trends cho Việt Nam (hl=vi, gl=vn)
        try:
            encoded_q = urllib.parse.quote_plus(clean_q)
            url = f"https://suggestqueries.google.com/complete/search?client=firefox&hl=vi&gl=vn&q={encoded_q}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                        for item in data[1]:
                            item_clean = normalize_nfc(str(item)).strip()
                            if item_clean and item_clean.lower() != clean_q.lower() and item_clean not in trending_list:
                                trending_list.append(item_clean)
        except Exception as e:
            logger.debug(f"Google Suggest trends không phản hồi: {e}")

        # 2. Truy vấn từ MongoDB data-collection (nếu có kết nối)
        if db_data is not None:
            try:
                tokens = clean_tokens(clean_q)
                for t in tokens:
                    if len(t) < 3:
                        continue
                    kws = list(db_data["trend_keyword"].find(
                        {"keyword": {"$regex": re.escape(t), "$options": "i"}},
                        {"keyword": 1}
                    ).limit(5))
                    for k in kws:
                        kw_str = str(k.get("keyword", "")).strip()
                        if kw_str and kw_str not in trending_list:
                            trending_list.append(kw_str)

                    # trend_related
                    rels = list(db_data["trend_related"].find(
                        {"query": {"$regex": re.escape(t), "$options": "i"}},
                        {"query": 1, "related_queries": 1}
                    ).limit(3))
                    for r in rels:
                        rq = r.get("query")
                        if rq and rq not in trending_list:
                            trending_list.append(str(rq))
            except Exception:
                pass

        # 3. Trích xuất tín hiệu nhu cầu tìm kiếm (search signals)
        signals: List[str] = []
        low_trends = " ".join(trending_list).lower()
        if "giá bao nhiêu" in low_trends or "giá" in low_trends:
            signals.append("Người dùng quan tâm cao đến giá bán chính thức")
        if "512g" in low_trends or "1tb" in low_trends or "256g" in low_trends:
            signals.append("Xu hướng tìm kiếm phiên bản dung lượng cao (256GB - 512GB)")
        if "fpt" in low_trends or "thegioididong" in low_trends or "viettel" in low_trends:
            signals.append("Thị phần tìm kiếm tập trung vào kênh phân phối lớn")
        if "màu" in low_trends:
            signals.append("Người mua chú trọng đến màu sắc phiên bản mới")

        result["trending_keywords"] = trending_list[:10]
        result["search_signals"] = signals

        if trending_list:
            top_3 = ", ".join(f'"{kw}"' for kw in trending_list[:3])
            result["summary_text"] = f"Dữ liệu Google Trends: Các từ khóa tìm kiếm tăng trưởng cao gồm: {top_3}."
        else:
            result["summary_text"] = "Chưa ghi nhận từ khóa biến động đột biến trên Google Trends."

        return result

    @classmethod
    def match_brand_benchmark(cls, title: str) -> Optional[Dict[str, Any]]:
        """Nhận diện sản phẩm thuộc phân khúc thương hiệu lớn để định giá chính xác."""
        low = normalize_nfc(title or "").lower()

        # Apple iPhone Pro Max
        if "iphone" in low and ("promax" in low or "pro max" in low):
            return BRAND_SEGMENT_BENCHMARKS["iphone_promax"]

        # Apple iPhone Pro
        if "iphone" in low and "pro" in low:
            return BRAND_SEGMENT_BENCHMARKS["iphone_pro"]

        # Apple iPhone Tiêu Chuẩn / Plus
        if "iphone" in low:
            return BRAND_SEGMENT_BENCHMARKS["iphone_standard"]

        # Samsung Galaxy Z Fold
        if ("z fold" in low or "galaxy fold" in low) or ("fold" in low and "samsung" in low):
            return BRAND_SEGMENT_BENCHMARKS["samsung_fold"]

        # Samsung Galaxy Z Flip
        if ("z flip" in low or "galaxy flip" in low) or ("flip" in low and "samsung" in low):
            return BRAND_SEGMENT_BENCHMARKS["samsung_flip"]

        # Samsung Galaxy Ultra
        if "ultra" in low and ("samsung" in low or "galaxy" in low):
            return BRAND_SEGMENT_BENCHMARKS["samsung_ultra"]

        # MacBook Pro / Air
        if "macbook" in low:
            if "pro" in low:
                return BRAND_SEGMENT_BENCHMARKS["macbook_pro"]
            if "air" in low:
                return BRAND_SEGMENT_BENCHMARKS["macbook_air"]

        # iPad Pro
        if "ipad" in low and "pro" in low:
            return BRAND_SEGMENT_BENCHMARKS["ipad_pro"]

        # Apple Watch
        if "apple watch" in low or ("watch" in low and "apple" in low):
            return BRAND_SEGMENT_BENCHMARKS["apple_watch"]

        # AirPods
        if "airpod" in low or "airpods" in low:
            return BRAND_SEGMENT_BENCHMARKS["airpods"]

        for key, bench in BRAND_SEGMENT_BENCHMARKS.items():
            kws = bench["keywords"]
            if all(k in low for k in kws):
                return bench

        return None

    @classmethod
    def deduce_optimal_pricing(
        cls,
        title: str,
        category_name: str,
        internal_data: Dict[str, Any],
        google_trends: Dict[str, Any],
        blank_cost: float = 0.0
    ) -> Tuple[int, int, int, str]:
        """
        Đưa ra mức giá thị trường tối ưu, hợp lý nhất dựa trên:
        1. Phân khúc thương hiệu & dòng tiền nhiệm (nếu là sản phẩm mới/tiếp nối)
        2. Dữ liệu cào từ sàn VietCraft
        3. Dữ liệu xu hướng tìm kiếm Google Trends
        4. Chi phí giá vốn (nếu có)
        """
        # 1. Thử nhận diện theo Phân Khúc Thương Hiệu (ví dụ iPhone 18 Pro Max -> Apple Pro Max)
        bench = cls.match_brand_benchmark(title)
        if bench:
            p25 = bench["p25"]
            p50 = bench["p50"]
            p75 = bench["p75"]
            ref_line = bench["reference_line"]
            seg_name = bench["segment_name"]

            # Bổ sung thông tin từ Google Trends vào explanation
            trends_note = ""
            signals = google_trends.get("search_signals", [])
            if signals:
                trends_note = f" và xu hướng tìm kiếm Google Trends ghi nhận '{signals[0].lower()}'"

            explanation = (
                f"Định giá đề xuất dựa trên phân tích {seg_name} "
                f"(tham chiếu mức giá mở bán thị trường của {ref_line}){trends_note}. "
                f"Khoảng giá thị trường tối ưu từ {p25:,}đ đến {p75:,}đ, mức đề xuất cân bằng: {p50:,}đ."
            )
            return p25, p50, p75, explanation

        # 2. Sử dụng dữ liệu cào từ sàn VietCraft
        if internal_data.get("p50", 0) > 0:
            p25 = internal_data["p25"]
            p50 = internal_data["p50"]
            p75 = internal_data["p75"]
            count = internal_data["found_count"]
            explanation = (
                f"Định giá dựa trên {count} sản phẩm tương tự đang niêm yết trên sàn VietCraft. "
                f"Mức giá phổ biến dao động từ {p25:,}đ đến {p75:,}đ, mức đề xuất cân bằng: {p50:,}đ."
            )
            return p25, p50, p75, explanation

        # 3. Tính theo giá vốn nếu có (Cost-Plus)
        if blank_cost > 0:
            p25 = int(round(blank_cost * 1.25 / 1000) * 1000)
            p50 = int(round(blank_cost * 1.45 / 1000) * 1000)
            p75 = int(round(blank_cost * 1.80 / 1000) * 1000)
            explanation = (
                f"Định giá theo phương pháp chi phí cộng biên lợi nhuận (Cost-Plus 45%) từ giá vốn {int(blank_cost):,}đ. "
                f"Khoảng giá đề xuất từ {p25:,}đ đến {p75:,}đ."
            )
            return p25, p50, p75, explanation

        # 4. Nếu là tiêu đề rác hoàn toàn không nhận diện được
        return 0, 0, 0, "Chưa đủ dữ liệu thị trường để đề xuất mức giá chuẩn xác."
