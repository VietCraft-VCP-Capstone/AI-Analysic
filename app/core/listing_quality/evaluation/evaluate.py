import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Dict, List, Set
import numpy as np
from PIL import Image
from app.core.listing_quality.detectors import (
    ImageQualityDetector,
    PodContentDetector,
    RequiredFieldsDetector,
    TextConsistencyDetector,
)
from app.core.listing_quality.evaluation.dataset import get_benchmark_dataset
from app.core.listing_quality.evaluation.metrics import compute_metrics
from app.core.listing_quality.evaluation.schema import DetectorMetrics

DETECTOR_CODES: Dict[str, Set[str]] = {
    "required_fields": {
        "TITLE_MISSING", "TITLE_EMPTY", "TITLE_TOO_SHORT",
        "DESCRIPTION_MISSING", "DESCRIPTION_EMPTY", "DESCRIPTION_TOO_SHORT",
        "IMAGES_MISSING", "IMAGES_INSUFFICIENT", "CATEGORY_MISSING",
        "PRICE_MISSING", "TAGS_MISSING"
    },
    "pod_content": {
        "MATERIAL_MISSING", "SIZE_INFO_MISSING", "CARE_INSTRUCTIONS_MISSING",
        "DRINKWARE_SPECS_MISSING", "BAG_MATERIAL_MISSING"
    },
    "image_quality": {
        "LOW_IMAGE_RESOLUTION", "BLURRY_IMAGE", "EXTREME_ASPECT_RATIO", "IMAGE_UNREADABLE"
    },
    "text_consistency": {
        "MATERIAL_CONTRADICTION", "CATEGORY_CONTRADICTION"
    }
}

def run_evaluation() -> Dict[str, DetectorMetrics]:
    dataset = get_benchmark_dataset()

    detectors = {
        "required_fields": RequiredFieldsDetector(),
        "pod_content": PodContentDetector(),
        "image_quality": ImageQualityDetector(),
        "text_consistency": TextConsistencyDetector()
    }

    all_predictions: Dict[str, List[Set[str]]] = {name: [] for name in detectors}
    all_ground_truths: List[Set[str]] = []

    for item in dataset:
        listing = {
            "title": item.title,
            "description": item.description,
            "images": item.images,
            "materials": item.materials,
            "original_price": item.original_price,
            "tags": item.tags,
            "categories": [item.category] if item.category else []
        }
        mock_clean = Image.fromarray(np.random.randint(0, 256, (800, 800, 3), dtype=np.uint8))
        mock_low_res = Image.fromarray(np.random.randint(0, 256, (300, 300, 3), dtype=np.uint8))
        mock_aspect = Image.fromarray(np.random.randint(0, 256, (600, 1500, 3), dtype=np.uint8))

        preloaded = {
            "mock_low_res": mock_low_res,
            "mock_aspect": mock_aspect,
        }
        for u in item.images:
            if u not in preloaded:
                preloaded[u] = mock_clean

        context = {"variants": item.variants, "preloaded_images": preloaded}
        gt = set(item.ground_truth_issues)
        all_ground_truths.append(gt)

        for det_name, det in detectors.items():
            issues = det.evaluate(listing, context)
            pred = {i.code for i in issues}
            all_predictions[det_name].append(pred)

    results: Dict[str, DetectorMetrics] = {}
    for det_name in detectors:
        codes = DETECTOR_CODES[det_name]
        m = compute_metrics(det_name, all_predictions[det_name], all_ground_truths, codes)
        results[det_name] = m

    return results

def print_evaluation_report(results: Dict[str, DetectorMetrics]) -> None:
    print("\n" + "=" * 78)
    print("  VIETCRAFT — LISTING QUALITY AUDIT V1 EVALUATION BENCHMARK")
    print("=" * 78)
    print(f"{'DETECTOR':<20} | {'SAMPLES':<7} | {'PRECISION':<9} | {'RECALL':<8} | {'F1-SCORE':<8} | {'FPR':<6}")
    print("-" * 78)

    for name, m in results.items():
        print(f"{name:<20} | {m.total_samples:<7} | {m.precision:<9.2f} | {m.recall:<8.2f} | {m.f1:<8.2f} | {m.fpr:<6.2f}")

    print("=" * 78)
    print("  Ghi chú: Đánh giá trên tập dữ liệu POD chuẩn và các trường hợp lỗi thực tế.")
    print("=" * 78 + "\n")

if __name__ == "__main__":
    res = run_evaluation()
    print_evaluation_report(res)
