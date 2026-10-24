MODEL_VERSION = "health-2.1"

WEIGHTS = {
    "conversion": 0.30,
    "rating": 0.25,
    "content": 0.20,
    "inventory": 0.15,
    "freshness": 0.10,
}

MIN_IMAGES = 5
MIN_DESCRIPTION_LENGTH = 150
MIN_TAGS_APPROVED = 3

MIN_TITLE_LENGTH = 20
MAX_TITLE_LENGTH = 120

K_BAYESIAN_SHRINKAGE = 50

FRESHNESS_FULL_SCORE_DAYS = 90
FRESHNESS_ZERO_SCORE_DAYS = 365

MIN_CATEGORY_SAMPLE = 8

EFFORT = {"image": 1, "tags": 1, "material": 1, "description": 2, "price": 2, "review": 3}
