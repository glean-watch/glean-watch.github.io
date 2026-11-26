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
# The site's other scripts: the analytics beacon (a file of Cloudflare's) and
# structured data, which is JSON, not code.
BEACON = re.compile(r'<script type="module" src="https://static\.cloudflareinsights\.com/[^"]+"[^>]*></script>')
LDJSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def ld(text):
    """The structured data on a page, as JSON, or None."""
    m = LDJSON.search(text)
    return json.loads(m.group(1)) if m else None
# An item page's way back to its list: an arrow drawn inline, hidden from
# screen readers, so the link's name is "All faces".
BACK = (r'<a class="back" href="%s"><svg viewBox="0 0 24 24" aria-hidden="true" '
        r'focusable="false"><path [^>]+/></svg>All %s</a>')
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
            # The gallery's own file is the one script; nothing inline but
            # structured data, whose values cannot close its tag.
            for m in LDJSON.finditer(text):
                self.assertNotRegex(m.group(1), "[<>&]", name)
            rest = LDJSON.sub("", BEACON.sub("", text.replace(GALLERY_TAG, "")))
            self.assertNotIn("<script", rest, name)
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
        self.assertIn("<title>Garmin Watch Faces, Apps and Games · Glean</title>", home)
        self.assertIn("<h1>Watch faces worth a second look.</h1>", home)
        # The words a search matches: the count and the watches' lines.
        self.assertIn("<p>2 watch faces for Garmin fēnix, Venu and more, on the Connect IQ Store.</p>", home)
        self.assertIn('content="2 watch faces for Garmin fēnix, Venu and more:', home)
        graph = {n["@type"]: n for n in ld(home)["@graph"]}
        self.assertEqual(graph["WebSite"]["url"], build.BASE)
        self.assertIn("https://www.facebook.com/gleanwatchfaces", graph["Organization"]["sameAs"])
        # An ownership tag for each search engine whose value is filled in, no other.
        for k, v in build.VERIFY.items():
            (self.assertIn if v else self.assertNotIn)('<meta name="%s"' % k, home)
        self.assertLess(home.index("/faces/stjarna/"), home.index("/faces/lykt/"))
        self.assertIn("Your sign, written in real stars.", home)
        self.assertEqual(home.count('<li class="card">'), 2)  # every face

    def test_coming_soon_names_nothing(self):
        for section in ("apps", "games"):
            p = self.pages["%s/index.html" % section]
            self.assertIn("<title>%s</title>" % build.esc(build.i18n.t("en", section + "_title")), p)
            self.assertIn("<h1>%s</h1>" % section.capitalize(), p)
            self.assertIn("<p>The first Glean %s are on their way.</p>" % section, p)
            self.assertIn("to hear when they land.", p)
            self.assertIn('<a href="/">see the faces</a>', p)
            self.assertNotIn('class="card"', p)

    def test_the_back_button_and_404_lead_to_the_faces(self):
        lykt = self.pages["faces/lykt/index.html"]
        self.assertRegex(lykt, BACK % ("/", "faces"))
        self.assertNotIn('class="crumb"', lykt)  # the tabs say where you are
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
        # An item's pictures under its page, for image search.
        self.assertIn("<loc>%sfaces/lykt/</loc><image:image><image:loc>%simg/lykt/01_"
                      % (build.BASE, build.BASE), xml)

    def test_the_face_page_says_what_it_is(self):
        lykt = self.pages["faces/lykt/index.html"]
        self.assertRegex(lykt, r"<title>Lykt [^<]*· Garmin watch face · Glean</title>")
        self.assertIn(' watch face: the five pumpkins"', lykt)
        graph = ld(lykt)["@graph"]
        self.assertEqual(graph[0]["installUrl"],
                         "https://apps.garmin.com/apps/00000000-0000-4000-8000-000000000002")
        self.assertEqual([c["item"] for c in graph[1]["itemListElement"]],
                         [build.BASE, build.BASE + "faces/lykt/"])
        # On to the other faces, so no page is reached from the grid alone.
        self.assertIn('<h2>More faces</h2>', lykt)
        self.assertIn('href="/faces/stjarna/"', lykt.split('class="more"')[1])

    def test_the_404_is_not_indexed(self):
        self.assertIn('<meta name="robots" content="noindex">', self.pages["404.html"])
        self.assertNotIn('content="noindex"', self.pages["index.html"])

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
        self.assertRegex(p, BACK % ("/apps/", "apps"))
        self.assertIn('<p class="cat">Data field · Outdoor</p>', p)
        self.assertIn('href="https://apps.garmin.com/apps/00000000-0000-4000-8000-000000000101"', p)
        self.assertNotIn("<h2>Settings</h2>", p)
        self.assertIn("<summary>Works on 2 watches</summary>", p)
        for n in ("fēnix® 6 Pro", "Venu® 2S"):
            self.assertIn("<li>%s</li>" % n, p)
        self.assertNotIn("<li>fēnix® 7</li>", p)  # the app's own watches, not the site's
        self.assertIn('href="/apps/" aria-current="page"', p)
        self.assertIn(GALLERY_TAG, p)
        self.assertIn("<title>Waymark · Garmin data field · Glean</title>", p)
        self.assertIn('alt="Waymark data field: picture 1"', p)
        app = ld(p)["@graph"][0]
        self.assertEqual((app["@type"], app["applicationCategory"], app["operatingSystem"]),
                         ("SoftwareApplication", "LifestyleApplication", "Garmin Connect IQ"))
        self.assertNotIn('class="more"', p)  # the only app has nothing to point on to

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
        self.assertRegex(p, BACK % ("/games/", "games"))
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

    def test_a_face_with_fewer_watches_lists_its_own(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        lykt = next(f for f in data["faces"] if f["slug"] == "lykt")
        lykt["watches"] = [{"line": "Venu", "names": ["Venu® 2S"]}]
        site, _ = make_site(data)
        build.build(site)
        got = pages(site)
        p = got["faces/lykt/index.html"]
        self.assertIn("<summary>Works on 1 watch</summary>", p)
        self.assertIn("<li>Venu® 2S</li>", p)
        self.assertNotIn('href="/help/#watches"', p)
        self.assertIn('<p class="works"><a href="/help/#watches">Works on 3 watches</a></p>',
                      got["faces/stjarna/index.html"])

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


class UnlockTest(unittest.TestCase):
    """The unlock, terms and refund pages: built only while faces.json
    carries an "unlock" block, with Paddle's script on the unlock page only."""

    def unlock(self, data, **over):
        u = {"env": "sandbox", "token": "test_abc", "server": "https://keys.example.dev",
             "seller": "A. Seller", "days": 7,
             "faces": [{"slug": data["faces"][0]["slug"], "name": data["faces"][0]["name"],
                        "price": "pri_01abc", "usd": "2.00"}]}
        u.update(over)
        return dict(data, unlock=u)

    def test_no_unlock_block_no_sales_pages(self):
        site, _ = make_site()
        self.addCleanup(shutil.rmtree, site, ignore_errors=True)
        paths = build.build(site)
        for name in ("unlock/", "terms/", "refunds/"):
            self.assertNotIn(name, paths)
            self.assertFalse((site / name).exists())
        self.assertNotIn("/terms/", pages(site)["index.html"])

    def test_the_pages_and_their_links(self):
        site, data = make_site()
        self.addCleanup(shutil.rmtree, site, ignore_errors=True)
        (site / "data" / "faces.json").write_text(json.dumps(self.unlock(data)), encoding="utf-8")
        paths = build.build(site)
        for name in ("unlock/", "terms/", "refunds/"):
            self.assertIn(name, paths)
        got = pages(site)
        u = got["unlock/index.html"]
        self.assertIn('data-env="sandbox"', u)
        self.assertIn('data-token="test_abc"', u)
        self.assertIn('data-price="pri_01abc"', u)
        self.assertIn("US$2.00", u)
        self.assertIn(build.PADDLE_JS, u)
        self.assertIn("/assets/unlock.js", u)
        self.assertIn("A. Seller", got["terms/index.html"])
        self.assertIn("Merchant of Record", got["terms/index.html"])
        for path, text in got.items():
            self.assertIn('href="/terms/"', text, path)
            self.assertIn('href="/refunds/"', text, path)
            if path != "unlock/index.html":
                self.assertNotIn(build.PADDLE_JS, text, path)
        # Taken away again, the pages go.
        (site / "data" / "faces.json").write_text(json.dumps(data), encoding="utf-8")
        build.build(site)
        self.assertFalse((site / "unlock").exists())

    def test_no_trial_on_the_store_yet(self):
        site, data = make_site()
        self.addCleanup(shutil.rmtree, site, ignore_errors=True)
        (site / "data" / "faces.json").write_text(json.dumps(self.unlock(data, faces=[])), encoding="utf-8")
        paths = build.build(site)
        for name in ("unlock/", "terms/", "refunds/"):
            self.assertIn(name, paths)
        u = pages(site)["unlock/index.html"]
        self.assertIn("Coming soon", u)
        self.assertNotIn(build.PADDLE_JS, u)
        self.assertNotIn('id="unlock"', u)

    def test_a_sold_face_links_its_unlock_code(self):
        """A face whose code the unlock page sells has a second button beside
        the store's, in every language, naming that face; the rest do not."""
        site, data = make_site()
        self.addCleanup(shutil.rmtree, site, ignore_errors=True)
        sold, other = data["faces"][0]["slug"], data["faces"][1]["slug"]
        link = 'href="/unlock/?face=%s"' % sold
        build.build(site)
        self.assertNotIn(link, pages(site)["faces/%s/index.html" % sold])
        (site / "data" / "faces.json").write_text(json.dumps(self.unlock(data)), encoding="utf-8")
        build.build(site)
        got = pages(site)
        self.assertIn(link, got["faces/%s/index.html" % sold])
        self.assertIn("Buy an unlock code", got["faces/%s/index.html" % sold])
        self.assertNotIn("/unlock/?face=", got["faces/%s/index.html" % other])
        for path, text in got.items():
            if path.endswith("faces/%s/index.html" % sold) and path != "faces/%s/index.html" % sold:
                self.assertIn(link, text, path)

    def test_values_are_escaped(self):
        site, data = make_site()
        self.addCleanup(shutil.rmtree, site, ignore_errors=True)
        (site / "data" / "faces.json").write_text(
            json.dumps(self.unlock(data, seller='<b>"x"</b>', token='t"><script>')), encoding="utf-8")
        build.build(site)
        got = pages(site)
        self.assertNotIn("<b>", got["terms/index.html"])
        self.assertNotIn('"><script>', got["unlock/index.html"])

    def test_bad_unlock_data_is_refused(self):
        site, data = make_site()
        self.addCleanup(shutil.rmtree, site, ignore_errors=True)
        f0 = self.unlock(data)["unlock"]["faces"][0]
        for bad in ({"env": "test"}, {"seller": " "}, {"server": "http://x"}, {"faces": None},
                    {"faces": [dict(f0, slug="nope")]}, {"faces": [dict(f0, price="price_1")]},
                    {"faces": [dict(f0, usd="2")]}):
            (site / "data" / "faces.json").write_text(json.dumps(self.unlock(data, **bad)),
                                                      encoding="utf-8")
            with self.assertRaises(SystemExit, msg=bad):
                build.build(site)


# Lykt's German listing: a title, and a description whose first paragraph
# is the page's lead and description. Stjärna has none.
DE = {"lykt": {"name": "Lykt <b>", "subtitle": "Kürbislaterne",
               "full": ["Ein „geschnitzter“ Kürbis & eine Kerze.", "Zweiter Absatz."]}}


def with_german(site):
    (site / "data" / "tr").mkdir()
    (site / "data" / "tr" / "de.json").write_text(json.dumps(DE, ensure_ascii=False), encoding="utf-8")


class LanguagesTest(unittest.TestCase):
    """A translated listing gets its pages under /<code>/, each naming the
    other languages; what has no translation stays English only."""

    def setUp(self):
        self.site, self.data = make_site()
        with_german(self.site)
        self.paths = build.build(self.site)
        self.pages = pages(self.site)

    def test_the_translated_face_page(self):
        p = self.pages["de/faces/lykt/index.html"]
        self.assertIn('<html lang="de">', p)
        self.assertIn("<title>Lykt &lt;b&gt; – Kürbislaterne · Garmin-Zifferblatt · Glean</title>", p)
        self.assertIn('<p class="lead">Ein „geschnitzter“ Kürbis &amp; eine Kerze.</p>', p)
        self.assertIn('content="Ein „geschnitzter“ Kürbis &amp; eine Kerze."', p)
        self.assertIn("<p>Zweiter Absatz.</p>", p)
        self.assertIn("Im Connect IQ Store laden", p)
        self.assertIn("Läuft auf 3 Uhren", p)
        self.assertIn('href="/de/">', p)  # back to the German faces
        self.assertIn('<a href="/de/" aria-current="page">Zifferblätter</a>', p)
        # The settings' names are English only: the description names them.
        self.assertNotIn('class="settings"', p)
        self.assertNotIn("the five pumpkins", p)  # nor an English caption
        app = ld(p)["@graph"][0]
        self.assertEqual((app["name"], app["inLanguage"]), ("Lykt <b>", "de"))

    def test_every_language_of_a_page_is_named(self):
        for page_ in ("faces/lykt/index.html", "de/faces/lykt/index.html"):
            p = self.pages[page_]
            self.assertIn('<link rel="alternate" hreflang="en" href="%sfaces/lykt/">' % build.BASE, p)
            self.assertIn('<link rel="alternate" hreflang="de" href="%sde/faces/lykt/">' % build.BASE, p)
            self.assertIn('<link rel="alternate" hreflang="x-default" href="%sfaces/lykt/">'
                          % build.BASE, p)
            self.assertIn('<a href="/de/faces/lykt/" hreflang="de" lang="de"', p)
        # A face with no translation has one language, so it names none.
        self.assertNotIn('rel="alternate"', self.pages["faces/stjarna/index.html"])
        self.assertNotIn('class="langs"', self.pages["faces/stjarna/index.html"])
        self.assertNotIn("de/faces/stjarna/index.html", self.pages)

    def test_the_header_menu_offers_every_language(self):
        def menu(name):
            return re.search(r'<details class="lang">(.*?)</details>', self.pages[name], re.S).group(1)
        # The page in each language it has...
        self.assertIn('<a href="/de/faces/lykt/" hreflang="de" lang="de">Deutsch</a>',
                      menu("faces/lykt/index.html"))
        self.assertIn('<a href="/faces/lykt/" hreflang="en" lang="en">English</a>',
                      menu("de/faces/lykt/index.html"))
        self.assertIn('aria-current="true">Deutsch</a>', menu("de/faces/lykt/index.html"))
        self.assertIn('<summary aria-label="Sprache: Deutsch">', menu("de/faces/lykt/index.html"))
        # ...else the language's home page, as on help and an English-only face.
        for name in ("faces/stjarna/index.html", "help/index.html", "404.html"):
            self.assertIn('<a href="/de/" hreflang="de" lang="de">Deutsch</a>', menu(name), name)
        # Only the languages the site has: no French face, no French link.
        self.assertNotIn('hreflang="fr"', menu("index.html"))

    def test_one_language_has_no_menu(self):
        site, _ = make_site()
        build.build(site)
        self.assertNotIn('class="lang"', (site / "index.html").read_text(encoding="utf-8"))

    def test_the_translated_home_lists_what_it_has(self):
        home = self.pages["de/index.html"]
        self.assertIn("<h1>Zifferblätter, die einen zweiten Blick wert sind.</h1>", home)
        self.assertIn('href="/de/faces/lykt/"', home)
        self.assertNotIn("stjarna", home.split("<main")[1].split("</main>")[0])
        self.assertIn('<span class="cat">Lustig</span>', home)
        self.assertIn('<span class="pitch">Kürbislaterne</span>', home)
        self.assertIn('hreflang="de" href="%sde/">' % build.BASE, self.pages["index.html"])
        # No German apps or games, so no German tab for them.
        self.assertNotIn("de/apps/index.html", self.pages)

    def test_the_sitemap_lists_every_language(self):
        xml = (self.site / "sitemap.xml").read_text(encoding="utf-8")
        for p in ("de/", "de/faces/lykt/"):
            self.assertIn("<loc>%s%s</loc>" % (build.BASE, p), xml)

    def test_help_and_privacy_stay_english(self):
        self.assertNotIn("de/help/index.html", self.pages)
        self.assertIn('<a href="/help/">Hilfe</a>', self.pages["de/index.html"])

    def test_a_language_folder_is_the_builds(self):
        stray = self.site / "de" / "faces" / "gone" / "index.html"
        stray.parent.mkdir(parents=True)
        stray.write_text("x", encoding="utf-8")
        build.build(self.site)
        self.assertFalse(stray.exists())

    def test_a_translation_of_what_the_site_does_not_list_is_refused(self):
        (self.site / "data" / "tr" / "de.json").write_text(
            json.dumps({"kompis": DE["lykt"]}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            build.build(self.site)

    def test_a_language_without_words_is_refused(self):
        (self.site / "data" / "tr" / "xx.json").write_text(json.dumps(DE), encoding="utf-8")
        with self.assertRaises(SystemExit):
            build.build(self.site)

    def test_internal_links_resolve(self):
        for name, text in self.pages.items():
            for url in re.findall(r'(?:href|src)="(/[^"]*)"', text):
                self.assertTrue(resolve(self.site, url.split("#")[0]).exists(), (name, url))


class CategoryTest(unittest.TestCase):
    """A category with enough faces gets a page, in every language that
    has its faces, linked from the home page and from each of its faces."""

    def setUp(self):
        self.old, build.CATEGORY_MIN = build.CATEGORY_MIN, 1
        self.site, self.data = make_site()
        with_german(self.site)
        build.build(self.site)
        self.pages = pages(self.site)

    def tearDown(self):
        build.CATEGORY_MIN = self.old

    def test_the_category_page(self):
        p = self.pages["faces/fun/index.html"]
        self.assertIn("<title>Fun Garmin Watch Faces · Glean</title>", p)
        self.assertIn("<h1>Fun watch faces</h1>", p)
        self.assertIn("<p>1 fun watch faces for Garmin", p)
        self.assertIn('href="/faces/lykt/"', p)
        self.assertNotIn('href="/faces/stjarna/"', p.split('class="grid"')[1])
        self.assertIn('<a href="/faces/fun/" aria-current="page">Fun</a>', p)
        de = self.pages["de/faces/fun/index.html"]
        self.assertIn("<h1>Zifferblätter: Lustig</h1>", de)
        # Stylish has no German face, so no German page.
        self.assertNotIn("de/faces/stylish/index.html", self.pages)

    def test_the_home_page_and_the_face_link_it(self):
        self.assertIn('<a href="/faces/fun/">Fun</a>', self.pages["index.html"])
        self.assertIn('<p class="cat"><a href="/faces/fun/">Fun</a></p>',
                      self.pages["faces/lykt/index.html"])
        self.assertIn('<p class="cat"><a href="/de/faces/fun/">Lustig</a></p>',
                      self.pages["de/faces/lykt/index.html"])

    def test_a_thin_category_has_no_page(self):
        build.CATEGORY_MIN = 2
        build.build(self.site)
        self.assertFalse((self.site / "faces" / "fun").exists())
        self.assertNotIn("/faces/fun/", (self.site / "index.html").read_text(encoding="utf-8"))

    def test_a_category_cannot_take_a_faces_folder(self):
        data = json.loads((self.site / "data" / "faces.json").read_text(encoding="utf-8"))
        data["faces"][1]["category"] = "Stjarna"
        (self.site / "data" / "faces.json").write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(SystemExit):
            build.build(self.site)


class WordsTest(unittest.TestCase):
    """Every language has every word English has."""

    def test_every_key(self):
        for lang in build.i18n.CODES:
            self.assertEqual(set(build.i18n.T[lang]), set(build.i18n.T["en"]), lang)
            self.assertEqual(set(build.i18n.NOUN[lang]), set(build.i18n.NOUN["en"]), lang)
        for english, words in build.i18n.WORD.items():
            self.assertEqual(len(words), len(build.i18n.CODES) - 1, english)

    def test_the_languages_are_the_listings(self):
        # The store's listing languages, as the main repo's languages.py names them.
        self.assertEqual(build.i18n.CODES[1:], ("pl", "de", "fr", "es", "it", "nl", "pt", "sk", "cs"))


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
