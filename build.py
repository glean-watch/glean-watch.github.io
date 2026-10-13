"""Build the Glean website: data/faces.json + templates/ -> static pages.

    python build.py

Standard library only. Every value from faces.json is escaped before it
reaches a template; the templates hold the only raw HTML. The same input
gives byte-identical pages. The pages are committed and GitHub Pages
serves them as they are.

The site has three sections, faces, apps and games, a tab each under the
header: a grid of cards (the faces' is the home page, the others are at
/apps/ and /games/) and a page per item at /<section>/<slug>/. faces.json
may leave apps and games out; a section with nothing in it says its first
are on the way, and names nothing. An app or game also carries its kind
("Data field") and its own watches.
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
# The item pages' gallery: the site's one script, its own file, nothing inline.
GALLERY_JS = '<script src="/assets/gallery.js" defer></script>'
SECTIONS = ("faces", "apps", "games")
TAB = {"faces": "", "apps": "apps/", "games": "games/"}  # each tab's page; the faces' is home
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# A section's tab once it has something in it: the headline, the line
# under it, the page's title and its description.
INTRO = {
    "faces": ("Watch faces worth a second look.", "All faces are free on the Connect IQ Store.",
              "Glean · Watch faces, apps and games for Garmin watches",
              "Watch faces for Garmin watches, all free on the Connect IQ Store."),
    "apps": ("Apps", "", "Apps · Glean",
             "Glean's apps for Garmin watches, on the Connect IQ Store."),
    "games": ("Games", "", "Games · Glean",
              "Glean's games for Garmin watches, on the Connect IQ Store."),
}


def esc(s):
    return html.escape(str(s), quote=True)


def load(site):
    return json.loads((Path(site) / "data" / "faces.json").read_text(encoding="utf-8"))


def template(site, name):
    return Template((Path(site) / "templates" / (name + ".html")).read_text(encoding="utf-8"))


def page(site, current, title, description, path, og_image, main, scripts=""):
    """A whole page around `main`; `path` and `og_image` are relative to BASE.
    `current` is what to mark: a section's tab, "help", "privacy" or None."""
    nav = {("tab_" if k in SECTIONS else "nav_") + k:
           (' aria-current="page"' if k == current else "") for k in SECTIONS + ("help", "privacy")}
    return template(site, "base").substitute(
        title=esc(title), description=esc(description), canonical=esc(BASE + path),
        og_image=esc(BASE + og_image), main=main, scripts=scripts, **nav)


def img(pic, alt, lazy, cls=None):
    return ('<img%s src="/%s" width="%d" height="%d" alt="%s"%s>'
            % (' class="%s"' % cls if cls else "", esc(pic["file"]), int(pic["w"]),
               int(pic["h"]), esc(alt), ' loading="lazy"' if lazy else ""))


def items(data, section):
    """A section's records, newest first; faces.json may leave apps and games out."""
    return data.get(section, [])


def label(section, item):
    """The line by an item's name: a face's category; an app's or game's
    kind and category, "Data field · Outdoor"."""
    if section == "faces":
        return item["category"]
    return "%s · %s" % (item["kind"], item["category"])


def card(section, item, lazy):
    shot = item["images"][0]
    return ('<li class="card"><a href="/%s/%s/">%s<span class="cat">%s</span>'
            '<span class="name">%s</span><span class="pitch">%s</span></a></li>'
            % (section, esc(item["slug"]), img(shot, shot["alt"], lazy),
               esc(label(section, item)), esc(item["name"]), esc(item["pitch"])))


def grid(section, records, eager=EAGER):
    """The cards of `records`, the first `eager` of them loading at once."""
    return ('<ul class="grid" role="list">\n%s\n</ul>'
            % "\n".join(card(section, r, i >= eager) for i, r in enumerate(records)))


def soon(section):
    """What a section with nothing in it says. It names nothing."""
    return "The first Glean %s are on their way." % section


def section_page(site, data, section):
    """A section's tab: every card in it, or the page saying its first are
    on the way. The faces' tab is the home page."""
    records = items(data, section)
    heading, line, title, description = INTRO[section]
    if records:
        main = template(site, "section").substitute(
            heading=esc(heading), line=("<p>%s</p>" % esc(line)) if line else "",
            grid=grid(section, records))
    else:
        description = "Glean's first %s for Garmin watches are on their way." % section
        main = template(site, "soon").substitute(heading=esc(heading), soon=soon(section))
    return page(site, section, title, description, TAB[section],
                data["faces"][0]["hero"]["file"], main)


def watch_count(lines):
    return sum(len(line["names"]) for line in lines)


def works_on(n):
    return "Works on %d watch%s" % (n, "" if n == 1 else "es")


def full_title(item):
    return item["name"] + (" – " + item["subtitle"] if item["subtitle"] else "")


def caption(shot):
    """'Lykt: the five pumpkins' -> 'The five pumpkins': the listing's caption,
    which the export put after the name in the alt text."""
    text = shot["alt"].partition(": ")[2] or shot["alt"]
    return text[:1].upper() + text[1:]


def settings_html(item):
    """The settings table, or nothing for an item without settings."""
    if not item["settings"]:
        return ""
    rows = "\n".join('<tr><th scope="row">%s</th><td>%s</td></tr>'
                     % (esc(r["name"]), esc(r["values"])) for r in item["settings"])
    return '  <h2>Settings</h2>\n  <table class="settings">\n%s\n  </table>' % rows


def works(section, item, data):
    """Where an item runs. Every face runs on every watch in the help's list;
    an app or game runs on its own, listed in place."""
    if section == "faces":
        return ('<p class="works"><a href="/help/#watches">%s</a></p>'
                % works_on(watch_count(data["watches"])))
    # Its own h2, so the product lines' h3s sit under it, not under Settings.
    return ('<h2>Watches</h2>\n  <details class="works"><summary>%s</summary>\n'
            '<div class="watches">\n%s\n</div></details>'
            % (works_on(watch_count(item["watches"])), watches_html(item["watches"])))


def item_page(site, data, section, item):
    shots, n = item["images"], len(item["images"])
    # Each slide opens its picture full size; each thumbnail is a link to its
    # slide, so the gallery still works where gallery.js does not run. One
    # picture has nothing to move between, so no thumbnails.
    slides = "\n".join(
        '<li class="slide" id="shot-%d" aria-roledescription="slide" aria-label="%d of %d" '
        'data-caption="%s"><a href="/%s">%s</a></li>'
        % (i + 1, i + 1, n, esc(caption(s)), esc(s["file"]), img(s, s["alt"], i > 0))
        for i, s in enumerate(shots))
    thumbs = "\n".join(
        '<li><a class="thumb" href="#shot-%d" aria-label="Picture %d: %s">%s</a></li>'
        % (i + 1, i + 1, esc(caption(s)), img(s, "", False)) for i, s in enumerate(shots))
    main = template(site, "item").substitute(
        section_href="/" + TAB[section], section=section,
        name=esc(item["name"]), label=esc(label(section, item)),
        subtitle=('<p class="sub">%s</p>' % esc(item["subtitle"])) if item["subtitle"] else "",
        store_url=esc(item["store_url"]), icon=img(item["icon"], "", False, "icon"),
        slides=slides, count=n, caption=esc(caption(shots[0])),
        thumbs=('  <ol class="thumbs" role="list">\n%s\n  </ol>' % thumbs) if n > 1 else "",
        short=esc(item["short"]), full="\n".join("<p>%s</p>" % esc(p) for p in item["full"]),
        settings=settings_html(item), works=works(section, item, data))
    return page(site, section, "%s · Glean" % full_title(item), item["short"],
                "%s/%s/" % (section, item["slug"]), item["hero"]["file"], main, GALLERY_JS)


def watches_html(lines):
    return "\n".join("<section><h3>%s</h3><ul>%s</ul></section>"
                     % (esc(line["line"]), "".join("<li>%s</li>" % esc(n) for n in line["names"]))
                     for line in lines)


def help_page(site, data):
    main = template(site, "help").substitute(watches=watches_html(data["watches"]),
                                             watch_count=watch_count(data["watches"]))
    return page(site, "help", "Help · Glean",
                "Installing a Glean watch face, changing its settings, and the watches it runs on.",
                "help/", data["faces"][0]["hero"]["file"], main)


def privacy_page(site, data):
    return page(site, "privacy", "Privacy · Glean",
                "What Glean's watch faces and this site do with your data: nothing leaves your watch.",
                "privacy/", data["faces"][0]["hero"]["file"], template(site, "privacy").substitute())


def not_found(site, data):
    return page(site, None, "Not found · Glean", "This page does not exist.", "404.html",
                data["faces"][0]["hero"]["file"], template(site, "404").substitute())


def sitemap(paths):
    urls = "".join("  <url><loc>%s</loc></url>\n" % esc(BASE + p) for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n' % urls)


ROBOTS = "User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % BASE


def check(site, data):
    """Refuse data the pages cannot honestly be built from: no face; a slug
    that is unsafe, or used twice (each names a folder under img/ as well as
    its page); a live app or game the privacy page says nothing about, since
    an app can do what no face does."""
    if not data["faces"]:
        raise SystemExit("build: faces.json lists no face")
    seen = set()
    for section in SECTIONS:
        for r in items(data, section):
            if not SLUG.fullmatch(str(r["slug"])):
                raise SystemExit("build: unsafe slug %r" % r["slug"])
            if r["slug"] in seen:
                raise SystemExit("build: the slug %r is used twice" % r["slug"])
            seen.add(r["slug"])
    # A section commented out, a draft, is no section.
    privacy = re.sub(r"<!--.*?-->", "", (Path(site) / "templates" / "privacy.html")
                     .read_text(encoding="utf-8"), flags=re.S)
    for section in ("apps", "games"):
        for r in items(data, section):
            if not re.search(r'(?<![\w-])id="%s"' % re.escape(r["slug"]), privacy):
                raise SystemExit('build: the privacy page has no section for %s (id="%s")'
                                 % (r["name"], r["slug"]))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _prune(folder, keep):
    """Delete the item folders under `folder` whose item is gone. The
    section's own index.html is a file, and stays."""
    if folder.exists():
        for d in folder.iterdir():
            if d.is_dir() and d.name not in keep:
                shutil.rmtree(d)


def build(site=HERE):
    """Write every page under `site` from its data and templates. Returns the
    pages' paths relative to BASE."""
    site = Path(site)
    data = load(site)
    check(site, data)
    paths = []
    for section in SECTIONS:
        records = items(data, section)
        _prune(site / section, {r["slug"] for r in records})
        _write(site / TAB[section] / "index.html", section_page(site, data, section))
        paths.append(TAB[section])
        for r in records:
            _write(site / section / r["slug"] / "index.html", item_page(site, data, section, r))
            paths.append("%s/%s/" % (section, r["slug"]))
    _write(site / "help" / "index.html", help_page(site, data))
    _write(site / "privacy" / "index.html", privacy_page(site, data))
    _write(site / "404.html", not_found(site, data))
    paths += ["help/", "privacy/"]
    _write(site / "sitemap.xml", sitemap(paths))
    _write(site / "robots.txt", ROBOTS)
    return paths


if __name__ == "__main__":
    for p in build():
        print("built /" + p)
