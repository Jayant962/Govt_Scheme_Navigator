"""
update_schemes.py

Auto-Update Pipeline:
  1. Run scraper → raw JSON
  2. Run AI extractor → structured JSON
  3. Bulk upsert into SQLite
  4. Remove stale schemes
  5. Rebuild FAISS vector store

Can be run manually or scheduled (cron / schedule library).
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from data_pipeline.scraper import GovtSchemeScraper
from data_pipeline.extractor import EligibilityExtractor
from database.db_manager import DBManager
from modules.vector_store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("update_pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("update_schemes")


def run_pipeline(use_live_scraping: bool = False, stale_days: int = 30):
    """
    Full update pipeline.

    Args:
        use_live_scraping: Attempt live web scraping in addition to seed data.
        stale_days: Remove DB schemes not updated within this many days.
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("GOVT SCHEME AI — UPDATE PIPELINE STARTED")
    logger.info("=" * 60)

    # ── Step 1: Scrape ────────────────────────────────────────────────────────
    logger.info("STEP 1/5: Scraping scheme data…")
    scraper = GovtSchemeScraper()
    raw_schemes = scraper.run(use_live=use_live_scraping)
    logger.info(f"  → Collected {len(raw_schemes)} raw schemes")

    # ── Step 2: Extract eligibility ───────────────────────────────────────────
    logger.info("STEP 2/5: Extracting eligibility criteria…")
    extractor = EligibilityExtractor()
    processed_schemes = extractor.extract_all(raw_schemes)
    logger.info(f"  → Processed {len(processed_schemes)} schemes")

    # ── Step 3: Update database ───────────────────────────────────────────────
    logger.info("STEP 3/5: Upserting into database…")
    db = DBManager()
    count = db.bulk_upsert(processed_schemes)
    logger.info(f"  → Upserted {count} schemes into DB")
    logger.info(f"  → Total schemes in DB: {db.count_schemes()}")

    # ── Step 4: Remove stale schemes ──────────────────────────────────────────
    logger.info("STEP 4/5: Removing stale schemes…")
    cutoff = (datetime.now() - timedelta(days=stale_days)).isoformat()
    # Only remove stale if we actually fetched live data (don't prune seed data)
    if use_live_scraping:
        db.delete_old_schemes(cutoff)
    else:
        logger.info("  → Skipped (not using live scraping — seed data is always fresh)")

    # ── Step 5: Rebuild FAISS index ───────────────────────────────────────────
    logger.info("STEP 5/5: Rebuilding FAISS vector store…")
    all_schemes = db.get_all_schemes()
    vs = VectorStore()
    vs.build(all_schemes)
    logger.info(f"  → Vector store built with {len(all_schemes)} schemes")

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(f"PIPELINE COMPLETE in {elapsed:.1f}s")
    logger.info(f"  Schemes in DB  : {db.count_schemes()}")
    logger.info(f"  Vector Store   : {vs.index.ntotal if vs.index else 0} vectors")
    logger.info("=" * 60)

    return {
        "schemes_collected": len(raw_schemes),
        "schemes_processed": len(processed_schemes),
        "schemes_in_db": db.count_schemes(),
        "elapsed_seconds": round(elapsed, 1),
    }


def schedule_daily(hour: int = 2, minute: int = 0):
    """
    Schedule the pipeline to run daily at the specified hour:minute.
    Blocks the current process.
    """
    import schedule

    logger.info(f"Scheduling daily pipeline run at {hour:02d}:{minute:02d}")
    schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(run_pipeline)

    while True:
        schedule.run_pending()
        time.sleep(60)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Govt Scheme AI – Update Pipeline")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Attempt live web scraping (may be blocked by portals)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run in scheduled mode (daily at 2 AM)",
    )
    parser.add_argument(
        "--hour",
        type=int,
        default=2,
        help="Hour for scheduled run (24h format, default 2)",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=30,
        help="Remove schemes older than N days (default 30)",
    )
    args = parser.parse_args()

    if args.schedule:
        schedule_daily(hour=args.hour)
    else:
        result = run_pipeline(
            use_live_scraping=args.live,
            stale_days=args.stale_days,
        )
        print("\n[OK] Pipeline complete:")
        for k, v in result.items():
            print(f"   {k}: {v}")
