import math
from typing import Any, Dict, List
import cv2
import numpy as np
from PIL import Image

from app.core.listing_intel import image_fetch
from ..schemas import Issue, Recommendation

class ImageQualityDetector:
    code = "image_quality"
    MIN_DIMENSION = 500
    MIN_SHARPNESS = 3.0
    MIN_ASPECT = 0.5
    MAX_ASPECT = 2.0
    MAX_IMAGES_TO_CHECK = 5

    def _compute_sharpness(self, img: Image.Image) -> float:
        try:
            rgb = np.asarray(img.convert("RGB"))
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            val = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            return math.log1p(max(0.0, val))
        except Exception:
            return 5.0

    def evaluate(self, listing: Dict[str, Any], context: Dict[str, Any]) -> List[Issue]:
        issues: List[Issue] = []
        images = listing.get("images") or []
        if not isinstance(images, list):
            return issues

        preloaded_images = context.get("preloaded_images", {})

        for idx, item in enumerate(images[:self.MAX_IMAGES_TO_CHECK]):
            field_name = f"images[{idx}]"
            img: Any = None
            url = str(item) if isinstance(item, str) else ""

            if url in preloaded_images:
                img = preloaded_images[url]
            elif isinstance(item, Image.Image):
                img = item
            elif url:
                try:
                    img = image_fetch.fetch(url, timeout=3)
                except Exception:
                    img = None

            if img is None:
                if url:
                    issues.append(Issue(
                        id=f"img_unreadable_{idx}",
                        code="IMAGE_UNREADABLE",
                        detector=self.code,
                        severity="medium",
                        field=field_name,
                        status="open",
                        confidence=0.9,
                        evidence={"url": url, "reason": "Không tải hoặc không giải mã được dữ liệu ảnh"},
                        message=f"Ảnh thứ {idx + 1} không mở được hoặc đường dẫn không hợp lệ.",
                        recommendation=Recommendation(
                            action="REPLACE_IMAGE",
                            message="Tải lại ảnh định dạng chuẩn JPG/PNG với kích thước tối thiểu 500x500px.",
                            field_link="images",
                            verification="Kiểm tra ảnh hiển thị đúng khi mở xem trước."
                        )
                    ))
                continue

            try:
                w, h = img.size
            except Exception:
                continue

            if min(w, h) < self.MIN_DIMENSION:
                issues.append(Issue(
                    id=f"img_low_res_{idx}",
                    code="LOW_IMAGE_RESOLUTION",
                    detector=self.code,
                    severity="medium",
                    field=field_name,
                    status="open",
                    confidence=1.0,
                    evidence={
                        "width": w,
                        "height": h,
                        "minimumWidth": self.MIN_DIMENSION,
                        "minimumHeight": self.MIN_DIMENSION
                    },
                    message=f"Ảnh thứ {idx + 1} có độ phân giải {w}x{h}px, dưới chuẩn tối thiểu {self.MIN_DIMENSION}px.",
                    recommendation=Recommendation(
                        action="REPLACE_HIGH_RES_IMAGE",
                        message="Thay thế bằng ảnh có độ phân giải cao hơn để tránh bị vỡ hình khi khách phóng to.",
                        field_link="images",
                        verification=f"Kiểm tra kích thước các cạnh ảnh lớn hơn hoặc bằng {self.MIN_DIMENSION}px."
                    )
                ))

            aspect = w / max(1, h)
            if aspect < self.MIN_ASPECT or aspect > self.MAX_ASPECT:
                issues.append(Issue(
                    id=f"img_aspect_{idx}",
                    code="EXTREME_ASPECT_RATIO",
                    detector=self.code,
                    severity="low",
                    field=field_name,
                    status="open",
                    confidence=1.0,
                    evidence={
                        "aspect_ratio": round(aspect, 2),
                        "expected_range": [self.MIN_ASPECT, self.MAX_ASPECT]
                    },
                    message=f"Ảnh thứ {idx + 1} có tỉ lệ khung hình lệch ({round(aspect, 2)}:1), dễ bị cắt viền.",
                    recommendation=Recommendation(
                        action="CROP_IMAGE_SQUARE",
                        message="Nên dùng tỉ lệ ảnh vuông 1:1 hoặc 4:3 để sản phẩm hiển thị cân đối nhất.",
                        field_link="images",
                        verification="Kiểm tra tỉ lệ khung hình cân đối."
                    )
                ))

            sharpness = self._compute_sharpness(img)
            if sharpness < self.MIN_SHARPNESS:
                issues.append(Issue(
                    id=f"img_blurry_{idx}",
                    code="BLURRY_IMAGE",
                    detector=self.code,
                    severity="medium",
                    field=field_name,
                    status="open",
                    confidence=0.85,
                    evidence={
                        "sharpness_score": round(sharpness, 2),
                        "minimum_threshold": self.MIN_SHARPNESS
                    },
                    message=f"Ảnh thứ {idx + 1} có độ sắc nét thấp, có thể bị nhoè hoặc mờ chi tiết.",
                    recommendation=Recommendation(
                        action="IMPROVE_IMAGE_SHARPNESS",
                        message="Chụp lại sản phẩm ở nơi đủ sáng và lấy nét rõ ràng vào hoạ tiết chính.",
                        field_link="images",
                        verification="Kiểm tra chi tiết và các đường nét trên ảnh sắc nét."
                    )
                ))

        return issues
