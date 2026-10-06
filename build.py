"""Build the Glean website: data/faces.json + templates/ -> static pages.

    python build.py

Standard library only. Every value from faces.json is escaped before it
reaches a template; the templates hold the only raw HTML. The same input
gives byte-identical pages. The pages are committed and GitHub Pages
serves them as they are.
"""
import html
import json
import re
import shutil
from pathlib import Path
from string import Template

BASE = "https://glean-watch.github.io/"
HERE = Path(__file__).resolve().parent
EAGER = 3  # the cards above the fold load at once, the rest lazily


def esc(s):
    return html.escape(str(s), quote=True)


def load(site):
    return json.loads((Path(site) / "data" / "faces.json").read_text(encoding="utf-8"))


def template(site, name):
    return Template((Path(site) / "templates" / (name + ".html")).read_text(encoding="utf-8"))


def page(site, current, title, description, path, og_image, main):
    """A whole page around `main`; `path` and `og_image` are relative to BASE."""
    nav = {k: (' aria-current="page"' if k == current else "")
           for k in ("faces", "help", "privacy")}
    return template(site, "base").substitute(
        title=esc(title), description=esc(description), canonical=esc(BASE + path),
        og_image=esc(BASE + og_image), main=main, nav_faces=nav["faces"],
        nav_help=nav["help"], nav_privacy=nav["privacy"])


def img(pic, alt, lazy, cls=None):
    return ('<img%s src="/%s" width="%d" height="%d" alt="%s"%s>'
            % (' class="%s"' % cls if cls else "", esc(pic["file"]), int(pic["w"]),
               int(pic["h"]), esc(alt), ' loading="lazy"' if lazy else ""))


def card(face, i):
    shot = face["images"][0]
    return ('<li class="card"><a href="/faces/%s/">%s<span class="cat">%s</span>'
            '<span class="name">%s</span><span class="pitch">%s</span></a></li>'
            % (esc(face["slug"]), img(shot, shot["alt"], i >= EAGER), esc(face["category"]),
               esc(face["name"]), esc(face["pitch"])))


def home(site, data):
    main = template(site, "home").substitute(
        cards="\n".join(card(f, i) for i, f in enumerate(data["faces"])))
    return page(site, "faces", "Glean · Watch faces for Garmin watches",
                "Watch faces for Garmin watches, all free on the Connect IQ Store.",
                "", data["faces"][0]["hero"]["file"], main)


def watch_count(data):
    return sum(len(line["names"]) for line in data["watches"])


def full_title(face):
    return face["name"] + (" – " + face["subtitle"] if face["subtitle"] else "")


def face_page(site, data, face):
    strip = "\n".join('<li><a href="/%s">%s</a></li>' % (esc(s["file"]), img(s, s["alt"], i > 0))
                      for i, s in enumerate(face["images"]))
    rows = "\n".join('<tr><th scope="row">%s</th><td>%s</td></tr>'
                     % (esc(r["name"]), esc(r["values"])) for r in face["settings"])
    main = template(site, "face").substitute(
        name=esc(face["name"]), category=esc(face["category"]),
        subtitle=('<p class="sub">%s</p>' % esc(face["subtitle"])) if face["subtitle"] else "",
        store_url=esc(face["store_url"]), icon=img(face["icon"], "", False, "icon"),
        strip=strip, short=esc(face["short"]),
        full="\n".join("<p>%s</p>" % esc(p) for p in face["full"]),
        settings=rows, watch_count=watch_count(data))
    return page(site, "faces", "%s · Glean" % full_title(face), face["short"],
                "faces/%s/" % face["slug"], face["hero"]["file"], main)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def build(site=HERE):
    """Write every page under `site` from its data and templates. Returns the
    pages' paths relative to BASE."""
    site = Path(site)
    data = load(site)
    if not data["faces"]:
        raise SystemExit("build: faces.json lists no face")
    slugs = [f["slug"] for f in data["faces"]]
    for s in slugs:
        if not re.fullmatch(r"[a-z0-9]+", s):
            raise SystemExit("build: unsafe slug %r" % s)
    faces_dir = site / "faces"
    if faces_dir.exists():
        for d in faces_dir.iterdir():
            if d.name not in slugs:
                shutil.rmtree(d)
    _write(site / "index.html", home(site, data))
    for f in data["faces"]:
        _write(faces_dir / f["slug"] / "index.html", face_page(site, data, f))
    return [""] + ["faces/%s/" % s for s in slugs]


if __name__ == "__main__":
    for p in build():
        print("built /" + p)
