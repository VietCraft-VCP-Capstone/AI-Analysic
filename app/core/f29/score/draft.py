from typing import Any, Dict, List, Optional

from bson import ObjectId


def product(title: str, description: str, tags: List[str], materials: List[str], category: str,
            image_urls: List[str], shop_id: str) -> Dict[str, Any]:
    return {"_id": None, "shop_id": ObjectId(shop_id) if ObjectId.is_valid(shop_id) else None,
            "title": title, "description": description, "tags": tags, "materials": materials,
            "categories": [category] if category.strip() else [], "images": image_urls}


def variants(price: Optional[float]) -> List[Dict[str, Any]]:
    return [{"is_active": True, "stock_quantity": 1, "retail_price": price}] if price else []
