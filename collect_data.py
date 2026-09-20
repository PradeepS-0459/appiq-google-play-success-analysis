"""
collect_data.py — Standalone Google Play Store App Metadata Scraper
==================================================================
Project : AppIQ — Category-Specific vs. Universal Drivers of App Store Success
Course  : Business Analytics Case Study (Semester VII)

Data Source : Google Play Store public web pages
Library     : google-play-scraper (pip install google-play-scraper)
Approach    : No API key, no login — scrapes publicly available metadata only

PRIVACY NOTE:
    developer_email and developer_website are NEVER collected or stored.
    Only developer_name (public brand/studio name) is retained.

Usage:
    pip install google-play-scraper pandas
    python collect_data.py

Output:
    data/raw_apps.csv  (incrementally saved; safe to resume after crash)
"""

import os
import sys
import csv
import time
import random
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("collect_data")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OUTPUT_DIR  = Path("data")
OUTPUT_FILE = OUTPUT_DIR / "raw_apps.csv"

# Delay (seconds) between individual app-detail requests to be respectful
MIN_DELAY = 0.4
MAX_DELAY = 1.0

# Target apps per category (we attempt to collect this many unique apps)
TARGET_PER_CATEGORY = 350

# Columns we will write — developer_email and developer_website are
# intentionally ABSENT.  These are PII for indie developers and must not
# appear at any stage.
OUTPUT_COLUMNS = [
    "app_id",
    "title",
    "category",
    "price",
    "is_free",
    "has_in_app_purchases",
    "content_rating",
    "size_mb",
    "install_count",
    "average_rating",
    "num_ratings",
    "developer_name",
    "last_updated_date",
]

# ---------------------------------------------------------------------------
# Google Play category identifiers
# ---------------------------------------------------------------------------
# These are the internal category/genre slugs used by Google Play.
# We target 35+ categories to satisfy the 30-40 requirement.
CATEGORIES = [
    # Main app categories
    "ART_AND_DESIGN",
    "AUTO_AND_VEHICLES",
    "BEAUTY",
    "BOOKS_AND_REFERENCE",
    "BUSINESS",
    "COMICS",
    "COMMUNICATION",
    "DATING",
    "EDUCATION",
    "ENTERTAINMENT",
    "EVENTS",
    "FINANCE",
    "FOOD_AND_DRINK",
    "HEALTH_AND_FITNESS",
    "HOUSE_AND_HOME",
    "LIBRARIES_AND_DEMO",
    "LIFESTYLE",
    "MAPS_AND_NAVIGATION",
    "MEDICAL",
    "MUSIC_AND_AUDIO",
    "NEWS_AND_MAGAZINES",
    "PARENTING",
    "PERSONALIZATION",
    "PHOTOGRAPHY",
    "PRODUCTIVITY",
    "SHOPPING",
    "SOCIAL",
    "SPORTS",
    "TOOLS",
    "TRAVEL_AND_LOCAL",
    "VIDEO_PLAYERS",
    "WEATHER",
    # Game sub-categories (counted as distinct categories)
    "GAME_ACTION",
    "GAME_ADVENTURE",
    "GAME_ARCADE",
    "GAME_BOARD",
    "GAME_CARD",
    "GAME_CASINO",
    "GAME_CASUAL",
    "GAME_EDUCATIONAL",
    "GAME_PUZZLE",
    "GAME_RACING",
    "GAME_ROLE_PLAYING",
    "GAME_SIMULATION",
    "GAME_SPORTS",
    "GAME_STRATEGY",
    "GAME_TRIVIA",
    "GAME_WORD",
]

# Human-readable names for progress logging
CATEGORY_DISPLAY = {
    "ART_AND_DESIGN":      "Art & Design",
    "AUTO_AND_VEHICLES":   "Auto & Vehicles",
    "BEAUTY":              "Beauty",
    "BOOKS_AND_REFERENCE": "Books & Reference",
    "BUSINESS":            "Business",
    "COMICS":              "Comics",
    "COMMUNICATION":       "Communication",
    "DATING":              "Dating",
    "EDUCATION":           "Education",
    "ENTERTAINMENT":       "Entertainment",
    "EVENTS":              "Events",
    "FINANCE":             "Finance",
    "FOOD_AND_DRINK":      "Food & Drink",
    "HEALTH_AND_FITNESS":  "Health & Fitness",
    "HOUSE_AND_HOME":      "House & Home",
    "LIBRARIES_AND_DEMO":  "Libraries & Demo",
    "LIFESTYLE":           "Lifestyle",
    "MAPS_AND_NAVIGATION": "Maps & Navigation",
    "MEDICAL":             "Medical",
    "MUSIC_AND_AUDIO":     "Music & Audio",
    "NEWS_AND_MAGAZINES":  "News & Magazines",
    "PARENTING":           "Parenting",
    "PERSONALIZATION":     "Personalization",
    "PHOTOGRAPHY":         "Photography",
    "PRODUCTIVITY":        "Productivity",
    "SHOPPING":            "Shopping",
    "SOCIAL":              "Social",
    "SPORTS":              "Sports",
    "TOOLS":               "Tools",
    "TRAVEL_AND_LOCAL":    "Travel & Local",
    "VIDEO_PLAYERS":       "Video Players",
    "WEATHER":             "Weather",
    "GAME_ACTION":         "Games — Action",
    "GAME_ADVENTURE":      "Games — Adventure",
    "GAME_ARCADE":         "Games — Arcade",
    "GAME_BOARD":          "Games — Board",
    "GAME_CARD":           "Games — Card",
    "GAME_CASINO":         "Games — Casino",
    "GAME_CASUAL":         "Games — Casual",
    "GAME_EDUCATIONAL":    "Games — Educational",
    "GAME_PUZZLE":         "Games — Puzzle",
    "GAME_RACING":         "Games — Racing",
    "GAME_ROLE_PLAYING":   "Games — Role Playing",
    "GAME_SIMULATION":     "Games — Simulation",
    "GAME_SPORTS":         "Games — Sports",
    "GAME_STRATEGY":       "Games — Strategy",
    "GAME_TRIVIA":         "Games — Trivia",
    "GAME_WORD":           "Games — Word",
}


# ---------------------------------------------------------------------------
# Helper: convert raw library output to our schema
# ---------------------------------------------------------------------------
def _parse_size(raw_size: str) -> float | None:
    """Convert size string (e.g. '45M', '12k', 'Varies with device') to MB."""
    if not raw_size or raw_size == "Varies with device":
        return None
    raw = str(raw_size).strip().upper()
    try:
        if raw.endswith("M"):
            return round(float(raw[:-1]), 2)
        if raw.endswith("K"):
            return round(float(raw[:-1]) / 1024, 4)
        if raw.endswith("G"):
            return round(float(raw[:-1]) * 1024, 2)
        # Sometimes it's just bytes as a number
        return round(float(raw) / (1024 * 1024), 4)
    except (ValueError, TypeError):
        return None


def _extract_row(detail: dict, category_slug: str) -> dict | None:
    """
    Map the raw dict returned by google-play-scraper's `app()` function
    to our output schema.  Returns None if the data is too incomplete.

    PRIVACY: developer_email and developer_website are NEVER read or stored.
    """
    app_id = detail.get("appId")
    if not app_id:
        return None

    # Install count — keep the raw string like "10,000,000+"
    raw_installs = detail.get("installs", "")          # e.g. "10,000,000+"
    if not raw_installs:
        # Some entries only have minInstalls (an int)
        min_inst = detail.get("minInstalls")
        raw_installs = f"{min_inst:,}+" if min_inst else ""

    # last_updated can be a Unix timestamp (int/float) or already a date string
    raw_updated = detail.get("updated")                # Unix timestamp (seconds)
    if isinstance(raw_updated, (int, float)):
        last_updated = datetime.utcfromtimestamp(raw_updated).strftime("%Y-%m-%d")
    elif isinstance(raw_updated, str):
        last_updated = raw_updated
    else:
        last_updated = ""

    # Determine human-readable category.
    # Prefer the genre string the library returns; fall back to our slug map.
    category_name = detail.get("genre") or CATEGORY_DISPLAY.get(category_slug, category_slug)

    # In-app purchases detection
    has_iap = detail.get("offersIAP", False) or bool(detail.get("inAppProductPrice"))

    row = {
        "app_id":                app_id,
        "title":                 detail.get("title", ""),
        "category":              category_name,
        "price":                 detail.get("price", 0),
        "is_free":               detail.get("free", True),
        "has_in_app_purchases":  has_iap,
        "content_rating":        detail.get("contentRating", ""),
        "size_mb":               _parse_size(detail.get("size", "")),
        "install_count":         raw_installs,
        "average_rating":        detail.get("score"),
        "num_ratings":           detail.get("ratings"),
        "developer_name":        detail.get("developer", ""),
        "last_updated_date":     last_updated,
    }
    return row


# ---------------------------------------------------------------------------
# Core collection logic
# ---------------------------------------------------------------------------
def _load_existing_ids(filepath: Path) -> set:
    """Load already-collected app_ids from the CSV so we can resume."""
    ids: set[str] = set()
    if filepath.exists():
        try:
            df = pd.read_csv(filepath, usecols=["app_id"], dtype=str)
            ids = set(df["app_id"].dropna())
            log.info("Resuming — %d apps already in %s", len(ids), filepath)
        except Exception as exc:
            log.warning("Could not read existing CSV for resume: %s", exc)
    return ids


def _append_rows(filepath: Path, rows: list[dict]) -> None:
    """Append a batch of rows to the CSV (create with header if new)."""
    write_header = not filepath.exists() or filepath.stat().st_size == 0
    with open(filepath, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def _discover_app_ids(category_slug: str, target: int) -> list[str]:
    """
    Discover app IDs for a category using Google Play search.

    Strategy: run many varied keyword searches relevant to the category
    to build up a pool of unique app IDs.  Each search returns up to 30
    results, so we need ~12-15 distinct queries to approach 350 unique IDs.

    Returns a deduplicated list of app_id strings.
    """
    import google_play_scraper as gps

    found_ids: list[str] = []
    seen: set[str] = set()

    def _add(app_id: str):
        if app_id and app_id not in seen:
            seen.add(app_id)
            found_ids.append(app_id)

    # Build a rich set of search terms from the category name
    display_name = CATEGORY_DISPLAY.get(category_slug, category_slug)
    base = display_name.replace("Games — ", "").replace(" & ", " ")

    # --- Category-specific keyword expansions ---
    # These extra keywords help cast a wider net within each category
    CATEGORY_EXTRA_KEYWORDS: dict[str, list[str]] = {
        "FINANCE":             ["banking", "investment", "budget", "stock market", "crypto", "wallet", "tax", "loan", "insurance", "money transfer"],
        "EDUCATION":           ["learning", "study", "classroom", "quiz", "language", "math", "science", "tutoring", "course", "exam prep"],
        "HEALTH_AND_FITNESS":  ["workout", "exercise", "diet", "yoga", "meditation", "step counter", "calorie", "running", "gym", "sleep tracker"],
        "PRODUCTIVITY":        ["task manager", "notes", "calendar", "planner", "to do list", "office", "document", "pdf", "scanner", "time tracker"],
        "COMMUNICATION":       ["messaging", "video call", "chat", "email", "sms", "social chat", "voice call", "group chat", "messenger", "conference"],
        "SHOPPING":            ["online shopping", "deals", "coupons", "marketplace", "ecommerce", "buy sell", "fashion", "electronics", "grocery delivery", "price compare"],
        "TOOLS":               ["file manager", "flashlight", "calculator", "vpn", "cleaner", "battery", "wifi", "keyboard", "translator", "qr code scanner"],
        "PHOTOGRAPHY":         ["camera", "photo editor", "filter", "collage", "selfie", "image", "picture", "gallery", "screenshot", "photo frame"],
        "MUSIC_AND_AUDIO":     ["music player", "radio", "podcast", "mp3", "songs", "karaoke", "dj", "audio recorder", "ringtone", "equalizer"],
        "TRAVEL_AND_LOCAL":    ["maps", "navigation", "hotel booking", "flight", "trip planner", "tourist", "gps", "ride sharing", "taxi", "travel guide"],
        "FOOD_AND_DRINK":      ["recipes", "restaurant", "food delivery", "cooking", "meal planner", "diet plan", "cafe", "ingredients", "kitchen", "baking"],
        "BUSINESS":            ["crm", "invoice", "project management", "accounting", "enterprise", "analytics", "sales", "marketing", "hr", "team management"],
        "MEDICAL":             ["doctor", "pharmacy", "health records", "symptom checker", "telemedicine", "prescription", "hospital", "first aid", "anatomy", "drug reference"],
        "LIFESTYLE":           ["home decor", "fashion style", "habit tracker", "daily routine", "astrology", "quotes", "journal", "wardrobe", "self improvement", "mindfulness"],
        "SOCIAL":              ["social media", "friends", "community", "dating", "network", "stories", "live stream", "profile", "followers", "social app"],
        "NEWS_AND_MAGAZINES":  ["news reader", "newspaper", "magazine", "headlines", "breaking news", "world news", "sports news", "tech news", "local news", "feed reader"],
        "BOOKS_AND_REFERENCE": ["ebook reader", "dictionary", "encyclopedia", "library", "audiobook", "novel", "comic reader", "pdf reader", "textbook", "reference guide"],
        "SPORTS":              ["live scores", "football", "cricket", "basketball", "soccer", "tennis", "fantasy sports", "sports news", "fitness sports", "nfl"],
        "WEATHER":             ["weather forecast", "rain radar", "temperature", "climate", "storm tracker", "wind", "humidity", "weather widget", "weather map", "barometer"],
        "ENTERTAINMENT":       ["movies", "streaming", "tv shows", "comedy", "memes", "funny videos", "anime", "cartoons", "celebrity", "wallpapers"],
        "PERSONALIZATION":     ["launcher", "themes", "wallpaper", "icon pack", "widget", "ringtones", "lock screen", "font", "home screen", "live wallpaper"],
        "MAPS_AND_NAVIGATION": ["gps navigation", "map offline", "driving directions", "route planner", "compass", "traffic", "street view", "location tracker", "speedometer", "earth map"],
        "VIDEO_PLAYERS":       ["video player", "media player", "video editor", "screen recorder", "movie player", "subtitle", "video downloader", "video converter", "slideshow", "projector"],
        "DATING":              ["dating app", "matchmaking", "singles", "romance", "love", "relationship", "flirt", "meet people", "local dating", "online dating"],
        "ART_AND_DESIGN":      ["drawing", "sketch", "painting", "coloring", "graphic design", "logo maker", "illustration", "canvas", "digital art", "3d design"],
        "AUTO_AND_VEHICLES":   ["car", "driving", "vehicle", "mechanic", "parking", "dashboard", "fuel", "automobile", "motorcycle", "electric vehicle"],
        "BEAUTY":              ["makeup", "skincare", "hairstyle", "beauty tips", "cosmetics", "nail art", "face filter", "beauty camera", "salon", "grooming"],
        "COMICS":              ["manga", "webtoon", "comic strip", "graphic novel", "superhero", "cartoon", "webcomic", "comic creator", "anime comic", "panel"],
        "EVENTS":              ["event planner", "tickets", "conference", "festival", "meetup", "party", "concert", "exhibition", "wedding", "birthday"],
        "HOUSE_AND_HOME":      ["real estate", "home design", "interior", "furniture", "renovation", "apartment", "mortgage", "moving", "smart home", "garden"],
        "LIBRARIES_AND_DEMO":  ["demo app", "sample", "showcase", "library", "api", "developer tools", "test app", "example", "tutorial app", "prototype"],
        "PARENTING":           ["baby tracker", "pregnancy", "kids", "child", "family", "parenting tips", "toddler", "baby names", "breastfeeding", "parent guide"],
        # Game sub-categories
        "GAME_ACTION":         ["action game", "shooter", "fighting", "battle", "combat", "war game", "fps", "survival", "gun game", "hero"],
        "GAME_ADVENTURE":      ["adventure game", "exploration", "quest", "rpg adventure", "story game", "mystery", "treasure", "escape", "journey", "open world"],
        "GAME_ARCADE":         ["arcade game", "retro", "classic arcade", "high score", "endless runner", "tap game", "pinball", "jump", "dodge", "coin"],
        "GAME_BOARD":          ["board game", "chess", "checkers", "monopoly", "backgammon", "ludo", "scrabble", "go game", "othello", "dice"],
        "GAME_CARD":           ["card game", "solitaire", "poker", "rummy", "blackjack", "hearts", "spades", "uno", "collectible cards", "trading cards"],
        "GAME_CASINO":         ["casino", "slots", "roulette", "bingo", "jackpot", "gambling", "lucky", "vegas", "bet", "spin"],
        "GAME_CASUAL":         ["casual game", "fun game", "simple game", "addictive game", "time killer", "relaxing game", "idle game", "clicker", "tycoon", "merge"],
        "GAME_EDUCATIONAL":    ["educational game", "kids learning", "brain training", "quiz game", "spelling", "memory game", "math game", "science game", "geography", "history game"],
        "GAME_PUZZLE":         ["puzzle game", "jigsaw", "match 3", "sudoku", "crossword", "brain teaser", "logic puzzle", "escape room", "riddle", "block puzzle"],
        "GAME_RACING":         ["racing game", "car racing", "bike racing", "speed", "drift", "formula", "drag racing", "offroad", "moto racing", "kart"],
        "GAME_ROLE_PLAYING":   ["rpg", "role playing", "mmorpg", "fantasy rpg", "turn based", "character", "dungeon", "dragon", "hero rpg", "gacha"],
        "GAME_SIMULATION":     ["simulation game", "simulator", "city builder", "farming", "life sim", "construction", "flight simulator", "train sim", "cooking game", "restaurant sim"],
        "GAME_SPORTS":         ["sports game", "football game", "soccer game", "basketball game", "cricket game", "tennis game", "boxing game", "golf game", "hockey", "wrestling"],
        "GAME_STRATEGY":       ["strategy game", "tower defense", "war strategy", "rts", "civilization", "empire", "conquest", "tactics", "army", "base building"],
        "GAME_TRIVIA":         ["trivia", "quiz show", "general knowledge", "trivia quiz", "questions", "who wants", "brain quiz", "challenge quiz", "fun trivia", "quiz battle"],
        "GAME_WORD":           ["word game", "word puzzle", "word search", "anagram", "word connect", "spelling bee", "word scramble", "hangman", "vocabulary", "word cross"],
    }

    # Base search terms that work for every category
    generic_modifiers = [
        "", "app", "best", "top", "popular", "free", "new 2024",
        "2025", "offline", "android", "pro", "lite", "premium",
    ]

    # Build the full search term list
    search_terms: list[str] = []

    # 1) Category-specific expanded keywords (most targeted)
    extra = CATEGORY_EXTRA_KEYWORDS.get(category_slug, [])
    for kw in extra:
        search_terms.append(kw)

    # 2) Base name with generic modifiers
    for mod in generic_modifiers:
        term = f"{base} {mod}".strip()
        if term not in search_terms:
            search_terms.append(term)

    # 3) Single-word variants of the base name
    for word in base.split():
        if len(word) >= 3 and word not in search_terms:
            search_terms.append(word)

    log.info("  Searching with %d query terms for %s ...", len(search_terms), display_name)

    # Run searches
    for i, term in enumerate(search_terms):
        if len(found_ids) >= target:
            break
        try:
            results = gps.search(
                term,
                lang="en",
                country="us",
                n_hits=30,
            )
            before = len(found_ids)
            for r in results:
                _add(r.get("appId", ""))
            gained = len(found_ids) - before
            if gained > 0:
                log.debug("  search '%s' → +%d new IDs (total: %d)", term, gained, len(found_ids))
        except Exception as exc:
            log.debug("  search '%s' failed: %s", term, exc)
        time.sleep(random.uniform(0.3, 0.7))

    log.info("  Discovery complete: %d unique app IDs found", len(found_ids))
    return found_ids[:target]


def collect_category(
    category_slug: str,
    existing_ids: set[str],
    output_file: Path,
    target: int = TARGET_PER_CATEGORY,
) -> int:
    """
    Collect app metadata for one category.
    Returns the number of NEW apps added.
    """
    import google_play_scraper as gps

    display = CATEGORY_DISPLAY.get(category_slug, category_slug)
    log.info("=" * 60)
    log.info("CATEGORY: %s  (%s)", display, category_slug)
    log.info("=" * 60)

    # Step 1: Discover app IDs (from lists + search)
    candidate_ids = _discover_app_ids(category_slug, target)
    # Remove already-collected IDs
    new_ids = [aid for aid in candidate_ids if aid not in existing_ids]
    log.info(
        "  Discovered %d candidates, %d new (after dedup against existing %d)",
        len(candidate_ids), len(new_ids), len(existing_ids),
    )

    if not new_ids:
        log.info("  Nothing new to collect — skipping.")
        return 0

    # Step 2: Fetch full details for each new app ID
    batch: list[dict] = []
    collected = 0
    errors = 0

    for i, app_id in enumerate(new_ids, 1):
        try:
            detail = gps.app(app_id, lang="en", country="us")
            row = _extract_row(detail, category_slug)
            if row:
                batch.append(row)
                existing_ids.add(app_id)    # track globally to avoid future dups
                collected += 1
        except Exception as exc:
            errors += 1
            if errors <= 5:
                log.warning("  [%d/%d] Error fetching %s: %s", i, len(new_ids), app_id, exc)
            elif errors == 6:
                log.warning("  (suppressing further individual error messages)")

        # Incremental save every 50 apps
        if len(batch) >= 50:
            _append_rows(output_file, batch)
            log.info(
                "  Saved batch — %d apps so far for %s  (errors: %d)",
                collected, display, errors,
            )
            batch.clear()

        # Respectful delay between requests
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        # Progress log every 100 apps
        if i % 100 == 0:
            log.info("  Progress: %d/%d fetched, %d collected, %d errors", i, len(new_ids), collected, errors)

    # Save any remaining rows in the final partial batch
    if batch:
        _append_rows(output_file, batch)

    log.info(
        "  DONE  %s — collected %d new apps, %d errors",
        display, collected, errors,
    )
    return collected


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    log.info("=" * 60)
    log.info("AppIQ Data Collection — Google Play Store Scraper")
    log.info("=" * 60)
    log.info("Target: %d+ unique apps across %d categories", TARGET_PER_CATEGORY * len(CATEGORIES), len(CATEGORIES))
    log.info("Output: %s", OUTPUT_FILE)
    log.info("")

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load already-collected IDs (for crash-safe resume)
    existing_ids = _load_existing_ids(OUTPUT_FILE)

    total_new = 0
    category_stats: dict[str, int] = {}

    for idx, cat in enumerate(CATEGORIES, 1):
        display = CATEGORY_DISPLAY.get(cat, cat)
        log.info("")
        log.info(">>> Category %d/%d: %s", idx, len(CATEGORIES), display)

        try:
            n = collect_category(cat, existing_ids, OUTPUT_FILE)
            category_stats[display] = n
            total_new += n
        except KeyboardInterrupt:
            log.warning("Interrupted by user — saving progress and exiting.")
            break
        except Exception as exc:
            log.error("Category %s FAILED entirely: %s — skipping.", display, exc)
            category_stats[display] = 0

        # Small pause between categories
        time.sleep(random.uniform(1.0, 2.0))

    # ---------------------------------------------------------------------------
    # Final summary
    # ---------------------------------------------------------------------------
    log.info("")
    log.info("=" * 60)
    log.info("COLLECTION COMPLETE")
    log.info("=" * 60)
    log.info("New apps added this run: %d", total_new)
    log.info("Total apps in CSV:       %d", len(existing_ids))
    log.info("")

    # Print per-category counts from the full CSV
    if OUTPUT_FILE.exists():
        df = pd.read_csv(OUTPUT_FILE)
        log.info("--- Per-Category Summary (full CSV) ---")
        cat_counts = df["category"].value_counts().sort_index()
        for cat_name, count in cat_counts.items():
            log.info("  %-30s %5d apps", cat_name, count)
        log.info("")
        log.info("Total unique app_ids: %d", df["app_id"].nunique())
        log.info("Total rows:           %d", len(df))
        log.info("Columns:              %s", list(df.columns))

        # Verify no PII columns leaked in
        forbidden = {"developer_email", "developer_website"}
        leaked = forbidden & set(df.columns)
        if leaked:
            log.error("!!! PII COLUMNS DETECTED: %s — removing them now.", leaked)
            df.drop(columns=list(leaked), inplace=True)
            df.to_csv(OUTPUT_FILE, index=False)
            log.info("PII columns removed and CSV re-saved.")
        else:
            log.info("✓ No PII columns (developer_email/website) present — GOOD.")

        # Final deduplication pass
        before = len(df)
        df.drop_duplicates(subset=["app_id"], keep="first", inplace=True)
        after = len(df)
        if before != after:
            log.info("Removed %d duplicate rows (by app_id).", before - after)
            df.to_csv(OUTPUT_FILE, index=False)
        else:
            log.info("✓ No duplicate app_ids found.")


if __name__ == "__main__":
    try:
        import google_play_scraper  # noqa: F401
    except ImportError:
        log.error(
            "google-play-scraper is not installed.\n"
            "Run:  pip install google-play-scraper pandas\n"
        )
        sys.exit(1)

    main()
