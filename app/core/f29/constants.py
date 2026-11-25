MODEL_VERSION = "health-3.1"

MIN_TITLE_LENGTH = 20
MAX_TITLE_LENGTH = 120

MIN_CATEGORY_SAMPLE = 8

BLOCKING_FIELDS = ("title", "materials", "moderation_status", "images", "variants.retail_price")

K_BAYESIAN_SHRINKAGE = 50

EFFORT = {"image": 1, "tags": 1, "material": 1, "description": 2, "price": 2, "review": 3,
          "images": 1, "materials": 1, "title": 1, "moderation_status": 3,
          "variants.retail_price": 1, "variants.stock": 1, "categories": 1}
