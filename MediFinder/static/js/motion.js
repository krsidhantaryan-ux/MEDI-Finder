/* ==========================================================================
   MediFinder — Motion System
   Framer Motion (Motion.dev) + motion.site patterns
   - Editorial hero stagger
   - Scroll-triggered reveals
   - Spring physics for cards, buttons, modal, toast stack
   - Layout animations, hover/press gestures
   - Respects prefers-reduced-motion
   ========================================================================== */
(() => {
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  // Load motion from CDN ESM
  let motion = null;
  async function loadMotion() {
    if (motion) return motion;
    try {
      motion = await import("https://cdn.jsdelivr.net/npm/motion@12.23.12/+esm");
      return motion;
    } catch (e) {
      console.warn("Motion failed to load, fallback to CSS", e);
      return null;
    }
  }

  // Utility: spring config
  const springSoft = { type: "spring", stiffness: 320, damping: 28, mass: 0.8 };
  const springBouncy = { type: "spring", stiffness: 420, damping: 22, mass: 0.7 };
  const springSmooth = { type: "spring", stiffness: 260, damping: 30, mass: 1 };

  // 1. Hero editorial stagger — motion.site pattern
  async function heroStagger() {
    const m = await loadMotion();
    if (prefersReduced) {
      $$(".hero [data-motion]").forEach(el => el.classList.add("in"));
      return;
    }
    if (!m) {
      // CSS fallback
      setTimeout(() => {
        $$(".hero .motion-fade, .hero [data-stagger]").forEach((el, i) => {
          setTimeout(() => el.classList.add("in"), i * 80);
        });
      }, 50);
      return;
    }
    const { animate, stagger } = m;

    // Eyebrow + headline chars stagger
    const eyebrow = $(".hero .eyebrow");
    const h1 = $(".hero h1");
    const lead = $(".hero .hero-lead");
    const searchbar = $(".hero .searchbar");
    const chips = $(".hero .chips");
    const meta = $(".hero .hero-meta");
    const visual = $(".hero-visual");

    if (eyebrow) animate(eyebrow, { opacity: [0, 1], y: [10, 0] }, { duration: 0.5, easing: "ease-out" });
    if (h1) {
      // Split by words for stagger
      const words = h1.innerHTML.split(/(\s+|<br>)/);
      // simple fade up for whole h1 with child spans
      animate(h1, { opacity: [0, 1], y: [18, 0] }, { duration: 0.6, easing: [0.16, 1, 0.3, 1], delay: 0.08 });
    }
    if (lead) animate(lead, { opacity: [0, 1], y: [12, 0] }, { duration: 0.55, delay: 0.18, easing: "ease-out" });
    if (searchbar) animate(searchbar, { opacity: [0, 1], y: [14, 0], scale: [0.98, 1] }, { duration: 0.6, delay: 0.28, ...springSoft });
    if (chips) {
      const chipEls = $$(".chip", chips);
      if (chipEls.length) animate(chipEls, { opacity: [0, 1], y: [8, 0] }, { duration: 0.4, delay: stagger(0.04, { start: 0.38 }), easing: "ease-out" });
    }
    if (meta) animate(meta, { opacity: [0, 1] }, { duration: 0.5, delay: 0.5 });
    if (visual) animate(visual, { opacity: [0, 1], x: [18, 0], scale: [0.98, 1] }, { duration: 0.7, delay: 0.22, ...springSmooth });
  }

  // 2. Scroll reveals — inView pattern from motion.site
  async function scrollReveals() {
    const m = await loadMotion();
    const targets = $$("[data-reveal], .feature, .stat, .testimonial-card, .card[data-animate]");
    if (prefersReduced) {
      targets.forEach(el => el.classList.add("in"));
      return;
    }
    if (!m) {
      // IntersectionObserver fallback
      const io = new IntersectionObserver((entries) => {
        entries.forEach(e => { if (e.isIntersecting) e.target.classList.add("in"); });
      }, { threshold: 0.15 });
      targets.forEach(el => io.observe(el));
      return;
    }
    const { inView, animate } = m;
    targets.forEach((el) => {
      inView(el, () => {
        animate(el, { opacity: [0, 1], y: [16, 0] }, { duration: 0.55, easing: [0.16, 1, 0.3, 1] });
        // stagger children if .stagger
        const children = el.matches(".stagger, .feature-grid, .stat-row") ? Array.from(el.children) : null;
        if (children && children.length) {
          animate(children, { opacity: [0, 1], y: [12, 0] }, { duration: 0.45, delay: m.stagger(0.07), easing: "ease-out" });
        }
      }, { amount: 0.2, margin: "0px 0px -10% 0px" });
    });

    // Parallax for hero visual
    const heroVisual = $(".hero-visual img");
    if (heroVisual && !prefersReduced && m.scroll) {
      try {
        const { scroll, transform } = m;
        // subtle parallax on scroll
        scroll(transform(heroVisual, { y: [0, -40] }), { target: $(".hero"), offset: ["start start", "end start"] });
      } catch {}
    }
  }

  // 3. Card hover — native gestures, independent transforms
  async function cardGestures() {
    const m = await loadMotion();
    const cards = $$(".card-hover, .med-card, .dash-stat, .testimonial-card");
    if (prefersReduced) return;
    cards.forEach(card => {
      card.addEventListener("mouseenter", () => {
        if (m) {
          m.animate(card, { y: -2, scale: 1.01 }, { duration: 0.2, easing: "ease-out" });
        } else {
          card.style.transform = "translateY(-2px)";
        }
      });
      card.addEventListener("mouseleave", () => {
        if (m) {
          m.animate(card, { y: 0, scale: 1 }, { duration: 0.25, easing: "ease-out" });
        } else {
          card.style.transform = "";
        }
      });
      card.addEventListener("mousedown", () => {
        if (m) m.animate(card, { scale: 0.99 }, { duration: 0.1 });
      });
      card.addEventListener("mouseup", () => {
        if (m) m.animate(card, { scale: 1.01 }, { duration: 0.15, easing: [0.175, 0.885, 0.32, 1.275] });
      });
    });

    // Button press gesture
    $$(".btn").forEach(btn => {
      btn.addEventListener("pointerdown", () => {
        if (!prefersReduced && m) m.animate(btn, { scale: 0.97 }, { duration: 0.1 });
      });
      btn.addEventListener("pointerup", () => {
        if (!prefersReduced && m) m.animate(btn, { scale: 1 }, { duration: 0.22, ...springBouncy });
      });
      btn.addEventListener("pointerleave", () => {
        if (!prefersReduced && m) m.animate(btn, { scale: 1 }, { duration: 0.2 });
      });
    });
  }

  // 4. Search results — layout animation + AnimatePresence-like
  async function resultsMotion() {
    const m = await loadMotion();
    if (prefersReduced) return;
    // Hook into global render
    const origRender = window.MF_renderResults;
    // We will enhance render via event
    document.addEventListener("mf:results-rendered", async (e) => {
      const list = document.getElementById("resultsList");
      if (!list) return;
      const items = Array.from(list.children);
      if (!m || !items.length) return;
      const { animate, stagger } = m;
      // Stagger entrance
      animate(items, { opacity: [0, 1], y: [14, 0] }, { duration: 0.42, delay: stagger(0.05), easing: [0.16, 1, 0.3, 1] });
    });
  }

  // 5. Modal — scale+fade from trigger source (spatial continuity)
  async function modalMotion() {
    const m = await loadMotion();
    const modalBack = document.getElementById("reserveModal") || $(".modal-back");
    if (!modalBack) return;

    // Intercept open
    const observer = new MutationObserver(async (mutations) => {
      for (const mut of mutations) {
        if (mut.attributeName === "class") {
          const isOpen = modalBack.classList.contains("open");
          const modal = $(".modal", modalBack);
          if (!modal) continue;
          if (isOpen) {
            if (prefersReduced) {
              modal.style.opacity = "1"; modal.style.transform = "none";
            } else if (m) {
              m.animate(modalBack, { opacity: [0, 1] }, { duration: 0.22, easing: "ease-out" });
              m.animate(modal, { opacity: [0, 1], scale: [0.94, 1], y: [10, 0] }, { duration: 0.42, easing: [0.16, 1, 0.3, 1] });
            }
          } else {
            if (m && !prefersReduced) {
              await m.animate(modal, { opacity: [1, 0], scale: [1, 0.96], y: [0, 8] }, { duration: 0.22, easing: "ease-in" }).finished.catch(()=>{});
              m.animate(modalBack, { opacity: [1, 0] }, { duration: 0.18 });
            }
          }
        }
      }
    });
    observer.observe(modalBack, { attributes: true });

    // Also enhance MF.openReserve if present
    if (window.MF && window.MF.openReserve) {
      const orig = window.MF.openReserve;
      window.MF.openReserve = function(...args) {
        orig.apply(this, args);
        // focus management
        setTimeout(() => {
          const firstInput = modalBack.querySelector("input");
          firstInput?.focus();
        }, 100);
      };
    }
  }

  // 6. Toast stack — motion.site toast stack (fan into scaled pile)
  async function toastStackMotion() {
    const m = await loadMotion();
    const wrap = document.getElementById("toastWrap");
    if (!wrap) return;

    // Watch for new toasts
    const obs = new MutationObserver((mutations) => {
      mutations.forEach(mut => {
        mut.addedNodes.forEach(async (node) => {
          if (!(node instanceof HTMLElement) || !node.classList.contains("toast")) return;
          if (prefersReduced) return;
          if (!m) {
            node.style.animation = "toastIn .28s var(--ease-out)";
            return;
          }
          const { animate } = m;
          // Entrance spring
          animate(node, { opacity: [0, 1], x: [28, 0], scale: [0.96, 1] }, { duration: 0.42, easing: [0.16, 1, 0.3, 1] });

          // Stack effect: scale down older toasts slightly
          const siblings = Array.from(wrap.children).filter(c => c !== node);
          siblings.forEach((sib, i) => {
            const depth = siblings.length - i;
            animate(sib, { scale: 1 - depth * 0.04, y: depth * -2, opacity: 1 - depth * 0.08 }, { duration: 0.32, ...springSoft });
          });

          // Auto dismiss with exit
          setTimeout(async () => {
            if (!node.isConnected) return;
            if (m) {
              await animate(node, { opacity: [1, 0], x: [0, 24], scale: [1, 0.96] }, { duration: 0.28, easing: "ease-in" }).finished.catch(()=>{});
            }
            node.remove();
            // Restack
            Array.from(wrap.children).forEach((sib, i) => {
              if (m && !prefersReduced) {
                const depth = wrap.children.length - i - 1;
                animate(sib, { scale: 1 - depth * 0.03, y: 0, opacity: 1 }, { duration: 0.32, ...springSoft });
              }
            });
          }, 4200);
        });
      });
    });
    obs.observe(wrap, { childList: true });
  }

  // 7. Chip layout animation — when filter changes
  async function chipLayout() {
    const m = await loadMotion();
    if (prefersReduced) return;
    $$("#catChips, #trendingChips, .chips").forEach(container => {
      container.addEventListener("click", async (e) => {
        const chip = e.target.closest(".chip");
        if (!chip) return;
        if (!m) return;
        // Bounce active chip
        m.animate(chip, { scale: [1, 1.08, 1] }, { duration: 0.38, easing: [0.34, 1.56, 0.64, 1] });
        // Layout animation for siblings
        const siblings = Array.from(container.children).filter(c => c !== chip);
        m.animate(siblings, { scale: [1, 0.98, 1] }, { duration: 0.28, delay: m.stagger(0.02) });
      });
    });
  }

  // 8. Searchbar focus — scale + glow
  async function searchbarMotion() {
    const m = await loadMotion();
    $$(".searchbar").forEach(bar => {
      const input = bar.querySelector("input");
      if (!input) return;
      input.addEventListener("focus", () => {
        if (prefersReduced) return;
        if (m) m.animate(bar, { scale: 1.01 }, { duration: 0.22, ...springSoft });
        bar.classList.add("is-focused");
      });
      input.addEventListener("blur", () => {
        if (m) m.animate(bar, { scale: 1 }, { duration: 0.2 });
        bar.classList.remove("is-focused");
      });
    });
  }

  // 9. Page transition — subtle fade
  async function pageTransition() {
    const m = await loadMotion();
    if (prefersReduced) return;
    if (!m) {
      document.body.style.opacity = "1";
      return;
    }
    // Initial page load
    m.animate("main", { opacity: [0, 1], y: [8, 0] }, { duration: 0.5, easing: [0.16, 1, 0.3, 1] });
  }

  // 10. Count-up for stats — motion values
  async function statCountUp() {
    const m = await loadMotion();
    const stats = $$(".stat .num");
    if (prefersReduced) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const text = el.textContent.trim();
        const numMatch = text.match(/(\d+)/);
        if (!numMatch) return;
        const target = parseInt(numMatch[1], 10);
        if (isNaN(target) || target > 1000) return;
        let current = 0;
        const start = performance.now();
        const duration = 900;
        function tick(now) {
          const p = Math.min((now - start) / duration, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          current = Math.round(eased * target);
          el.textContent = text.replace(/\d+/, current);
          if (p < 1) requestAnimationFrame(tick);
          else el.textContent = text;
        }
        requestAnimationFrame(tick);
        io.unobserve(el);
      });
    }, { threshold: 0.5 });
    stats.forEach(s => io.observe(s));
  }

  // Init all
  document.addEventListener("DOMContentLoaded", () => {
    heroStagger();
    scrollReveals();
    cardGestures();
    resultsMotion();
    modalMotion();
    toastStackMotion();
    chipLayout();
    searchbarMotion();
    pageTransition();
    statCountUp();
  });

  // Expose for manual triggers
  window.MFMotion = { heroStagger, scrollReveals, toastStackMotion, loadMotion };
})();
