/* ==========================================================================
   MediFinder Motion System
   Motion.dev is used as product feedback, not decoration: restrained reveal,
   result loading, modal/toast entry, and small state confirmations.
   ========================================================================== */
import { animate, inView, stagger } from "https://cdn.jsdelivr.net/npm/motion@latest/+esm";

(function () {
    "use strict";

    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const EASE = [0.22, 1, 0.36, 1];
    const SPRING = { type: "spring", stiffness: 460, damping: 34, mass: 0.8 };

    window.MF = window.MF || {};

    function ready(fn) {
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn, { once: true });
        else fn();
    }

    function skip() { return prefersReduced.matches; }

    function revealOne(el, delay = 0) {
        if (!el || skip() || el.dataset.motionPlayed) return;
        el.dataset.motionPlayed = "1";
        animate(el, { opacity: [0, 1], y: [12, 0] }, { duration: 0.38, delay, ease: EASE });
    }

    function revealList(items, options = {}) {
        const elements = Array.from(items || []).filter(Boolean);
        if (!elements.length || skip()) return;
        elements.forEach((el) => { el.dataset.motionPlayed = "1"; });
        animate(
            elements,
            { opacity: [0, 1], y: [10, 0] },
            { duration: options.duration || 0.32, delay: stagger(options.stagger || 0.035, { startDelay: options.startDelay || 0 }), ease: EASE }
        );
    }

    function pop(el) {
        if (!el || skip()) return;
        animate(el, { opacity: [0, 1], y: [8, 0], scale: [0.985, 1] }, SPRING);
    }

    function pulse(el) {
        if (!el || skip()) return;
        animate(el, { scale: [1, 1.018, 1] }, { duration: 0.24, ease: EASE });
    }

    function wireScrollProgress() {
        const progress = document.querySelector(".scroll-progress");
        if (!progress || skip()) return;
        let ticking = false;
        const update = () => {
            const max = document.documentElement.scrollHeight - window.innerHeight;
            const ratio = max > 0 ? window.scrollY / max : 0;
            progress.style.transform = `scaleX(${Math.max(0, Math.min(1, ratio))})`;
            ticking = false;
        };
        window.addEventListener("scroll", () => {
            if (!ticking) {
                window.requestAnimationFrame(update);
                ticking = true;
            }
        }, { passive: true });
        update();
    }

    function wireNav() {
        const nav = document.querySelector(".nav");
        if (!nav) return;
        const update = () => nav.classList.toggle("is-scrolled", window.scrollY > 6);
        window.addEventListener("scroll", update, { passive: true });
        update();
    }

    function wireReveal() {
        if (skip()) return;
        document.documentElement.classList.add("motion-ready");
        inView("[data-motion], .stat, .feature-grid > *, .process-grid > *, .dash-stat", (element) => {
            revealOne(element);
        }, { margin: "0px 0px -48px 0px", amount: 0.12 });
    }

    function wireHero() {
        if (skip()) return;
        const hero = document.querySelector(".home-hero");
        if (!hero) return;
        revealList(hero.querySelectorAll(".location-pill, .eyebrow, h1, .hero-lead, .searchbar, .chips, .intent-card"), { stagger: 0.035, startDelay: 0.03 });
        pop(hero.querySelector(".home-map-card"));
    }

    function wireFeedback() {
        if (skip()) return;
        document.addEventListener("pointerdown", (event) => {
            const target = event.target.closest(".btn, .chip, .intent-card, .nearby-item, .dash-side a");
            if (!target || target.disabled) return;
            animate(target, { scale: [1, 0.985, 1] }, { duration: 0.2, ease: EASE });
        });
    }

    ready(() => {
        wireScrollProgress();
        wireNav();
        wireReveal();
        wireHero();
        wireFeedback();
    });

    MF.motion = { animate, inView, stagger, revealOne, revealList, pop, pulse, modal: pop, toast: pop };
})();
