import os
import shutil
import argparse

def main():
    parser = argparse.ArgumentParser(description="Clean up manifest folders that didn't have any debug symbols.")
    parser.add_argument("--dir", default="manifest_downloads", help="Directory where downloads and logs are located")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    args = parser.parse_args()

    if not os.path.exists(args.dir):
        print(f"Error: Directory '{args.dir}' not found.")
        return

    success_log = os.path.join(args.dir, "symbols_found.log")
    if not os.path.exists(success_log):
        print(f"Error: Success log '{success_log}' not found. Run analyzer.py first.")
        return

    # 1. Identify manifests to keep
    manifests_to_keep = set()
    with open(success_log, "r", encoding="utf-8") as f:
        for line in f:
            if "|" not in line: continue
            parts = line.split("|")
            if len(parts) < 3: continue
            
            # The path is in the 3rd column
            rel_path = parts[2].strip()
            
            # rel_path is appid\depotid\manifestid\filename
            # We want appid\depotid\manifestid
            path_parts = rel_path.replace("\\", "/").split("/")
            if len(path_parts) >= 3:
                # Reconstruct the manifest directory path using OS-native separators
                manifest_dir = os.path.join(path_parts[0], path_parts[1], path_parts[2])
                manifests_to_keep.add(manifest_dir)

    print(f"Found {len(manifests_to_keep)} manifests to keep based on findings in {success_log}.\n")

    # 2. Walk the directory to find all manifest folders
    deleted_count = 0
    kept_count = 0

    # We iterate over app folders
    for app_id in os.listdir(args.dir):
        app_path = os.path.join(args.dir, app_id)
        if not os.path.isdir(app_path): continue
        if app_id.endswith(".log"): continue # Skip logs in the root dir
        
        # Then depot folders
        for depot_id in os.listdir(app_path):
            depot_path = os.path.join(app_path, depot_id)
            if not os.path.isdir(depot_path): continue
            
            # Then manifest folders
            for manifest_id in os.listdir(depot_path):
                manifest_path = os.path.join(depot_path, manifest_id)
                if not os.path.isdir(manifest_path): continue
                
                # Check if this manifest is in the keep set
                rel_manifest_path = os.path.join(app_id, depot_id, manifest_id)
                
                if rel_manifest_path not in manifests_to_keep:
                    if args.dry_run:
                        print(f"[DRY-RUN] Would delete: {rel_manifest_path}")
                    else:
                        print(f"Deleting: {rel_manifest_path}...")
                        try:
                            shutil.rmtree(manifest_path)
                        except Exception as e:
                            print(f"Error deleting {rel_manifest_path}: {e}")
                    deleted_count += 1
                else:
                    kept_count += 1

    print(f"\nCleanup complete.")
    print(f"Kept:    {kept_count}")
    print(f"Deleted: {deleted_count}")

if __name__ == "__main__":
    main()
