from scraper import SteamDBScraper
from downloader import DepotDownloader
import argparse
import sys
import os
import yaml
import logging

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("steamdepoter.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Steam Depot Scraper and Downloader")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--app", help="Steam App ID (overrides config)")
    parser.add_argument("--depot", help="Steam Depot ID (overrides config)")
    parser.add_argument("--username", help="Steam Username (overrides config)")
    parser.add_argument("--password", help="Steam Password (overrides config)")
    parser.add_argument("--branch", help="Branch to download (overrides config)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (overrides config if set)")
    args = parser.parse_args()
    
    config = {}
    if os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    else:
        if not (args.app and args.depot and args.username):
            logger.error(f"Config file '{args.config}' not found, and required CLI arguments (--app, --depot, --username) were not provided.")
            sys.exit(1)

    username = args.username or config.get("username", "")
    password = args.password or config.get("password", "")
    branch = args.branch or config.get("branch", "public")
    headless = args.headless or config.get("headless", False)
    
    if args.app and args.depot:
        downloads = {args.app: [args.depot]}
    else:
        downloads = config.get("download", {})

    logger.info("=========================================")
    logger.info("          Steam Depot Downloader         ")
    logger.info("=========================================")
    logger.info(f"Loaded config from: {args.config}")
    logger.info(f"Apps to process:    {len(downloads)}")
    logger.info("=========================================")

    scraper = SteamDBScraper(headless=headless)
    downloader = DepotDownloader()
    
    total_manifests_downloaded = 0
    total_manifests_failed = 0

    for app_id, depots in downloads.items():
        for depot_id in depots:
            logger.info(f"\n>>> Processing App: {app_id} | Depot: {depot_id} <<<")
            
            # 1. Scrape Manifests
            manifests = scraper.fetch_manifests(depot_id)
            if not manifests:
                logger.error(f"Failed to fetch manifests for Depot {depot_id}. Skipping.")
                continue
                
            branch_manifests = [m for m in manifests if m['branch'] == branch]
            if not branch_manifests:
                logger.error(f"No manifests found for branch '{branch}' in Depot {depot_id}. Skipping.")
                continue
                
            # 2. Download Manifests
            logger.info(f"Downloading {len(branch_manifests)} manifests for Depot {depot_id}...")
            
            for i, m in enumerate(branch_manifests, 1):
                manifest_id = m['manifest_id']
                logger.info(f"\n--- [App {app_id}|Depot {depot_id}] Manifest {i}/{len(branch_manifests)}: {manifest_id} ({m['date']}) ---")
                
                success = downloader.download_manifest(
                    app_id=app_id,
                    depot_id=depot_id,
                    manifest_id=manifest_id,
                    username=username,
                    password=password
                )
                
                if success:
                    total_manifests_downloaded += 1
                else:
                    total_manifests_failed += 1
                    
    logger.info("\n=========================================")
    logger.info(f"Pipeline completed: {total_manifests_downloaded} downloaded successfully, {total_manifests_failed} failed.")
    logger.info("=========================================")
    
    if total_manifests_failed > 0:
        logger.error("Pipeline finished with errors. Check steamdepoter.log for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()
