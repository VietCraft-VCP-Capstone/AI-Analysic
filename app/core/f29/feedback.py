from datetime import datetime, timezone

from app.core.f29 import constants

COLL = "f29_feedback"
VERDICTS = ("ai_wrong", "ai_right")


def save(product_id: str, shop_id: str, image_url: str, verdict: str, ai: dict | None) -> dict:
    now = datetime.now(timezone.utc)
    constants.store_db()[COLL].update_one(
        {"product_id": product_id, "image_url": image_url},
        {"$set": {"shop_id": shop_id, "verdict": verdict, "ai": ai,
                  "model_version": constants.MODEL_VERSION, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"image_url": image_url, "verdict": verdict}


def of_product(product_id: str) -> list[dict]:
    docs = constants.store_db()[COLL].find({"product_id": product_id})
    return [{"image_url": d.get("image_url"), "verdict": d.get("verdict"), "updated_at": d.get("updated_at")}
            for d in docs]
