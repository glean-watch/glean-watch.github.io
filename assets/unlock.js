// The unlock page: checks a watch ID with the key server, opens Paddle's
// checkout for that face and watch, and shows the code once the sale is in.
// Its settings are the form's data- attributes, written by build.py.
(function () {
  "use strict";
  var form = document.getElementById("unlock");
  if (!form) return;
  var server = form.getAttribute("data-server");
  var token = form.getAttribute("data-token");
  var env = form.getAttribute("data-env");
  var face = document.getElementById("unlock-face");
  var watch = document.getElementById("unlock-watch");
  var go = document.getElementById("unlock-go");
  var status = document.getElementById("unlock-status");
  var box = document.getElementById("unlock-code");
  var theCode = document.getElementById("unlock-the-code");
  var ID = /^[0-9A-HJKMNP-TV-Z]{8}$/;

  // A face's page links here as /unlock/?face=<slug>: that face is chosen.
  var asked = (/[?&]face=([a-z0-9-]+)/.exec(location.search) || [])[1];
  if (asked) {
    for (var i = 0; i < face.options.length; i++) {
      if (face.options[i].value === asked) { face.selectedIndex = i; break; }
    }
  }
  var confirmed = ""; // a face|watch the buyer says is right though the server never saw it
  var ready = false;

  // As the watch reads what people type: capitals, no spaces or dashes,
  // I and L as 1, O as 0.
  function normalize(s) {
    return String(s || "").toUpperCase().replace(/[^A-Z0-9]/g, "")
      .replace(/[IL]/g, "1").replace(/O/g, "0");
  }
  function pretty(s) { return s.slice(0, 4) + "-" + s.slice(4); }
  function say(text) { status.textContent = text; }
  function busy(on) { go.disabled = on; }

  function showCode(c) {
    theCode.textContent = c;
    box.hidden = false;
    say("");
  }

  function ask(slug, id) {
    var url = server + "/watch?f=" + encodeURIComponent(slug) + "&w=" + encodeURIComponent(id);
    return fetch(url, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("server " + r.status);
      return r.json();
    });
  }

  if (window.Paddle) {
    try {
      if (env === "sandbox") window.Paddle.Environment.set("sandbox");
      window.Paddle.Initialize({ token: token, eventCallback: onPaddle });
      ready = true;
    } catch (e) { ready = false; }
  }

  var pending = null; // {slug, id} of the open checkout
  function onPaddle(ev) {
    if (!ev || ev.name !== "checkout.completed" || !pending) return;
    var p = pending;
    pending = null;
    try { window.Paddle.Checkout.close(); } catch (e) { /* already closed */ }
    say("Payment received. Fetching your code…");
    var tries = 0;
    (function poll() {
      ask(p.slug, p.id).then(function (w) {
        if (w.code) { showCode(w.code); busy(false); return; }
        if (++tries < 30) { setTimeout(poll, 2000); return; }
        say("Your payment went through, but the code is not ready yet. Type the watch ID again in a few minutes to see it.");
        busy(false);
      }, function () {
        if (++tries < 30) { setTimeout(poll, 2000); return; }
        say("Your payment went through, but this page could not reach the server. Type the watch ID again later to see your code.");
        busy(false);
      });
    })();
  }

  function checkout(slug, id) {
    var opt = face.options[face.selectedIndex];
    if (!ready) {
      say("The checkout could not load. Check that nothing blocks cdn.paddle.com, then reload the page.");
      busy(false);
      return;
    }
    pending = { slug: slug, id: id };
    say("");
    window.Paddle.Checkout.open({
      items: [{ priceId: opt.getAttribute("data-price"), quantity: 1 }],
      customData: { face: slug, watch: id },
      settings: { displayMode: "overlay", allowLogout: true }
    });
    busy(false);
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    box.hidden = true;
    var slug = face.value;
    var id = normalize(watch.value);
    if (!ID.test(id)) {
      say("A watch ID is eight letters and digits, like K7Q2-9MXA. Check it against the face's settings.");
      watch.focus();
      return;
    }
    watch.value = pretty(id);
    busy(true);
    say("Checking the watch ID…");
    ask(slug, id).then(function (w) {
      if (w.code) {
        say("");
        showCode(w.code);
        busy(false);
        return;
      }
      if (!w.seen && confirmed !== slug + "|" + id) {
        confirmed = slug + "|" + id;
        say("This watch has not checked in with us yet. Compare the ID with the one under Watch ID in the face's settings, and let the watch sync with your phone. If the ID is right, press the button again to pay.");
        busy(false);
        return;
      }
      checkout(slug, id);
    }, function () {
      say("The unlock server could not be reached. Try again in a minute.");
      busy(false);
    });
  });
})();
