// Purser landing page: the heading tape, scroll reveals and the instrument
// readouts. The page is complete without this file; it only adds motion.

(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- heading tape ----------
  // A compass tape, 10 px per degree, drawn twice over (0-720) so it can wrap.
  // Scrolling the page turns the heading from 360 through to 060; the pointer
  // stays on the page's centre line.
  const PX_PER_DEG = 10;
  const tapes = document.querySelectorAll("[data-tape]");

  function tapeSvg(bright) {
    const width = 720 * PX_PER_DEG;
    let ticks = "";
    let labels = "";
    for (let deg = 0; deg < 720; deg += 5) {
      const x = deg * PX_PER_DEG;
      const major = deg % 10 === 0;
      ticks += `M${x} 40V${major ? 30 : 34}`;
      if (major) {
        const n = String(((deg % 360) / 10) || 36).padStart(2, "0");
        labels += `<text x="${x}" y="20">${n}</text>`;
      }
    }
    const tick = bright ? "#c9d1e3" : "#3a4a78";
    const text = bright ? "#f6efe3" : "#5d6b8f";
    return `<svg width="${width}" height="56" viewBox="0 0 ${width} 56" fill="none">` +
      `<path d="${ticks}" stroke="${tick}" stroke-width="1"/>` +
      `<g font-family="IBM Plex Mono, ui-monospace, monospace" font-size="12" fill="${text}" text-anchor="middle">${labels}</g></svg>`;
  }

  tapes.forEach((el) => { el.innerHTML = tapeSvg(el.classList.contains("tape-bright")); });

  const nav = document.querySelector(".nav");
  let ticking = false;
  function setHeading() {
    ticking = false;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const progress = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
    const heading = 360 + 60 * progress;
    const centre = tapes[0] ? tapes[0].parentElement.clientWidth / 2 : 0;
    const x = centre - heading * PX_PER_DEG;
    tapes.forEach((el) => { el.style.transform = `translate3d(${x}px,0,0)`; });
    if (nav) nav.classList.toggle("stuck", window.scrollY > 8);
  }
  function onScroll() {
    if (!ticking) { ticking = true; requestAnimationFrame(setHeading); }
  }
  setHeading();
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);

  // ---------- quote: wrap each word so it can arrive on its own ----------
  document.querySelectorAll("[data-words]").forEach((el) => {
    const words = el.textContent.trim().split(/\s+/);
    el.setAttribute("aria-label", el.textContent.trim());
    el.innerHTML = words
      .map((w, i) => `<span class="w" aria-hidden="true" style="--w:${i}">${w}</span>`)
      .join(" ");
  });

  // ---------- instrument readouts count up with the arcs ----------
  function countUp(textEl) {
    const target = parseFloat(textEl.dataset.count);
    const decimals = parseInt(textEl.dataset.decimals || "0", 10);
    const suffix = textEl.dataset.suffix || "";
    const start = performance.now() + 300;
    const duration = 1600;
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    function frame(now) {
      const t = Math.min(1, Math.max(0, (now - start) / duration));
      textEl.textContent = (target * ease(t)).toFixed(decimals) + suffix;
      if (t < 1) requestAnimationFrame(frame);
    }
    textEl.textContent = (0).toFixed(decimals) + suffix;
    requestAnimationFrame(frame);
  }

  // ---------- architecture: once drawn, a pulse keeps flowing through it ----------
  // Two pulses leave the question together, take the two searches, meet at
  // rank fusion and part again for the app and Claude.
  function startPulses(flow) {
    flow.classList.add("pulsing");
    flow.querySelectorAll(".pulse animateMotion").forEach((m) => {
      try { m.beginElement(); } catch (_) { /* SMIL unsupported: pulses stay hidden */ }
    });
  }

  // ---------- reveal on scroll ----------
  const targets = document.querySelectorAll("[data-reveal], [data-words], [data-flow], [data-gauges], .footer");
  if (reduce || !("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const el = entry.target;
      el.classList.add("in");
      if (el.hasAttribute("data-gauges")) el.querySelectorAll("[data-count]").forEach(countUp);
      if (el.hasAttribute("data-flow")) setTimeout(() => startPulses(el), 2200);
      io.unobserve(el);
    });
  }, { threshold: 0.25, rootMargin: "0px 0px -8% 0px" });
  targets.forEach((el) => io.observe(el));
})();
