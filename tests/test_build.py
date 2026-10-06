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
    for f in data["faces"]:
        for pic in f["images"] + [f["icon"], f["hero"]]:
            p = tmp / pic["file"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"")
    return tmp, data


def pages(site):
    return {p.relative_to(site).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(site.rglob("*.html")) if "templates" not in p.parts}


def resolve(site, url):
    path = url.split("#")[0]
    if path.endswith("/"):
        path += "index.html"
    return site / path.lstrip("/")


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.site, self.data = make_site()
        self.paths = build.build(self.site)
        self.pages = pages(self.site)

    def test_every_page_is_written(self):
        for p in ("index.html", "faces/stjarna/index.html", "faces/lykt/index.html"):
            self.assertIn(p, self.pages)

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

    def test_the_face_page(self):
        lykt = self.pages["faces/lykt/index.html"]
        self.assertIn('href="https://apps.garmin.com/apps/00000000-0000-4000-8000-000000000002"', lykt)
        self.assertEqual(lykt.count('<a href="/img/lykt/0'), 5)  # each slide opens full size
        self.assertIn("<th scope=\"row\">Candle follows</th>", lykt)
        self.assertIn("Works on 3 watches", lykt)

    def test_the_home_page(self):
        home = self.pages["index.html"]
        self.assertLess(home.index("/faces/stjarna/"), home.index("/faces/lykt/"))
        self.assertIn("Your sign, written in real stars.", home)
        self.assertIn("All faces are free on the Connect IQ Store.", home)

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

    def test_the_script_loads_on_face_pages_only(self):
        for name, text in self.pages.items():
            self.assertEqual(GALLERY_TAG in text, name.startswith("faces/"), name)

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

    def test_the_nav_marks_the_current_page(self):
        self.assertIn('href="/help/" aria-current="page"', self.pages["help/index.html"])
        self.assertIn('href="/privacy/" aria-current="page"', self.pages["privacy/index.html"])
        self.assertNotIn('aria-current="page">Faces', self.pages["404.html"])

    def test_the_sitemap(self):
        xml = (self.site / "sitemap.xml").read_text(encoding="utf-8")
        for p in ("", "faces/stjarna/", "faces/lykt/", "help/", "privacy/"):
            self.assertIn("<loc>%s%s</loc>" % (build.BASE, p), xml)
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
