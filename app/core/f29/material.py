from app.core.listing_intel.lexicon import attributes


def has_material(product: dict) -> bool:
    materials = product.get("materials")
    if isinstance(materials, list) and any(isinstance(m, str) and m.strip() for m in materials):
        return True
    text = " ".join(v for v in (product.get("title"), product.get("description")) if isinstance(v, str))
    return bool(attributes(text).get("material"))
