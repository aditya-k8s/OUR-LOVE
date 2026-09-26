/* Our Love - public site interactions. No dependencies. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, value);
    } catch (e) { return null; }
    return value;
  }

  /* ------------------------------------------------------------ reveal on scroll */
  function initReveal() {
    var items = $$(".reveal, .future-item, .timeline-item");
    items.forEach(function (el) {
      if (el.dataset.delay) el.style.setProperty("--delay", el.dataset.delay + "s");
    });
    if (reduceMotion || !("IntersectionObserver" in window)) {
      items.forEach(function (el) { el.classList.add("is-visible"); });
      return;
    }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    // Stagger siblings that enter together.
    items.forEach(function (el) {
      var parent = el.parentElement;
      if (!el.dataset.delay && parent) {
        var siblings = Array.prototype.filter.call(parent.children, function (c) { return c.classList.contains("reveal"); });
        var index = siblings.indexOf(el);
        if (index > 0 && siblings.length > 1) el.style.setProperty("--delay", Math.min(index * 0.08, 0.5) + "s");
      }
      observer.observe(el);
    });
  }

  /* ------------------------------------------------------------ header + parallax */
  function initScroll() {
    var header = $("[data-header]");
    var parallax = $("[data-parallax]");
    var ticking = false;
    function update() {
      var y = window.scrollY || window.pageYOffset;
      if (header) header.classList.toggle("is-scrolled", y > 40);
      if (parallax && !reduceMotion && y < window.innerHeight * 1.2) {
        parallax.style.transform = "translate3d(0," + (y * 0.25).toFixed(1) + "px,0)";
        parallax.style.opacity = String(Math.max(0.15, 1 - y / (window.innerHeight * 1.1)));
      }
      ticking = false;
    }
    window.addEventListener("scroll", function () {
      if (!ticking) { window.requestAnimationFrame(update); ticking = true; }
    }, { passive: true });
    update();
  }

  /* ------------------------------------------------------------ floating dust */
  function initParticles() {
    var canvas = $("[data-particles]");
    if (!canvas || reduceMotion || !canvas.getContext) return;
    var ctx = canvas.getContext("2d");
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var motes = [];
    var running = true;
    function resize() {
      canvas.width = canvas.offsetWidth * dpr;
      canvas.height = canvas.offsetHeight * dpr;
      var count = Math.round(Math.min(60, canvas.offsetWidth / 22));
      motes = [];
      for (var i = 0; i < count; i++) {
        motes.push({
          x: Math.random() * canvas.width, y: Math.random() * canvas.height,
          r: (Math.random() * 1.4 + 0.4) * dpr, vy: -(Math.random() * 0.18 + 0.04) * dpr,
          vx: (Math.random() - 0.5) * 0.08 * dpr, a: Math.random() * 0.5 + 0.15, t: Math.random() * Math.PI * 2
        });
      }
    }
    function frame() {
      if (!running) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (var i = 0; i < motes.length; i++) {
        var m = motes[i];
        m.t += 0.01; m.x += m.vx + Math.sin(m.t) * 0.05; m.y += m.vy;
        if (m.y < -10) { m.y = canvas.height + 10; m.x = Math.random() * canvas.width; }
        ctx.beginPath();
        ctx.fillStyle = "rgba(245,230,210," + (m.a * (0.6 + 0.4 * Math.sin(m.t * 2))).toFixed(3) + ")";
        ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
        ctx.fill();
      }
      window.requestAnimationFrame(frame);
    }
    resize();
    window.addEventListener("resize", resize);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        var visible = entries[0].isIntersecting;
        if (visible && !running) { running = true; frame(); } else if (!visible) { running = false; }
      }).observe(canvas);
    }
    frame();
  }

  /* ------------------------------------------------------------ counters + progress */
  function initCounters() {
    $$("[data-progress]").forEach(function (bar) {
      requestAnimationFrame(function () { bar.style.setProperty("--value", (parseInt(bar.dataset.progress, 10) || 0) + "%"); });
    });
    if (reduceMotion || !("IntersectionObserver" in window)) return;
    var counters = $$("[data-count]");
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        observer.unobserve(el);
        var target = parseInt(el.dataset.count, 10) || 0;
        if (target < 2) return;
        var start = performance.now();
        var duration = 1600;
        function step(now) {
          var p = Math.min(1, (now - start) / duration);
          var eased = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(target * eased).toLocaleString("en-GB");
          if (p < 1) requestAnimationFrame(step);
        }
        el.textContent = "0";
        requestAnimationFrame(step);
      });
    }, { threshold: 0.4 });
    counters.forEach(function (el) { observer.observe(el); });
  }

  /* ------------------------------------------------------------ theme */
  function initTheme() {
    $$("[data-theme-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var root = document.documentElement;
        var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
        root.setAttribute("data-theme", next);
        store("ourlove-theme", next);
      });
    });
  }

  /* ------------------------------------------------------------ music (never autoplays) */
  function initMusic() {
    var audio = $("[data-music]");
    var btn = $("[data-music-toggle]");
    if (!audio || !btn) return;
    audio.volume = 0.6;
    btn.addEventListener("click", function () {
      if (audio.paused) {
        audio.play().then(function () { btn.setAttribute("aria-pressed", "true"); }).catch(function () {
          btn.setAttribute("aria-pressed", "false");
        });
      } else {
        audio.pause();
        btn.setAttribute("aria-pressed", "false");
      }
    });
  }

  /* ------------------------------------------------------------ lightbox */
  function initLightbox() {
    var box = $("[data-lightbox]");
    if (!box) return;
    var img = $("[data-lb-img]", box);
    var caption = $("[data-lb-caption]", box);
    var meta = $("[data-lb-meta]", box);
    var counter = $("[data-lb-counter]", box);
    var items = [];
    var index = 0;
    var lastFocus = null;

    function show(i) {
      if (!items.length) return;
      index = (i + items.length) % items.length;
      var item = items[index];
      img.classList.add("is-loading");
      img.onload = function () { img.classList.remove("is-loading"); };
      img.src = item.dataset.src;
      img.alt = item.dataset.caption || "Photo";
      caption.textContent = item.dataset.caption || "";
      meta.textContent = item.dataset.meta || "";
      counter.textContent = (index + 1) + " / " + items.length;
      var next = items[(index + 1) % items.length];
      if (next) { var pre = new Image(); pre.src = next.dataset.src; }
    }
    function open(group, i) {
      items = $$("[data-lb-item]", group);
      lastFocus = document.activeElement;
      box.hidden = false;
      box.classList.add("is-open");
      document.body.style.overflow = "hidden";
      show(i);
      $("[data-lb-close]", box).focus();
    }
    function close() {
      box.classList.remove("is-open");
      box.hidden = true;
      document.body.style.overflow = "";
      img.removeAttribute("src");
      if (lastFocus) lastFocus.focus();
    }
    document.addEventListener("click", function (e) {
      var item = e.target.closest("[data-lb-item]");
      if (!item) return;
      var group = item.closest("[data-lb-group]") || document;
      open(group, $$("[data-lb-item]", group).indexOf(item));
    });
    $("[data-lb-close]", box).addEventListener("click", close);
    $("[data-lb-prev]", box).addEventListener("click", function () { show(index - 1); });
    $("[data-lb-next]", box).addEventListener("click", function () { show(index + 1); });
    box.addEventListener("click", function (e) { if (e.target === box) close(); });
    document.addEventListener("keydown", function (e) {
      if (!box.classList.contains("is-open")) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") show(index + 1);
      else if (e.key === "ArrowLeft") show(index - 1);
      else if (e.key === "Tab") {
        var focusables = $$("button", box);
        var first = focusables[0], last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
    var startX = null, startY = null;
    box.addEventListener("touchstart", function (e) { startX = e.touches[0].clientX; startY = e.touches[0].clientY; }, { passive: true });
    box.addEventListener("touchend", function (e) {
      if (startX === null) return;
      var dx = e.changedTouches[0].clientX - startX;
      var dy = e.changedTouches[0].clientY - startY;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) show(index + (dx < 0 ? 1 : -1));
      else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) close();
      startX = startY = null;
    });
  }

  /* ------------------------------------------------------------ easter egg */
  function initSecret() {
    var trigger = $("[data-secret-trigger]");
    var overlay = $("[data-secret]");
    if (!trigger || !overlay || document.body.dataset.easter !== "on") return;
    var clicks = 0, timer = null;
    trigger.addEventListener("click", function () {
      clicks += 1;
      clearTimeout(timer);
      timer = setTimeout(function () { clicks = 0; }, 1600);
      if (clicks < 5) return;
      clicks = 0;
      $("[data-secret-text]", overlay).textContent = document.body.dataset.easterMessage || "You found a little secret.";
      overlay.classList.add("is-open");
      $("[data-secret-close]", overlay).focus();
      if (!reduceMotion) floatHearts(trigger);
    });
    function hide() { overlay.classList.remove("is-open"); trigger.focus(); }
    $("[data-secret-close]", overlay).addEventListener("click", hide);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && overlay.classList.contains("is-open")) hide(); });
  }

  function floatHearts(source) {
    var svg = source.querySelector("svg");
    if (!svg) return;
    for (var i = 0; i < 14; i++) {
      (function (i) {
        setTimeout(function () {
          var heart = svg.cloneNode(true);
          heart.classList.add("float-heart");
          heart.style.left = (10 + Math.random() * 80) + "vw";
          heart.style.top = (60 + Math.random() * 30) + "vh";
          heart.style.animationDuration = (2.6 + Math.random() * 1.6) + "s";
          document.body.appendChild(heart);
          setTimeout(function () { heart.remove(); }, 4500);
        }, i * 120);
      })(i);
    }
  }

  /* ------------------------------------------------------------ filters */
  function initFilters() {
    $$("[data-filters-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var form = btn.closest("form");
        var open = form.classList.toggle("is-open");
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      });
    });
    $$("form[data-autosubmit] select").forEach(function (select) {
      select.addEventListener("change", function () {
        if (window.matchMedia("(min-width: 700px)").matches) select.form.submit();
      });
    });
  }

  /* ------------------------------------------------------------ toasts */
  function initToasts() {
    var stack = $("[data-toasts]");
    if (stack) setTimeout(function () { stack.remove(); }, 6000);
  }

  /* ------------------------------------------------------------ PWA install + service worker */
  function initPWA() {
    var deferred = null;
    var buttons = $$("[data-install]");
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferred = e;
      buttons.forEach(function (b) { b.hidden = false; });
    });
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!deferred) return;
        deferred.prompt();
        deferred.userChoice.finally(function () {
          deferred = null;
          buttons.forEach(function (b) { b.hidden = true; });
        });
      });
    });
    window.addEventListener("appinstalled", function () { buttons.forEach(function (b) { b.hidden = true; }); });

    var standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
    var ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    var hint = $("[data-ios-hint]");
    if (hint && ios && !standalone) hint.hidden = false;

    if ("serviceWorker" in navigator && document.body.dataset.sw) {
      window.addEventListener("load", function () {
        navigator.serviceWorker.register(document.body.dataset.sw, { scope: "/" }).catch(function () { /* offline support is optional */ });
      });
    }
    $$("form[data-logout]").forEach(function (form) {
      form.addEventListener("submit", function () {
        if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage("clear-pages");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initReveal();
    initScroll();
    initParticles();
    initCounters();
    initTheme();
    initMusic();
    initLightbox();
    initSecret();
    initFilters();
    initToasts();
    initPWA();
  });
})();
