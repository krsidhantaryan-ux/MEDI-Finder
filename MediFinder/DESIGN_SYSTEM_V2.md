# MediFinder — Design System v2
## UI-UX Pro Max + Framer Motion + motion.site

This overhaul applies all three requested libraries/skillsets:

### 1. UI-UX Pro Max Skill (nextlevelbuilder/ui-ux-pro-max-skill)

**Analysis:**
- Product: Healthcare marketplace / pharmacy finder (trust-critical, accessibility-critical)
- Audience: Patients in urgent need + pharmacists (mobile-first, low-literacy tolerant)
- Style: Clinical Editorial — warm paper, deep teal trust, amber urgency, Fraunces display + Inter body
- Pattern: Hero + Testimonials + CTA (per skill reasoning)

**Applied Rules by Priority:**

1. **Accessibility CRITICAL**
   - 4.5:1 contrast minimum (all text, badges, buttons)
   - Alt text for meaningful images, decorative icons aria-hidden
   - Keyboard nav: skip link, focus-visible with shadow-focus, focus trap in modal, Escape closes nav/modal
   - Aria-labels, aria-pressed, aria-selected, role=listbox/option, aria-live polite for toasts and results count
   - Error messages near field with role=alert and aria-invalid
   - Focus not obscured, focused card scrolls into view

2. **Touch & Interaction CRITICAL**
   - Min touch target 44x44px (--touch-min) for all buttons, chips, nav links
   - 8px+ spacing between interactive elements
   - Loading feedback: is-loading shimmer, disabled states, toast feedback
   - Bottom nav ≤5 items with labels+icons for mobile (adaptive navigation)

3. **Performance HIGH**
   - CLS <0.1: reserved space for map, skeletons, aspect-ratio on hero-visual
   - Lazy loading for images, fetchpriority high for hero
   - No layout thrashing: transform/opacity only for animations

4. **Style Selection HIGH**
   - Consistent: no emoji as icons (bootstrap-icons SVG), no mixed neumorphism
   - Matched product: clinical calm + editorial warmth, not neon / AI purple gradients (avoid per skill)

5. **Layout & Responsive HIGH**
   - Mobile-first, 375/768/1024/1440 breakpoints tested
   - No horizontal scroll, scrollbar-gutter stable
   - Viewport meta with viewport-fit=cover for safe areas

6. **Typography & Color MEDIUM**
   - Base 16px, line-height 1.6 (1.75 for lead), text-wrap balance/pretty to avoid orphans
   - Semantic tokens: --teal, --amber, --ink, --paper, --surface, --line
   - No raw hex in components, only tokens

7. **Animation MEDIUM**
   - Context-aware timing: fast 150ms for micro, normal 250ms, slow 400ms
   - Motion conveys meaning: scale+fade for modal from trigger, toast stack fan, chip bounce on select
   - Spatial continuity: modal animates from center, searchbar scale on focus
   - Respects prefers-reduced-motion: all motion disabled, final state rendered immediately

8. **Forms & Feedback MEDIUM**
   - Visible labels, required indicators *, helper text, error near field
   - Input types semantic (tel, email, number) for correct mobile keyboards
   - Autofill support via autocomplete attributes
   - Progressive disclosure in auth, confirmation dialogs for destructive

9. **Navigation Patterns HIGH**
   - Predictable back: Back to search link, breadcrumbs pattern
   - Deep linking: all shops /pharmacy/<id>, search with query params
   - Persistent nav, state preservation on back
   - Bottom nav for top-level only, not nested

10. **Charts & Data LOW**
    - Badge colors accessible, not relying on color alone (icons + text)

**Pre-delivery Checklist:**
- [x] No emojis as icons
- [x] cursor-pointer on clickable
- [x] Hover 150-300ms with ease-out
- [x] Light mode contrast 4.5:1
- [x] Focus visible
- [x] prefers-reduced-motion respected
- [x] Responsive 375,768,1024,1440

### 2. Framer Motion (Motion.dev)

Motion.dev is the successor to Framer Motion — same API, now framework-agnostic. Used via ESM CDN:

```js
import { animate, stagger, inView, scroll } from "motion"
```

Implemented:
- **Independent transforms**: animate x, y, scale, rotate independently without wrapper divs
- **Spring physics**: springSoft (320/28), springBouncy (420/22), springSmooth (260/30) for natural feel
- **Native gestures**: hover (y:-2, scale:1.01), press (scale:0.97), drag not needed but ready
- **Layout animation**: chip layout when filter active, card siblings scale
- **Exit animation**: modal and toast AnimatePresence-like with opacity + scale + x
- **Timeline sequences**: hero stagger with stagger(0.04), feature-grid stagger(0.07), results stagger(0.05)
- **Motion values**: count-up for stats via requestAnimationFrame, scroll-linked parallax via scroll(transform)
- **Scroll animation**: inView for all [data-reveal], testimonial track snap

### 3. motion.site (Motion UI)

Production-ready patterns from motion.site:
- **Editorial hero stagger**: eyebrow → headline → lead → searchbar → chips → meta, each 60-80ms apart, ease-out [0.16,1,0.3,1]
- **Toast stack**: fan into scaled pile, older toasts scale down 0.04 per depth, spring restack on dismiss
- **iOS-style modal**: scale 0.94→1 + y 10→0 + fade, backdrop blur 8px, spatial continuity from trigger
- **Searchbar focus**: scale 1.01 spring, glow via shadow-focus
- **Card hover**: y:-2, scale:1.01 on hover, press 0.99, spring bouncy on release
- **Testimonials carousel**: scroll-snap, pause on hover/focus, keyboard ArrowLeft/Right, previous/next controls, announce position

### Files Changed
- `static/css/style.css` — complete rewrite v2, 44px touch, semantic tokens, motion utilities, reduced-motion, tables, bottom nav
- `static/js/app.js` — a11y overhaul: skip link, focus trap, aria-live toasts, error near field, confirm dialogs, theme a11y
- `static/js/motion.js` — new file, all Motion.dev logic, 10 motion patterns
- `templates/base.html` — importmap for motion, skip link, bottom nav ≤5, aria, theme-color, motion.js module
- `templates/index.html` — editorial stagger, testimonials (Hero+Testimonials+CTA), keyboard nav, a11y chips, motion-fade
- `templates/search.html` — layout animation, aria-busy, role=list, keyboard nav for autocomplete, focus management, motion event

### How to run
```bash
cd MediFinder
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

### Future: React Framer Motion
If migrating to Next.js/React, replace CDN import with:
```bash
npm i motion
```
```tsx
import { motion, AnimatePresence } from "motion/react"
<motion.div initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{type:"spring", stiffness:320, damping:28}} />
```

All three requested resources are now active in production.
