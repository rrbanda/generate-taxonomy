import os
import argparse
import logging
from utils import setup_logging, extract_tarball, process_html_files

def main():
    parser = argparse.ArgumentParser(description="Extract .txt and .md from .html files with metadata.")
    parser.add_argument("tarball", help="Path to the website tarball")
    parser.add_argument("-o", "--output", default=".", help="Directory to extract and process")
    args = parser.parse_args()

    setup_logging()

    if not os.path.exists(args.tarball):
        logging.error(f"Tarball not found: {args.tarball}")
        return 1

    try:
        extract_tarball(args.tarball, args.output)
        count = process_html_files(args.output)

        if count == 0:
            logging.warning("⚠️ No HTML files were processed.")
        else:
            logging.info(f"✅ Done. Total HTML files processed: {count}")
        return 0

    except Exception as e:
        logging.exception("❌ Unexpected error during extraction and processing")
        return 1

if __name__ == "__main__":
    exit(main())

