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
("Data field") and its own watches; a face carries its own watches only
when it runs on fewer than the help page lists.

When faces.json carries an "unlock" block (the export writes it once a
trial edition sells through Paddle), the site also gets /unlock/, where a
code for a face's trial edition is bought, and the terms and refund pages
Paddle's review asks for, linked from every page's footer.
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
# The unlock page's scripts: Paddle's checkout, then the page's own.
PADDLE_JS = "https://cdn.paddle.com/paddle/v2/paddle.js"
UNLOCK_JS = ('<script src="%s" defer></script>\n<script src="/assets/unlock.js" defer></script>'
             % PADDLE_JS)
ENVS = ("live", "sandbox")
SECTIONS = ("faces", "apps", "games")
TAB = {"faces": "", "apps": "apps/", "games": "games/"}  # each tab's page; the faces' is home
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# A section's tab once it has something in it: the headline, the line
# under it, the page's title and its description. The line and the
# description name the count and the first product lines of the help's
# watch list ({n}, {lines}): people search "fenix 8 watch face", so the
# words a search matches are on the page, not only in the store.
INTRO = {
    "faces": ("Watch faces worth a second look.",
              "{n} watch faces for Garmin {lines} and more, on the Connect IQ Store.",
              "Garmin Watch Faces, Apps and Games · Glean",
              "{n} watch faces for Garmin {lines} and more: nature, data, analog and "
              "digital dials, with apps and games, all on the Connect IQ Store."),
    "apps": ("Apps", "", "Garmin Apps and Widgets · Glean",
             "Glean's apps and widgets for Garmin {lines} and more, on the Connect IQ Store."),
    "games": ("Games", "", "Garmin Watch Games · Glean",
              "Glean's games for Garmin {lines} and more, on the Connect IQ Store."),
}
# What an item is, in the words people search with: a page's title, its
# pictures' alt text and its structured data say it.
NOUN = {"faces": "watch face", "games": "watch game"}  # an app says its kind
# The search engines' site-ownership tags, each written on the home page once
# its value is filled in (Search Console, Bing Webmaster Tools). The values
# are public by design: each only proves who may read the site's reports.
VERIFY = {"google-site-verification": "4PEZzT9MYKGHM9pmV8waqmkdYDirJownE4EssRq56Mc", "msvalidate.01": ""}
# Glean elsewhere, for the structured data's sameAs.
SAME_AS = ("https://www.facebook.com/gleanwatchfaces", "https://www.instagram.com/gleanwatchfaces/",
           "https://ko-fi.com/glean")
RELATED = 3  # the "more" cards under an item, one row of the grid


def esc(s):
    return html.escape(str(s), quote=True)


def load(site):
    return json.loads((Path(site) / "data" / "faces.json").read_text(encoding="utf-8"))


def template(site, name):
    return Template((Path(site) / "templates" / (name + ".html")).read_text(encoding="utf-8"))


def page(site, current, title, description, path, og_image, main, scripts="", legal="", head=""):
    """A whole page around `main`; `path` and `og_image` are relative to BASE.
    `current` is what to mark: a section's tab, "help", "privacy" or None.
    `legal` is the footer's line of sales pages, empty while nothing sells.
    `head` is more of the head: structured data, a robots or ownership tag."""
    nav = {("tab_" if k in SECTIONS else "nav_") + k:
           (' aria-current="page"' if k == current else "") for k in SECTIONS + ("help", "privacy")}
    return template(site, "base").substitute(
        title=esc(title), description=esc(description), canonical=esc(BASE + path),
        og_image=esc(BASE + og_image), main=main, scripts=scripts, legal=legal, head=head, **nav)


def jsonld(graph):
    """Structured data for search engines: data, not code, so the one inline
    <script> the site allows. Every <, > and & is written as its \\u escape,
    so no value can close the tag."""
    text = json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    for c in "<>&":
        text = text.replace(c, "\\u%04x" % ord(c))
    return '<script type="application/ld+json">%s</script>' % text


ORG = {"@type": "Organization", "@id": BASE + "#org", "name": "Glean", "url": BASE}


def lines_named(data, k=5):
    """'fēnix, epix, Forerunner, Venu, vívoactive': the help's first product lines."""
    return ", ".join(w["line"] for w in data["watches"][:k])


def noun(section, item):
    """'watch face', 'widget', 'data field', 'watch game'."""
    return NOUN.get(section) or item["kind"].lower()


def legal_line(data):
    """The footer's links to the sales pages, once the site sells codes."""
    if "unlock" not in data:
        return ""
    return ('\n  <p class="fine"><a href="/unlock/">Unlock a trial</a> · <a href="/terms/">Terms</a>'
            ' · <a href="/refunds/">Refunds</a> · <a href="/privacy/">Privacy</a></p>')


def usd(amount):
    """A price before tax: Paddle adds the buyer's VAT or sales tax at checkout."""
    return "US$%s + tax" % amount


def unlock_page(site, data):
    u = data["unlock"]
    options = "\n".join(
        '<option value="%s" data-price="%s">%s · %s</option>'
        % (esc(f["slug"]), esc(f["price"]), esc(f["name"]), esc(usd(f["usd"])))
        for f in u["faces"])
    prices = "\n".join("<li>%s: %s</li>" % (esc(f["name"]), esc(usd(f["usd"]))) for f in u["faces"])
    main = template(site, "unlock").substitute(
        env=esc(u["env"]), token=esc(u["token"]), server=esc(u["server"]),
        options=options, prices=prices, days=int(u["days"]))
    return page(site, None, "Unlock a trial · Glean",
                "Buy the code that unlocks a Glean face's free trial edition on your watch, for good.",
                "unlock/", data["faces"][0]["hero"]["file"], main, UNLOCK_JS, legal_line(data))


def legal_page(site, data, name, title, description):
    main = template(site, name).substitute(seller=esc(data["unlock"]["seller"]),
                                           days=int(data["unlock"]["days"]))
    return page(site, None, "%s · Glean" % title, description, name + "/",
                data["faces"][0]["hero"]["file"], main, "", legal_line(data))


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
    words = {"n": len(records), "lines": lines_named(data)}
    line, description = line.format(**words), description.format(**words)
    head = ""
    if section == "faces":
        head = "\n".join(['<meta name="%s" content="%s">' % (esc(k), esc(v))
                          for k, v in sorted(VERIFY.items()) if v]
                         + [jsonld([dict(ORG, logo=BASE + "apple-touch-icon.png", sameAs=list(SAME_AS)),
                                    {"@type": "WebSite", "@id": BASE + "#website", "name": "Glean",
                                     "url": BASE, "publisher": {"@id": BASE + "#org"}}])])
    if records:
        main = template(site, "section").substitute(
            heading=esc(heading), line=("<p>%s</p>" % esc(line)) if line else "",
            grid=grid(section, records))
    else:
        description = "Glean's first %s for Garmin watches are on their way." % section
        main = template(site, "soon").substitute(heading=esc(heading), soon=soon(section))
    return page(site, section, title, description, TAB[section],
                data["faces"][0]["hero"]["file"], main, legal=legal_line(data), head=head)


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
    """Where an item runs. A face runs on every watch in the help's list
    unless it carries its own, as an app or game always does: those are
    listed in place."""
    if "watches" not in item:
        return ('<p class="works"><a href="/help/#watches">%s</a></p>'
                % works_on(watch_count(data["watches"])))
    # Its own h2, so the product lines' h3s sit under it, not under Settings.
    return ('<h2>Watches</h2>\n  <details class="works"><summary>%s</summary>\n'
            '<div class="watches">\n%s\n</div></details>'
            % (works_on(watch_count(item["watches"])), watches_html(item["watches"])))


def related(data, section, item, k=RELATED):
    """Up to `k` other items of the section, its own category first, then
    the newest: the links on from an item page, so every page is reached
    from more than its list."""
    others = [r for r in items(data, section) if r["slug"] != item["slug"]]
    same = [r for r in others if r["category"] == item["category"]]
    return (same + [r for r in others if r not in same])[:k]


def item_head(section, item, path):
    """An item's structured data: what it is, and where it sits in the site."""
    url = BASE + path
    app = {"@type": "SoftwareApplication", "@id": url + "#app", "name": item["name"],
           "description": item["short"], "url": url,
           "image": [BASE + s["file"] for s in item["images"]],
           "applicationCategory": "GameApplication" if section == "games" else "LifestyleApplication",
           "applicationSubCategory": label(section, item),
           "operatingSystem": "Garmin Connect IQ", "installUrl": item["store_url"], "publisher": ORG}
    if item["subtitle"]:
        app["alternateName"] = full_title(item)
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": section.capitalize(), "item": BASE + TAB[section]},
        {"@type": "ListItem", "position": 2, "name": item["name"], "item": url}]}
    return jsonld([app, crumbs])


def more_html(data, section, item):
    """The cards of a few other items, or nothing when the section has one."""
    others = related(data, section, item)
    if not others:
        return ""
    return ('<section class="more">\n<h2>More %s</h2>\n%s\n</section>'
            % (section, grid(section, others, eager=0)))


def item_page(site, data, section, item):
    shots, n = item["images"], len(item["images"])
    what = noun(section, item)

    def alt(s):
        """'Gren watch face: the three themes', for image search as much as
        for a screen reader."""
        c = caption(s)
        return "%s %s: %s" % (item["name"], what, c[:1].lower() + c[1:])

    # Each slide opens its picture full size; each thumbnail is a link to its
    # slide, so the gallery still works where gallery.js does not run. One
    # picture has nothing to move between, so no thumbnails.
    slides = "\n".join(
        '<li class="slide" id="shot-%d" aria-roledescription="slide" aria-label="%d of %d" '
        'data-caption="%s"><a href="/%s">%s</a></li>'
        % (i + 1, i + 1, n, esc(caption(s)), esc(s["file"]), img(s, alt(s), i > 0))
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
        settings=settings_html(item), works=works(section, item, data),
        more=more_html(data, section, item))
    path = "%s/%s/" % (section, item["slug"])
    # "Gren – Fractal Tree, Ember Light · Garmin watch face · Glean": the
    # words a search matches come before the brand, which matches nothing.
    return page(site, section, "%s · Garmin %s · Glean" % (full_title(item), what), item["short"],
                path, item["hero"]["file"], main, GALLERY_JS, legal_line(data),
                item_head(section, item, path))


def watches_html(lines):
    return "\n".join("<section><h3>%s</h3><ul>%s</ul></section>"
                     % (esc(line["line"]), "".join("<li>%s</li>" % esc(n) for n in line["names"]))
                     for line in lines)


def help_page(site, data):
    main = template(site, "help").substitute(watches=watches_html(data["watches"]),
                                             watch_count=watch_count(data["watches"]))
    return page(site, "help", "Help · Glean",
                "Installing a Glean watch face, changing its settings, and the watches it runs on.",
                "help/", data["faces"][0]["hero"]["file"], main, legal=legal_line(data))


def privacy_page(site, data):
    return page(site, "privacy", "Privacy · Glean",
                "What Glean's faces, apps and this site do with your data: nothing leaves your watch but a rounded place for the stargazing forecast, and a trial edition's watch ID.",
                "privacy/", data["faces"][0]["hero"]["file"], template(site, "privacy").substitute(), "", legal_line(data))


def not_found(site, data):
    return page(site, None, "Not found · Glean", "This page does not exist.", "404.html",
                data["faces"][0]["hero"]["file"], template(site, "404").substitute(), "", legal_line(data),
                '<meta name="robots" content="noindex">')


def sitemap(paths, images=None):
    """Every page, and under an item's page its pictures, so image search
    finds them by the page they belong to."""
    images = images or {}
    urls = "".join(
        "  <url><loc>%s</loc>%s</url>\n"
        % (esc(BASE + p), "".join("<image:image><image:loc>%s</image:loc></image:image>"
                                  % esc(BASE + f) for f in images.get(p, ())))
        for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n%s</urlset>\n' % urls)


ROBOTS = "User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % BASE


def check(site, data):
    """Refuse data the pages cannot honestly be built from: no face; a slug
    that is unsafe, or used twice (each names a folder under img/ as well as
    its page); a live app or game the privacy page says nothing about, since
    an app can do what no face does."""
    if not data["faces"]:
        raise SystemExit("build: faces.json lists no face")
    u = data.get("unlock")
    if u is not None:
        if u.get("env") not in ENVS:
            raise SystemExit("build: unlock.env must be one of %s" % ", ".join(ENVS))
        if not str(u.get("seller", "")).strip():
            raise SystemExit("build: unlock.seller, the legal name Paddle knows, is empty")
        if not str(u.get("server", "")).startswith("https://"):
            raise SystemExit("build: unlock.server is not an https address")
        if not u.get("faces"):
            raise SystemExit("build: unlock lists no face")
        live = {r["slug"] for r in data["faces"]}
        for f in u["faces"]:
            if f["slug"] not in live:
                raise SystemExit("build: unlock sells %s, which the site does not list" % f["slug"])
            if not re.fullmatch(r"pri_[a-z0-9]+", str(f["price"])):
                raise SystemExit("build: %s's price id %r is not Paddle's" % (f["slug"], f["price"]))
            if not re.fullmatch(r"\d+\.\d\d", str(f["usd"])):
                raise SystemExit("build: %s's usd %r is not N.NN" % (f["slug"], f["usd"]))
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
    paths, images = [], {}
    for section in SECTIONS:
        records = items(data, section)
        _prune(site / section, {r["slug"] for r in records})
        _write(site / TAB[section] / "index.html", section_page(site, data, section))
        paths.append(TAB[section])
        for r in records:
            _write(site / section / r["slug"] / "index.html", item_page(site, data, section, r))
            paths.append("%s/%s/" % (section, r["slug"]))
            images[paths[-1]] = [s["file"] for s in r["images"]]
    _write(site / "help" / "index.html", help_page(site, data))
    _write(site / "privacy" / "index.html", privacy_page(site, data))
    _write(site / "404.html", not_found(site, data))
    paths += ["help/", "privacy/"]
    sales = (("unlock", None, None),
             ("terms", "Terms of sale", "The terms on which Glean sells unlock codes for its faces' trial editions."),
             ("refunds", "Refunds", "Glean's refund policy for unlock codes."))
    for name, title, description in sales:
        if "unlock" in data:
            text = (unlock_page(site, data) if name == "unlock"
                    else legal_page(site, data, name, title, description))
            _write(site / name / "index.html", text)
            paths.append(name + "/")
        elif (site / name).exists():
            shutil.rmtree(site / name)
    _write(site / "sitemap.xml", sitemap(paths, images))
    _write(site / "robots.txt", ROBOTS)
    return paths


if __name__ == "__main__":
    for p in build():
        print("built /" + p)
