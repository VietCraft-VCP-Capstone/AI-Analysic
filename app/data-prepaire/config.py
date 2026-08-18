"""Configuration for the VietCraft data collectors."""

# Load .env if python-dotenv is installed. Real environment variables always
# win over the file, so GitHub Actions secrets are never shadowed by a stale
# .env that happened to get committed.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

GEO = "VN"          # Vietnam. Use "" for worldwide.
LANGUAGE = "vi"

# Google allows 5 keywords per request and normalises them 0-100 against each
# other WITHIN that request. To compare keywords across different requests we
# include one fixed anchor keyword in every batch and rescale afterwards.
# That leaves 4 real keywords per request.
BATCH_SIZE = 4

# ---------------------------------------------------------------------------
# Throttling. Google Trends is aggressive about rate limits and gives no
# warning before it starts returning 429 -- and once it does, the block can
# last tens of minutes. Slow is the only reliable setting.
#
# Two independent throttles:
#   REQUEST_DELAY  trendspy's own minimum gap between HTTP calls
#   SLEEP_MIN/MAX  our extra pause between batches, randomised so the traffic
#                  does not look like a metronome
#
# 14 batches x ~20s = about 5 minutes for a full backfill. Worth it.
# Still getting 429? Double both, and wait 30-60 minutes before retrying --
# hammering a rate limit makes it last longer.
# ---------------------------------------------------------------------------

REQUEST_DELAY = 5.0
SLEEP_MIN = 15.0
SLEEP_MAX = 25.0

# Our own retry loop in fetch_batch(). Keep TRENDSPY_RETRIES at 1 so the two
# do not multiply -- see below.
MAX_RETRIES = 4

# trendspy runs its own retry loop inside _get(). Left at the default it
# nests under ours: 4 outer x 5 inner x 2 HTTP = 40 requests for one batch
# that keeps failing, which is how a single 429 snowballs into a block.
# Set to 1 and let the outer loop own retries -- it backs off in minutes,
# which is what a rate limit actually needs.
TRENDSPY_RETRIES = 1

# A 429 needs minutes, not seconds. Backoff: 60s, 120s, 240s.
RETRY_BASE = 60.0

# ---------------------------------------------------------------------------
# Request budget
#
# Verified by patching session.get: ONE interest_over_time() or
# related_queries() call issues TWO HTTP requests -- Google's token dance.
#   #1  /trends/embed/explore/TIMESERIES   -> returns a token
#   #2  /trends/api/widgetdata/multiline   -> returns the data
#
# So real cost, at 44 keywords and BATCH_SIZE=4:
#   backfill weekly / daily / cron daily   11 batches -> 22 HTTP
#   related, whole registry                44 calls   -> 88 HTTP
#   related, budgeted                      10 calls   -> 20 HTTP
#
# Every collector prints its HTTP count when it finishes. Use those numbers,
# not estimates, to decide what fits in a day.
# ---------------------------------------------------------------------------

DISCOVERY_MAX_SEEDS_PER_RUN = 10

# ---------------------------------------------------------------------------
# Candidate filtering vocabulary (used by verify_data.py --discovery-stats,
# and later by the discovery scorer).
#
# PRODUCT_WORDS is an accept list: does the phrase name something printable?
# NON_COMMERCIAL_WORDS is a reject list: informational intent, not buying
# intent. Reject lists generalise better than accept lists -- an accept list
# can only ever find what you already thought of.
# ---------------------------------------------------------------------------

PRODUCT_WORDS = [
    "áo", "cốc", "ly", "túi", "tote", "tranh", "poster", "sticker", "móc khóa",
    "quà", "nón", "mũ", "gối", "sổ", "lịch", "hoodie", "shirt", "tee", "mug",
    "bag", "print", "gift", "canvas",
]

NON_COMMERCIAL_WORDS = [
    "wallpaper", "hình nền", "download", "tải", "xem", "tập", "phần",
    "lyrics", "lời bài hát", "review", "nghĩa là", "là gì", "cách", "hướng dẫn",
    "full", "vietsub", "trailer", "spoiler", "raw", "manga", "truyện",
]

# Timezone offset in minutes, Google's convention (negative east of UTC).
# Vietnam is UTC+7 -> -420. trendspy defaults to 360 (UTC-6), which shifts
# the day boundary and misaligns daily points.
TZ_OFFSET = -420

# Timeframes chosen from trendspy's resolution rules:
#   8-269 days   -> daily points
#   270-1899 days -> weekly points
TIMEFRAME_DAILY = "today 3-m"    # ~90 daily points, feeds ARIMA
TIMEFRAME_WEEKLY = "today 5-y"   # ~260 weekly points, feeds STL seasonality

# ---------------------------------------------------------------------------
# The anchor keyword.
#
# Must be BOTH mid-volume AND non-seasonal:
#   - too loud  -> it takes the whole 0-100 scale and flattens everything else
#   - too quiet -> it lands near 0, and the rescale divides by ~0
#   - seasonal  -> the scale factor swings with the season, so batches
#                  collected at different times stop being comparable
#
# 'quà sinh nhật' measured mean 20.3 / peak 36.0 in the first run: steady
# through the year (only 1.8x swing) and about 2.5x quieter than 'áo thun',
# which was drowning the rest of the set.
#
# Re-check after every backfill:
#     python collect_trends.py --inspect ./data/trends_weekly.json
# ---------------------------------------------------------------------------

ANCHOR = "quà sinh nhật"

# ---------------------------------------------------------------------------
# Seed keywords: (keyword, product_type, topic)
#
# Start with 60-80. That is 15-20 requests per run -- comfortable inside the
# rate limits, and enough breadth for the Gap Score to have something to rank.
# Expand later; the collector picks up whatever is active in the database.
#
# Mix three kinds deliberately:
#   - evergreen  : baseline, should be flat
#   - seasonal   : Tet, 8/3, 20/11, Christmas -- proves STL works
#   - emerging   : slang, memes, fandoms -- proves trend detection works
# ---------------------------------------------------------------------------

SEED_KEYWORDS = [
    # --- evergreen / baseline -------------------------------------------
    ("áo thun",                  "tshirt", "evergreen"),
    ("áo phông nam",             "tshirt", "evergreen"),
    ("áo phông nữ",              "tshirt", "evergreen"),
    ("in áo thun",               "tshirt", "evergreen"),
    ("áo đôi",                   "tshirt", "couple"),
    ("áo nhóm",                  "tshirt", "group"),
    ("áo lớp",                   "tshirt", "school"),
    ("áo đồng phục",             "tshirt", "school"),
    ("áo gia đình",              "tshirt", "family"),
    ("cốc in hình",              "mug",    "evergreen"),
    ("cốc quà tặng",             "mug",    "gift"),
    ("túi tote",                 "tote",   "evergreen"),
    ("tranh treo tường",         "poster", "evergreen"),
    ("tranh canvas",             "poster", "decor"),
    ("poster trang trí",         "poster", "decor"),
    ("móc khóa",                 "generic", "evergreen"),

    # --- seasonal: Tet ---------------------------------------------------
    ("áo tết",                   "tshirt", "tet"),
    ("quà tết",                  "generic", "tet"),
    ("lì xì tết",                "generic", "tet"),
    ("trang trí tết",            "poster", "tet"),

    # --- seasonal: 8/3 and 20/10 ----------------------------------------
    ("quà 8/3",                  "generic", "womens_day"),
    ("quà tặng mẹ",              "generic", "womens_day"),
    ("quà 20/10",                "generic", "womens_day"),

    # --- seasonal: 20/11 teachers' day ----------------------------------
    ("quà 20/11",                "generic", "teachers_day"),
    ("quà tặng thầy cô",         "generic", "teachers_day"),

    # --- seasonal: Christmas / New Year ---------------------------------
    ("quà giáng sinh",           "generic", "christmas"),
    ("trang trí noel",           "poster", "christmas"),
    ("áo giáng sinh",            "tshirt", "christmas"),

    # --- seasonal: Valentine --------------------------------------------
    ("quà valentine",            "generic", "valentine"),
    ("quà tặng người yêu",       "generic", "valentine"),

    # --- occasion / gifting ---------------------------------------------
    ("quà tặng",                 "generic", "gift"),
    ("quà cưới",                 "generic", "wedding"),
    ("quà tân gia",              "generic", "housewarming"),
    ("quà tặng bạn thân",        "generic", "friendship"),
    ("quà handmade",             "generic", "gift"),
    ("quà lưu niệm",             "generic", "travel"),

    # --- culture / emerging ----------------------------------------------
    ("áo anime",                 "tshirt", "anime"),
    ("áo kpop",                  "tshirt", "kpop"),
    ("áo oversize",              "tshirt", "streetwear"),
    ("áo local brand",           "tshirt", "streetwear"),
    ("áo vintage",               "tshirt", "vintage"),
    ("áo hoodie",                "tshirt", "streetwear"),
    ("áo bóng đá việt nam",      "tshirt", "sport"),
    ("áo thun thể thao",         "tshirt", "sport"),
]

# ---------------------------------------------------------------------------
# Dropped after the first backfill measured them at zero in Vietnam:
#
#   cốc lập trình viên, áo thun lập trình viên, merch idol, poster phòng ngủ,
#   áo thun meme, ly sứ quà tặng, cốc văn phòng, quà tặng đồng nghiệp,
#   áo thun mèo, áo thun chó, quà tặng cho người nuôi mèo, áo thun du lịch,
#   quà lưu niệm đà nẵng, quà lưu niệm hà nội, áo gia đình tết,
#   cốc quà tặng giáo viên, áo thun in hình, túi tote in hình, túi tote vải,
#   cốc sứ in hình, áo thun anime, áo thun kpop, áo thun cặp đôi,
#   áo thun oversize, áo thun vintage
#
# Two lessons worth keeping:
#
# 1. Long compound phrases die. Vietnamese searchers type "áo đôi", not
#    "áo thun cặp đôi"; "áo anime", not "áo thun anime". Broaden the head
#    noun and drop the qualifier.
# 2. Niches that are real on Etsy are not automatically real here. Developer
#    mugs and cat-owner gifts sell in the US; nobody searches for them in
#    Vietnamese. Test before assuming.
#
# Do not guess replacements -- let --related tell you. It returns the rising
# queries Vietnamese users actually type, which is exactly how this list
# should grow.
# ---------------------------------------------------------------------------
