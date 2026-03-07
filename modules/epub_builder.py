from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip()).strip("-").lower()
    return text or "book"


def build_simple_epub(
    output_path: str | Path,
    *,
    title: str,
    author: str,
    description: str,
    chapters: list[tuple[str, str]] | None = None,
    language: str = "en",
) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    safe_title = html.escape(title or "Untitled")
    safe_author = html.escape(author or "Unknown Author")
    safe_description = html.escape(description or "")
    book_id = _slugify(f"{title}-{author}")
    chapter_items = chapters or [
        ("Introduction", description or "Practical starter guide."),
        ("Quick Start", "Set one clear goal, prepare the asset pack, and publish with a repeatable workflow."),
        ("Execution Notes", "Use the checklist, validate results, and iterate only on confirmed platform signals."),
    ]

    nav_points = []
    content_docs = []
    manifest_items = [
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="style" href="styles.css" media-type="text/css"/>',
    ]
    spine_items = []

    for idx, (chapter_title, chapter_body) in enumerate(chapter_items, start=1):
        cid = f"chapter{idx}"
        href = f"{cid}.xhtml"
        manifest_items.append(f'<item id="{cid}" href="{href}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'<itemref idref="{cid}"/>')
        nav_points.append((cid, chapter_title))
        body_html = "<p>" + "</p><p>".join(
            html.escape(x.strip()) for x in re.split(r"\n\s*\n", chapter_body or "") if x.strip()
        ) + "</p>"
        content_docs.append(
            (
                href,
                f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}" lang="{language}">
  <head>
    <title>{html.escape(chapter_title)}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
  </head>
  <body>
    <h1>{html.escape(chapter_title)}</h1>
    {body_html}
  </body>
</html>
""",
            )
        )

    package_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">urn:vito:{book_id}</dc:identifier>
    <dc:title>{safe_title}</dc:title>
    <dc:language>{language}</dc:language>
    <dc:creator>{safe_author}</dc:creator>
    <dc:description>{safe_description}</dc:description>
  </metadata>
  <manifest>
    {' '.join(manifest_items)}
  </manifest>
  <spine toc="ncx">
    {' '.join(spine_items)}
  </spine>
</package>
"""

    nav_html = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}" lang="{language}">
  <head><title>Contents</title></head>
  <body>
    <nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops" id="toc">
      <h1>Contents</h1>
      <ol>
        {items}
      </ol>
    </nav>
  </body>
</html>
""".format(
        language=language,
        items="".join(f'<li><a href="{cid}.xhtml">{html.escape(ch_title)}</a></li>' for cid, ch_title in nav_points),
    )

    toc_ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:vito:{book_id}"/>
  </head>
  <docTitle><text>{title}</text></docTitle>
  <navMap>
    {points}
  </navMap>
</ncx>
""".format(
        book_id=book_id,
        title=safe_title,
        points="".join(
            f'<navPoint id="{cid}" playOrder="{idx}"><navLabel><text>{html.escape(ch_title)}</text></navLabel><content src="{cid}.xhtml"/></navPoint>'
            for idx, (cid, ch_title) in enumerate(nav_points, start=1)
        ),
    )

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    styles_css = """body { font-family: serif; line-height: 1.5; margin: 5%; }
h1 { page-break-before: always; font-size: 1.6em; }
p { margin: 0 0 1em 0; }
"""

    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", package_opf)
        zf.writestr("OEBPS/toc.ncx", toc_ncx)
        zf.writestr("OEBPS/nav.xhtml", nav_html)
        zf.writestr("OEBPS/styles.css", styles_css)
        for href, doc in content_docs:
            zf.writestr(f"OEBPS/{href}", doc)

    return str(out)
