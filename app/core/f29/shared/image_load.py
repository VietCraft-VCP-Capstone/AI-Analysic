import io

from PIL import Image

TRAIN_SIDE = 256
TRAIN_QUALITY = 85


def as_trained(img: Image.Image) -> Image.Image:
    small = img.copy()
    small.thumbnail((TRAIN_SIDE, TRAIN_SIDE))
    buf = io.BytesIO()
    small.convert("RGB").save(buf, "JPEG", quality=TRAIN_QUALITY)
    buf.seek(0)
    with Image.open(buf) as im:
        return im.convert("RGB")
