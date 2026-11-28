import io

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

KINDS = ("jpeg", "resize", "crop", "flip", "rotate", "bright", "text", "border")
WHITE = (255, 255, 255)


def _jpeg(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def make_copy(img: Image.Image, kind: str, rng: np.random.Generator) -> Image.Image:
    w, h = img.size
    if kind == "jpeg":
        return _jpeg(img, int(rng.integers(50, 96)))
    if kind == "resize":
        s = rng.uniform(0.5, 1.5)
        return img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.Resampling.LANCZOS)
    if kind == "crop":
        f = rng.uniform(0.05, 0.30)
        return img.crop((int(w * f / 2), int(h * f / 2), int(w * (1 - f / 2)), int(h * (1 - f / 2))))
    if kind == "flip":
        return ImageOps.mirror(img)
    if kind == "rotate":
        return img.rotate(rng.uniform(-10, 10), resample=Image.Resampling.BICUBIC, fillcolor=WHITE)
    if kind == "bright":
        return ImageEnhance.Brightness(img).enhance(rng.uniform(0.8, 1.2))
    if kind == "text":
        out = img.copy()
        font = ImageFont.load_default(size=max(12, int(h * 0.1)))
        ImageDraw.Draw(out).text((w * rng.uniform(0.05, 0.4), h * 0.8), "VIETCRAFT", font=font,
                                 fill=(0, 0, 0), stroke_width=2, stroke_fill=WHITE)
        return out
    return ImageOps.expand(img, border=int(min(w, h) * rng.uniform(0.03, 0.10)), fill=WHITE)
