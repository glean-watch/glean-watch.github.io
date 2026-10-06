// The face page's picture gallery: arrows, a counter, the caption and the
// thumbnails, over a strip of slides that already swipes and snaps without
// this script. Nothing plays by itself; reduced motion scrolls instantly.
(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.querySelectorAll(".gallery").forEach(function (g) {
    var track = g.querySelector(".slides");
    var slides = g.querySelectorAll(".slide");
    var thumbs = g.querySelectorAll(".thumb");
    var prev = g.querySelector(".prev");
    var next = g.querySelector(".next");
    var count = g.querySelector(".count");
    var caption = g.querySelector(".caption");
    var cur = -1;
    var target = null;  // where a button or thumbnail is scrolling to
    var settle = 0;

    function show(i) {
      if (i === cur) {
        return;
      }
      cur = i;
      thumbs.forEach(function (t, j) {
        if (j === i) {
          t.setAttribute("aria-current", "true");
        } else {
          t.removeAttribute("aria-current");
        }
      });
      count.textContent = (i + 1) + " / " + slides.length;
      caption.textContent = slides[i].dataset.caption;
      prev.disabled = i === 0;
      next.disabled = i === slides.length - 1;
    }

    function inView() {
      return Math.round(track.scrollLeft / track.clientWidth);
    }

    function go(i) {
      i = Math.max(0, Math.min(slides.length - 1, i));
      target = reduce ? null : i;
      track.scrollTo({ left: i * track.clientWidth, behavior: reduce ? "auto" : "smooth" });
      show(i);
    }

    // Every slide is the track's full width, so the slide in view is the
    // scroll offset in widths; a swipe lands here as well as the buttons.
    // While a button's smooth scroll passes the slides between, the counter
    // and caption stay on its destination; once scrolling settles they
    // follow wherever the strip really stopped, should a swipe cut in.
    track.addEventListener("scroll", function () {
      clearTimeout(settle);
      settle = setTimeout(function () {
        target = null;
        show(inView());
      }, 150);
      if (target === null || inView() === target) {
        target = null;
        show(inView());
      }
    }, { passive: true });
    prev.addEventListener("click", function () { go(cur - 1); });
    next.addEventListener("click", function () { go(cur + 1); });
    thumbs.forEach(function (t, j) {
      t.addEventListener("click", function (e) {
        e.preventDefault();  // no jump down the page to the slide's anchor
        go(j);
      });
    });
    g.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        go(cur - 1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        go(cur + 1);
      }
    });
    window.addEventListener("resize", function () {
      track.scrollLeft = cur * track.clientWidth;
    });

    prev.hidden = false;
    next.hidden = false;
    count.hidden = false;
    show(inView());
  });
})();
