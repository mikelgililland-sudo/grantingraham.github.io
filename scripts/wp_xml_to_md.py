import re
from pathlib import Path
from datetime import datetime
from slugify import slugify
from lxml import etree
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import frontmatter

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "wp": "http://wordpress.org/export/1.2/",
}

def clean_html_to_md(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = md(str(soup), heading_style="ATX")
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text

def parse_wp_date(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 2
    while True:
        candidate = path.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1

def main():
    repo = Path(__file__).resolve().parents[1]
    wp_dir = repo / "wordpress-export"

    xml_files = sorted(wp_dir.glob("*.xml"))
    if not xml_files:
        raise SystemExit(f"No .xml found in {wp_dir}")

    xml_path = xml_files[0]

    out_posts = repo / "content" / "posts"
    out_pages = repo / "content" / "pages"
    out_posts.mkdir(parents=True, exist_ok=True)
    out_pages.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {xml_path.name}")
    tree = etree.parse(str(xml_path))
    items = tree.findall(".//item")

    count_posts = 0
    count_pages = 0
    count_skipped = 0

    for item in items:
        post_type = item.findtext("wp:post_type", namespaces=NS) or ""
        status = item.findtext("wp:status", namespaces=NS) or ""
        title = (item.findtext("title") or "").strip()
        creator = (item.findtext("dc:creator", namespaces=NS) or "").strip()
        slug = (item.findtext("wp:post_name", namespaces=NS) or "").strip()
        wp_id = (item.findtext("wp:post_id", namespaces=NS) or "").strip()

        if post_type not in ("post", "page"):
            count_skipped += 1
            continue

        html = item.findtext("content:encoded", namespaces=NS) or ""
        body = clean_html_to_md(html)

        date_str = (item.findtext("wp:post_date", namespaces=NS) or "").strip()
        dt = parse_wp_date(date_str)

        # If slug missing, derive it
        if not slug:
            slug = slugify(title) if title else f"wp-{wp_id}"

        fm = {
            "title": title if title else f"(untitled {wp_id})",
            "author": creator if creator else None,
            "wp_id": int(wp_id) if wp_id.isdigit() else wp_id,
            "wp_status": status,
            "wp_type": post_type,
            "source_xml": xml_path.name,
        }

        # Your rule: only set date if WordPress provides a real date
        if dt:
            fm["date"] = dt.strftime("%Y-%m-%d %H:%M:%S")

        cats, tags = [], []
        for c in item.findall("category"):
            domain = (c.get("domain") or "").strip()
            val = (c.text or "").strip()
            if not val:
                continue
            if domain == "category":
                cats.append(val)
            elif domain == "post_tag":
                tags.append(val)

        if cats:
            fm["categories"] = sorted(set(cats))
        if tags:
            fm["tags"] = sorted(set(tags))

        post = frontmatter.Post(body)
        for k, v in fm.items():
            if v is not None and v != "":
                post[k] = v

        # Output location
        if post_type == "post" and dt:
            dest_dir = out_posts / str(dt.year) / f"{dt.month:02d}"
        elif post_type == "post":
            dest_dir = out_posts / "undated"
        else:
            dest_dir = out_pages

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = ensure_unique_path(dest_dir / f"{slug}.md")
        dest.write_text(frontmatter.dumps(post), encoding="utf-8")

        if post_type == "post":
            count_posts += 1
        else:
            count_pages += 1

    print(f"Done. posts={count_posts}, pages={count_pages}, skipped={count_skipped}")
    print("Output:")
    print(f"  {out_posts}")
    print(f"  {out_pages}")

if __name__ == "__main__":
    main()
