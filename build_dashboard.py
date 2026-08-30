#!/usr/bin/env python3
"""
Build the dashboard from its template plus the exported measurement data.

Two outputs, because they have different hosts:
  dashboard/index.html - body fragment (the Artifact host supplies the skeleton)
  docs/index.html      - standalone page with a full HTML skeleton, served by
                         GitHub Pages so teammates can open it from a link
"""
import pathlib

tpl = pathlib.Path("dashboard/index_template.html").read_text()
data = pathlib.Path("dashboard/data.json").read_text()
page = tpl.replace("/*__DATA__*/", data)

pathlib.Path("dashboard/index.html").write_text(page)

standalone = (
    '<!doctype html>\n<html lang="en">\n<head>\n'
    '<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
    '<style>:root{color-scheme:light dark}body{margin:0}'
    'img{max-width:100%}[hidden]{display:none!important}</style>\n'
    + page +
    '\n</body>\n</html>\n'
)
# the template opens with <title>/<link>/<style>, which belong in <head>;
# browsers relocate them correctly, and keeping one source avoids drift.
pathlib.Path("docs/index.html").write_text(standalone)

print(f"dashboard/index.html  {len(page)/1024:.0f} kB  (artifact fragment)")
print(f"docs/index.html       {len(standalone)/1024:.0f} kB  (GitHub Pages)")
