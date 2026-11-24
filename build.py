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
when it runs on fewer than the help page lists. A face category with at
least CATEGORY_MIN faces has its own page, /faces/<category>/, linked from
the home page and from its faces.

Each language of i18n.py beyond English has the same pages under /<code>/
(/de/, /de/faces/gren/), for the items data/tr/<code>.json translates:
their listing's title and full description in that language, the site's
own words from i18n.py. Every page names its other languages (hreflang)
and links them in the footer. Help, privacy, the sales pages and the 404
are English only.

When faces.json carries an "unlock" block (the export writes it once a
trial edition sells through Paddle), the site also gets /unlock/, where a
code for a face's trial edition is bought, and the terms and refund pages
Paddle's review asks for, linked from every page's footer.
"""
import html
import json
import re
import shutil
import sys
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i18n  # noqa: E402

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
# A face category gets its own page from this many faces: fewer would be
# a thin page that only repeats the faces' own.
CATEGORY_MIN = 3
# The search engines' site-ownership tags, each written on the home page once
# its value is filled in (Search Console, Bing Webmaster Tools). The values
# are public by design: each only proves who may read the site's reports.
VERIFY = {"google-site-verification": "4PEZzT9MYKGHM9pmV8waqmkdYDirJownE4EssRq56Mc", "msvalidate.01": ""}
# Glean elsewhere, for the structured data's sameAs.
SAME_AS = ("https://www.facebook.com/gleanwatchfaces", "https://www.instagram.com/gleanwatchfaces/",
           "https://ko-fi.com/glean")
RELATED = 3  # the "more" cards under an item, one row of the grid
DESCRIPTION_MAX = 160  # a translated page's description, cut at a word


def esc(s):
    return html.escape(str(s), quote=True)


def load(site):
    """faces.json, with "tr": {code: {slug: words}} from data/tr/."""
    site = Path(site)
    data = json.loads((site / "data" / "faces.json").read_text(encoding="utf-8"))
    tr_dir = site / "data" / "tr"
    data["tr"] = ({f.stem: json.loads(f.read_text(encoding="utf-8"))
                   for f in sorted(tr_dir.glob("*.json"))} if tr_dir.exists() else {})
    return data


def template(site, name):
    return Template((Path(site) / "templates" / (name + ".html")).read_text(encoding="utf-8"))


def pre(lang):
    """A language's folder under the site: '' for English, 'de/'."""
    return "" if lang == "en" else lang + "/"


def alternate_links(alternates):
    """hreflang links to every language of a page, English the default."""
    if not alternates or len(alternates) < 2:
        return ""
    links = ['<link rel="alternate" hreflang="%s" href="%s">' % (c, esc(BASE + alternates[c]))
             for c in i18n.CODES if c in alternates]
    links.append('<link rel="alternate" hreflang="x-default" href="%s">' % esc(BASE + alternates["en"]))
    return "\n" + "\n".join(links)


def language_line(lang, alternates):
    """The footer's links to the page in its other languages."""
    if not alternates or len(alternates) < 2:
        return ""
    links = " · ".join(
        '<a href="/%s" hreflang="%s" lang="%s"%s>%s</a>'
        % (esc(alternates[c]), c, c, ' aria-current="page"' if c == lang else "", esc(i18n.NAME[c]))
        for c in i18n.CODES if c in alternates)
    return '\n  <nav class="langs" aria-label="%s">%s</nav>' % (esc(i18n.t(lang, "language")), links)


# The header's language menu: a globe, then the language's code.
GLOBE = ('<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9"/>'
         '<path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/></svg>')


def homes(data):
    """The languages with a home page: English, and each with a face in it."""
    if data is None:
        return ("en",)
    return tuple(c for c in i18n.CODES if c == "en" or items(data, "faces", c))


def language_menu(lang, alternates, data):
    """The header's menu of languages: each opens this page in it, or that
    language's home page where this page is English only. No script: a
    <details> opens and closes it."""
    links = []
    for c in homes(data):
        href = (alternates or {}).get(c, pre(c))
        links.append('<li><a href="/%s" hreflang="%s" lang="%s"%s>%s</a></li>'
                     % (esc(href), c, c, ' aria-current="true"' if c == lang else "",
                        esc(i18n.NAME[c])))
    if len(links) < 2:
        return ""
    return ('<details class="lang">\n  <summary aria-label="%s: %s">%s<span>%s</span></summary>\n'
            '  <ul role="list">\n  %s\n  </ul>\n</details>'
            % (esc(i18n.t(lang, "language")), esc(i18n.NAME[lang]), GLOBE, lang.upper(),
               "\n  ".join(links)))


def page(site, current, title, description, path, og_image, main, scripts="", legal="", head="",
         lang="en", alternates=None, tabs=None, data=None):
    """A whole page around `main`; `path` and `og_image` are relative to BASE.
    `current` is what to mark: a section's tab, "help", "privacy" or None.
    `legal` is the footer's line of sales pages, empty while nothing sells.
    `head` is more of the head: structured data, a robots or ownership tag.
    `alternates` is {code: path} of the page in every language it has;
    `tabs` the sections' hrefs, tab_hrefs(), English's when not given;
    `data` names the languages the header's menu offers."""
    nav = {("tab_" if k in SECTIONS else "nav_") + k:
           (' aria-current="page"' if k == current else "") for k in SECTIONS + ("help", "privacy")}
    words = {"t_" + k: esc(i18n.t(lang, k)) for k in
             ("faces", "apps", "games", "help", "privacy", "coffee", "kofi", "on_facebook",
              "on_instagram", "trademark")}
    hrefs = {"href_" + s: (tabs or {}).get(s, "/" + TAB[s]) for s in SECTIONS}
    return template(site, "base").substitute(
        lang=lang, title=esc(title), description=esc(description), canonical=esc(BASE + path),
        og_image=esc(BASE + og_image), main=main, scripts=scripts, legal=legal,
        head=head + alternate_links(alternates), languages=language_line(lang, alternates),
        menu=language_menu(lang, alternates, data),
        **nav, **words, **hrefs)


def tab_hrefs(data, lang):
    """Each section's tab in `lang`, or in English where `lang` has none of it."""
    return {s: "/" + (pre(lang) if items(data, s, lang) else "") + TAB[s] for s in SECTIONS}


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


def noun(lang, section, item):
    """What the item is, as people search for it: 'Garmin watch face',
    'Garmin-Widget', 'gra na zegarek Garmin'."""
    if section == "faces":
        return i18n.NOUN[lang]["face"]
    if section == "games":
        return i18n.NOUN[lang]["game"]
    return i18n.NOUN[lang].get(item["kind"].lower(), i18n.NOUN[lang]["app"])


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
    """The checkout, or, while no trial edition is on the store yet, the page
    saying the first are coming (the terms and refunds stay up beside it)."""
    u = data["unlock"]
    if not u["faces"]:
        main = template(site, "unlock_soon").substitute(days=int(u["days"]))
        return page(site, None, "Unlock a trial · Glean",
                    "Glean's faces are getting free trial editions; their unlock codes will be sold here.",
                    "unlock/", data["faces"][0]["hero"]["file"], main, "", legal_line(data), data=data)
    options ="\n".join(
        '<option value="%s" data-price="%s">%s · %s</option>'
        % (esc(f["slug"]), esc(f["price"]), esc(f["name"]), esc(usd(f["usd"])))
        for f in u["faces"])
    prices = "\n".join("<li>%s: %s</li>" % (esc(f["name"]), esc(usd(f["usd"]))) for f in u["faces"])
    main = template(site, "unlock").substitute(
        env=esc(u["env"]), token=esc(u["token"]), server=esc(u["server"]),
        options=options, prices=prices, days=int(u["days"]))
    return page(site, None, "Unlock a trial · Glean",
                "Buy the code that unlocks a Glean face's free trial edition on your watch, for good.",
                "unlock/", data["faces"][0]["hero"]["file"], main, UNLOCK_JS, legal_line(data),
                data=data)


def legal_page(site, data, name, title, description):
    main = template(site, name).substitute(seller=esc(data["unlock"]["seller"]),
                                           days=int(data["unlock"]["days"]))
    return page(site, None, "%s · Glean" % title, description, name + "/",
                data["faces"][0]["hero"]["file"], main, "", legal_line(data), data=data)


def img(pic, alt, lazy, cls=None):
    return ('<img%s src="/%s" width="%d" height="%d" alt="%s"%s>'
            % (' class="%s"' % cls if cls else "", esc(pic["file"]), int(pic["w"]),
               int(pic["h"]), esc(alt), ' loading="lazy"' if lazy else ""))


def items(data, section, lang="en"):
    """A section's records, newest first, in `lang`: an English record with
    its name, subtitle and description in that language, and only those the
    language has; faces.json may leave apps and games out."""
    records = data.get(section, [])
    if lang == "en":
        return records
    words = data["tr"].get(lang, {})
    return [dict(r, name=words[r["slug"]]["name"], subtitle=words[r["slug"]]["subtitle"],
                 full=words[r["slug"]]["full"]) for r in records if r["slug"] in words]


def label(section, item, lang="en"):
    """The line by an item's name: a face's category; an app's or game's
    kind and category, "Data field · Outdoor"."""
    if section == "faces":
        return i18n.word(lang, item["category"])
    return "%s · %s" % (i18n.word(lang, item["kind"]), i18n.word(lang, item["category"]))


def card(section, item, lazy, lang="en"):
    shot = item["images"][0]
    if lang == "en":
        alt, pitch = shot["alt"], item["pitch"]
    else:  # the ad copy's line is English; the listing's subtitle is translated
        alt, pitch = "%s – %s" % (item["name"], noun(lang, section, item)), item["subtitle"]
    return ('<li class="card"><a href="/%s%s/%s/">%s<span class="cat">%s</span>'
            '<span class="name">%s</span><span class="pitch">%s</span></a></li>'
            % (pre(lang), section, esc(item["slug"]), img(shot, alt, lazy),
               esc(label(section, item, lang)), esc(item["name"]), esc(pitch)))


def grid(section, records, eager=EAGER, lang="en"):
    """The cards of `records`, the first `eager` of them loading at once."""
    return ('<ul class="grid" role="list">\n%s\n</ul>'
            % "\n".join(card(section, r, i >= eager, lang) for i, r in enumerate(records)))


def soon(section):
    """What a section with nothing in it says. It names nothing."""
    return "The first Glean %s are on their way." % section


def categories(data):
    """[(slug, English name)] of the face categories with a page of their
    own, the most faces first."""
    count = {}
    for f in data["faces"]:
        count[f["category"]] = count.get(f["category"], 0) + 1
    names = sorted((c for c, n in count.items() if n >= CATEGORY_MIN and cat_slug(c)),
                   key=lambda c: (-count[c], c))
    return [(cat_slug(c), c) for c in names]


def cat_slug(name):
    """'Analog' -> 'analog'; None for a name that makes no safe folder."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s if SLUG.fullmatch(s) else None


def cat_path(lang, slug):
    return "%sfaces/%s/" % (pre(lang), slug)


def cat_nav(data, lang, current=None):
    """The links to every category page, by style."""
    cats = [(s, c) for s, c in categories(data) if cat_records(data, c, lang)]
    if not cats:
        return ""
    links = "\n".join('  <a href="/%s"%s>%s</a>'
                      % (cat_path(lang, s), ' aria-current="page"' if s == current else "",
                         esc(i18n.word(lang, c))) for s, c in cats)
    return '<nav class="cats" aria-label="%s">\n%s\n</nav>' % (esc(i18n.t(lang, "by_style")), links)


def cat_records(data, name, lang):
    return [f for f in items(data, "faces", lang) if f["category"] == name]


def section_langs(data, section):
    """{code: path} of a section's tab in every language that has it."""
    out = {"en": TAB[section]}
    for lang in i18n.CODES[1:]:
        if items(data, section, lang):
            out[lang] = pre(lang) + TAB[section]
    return out


def section_page(site, data, section, lang="en"):
    """A section's tab: every card in it, or the page saying its first are
    on the way. The faces' tab is the home page."""
    records = items(data, section, lang)
    words = {"n": len(records), "lines": lines_named(data)}
    key = "home" if section == "faces" else section
    heading = i18n.t(lang, key + "_h1")
    line = i18n.t(lang, "home_line", **words) if section == "faces" else ""
    title = i18n.t(lang, key + "_title")
    description = i18n.t(lang, key + "_desc", **words)
    head = ""
    if section == "faces" and lang == "en":
        head = "\n".join(['<meta name="%s" content="%s">' % (esc(k), esc(v))
                          for k, v in sorted(VERIFY.items()) if v]
                         + [jsonld([dict(ORG, logo=BASE + "apple-touch-icon.png", sameAs=list(SAME_AS)),
                                    {"@type": "WebSite", "@id": BASE + "#website", "name": "Glean",
                                     "url": BASE, "publisher": {"@id": BASE + "#org"}}])])
    if records:
        main = template(site, "section").substitute(
            heading=esc(heading), line=("<p>%s</p>" % esc(line)) if line else "",
            cats=cat_nav(data, lang) if section == "faces" else "",
            grid=grid(section, records, lang=lang))
    else:
        description = "Glean's first %s for Garmin watches are on their way." % section
        main = template(site, "soon").substitute(heading=esc(heading), soon=soon(section))
    return page(site, section, title, description, pre(lang) + TAB[section],
                data["faces"][0]["hero"]["file"], main, legal=legal_line(data), head=head,
                lang=lang, alternates=section_langs(data, section), tabs=tab_hrefs(data, lang),
                data=data)


def cat_langs(data, slug, name):
    return {lang: cat_path(lang, slug) for lang in i18n.CODES if cat_records(data, name, lang)}


def category_page(site, data, slug, name, lang="en"):
    """A category's faces: the grid of one style, with the others a click away."""
    records = cat_records(data, name, lang)
    cat = i18n.word(lang, name)
    words = {"n": len(records), "lines": lines_named(data), "cat": cat, "lcat": cat.lower()}
    heading, line = i18n.t(lang, "cat_h1", **words), i18n.t(lang, "cat_line", **words)
    title = i18n.t(lang, "cat_title", **words)
    description = line if lang == "en" else "%s: %s. %s" % (i18n.t(lang, "faces"), cat, line)
    path = cat_path(lang, slug)
    crumbs = jsonld([{"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": i18n.t(lang, "faces"), "item": BASE + pre(lang)},
        {"@type": "ListItem", "position": 2, "name": cat, "item": BASE + path}]}])
    main = template(site, "section").substitute(
        heading=esc(heading), line="<p>%s</p>" % esc(line), cats=cat_nav(data, lang, slug),
        grid=grid("faces", records, lang=lang))
    return page(site, "faces", title, description, path, records[0]["hero"]["file"], main,
                legal=legal_line(data), head=crumbs, lang=lang, alternates=cat_langs(data, slug, name),
                tabs=tab_hrefs(data, lang), data=data)


def watch_count(lines):
    return sum(len(line["names"]) for line in lines)


def works_on(n, lang="en"):
    return i18n.t(lang, "works_on_1") if n == 1 else i18n.t(lang, "works_on", n=n)


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


def works(section, item, data, lang="en"):
    """Where an item runs. A face runs on every watch in the help's list
    unless it carries its own, as an app or game always does: those are
    listed in place."""
    if "watches" not in item:
        return ('<p class="works"><a href="/help/#watches">%s</a></p>'
                % esc(works_on(watch_count(data["watches"]), lang)))
    # Its own h2, so the product lines' h3s sit under it, not under Settings.
    return ('<h2>%s</h2>\n  <details class="works"><summary>%s</summary>\n'
            '<div class="watches">\n%s\n</div></details>'
            % (esc(i18n.t(lang, "watches")), esc(works_on(watch_count(item["watches"]), lang)),
               watches_html(item["watches"])))


def related(data, section, item, k=RELATED, lang="en"):
    """Up to `k` other items of the section, its own category first, then
    the newest: the links on from an item page, so every page is reached
    from more than its list."""
    others = [r for r in items(data, section, lang) if r["slug"] != item["slug"]]
    same = [r for r in others if r["category"] == item["category"]]
    return (same + [r for r in others if r not in same])[:k]


def item_head(section, item, path, lang="en", description=None):
    """An item's structured data: what it is, and where it sits in the site."""
    url = BASE + path
    app = {"@type": "SoftwareApplication", "@id": url + "#app", "name": item["name"],
           "description": description or item["short"], "url": url,
           "image": [BASE + s["file"] for s in item["images"]],
           "applicationCategory": "GameApplication" if section == "games" else "LifestyleApplication",
           "applicationSubCategory": label(section, item, lang),
           "operatingSystem": "Garmin Connect IQ", "installUrl": item["store_url"], "publisher": ORG}
    if lang != "en":
        app["inLanguage"] = lang
    if item["subtitle"]:
        app["alternateName"] = full_title(item)
    section_name = section.capitalize() if lang == "en" else i18n.t(lang, section)
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": section_name,
         "item": BASE + pre(lang) + TAB[section]},
        {"@type": "ListItem", "position": 2, "name": item["name"], "item": url}]}
    return jsonld([app, crumbs])


def more_html(data, section, item, lang="en"):
    """The cards of a few other items, or nothing when the section has one."""
    others = related(data, section, item, lang=lang)
    if not others:
        return ""
    return ('<section class="more">\n<h2>%s</h2>\n%s\n</section>'
            % (esc(i18n.t(lang, "more_" + section)), grid(section, others, eager=0, lang=lang)))


def item_langs(data, section, item):
    return {lang: "%s%s/%s/" % (pre(lang), section, item["slug"]) for lang in i18n.CODES
            if lang == "en" or item["slug"] in data["tr"].get(lang, {})}


def cut(text, n=DESCRIPTION_MAX):
    """`text` at most `n` characters, cut at a word with an ellipsis."""
    if len(text) <= n:
        return text
    return text[:n - 1].rsplit(" ", 1)[0].rstrip(",;:–-") + "…"


def unlock_button(data, section, item, lang="en"):
    """Beside the store's button, a face whose trial edition sells its
    unlock code through Paddle links the unlock page, that face chosen."""
    sold = [f["slug"] for f in (data.get("unlock") or {}).get("faces") or []]
    if section != "faces" or item["slug"] not in sold:
        return ""
    return ('\n    <a class="store alt" href="/unlock/?face=%s">%s</a>'
            % (esc(item["slug"]), esc(i18n.t(lang, "unlock"))))


def item_page(site, data, section, item, lang="en"):
    shots, n = item["images"], len(item["images"])
    what = noun(lang, section, item)
    cats = dict((c, s) for s, c in categories(data))
    if lang == "en":
        def cap(i, s):
            return caption(s)

        def alt(i, s):
            """'Gren watch face: the three themes', for image search as much
            as for a screen reader."""
            c = caption(s)
            return "%s %s: %s" % (item["name"], what.replace("Garmin ", "", 1), c[:1].lower() + c[1:])
        short, full = item["short"], item["full"]
    else:  # the captions are English only: a picture is named by its number
        def cap(i, s):
            return i18n.t(lang, "picture", i=i + 1)

        def alt(i, s):
            return "%s – %s (%d/%d)" % (item["name"], what, i + 1, n)
        short, full = item["full"][0], item["full"][1:]
    # Each slide opens its picture full size; each thumbnail is a link to its
    # slide, so the gallery still works where gallery.js does not run. One
    # picture has nothing to move between, so no thumbnails.
    slides = "\n".join(
        '<li class="slide" id="shot-%d" aria-roledescription="slide" aria-label="%d%s%d" '
        'data-caption="%s"><a href="/%s">%s</a></li>'
        % (i + 1, i + 1, " of " if lang == "en" else " / ", n, esc(cap(i, s)), esc(s["file"]),
           img(s, alt(i, s), i > 0))
        for i, s in enumerate(shots))
    thumbs = "\n".join(
        '<li><a class="thumb" href="#shot-%d" aria-label="%s">%s</a></li>'
        % (i + 1, esc("%s: %s" % (i18n.t(lang, "picture", i=i + 1), cap(i, s)) if lang == "en"
                      else cap(i, s)), img(s, "", False)) for i, s in enumerate(shots))
    lab = esc(label(section, item, lang))
    if section == "faces" and item["category"] in cats and cat_records(data, item["category"], lang):
        lab = '<a href="/%s">%s</a>' % (cat_path(lang, cats[item["category"]]), lab)
    main = template(site, "item").substitute(
        section_href="/" + pre(lang) + TAB[section], all=esc(i18n.t(lang, "all_" + section)),
        name=esc(item["name"]), label=lab,
        subtitle=('<p class="sub">%s</p>' % esc(item["subtitle"])) if item["subtitle"] else "",
        store=esc(i18n.t(lang, "store")),
        store_url=esc(item["store_url"]), unlock=unlock_button(data, section, item, lang),
        icon=img(item["icon"], "", False, "icon"),
        pictures_of=esc(i18n.t(lang, "pictures_of", name=item["name"])),
        prev=esc(i18n.t(lang, "prev")), next=esc(i18n.t(lang, "next")),
        slides=slides, count=n, caption=esc(cap(0, shots[0])),
        thumbs=('  <ol class="thumbs" role="list">\n%s\n  </ol>' % thumbs) if n > 1 else "",
        short=esc(short), full="\n".join("<p>%s</p>" % esc(p) for p in full),
        # The settings' names and values are English only, so a translated
        # page leaves them to its description, which names them in its words.
        settings=settings_html(item) if lang == "en" else "",
        works=works(section, item, data, lang),
        more=more_html(data, section, item, lang))
    path = "%s%s/%s/" % (pre(lang), section, item["slug"])
    description = item["short"] if lang == "en" else cut(short)
    # "Gren – Fractal Tree, Ember Light · Garmin watch face · Glean": the
    # words a search matches come before the brand, which matches nothing.
    return page(site, section, "%s · %s · Glean" % (full_title(item), what), description,
                path, item["hero"]["file"], main, GALLERY_JS, legal_line(data),
                item_head(section, item, path, lang, description), lang=lang,
                alternates=item_langs(data, section, item), tabs=tab_hrefs(data, lang), data=data)


def watches_html(lines):
    return "\n".join("<section><h3>%s</h3><ul>%s</ul></section>"
                     % (esc(line["line"]), "".join("<li>%s</li>" % esc(n) for n in line["names"]))
                     for line in lines)


def help_page(site, data):
    main = template(site, "help").substitute(watches=watches_html(data["watches"]),
                                             watch_count=watch_count(data["watches"]))
    return page(site, "help", "Help · Glean",
                "Installing a Glean watch face, changing its settings, and the watches it runs on.",
                "help/", data["faces"][0]["hero"]["file"], main, legal=legal_line(data), data=data)


def privacy_page(site, data):
    return page(site, "privacy", "Privacy · Glean",
                "What Glean's faces, apps and this site do with your data: nothing leaves your watch but a rounded place for the stargazing forecast, and a trial edition's watch ID.",
                "privacy/", data["faces"][0]["hero"]["file"], template(site, "privacy").substitute(), "",
                legal_line(data), data=data)


def not_found(site, data):
    return page(site, None, "Not found · Glean", "This page does not exist.", "404.html",
                data["faces"][0]["hero"]["file"], template(site, "404").substitute(), "", legal_line(data),
                '<meta name="robots" content="noindex">', data=data)


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
    its page), or a category's; a translation in a language the site has no
    words for, or of an item it does not list; a live app or game the
    privacy page says nothing about, since an app can do what no face does."""
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
        if not isinstance(u.get("faces"), list):
            raise SystemExit("build: unlock.faces is not a list")
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
    for slug, name in categories(data):
        if slug in seen:
            raise SystemExit("build: the category %s and a face share the folder %r" % (name, slug))
    for lang, words in data["tr"].items():
        if lang not in i18n.CODES[1:]:
            raise SystemExit("build: data/tr/%s.json is in a language i18n.py has no words for" % lang)
        for slug, w in words.items():
            if slug not in seen:
                raise SystemExit("build: data/tr/%s.json translates %r, which the site does not list"
                                 % (lang, slug))
            if not w["full"]:
                raise SystemExit("build: data/tr/%s.json has no description for %s" % (lang, slug))
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
    cats = categories(data)
    for lang in i18n.CODES:
        if lang != "en" and (site / lang).exists():
            shutil.rmtree(site / lang)  # a language's folder is the build's alone
        for section in SECTIONS:
            records = items(data, section, lang)
            if lang == "en":
                keep = {r["slug"] for r in records} | ({s for s, _ in cats} if section == "faces" else set())
                _prune(site / section, keep)
            elif not records:
                continue
            _write(site / pre(lang) / TAB[section] / "index.html", section_page(site, data, section, lang))
            paths.append(pre(lang) + TAB[section])
            for r in records:
                p = "%s%s/%s/" % (pre(lang), section, r["slug"])
                _write(site / p / "index.html", item_page(site, data, section, r, lang))
                paths.append(p)
                if lang == "en":
                    images[p] = [s["file"] for s in r["images"]]
        for slug, name in cats:
            if cat_records(data, name, lang):
                p = cat_path(lang, slug)
                _write(site / p / "index.html", category_page(site, data, slug, name, lang))
                paths.append(p)
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
