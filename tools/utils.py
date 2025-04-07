import os
import tarfile
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import html

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s - %(message)s'
    )

def extract_tarball(tar_path, extract_to):
    try:
        with tarfile.open(tar_path, 'r:*') as tar:
            tar.extractall(path=extract_to)
        logging.info(f"Extracted tarball to: {extract_to}")
    except Exception as e:
        logging.error(f"Error extracting tarball: {e}")
        raise

def extract_html_metadata(html_path, soup):
    title_tag = soup.title.string.strip() if soup.title and soup.title.string else "Untitled"
    slug = os.path.splitext(os.path.basename(html_path))[0]
    rel_path = os.path.relpath(html_path)
    return title_tag, slug, rel_path

def extract_text_and_links(html_path):
    try:
        with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f, 'html.parser')
            title, slug, source = extract_html_metadata(html_path, soup)
            text = soup.get_text(separator='\n', strip=True)

            links = []
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                link_text = a.get_text(strip=True)
                if href and not href.startswith('#'):
                    links.append(f"- [{link_text or href}]({href})")

            return title, slug, source, text, links
    except Exception as e:
        logging.error(f"Error processing {html_path}: {e}")
        return "Untitled", "unknown", html_path, "", []

def write_outputs(html_path, title, slug, source, text, links):
    base_name = os.path.splitext(html_path)[0]
    txt_path = base_name + ".txt"
    md_path = base_name + ".md"

    title = html.escape(title.replace('"', "'"))
    slug = html.escape(slug.replace('"', "'"))

    frontmatter = f"""---
title: "{title}"
slug: "{slug}"
source: "{source}"
---\n"""

    md_content = frontmatter + "\n" + text
    if links:
        md_content += "\n\n## Links\n" + "\n".join(links)

    try:
        with open(txt_path, 'w', encoding='utf-8') as f_txt:
            f_txt.write(text)

        with open(md_path, 'w', encoding='utf-8') as f_md:
            f_md.write(md_content)

        logging.info(f"✓ Generated: {txt_path} and {md_path}")
    except Exception as e:
        logging.error(f"Failed to write output files for {html_path}: {e}")

def process_html_files(root_dir):
    count = 0
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if not file.lower().endswith('.html') or file.startswith('._') or file == '.DS_Store':
                continue

            html_path = os.path.join(subdir, file)
            title, slug, source, text, links = extract_text_and_links(html_path)

            if text.strip():
                write_outputs(html_path, title, slug, source, text, links)
                count += 1

            try:
                os.remove(html_path)
            except Exception as e:
                logging.warning(f"Could not remove {html_path}: {e}")

    logging.info(f"✅ Processed {count} HTML files.")
    return count

