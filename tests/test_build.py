"""build.py: every page is written, linked, escaped and the same twice."""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
import build  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixture" / "faces.json"
# Pages a later task adds; until then the nav may point at them.
LATER = ()
GALLERY_TAG = '<script src="/assets/gallery.js" defer></script>'
# The site's icon, written beside the pages by the export.
ICON_FILES = ("favicon.ico", "apple-touch-icon.png")


def make_site(data=None):
    """The site's templates and assets with the fixture data, and empty
    stand-ins for its images, in a temporary folder."""
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(SITE / "templates", tmp / "templates")
    shutil.copytree(SITE / "assets", tmp / "assets")
    data = data or json.loads(FIXTURE.read_text(encoding="utf-8"))
    (tmp / "data").mkdir()
    (tmp / "data" / "faces.json").write_text(json.dumps(data, ensure_ascii=False),
                                             encoding="utf-8")
    for f in data["faces"] + data.get("apps", []) + data.get("games", []):
        for pic in f["images"] + [f["icon"], f["hero"]]:
            p = tmp / pic["file"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"")
    for name in ICON_FILES:
        (tmp / name).write_bytes(b"")
    return tmp, data


def pages(site):
    return {p.relative_to(site).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(site.rglob("*.html")) if "templates" not in p.parts}


def resolve(site, url):
    path = url.split("#")[0]
    if path.endswith("/"):
        path += "index.html"
    return site / path.lstrip("/")


def fake_item(slug, name, kind, category, pictures, settings, watches, n):
    """An app or game in the shape the export will write."""
    return {"slug": slug, "name": name, "subtitle": "", "category": category,
            "pitch": "%s in one line." % name, "short": "What %s does." % name,
            "full": ["First paragraph."], "settings": settings,
            "store_url": "https://apps.garmin.com/apps/00000000-0000-4000-8000-00000000010%d" % n,
            "images": [{"file": "img/%s/0%d_shot.jpg" % (slug, i), "alt": "%s: picture %d" % (name, i),
                        "w": 720, "h": 720} for i in range(1, pictures + 1)],
            "icon": {"file": "img/%s/icon_500.jpg" % slug, "w": 500, "h": 500},
            "hero": {"file": "img/%s/hero_1440x720.jpg" % slug, "w": 1440, "h": 720},
            "kind": kind, "watches": watches}


def with_apps():
    """The fixture, plus one app and one game. Their names are invented:
    this file is published, and no real project may be named here before
    the store shows it."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["apps"] = [fake_item("waymark", "Waymark", "Data field", "Outdoor", 1, [],
                              [{"line": "fēnix", "names": ["fēnix® 6 Pro"]},
                               {"line": "Venu", "names": ["Venu® 2S"]}], 1)]
    data["games"] = [fake_item("tile-hop", "Tile Hop", "App", "Games", 3,
                               [{"name": "Speed", "values": "Slow, Fast"}],
                               [{"line": "Venu", "names": ["Venu® 2S"]}], 2)]
    return data


def add_privacy(site, *ids):
    """The privacy page with a section per id, as an app's release adds."""
    p = site / "templates" / "privacy.html"
    p.write_text(p.read_text(encoding="utf-8")
                 + "".join('<section id="%s"></section>\n' % i for i in ids), encoding="utf-8")


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.site, self.data = make_site()
        self.paths = build.build(self.site)
        self.pages = pages(self.site)

    def test_every_page_is_written(self):
        for p in ("index.html", "apps/index.html", "games/index.html",
                  "faces/stjarna/index.html", "faces/lykt/index.html"):
            self.assertIn(p, self.pages)
        self.assertNotIn("faces/index.html", self.pages)  # the faces' tab is the home page

    def test_internal_links_resolve(self):
        for name, text in self.pages.items():
            for url in re.findall(r'(?:href|src)="(/[^"]*)"', text):
                if url.split("#")[0] in LATER:
                    continue
                self.assertTrue(resolve(self.site, url).exists(), (name, url))

    def test_text_is_escaped(self):
        lykt = self.pages["faces/lykt/index.html"]
        for name, text in self.pages.items():
            # The gallery's own file is the one script; nothing inline.
            self.assertNotIn("<script", text.replace(GALLERY_TAG, ""), name)
        self.assertIn("Lykt &lt;script&gt;alert(1)&lt;/script&gt;", lykt)
        self.assertIn('content="A &quot;carved&quot; pumpkin &amp; a candle."', lykt)
        self.assertIn("Jack-o&#x27;-Lantern", lykt)
        self.assertIn("Five pumpkins &amp; a candle.", lykt)

    def test_open_graph_and_canonical(self):
        for name, text in self.pages.items():
            for prop in ("og:title", "og:description", "og:image", "og:url"):
                self.assertIn('property="%s"' % prop, text, name)
            self.assertRegex(text, r'<link rel="canonical" href="%s' % re.escape(build.BASE))
            self.assertRegex(text, r'property="og:image" content="%simg/' % re.escape(build.BASE))
        self.assertIn('content="%sfaces/lykt/"' % build.BASE, self.pages["faces/lykt/index.html"])

    def test_every_page_carries_the_icon(self):
        for name, text in self.pages.items():
            self.assertIn('<link rel="icon" href="/favicon.ico">', text, name)
            self.assertIn('<link rel="apple-touch-icon" href="/apple-touch-icon.png">', text, name)

    def test_the_face_page(self):
        lykt = self.pages["faces/lykt/index.html"]
        self.assertIn('href="https://apps.garmin.com/apps/00000000-0000-4000-8000-000000000002"', lykt)
        self.assertEqual(lykt.count('<a href="/img/lykt/0'), 5)  # each slide opens full size
        self.assertIn("<th scope=\"row\">Candle follows</th>", lykt)
        self.assertIn("Works on 3 watches", lykt)

    def test_the_home_page(self):
        home = self.pages["index.html"]
        self.assertIn("<title>Glean · Watch faces, apps and games for Garmin watches</title>", home)
        self.assertIn("<h1>Watch faces worth a second look.</h1>", home)
        self.assertIn("<p>All faces are free on the Connect IQ Store.</p>", home)
        self.assertLess(home.index("/faces/stjarna/"), home.index("/faces/lykt/"))
        self.assertIn("Your sign, written in real stars.", home)
        self.assertEqual(home.count('<li class="card">'), 2)  # every face

    def test_coming_soon_names_nothing(self):
        for section in ("apps", "games"):
            p = self.pages["%s/index.html" % section]
            self.assertIn("<title>%s · Glean</title>" % section.capitalize(), p)
            self.assertIn("<h1>%s</h1>" % section.capitalize(), p)
            self.assertIn("<p>The first Glean %s are on their way.</p>" % section, p)
            self.assertIn("to hear when they land.", p)
            self.assertIn('<a href="/">see the faces</a>', p)
            self.assertNotIn('class="card"', p)

    def test_the_breadcrumb_and_404_lead_to_the_faces(self):
        self.assertIn('<nav class="crumb" aria-label="Breadcrumb"><a href="/">Faces</a> ›',
                      self.pages["faces/lykt/index.html"])
        self.assertIn('<a href="/">See every face</a>', self.pages["404.html"])

    def test_non_ascii_survives(self):
        self.assertIn('<meta charset="utf-8">', self.pages["faces/stjarna/index.html"])
        self.assertIn("<h1>Stjärna</h1>", self.pages["faces/stjarna/index.html"])

    def test_the_same_twice(self):
        before = {p: p.read_bytes() for p in self.site.rglob("*") if p.is_file()}
        build.build(self.site)
        after = {p: p.read_bytes() for p in self.site.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_a_removed_face_loses_its_page(self):
        data = dict(self.data, faces=self.data["faces"][:1])
        (self.site / "data" / "faces.json").write_text(json.dumps(data, ensure_ascii=False),
                                                       encoding="utf-8")
        build.build(self.site)
        self.assertFalse((self.site / "faces" / "lykt").exists())

    def test_the_gallery(self):
        lykt = self.pages["faces/lykt/index.html"]
        self.assertIn('<section class="gallery" aria-roledescription="carousel"', lykt)
        slides = re.findall(r'<li class="slide" id="(shot-\d)"', lykt)
        self.assertEqual(slides, ["shot-1", "shot-2", "shot-3", "shot-4", "shot-5"])
        thumbs = re.findall(r'<a class="thumb" href="#(shot-\d)"', lykt)
        self.assertEqual(thumbs, slides)  # every thumbnail points at a slide that exists
        self.assertIn('aria-label="2 of 5"', lykt)

    def test_the_gallery_works_without_the_script(self):
        # The arrows and the counter mean nothing until gallery.js runs.
        lykt = self.pages["faces/lykt/index.html"]
        self.assertIn('<button class="arrow prev" type="button" aria-label="Previous picture" hidden>', lykt)
        self.assertIn('<button class="arrow next" type="button" aria-label="Next picture" hidden>', lykt)
        self.assertIn('<span class="count" hidden>1 / 5</span>', lykt)

    def test_the_caption_is_the_listing_caption(self):
        lykt = self.pages["faces/lykt/index.html"]
        self.assertIn('<p class="caption" aria-live="polite">The face on the watch</p>', lykt)
        self.assertIn('data-caption="The five pumpkins"', lykt)

    def test_the_script_loads_on_item_pages_only(self):
        for name, text in self.pages.items():
            item = bool(re.fullmatch(r"(faces|apps|games)/[^/]+/index\.html", name))
            self.assertEqual(GALLERY_TAG in text, item, name)

    def test_help_privacy_and_404_are_written(self):
        for p in ("help/index.html", "privacy/index.html", "404.html"):
            self.assertIn(p, self.pages)

    def test_help_lists_every_watch(self):
        help_ = self.pages["help/index.html"]
        for line in self.data["watches"]:
            self.assertIn("<h3>%s</h3>" % line["line"], help_)
            for n in line["names"]:
                self.assertIn("<li>%s</li>" % n, help_)
        self.assertIn('id="watches"', help_)
        self.assertIn("The 3 watches", help_)

    def test_the_tabs(self):
        want = [("/", "Faces"), ("/apps/", "Apps"), ("/games/", "Games")]
        for name, text in self.pages.items():
            tabs = re.search(r'<nav class="tabs" aria-label="Sections">(.*?)</nav>', text, re.S)
            self.assertTrue(tabs, name)
            self.assertEqual(re.findall(r'<a href="(/\w*/?)"[^>]*>(\w+)</a>', tabs.group(1)), want,
                             name)

    def test_the_header_keeps_help_and_privacy(self):
        for name, text in self.pages.items():
            nav = re.search(r'<nav aria-label="Main">(.*?)</nav>', text, re.S).group(1)
            self.assertEqual(re.findall(r'<a href="(/\w+/)"[^>]*>(\w+)</a>', nav),
                             [("/help/", "Help"), ("/privacy/", "Privacy")], name)

    def test_the_nav_marks_the_current_page(self):
        def tabs(name):
            return re.search(r'<nav class="tabs"[^>]*>(.*?)</nav>', self.pages[name], re.S).group(1)
        self.assertIn('<a href="/" aria-current="page">Faces</a>', tabs("index.html"))
        self.assertIn('<a href="/" aria-current="page">Faces</a>', tabs("faces/lykt/index.html"))
        self.assertIn('<a href="/apps/" aria-current="page">Apps</a>', tabs("apps/index.html"))
        self.assertIn('<a href="/games/" aria-current="page">Games</a>', tabs("games/index.html"))
        for name in ("help/index.html", "privacy/index.html", "404.html"):
            self.assertNotIn("aria-current", tabs(name), name)
        self.assertIn('href="/help/" aria-current="page"', self.pages["help/index.html"])
        self.assertIn('href="/privacy/" aria-current="page"', self.pages["privacy/index.html"])
        self.assertNotIn('aria-current="page"', self.pages["404.html"])

    def test_the_nav_carries_ko_fi(self):
        # An icon alone, so the link's name is its label; the drawing is hidden.
        for name, text in self.pages.items():
            nav = re.search(r'<nav aria-label="Main">(.*?)</nav>', text, re.S).group(1)
            self.assertRegex(nav, r'<a class="kofi" href="https://ko-fi\.com/glean" '
                                  r'aria-label="[^"]+"', name)
            self.assertIn('<svg viewBox="0 0 24 24" aria-hidden="true"', nav, name)

    def test_the_sitemap(self):
        xml = (self.site / "sitemap.xml").read_text(encoding="utf-8")
        for p in ("", "apps/", "games/", "faces/stjarna/", "faces/lykt/", "help/", "privacy/"):
            self.assertIn("<loc>%s%s</loc>" % (build.BASE, p), xml)
        self.assertNotIn("faces/</loc>", xml)
        self.assertNotIn("404", xml)

    def test_robots_points_at_the_sitemap(self):
        self.assertEqual((self.site / "robots.txt").read_text(encoding="utf-8"),
                         "User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % build.BASE)

    def test_a_removed_face_leaves_the_sitemap(self):
        data = dict(self.data, faces=self.data["faces"][:1])
        (self.site / "data" / "faces.json").write_text(json.dumps(data, ensure_ascii=False),
                                                       encoding="utf-8")
        build.build(self.site)
        self.assertNotIn("faces/lykt/", (self.site / "sitemap.xml").read_text(encoding="utf-8"))

    def test_an_unsafe_slug_is_refused(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["faces"][0]["slug"] = "../x"
        site, _ = make_site(data)
        with self.assertRaises(SystemExit):
            build.build(site)


class AppsTest(unittest.TestCase):
    def setUp(self):
        self.site, self.data = make_site(with_apps())
        add_privacy(self.site, "waymark", "tile-hop")
        self.paths = build.build(self.site)
        self.pages = pages(self.site)

    def rebuild(self, data, *ids):
        site, _ = make_site(data)
        add_privacy(site, *ids)
        build.build(site)
        return site

    def test_their_pages_are_written(self):
        for p in ("apps/index.html", "apps/waymark/index.html", "games/index.html",
                  "games/tile-hop/index.html"):
            self.assertIn(p, self.pages)

    def test_internal_links_resolve(self):
        for name, text in self.pages.items():
            for url in re.findall(r'(?:href|src)="(/[^"]*)"', text):
                self.assertTrue(resolve(self.site, url).exists(), (name, url))

    def test_the_home_page_is_the_faces_tab(self):
        home = self.pages["index.html"]
        self.assertNotIn('href="/apps/waymark/"', home)
        self.assertNotIn('href="/games/tile-hop/"', home)
        self.assertNotIn("on their way", home)

    def test_the_apps_grid_survives_a_rebuild(self):
        # apps/ holds the tab's index.html beside the app folders; the
        # pruning of apps that left must not take the file with it.
        build.build(self.site)
        self.assertTrue((self.site / "apps" / "index.html").is_file())
        self.assertTrue((self.site / "apps" / "waymark" / "index.html").is_file())

    def test_the_section_grids(self):
        apps = self.pages["apps/index.html"]
        self.assertIn("<h1>Apps</h1>", apps)
        self.assertIn('<li class="card"><a href="/apps/waymark/">', apps)
        self.assertNotIn("on their way", apps)
        self.assertIn('<li class="card"><a href="/games/tile-hop/">', self.pages["games/index.html"])

    def test_the_card_names_the_kind(self):
        self.assertIn('<span class="cat">Data field · Outdoor</span>', self.pages["apps/index.html"])
        self.assertIn('<span class="cat">Stylish</span>', self.pages["index.html"])

    def test_the_app_page(self):
        p = self.pages["apps/waymark/index.html"]
        self.assertIn('<nav class="crumb" aria-label="Breadcrumb"><a href="/apps/">Apps</a> › '
                      '<span aria-current="page">Waymark</span></nav>', p)
        self.assertIn('<p class="cat">Data field · Outdoor</p>', p)
        self.assertIn('href="https://apps.garmin.com/apps/00000000-0000-4000-8000-000000000101"', p)
        self.assertNotIn("<h2>Settings</h2>", p)
        self.assertIn("<summary>Works on 2 watches</summary>", p)
        for n in ("fēnix® 6 Pro", "Venu® 2S"):
            self.assertIn("<li>%s</li>" % n, p)
        self.assertNotIn("<li>fēnix® 7</li>", p)  # the app's own watches, not the site's
        self.assertIn('href="/apps/" aria-current="page"', p)
        self.assertIn(GALLERY_TAG, p)
        self.assertIn("<title>Waymark · Glean</title>", p)

    def test_one_picture_has_no_controls(self):
        p = self.pages["apps/waymark/index.html"]
        self.assertEqual(len(re.findall(r'<li class="slide"', p)), 1)
        self.assertNotIn('class="thumbs"', p)
        self.assertIn('<button class="arrow prev" type="button" aria-label="Previous picture" hidden>', p)
        # ...and gallery.js leaves them hidden for a single picture.
        js = (SITE / "assets" / "gallery.js").read_text(encoding="utf-8")
        self.assertRegex(js, r"if \(slides\.length < 2\) \{\s*return;")

    def test_the_game_page(self):
        p = self.pages["games/tile-hop/index.html"]
        self.assertIn('<a href="/games/">Games</a> › <span aria-current="page">Tile Hop</span>', p)
        self.assertIn('<p class="cat">App · Games</p>', p)
        self.assertIn('<th scope="row">Speed</th>', p)
        self.assertIn("<summary>Works on 1 watch</summary>", p)
        self.assertEqual(re.findall(r'<a class="thumb" href="#(shot-\d)"', p),
                         ["shot-1", "shot-2", "shot-3"])

    def test_the_face_page_keeps_its_shape(self):
        lykt = self.pages["faces/lykt/index.html"]
        self.assertIn('<p class="cat">Fun</p>', lykt)
        self.assertIn('<p class="works"><a href="/help/#watches">Works on 3 watches</a></p>', lykt)
        self.assertIn("<h2>Settings</h2>", lykt)

    def test_the_sitemap_lists_them(self):
        xml = (self.site / "sitemap.xml").read_text(encoding="utf-8")
        for p in ("apps/waymark/", "games/tile-hop/"):
            self.assertIn("<loc>%s%s</loc>" % (build.BASE, p), xml)

    def test_the_same_twice(self):
        before = {p: p.read_bytes() for p in self.site.rglob("*") if p.is_file()}
        build.build(self.site)
        after = {p: p.read_bytes() for p in self.site.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_a_removed_app_loses_its_page(self):
        data = dict(self.data, apps=[])
        (self.site / "data" / "faces.json").write_text(json.dumps(data, ensure_ascii=False),
                                                       encoding="utf-8")
        build.build(self.site)
        self.assertFalse((self.site / "apps" / "waymark").exists())
        self.assertIn("The first Glean apps are on their way.",
                      (self.site / "apps" / "index.html").read_text(encoding="utf-8"))

    def test_one_section_live_the_other_coming_soon(self):
        data = with_apps()
        data["games"] = []
        site = self.rebuild(data, "waymark")
        self.assertIn('<li class="card"><a href="/apps/waymark/">',
                      (site / "apps" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("<p>The first Glean games are on their way.</p>",
                      (site / "games" / "index.html").read_text(encoding="utf-8"))

    def test_an_app_without_a_privacy_section_is_refused(self):
        with self.assertRaises(SystemExit) as e:
            self.rebuild(with_apps(), "tile-hop")
        self.assertIn("Waymark", str(e.exception))

    def test_a_privacy_id_must_be_the_items_own(self):
        for near_miss in ('<p data-id="waymark"></p>', '<p id="waymark-old"></p>'):
            site, _ = make_site(with_apps())
            add_privacy(site, "tile-hop")
            p = site / "templates" / "privacy.html"
            p.write_text(p.read_text(encoding="utf-8") + near_miss, encoding="utf-8")
            with self.assertRaises(SystemExit, msg=near_miss):
                build.build(site)

    def test_headings_step_down_one_level_at_a_time(self):
        # The watch list's product lines are h3s: they need an h2 of their
        # own, not the Settings one, nor none at all.
        for name in ("apps/waymark/index.html", "games/tile-hop/index.html"):
            levels = [int(h) for h in re.findall(r"<h([1-6])[ >]", self.pages[name])]
            for a, b in zip(levels, levels[1:]):
                self.assertLessEqual(b, a + 1, (name, levels))
            self.assertIn("<h2>Watches</h2>", self.pages[name])

    def test_a_commented_out_privacy_section_does_not_count(self):
        site, _ = make_site(with_apps())
        add_privacy(site, "tile-hop")
        p = site / "templates" / "privacy.html"
        p.write_text(p.read_text(encoding="utf-8") + '<!-- <section id="waymark"></section> -->',
                     encoding="utf-8")
        with self.assertRaises(SystemExit) as e:
            build.build(site)
        self.assertIn("Waymark", str(e.exception))

    def test_a_slug_used_twice_is_refused(self):
        data = with_apps()
        data["games"][0]["slug"] = "lykt"  # a face's slug: both would own img/lykt/
        with self.assertRaises(SystemExit):
            self.rebuild(data, "waymark", "lykt")

    def test_an_unsafe_slug_is_refused(self):
        for bad in ("Way_mark", "-waymark", "way--mark", "../x"):
            data = with_apps()
            data["apps"][0]["slug"] = bad
            with self.assertRaises(SystemExit, msg=bad):
                self.rebuild(data, bad, "tile-hop")


def luminance(hex_):
    c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class PaletteTest(unittest.TestCase):
    def test_text_meets_aa(self):
        css = (SITE / "assets" / "site.css").read_text(encoding="utf-8")
        t = dict(re.findall(r"--(\w+):\s*(#[0-9a-f]{6})", css))
        pairs = [("ink", "paper"), ("body", "paper"), ("muted", "paper"), ("ink", "card"),
                 ("body", "card"), ("muted", "card"), ("paper", "ink")]
        for fg, bg in pairs:
            self.assertGreaterEqual(contrast(t[fg], t[bg]), 4.5, (fg, bg))


if __name__ == "__main__":
    unittest.main()
