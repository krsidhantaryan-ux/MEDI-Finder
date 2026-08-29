# MediFinder UI/UX Style Scout

**Date:** 2026-08-29  
**Goal:** Find a less “AI-generated” and more product-grade UI direction for MediFinder using Agent Reach-assisted research, web search, screenshots, competitor UX patterns and the current app’s product needs.

---

## 1. Executive recommendation

The current redesign looks too AI because it uses many generic 2025/2026 AI-site tropes:

- Large gradient mesh backgrounds.
- Glassmorphism cards everywhere.
- Floating decorative mock panels.
- Over-rounded containers.
- Excessive glow/shadow.
- “Command center” marketing copy.
- Too many badges and animated decorative elements.
- A hero that feels like a SaaS landing page rather than a real medicine utility.

**Best direction for MediFinder:**

> **Local Healthcare Utility — search-first, calm, dense, trustworthy, location-aware.**

Think:

- **GoodRx** for medicine price/location comparison clarity.
- **Alto Pharmacy** for calm medication-management UI and patient reassurance.
- **Zocdoc** for bold search-first marketplace architecture.
- **Tata 1mg / PharmEasy / Netmeds** for Indian pharmacy expectations: location, prescription upload, categories, verification, repeat orders.

The design should feel like a reliable public utility, not a trendy AI SaaS page.

---

## 2. What “less AI” means here

### Remove or reduce

| Current pattern | Why it feels AI-made | Replacement |
|---|---|---|
| Mesh gradients | Generic AI landing-page visual | Flat off-white background with small accent bands |
| Glass blur everywhere | Overused template aesthetic | Solid cards with light border and restrained shadow |
| Giant abstract hero visual | Decorative, not useful | Real homepage map + search + upload prescription actions |
| “Clinical Command” language | Sounds artificial / SaaS-y | Plain human copy: “Find medicine near you” |
| Floating badges | Looks fabricated | Use real data cards: nearest pharmacies, recent availability |
| Too much motion | Feels generated rather than intentional | Only animate search results, modal entry, status changes |
| Huge rounded radii | Toy-like / template feel | 10–16px radius for cards, 999px only for pills/chips |
| Mixed decorative sections | Lacks product focus | One consistent app-like layout system |

### Keep

- Auto-location and map.
- Search-first hero.
- Verified pharmacy trust signals.
- Rx/OTC clarity.
- Dark mode, but make it quieter.
- Motion.dev, but use it sparingly.

---

## 3. Visual directions worth considering

### Option A — GoodRx-style “comparison utility”

**Best for:** MediFinder’s current core promise: compare nearby medicine availability.  
**Feel:** clean, direct, commercial, highly usable.

#### Visual traits

- Mostly white/off-white background.
- Large search input but minimal decoration.
- Simple list rows/cards with strong price and pharmacy name.
- Map/list split on desktop.
- Filters are functional, not decorative.
- Green/yellow accent only for CTA and price/availability.

#### UX traits

- Search drug.
- Select dose/quantity.
- Enter location.
- Compare pharmacies.
- Take action.

#### Why it fits MediFinder

MediFinder is not primarily an e-commerce shop yet; it is a **comparison + reservation** tool. This direction makes the product feel useful fast.

#### Risk

Could feel too plain if there is no brand polish. Needs excellent spacing, typography and icons.

---

### Option B — Alto-style “calm medication manager”

**Best for:** account, reservations, refills, medication history.  
**Feel:** warm, premium, caring, personal.

#### Visual traits

- Pale green / cream surfaces.
- Generous white cards.
- Medication cards grouped by person/family member.
- Human support language.
- Simple mobile-first hierarchy.

#### UX traits

- “Your meds” is the anchor.
- Upcoming delivery/hold appears at the top.
- Refill and reminders are primary repeat actions.
- Support/chat is easy to reach.

#### Why it fits MediFinder

Useful for making accounts feel valuable. Also helps the app feel less like a generic marketplace and more like a healthcare companion.

#### Risk

If applied to the public search page too strongly, it may reduce comparison density.

---

### Option C — Zocdoc-style “bold marketplace search”

**Best for:** homepage and marketplace discovery.  
**Feel:** confident, modern, memorable, consumer-grade.

#### Visual traits

- White background.
- Big typography.
- One sharp accent color.
- Hero built around a multi-field search bar.
- Trust/review signals near profiles.
- Cards and profiles feel editorial but restrained.

#### UX traits

- User enters need + location.
- Results show availability, trust, ratings and action.
- Strong profile pages.

#### Why it fits MediFinder

The pharmacy search problem is close to provider search: trust, distance, open status, and availability all matter.

#### Risk

A neon accent or too-bold campaign style could feel inappropriate for medicine if overused.

---

### Option D — Tata 1mg / PharmEasy / Netmeds “India e-pharmacy marketplace”

**Best for:** future prescription upload, categories, delivery, labs, consults.  
**Feel:** familiar for Indian users.

#### Visual traits

- Location at top.
- Search bar high on page.
- Icon category grid.
- Upload prescription card near first fold.
- Offer strips and banners.
- Product/category grids.

#### UX traits

- Choose location/pincode.
- Search or upload prescription.
- Pharmacist verifies prescription.
- Confirm address/payment.
- Track order.

#### Why it fits MediFinder

Users in India already understand this model. Patna/Bihar users will expect prescription upload and location-aware availability.

#### Risk

These apps can feel cluttered. MediFinder should borrow workflow patterns, not their banner-heavy visual clutter.

---

## 4. Recommended final hybrid

### “Verified Local Pharmacy Finder”

A focused hybrid:

- **GoodRx** result clarity.
- **Alto** calm account/refill UI.
- **Zocdoc** search-first homepage discipline.
- **Indian e-pharmacy** prescription/location workflow.

### Brand personality

- Practical.
- Local.
- Trustworthy.
- Fast in emergencies.
- Human, not futuristic.

### Visual palette

| Token | Recommended value | Usage |
|---|---|---|
| Background | `#FAFAF7` | Main page background |
| Surface | `#FFFFFF` | Cards/forms |
| Ink | `#111827` | Main text |
| Muted | `#667085` | Secondary text |
| Border | `#E5E7EB` | Card/table lines |
| Primary green | `#0F766E` | Search/hold CTA, verified state |
| Deep green | `#064E3B` | Header/footer/accent text |
| Safety yellow | `#FACC15` | Highlights, warnings, Zocdoc-like energy used sparingly |
| Error | `#DC2626` | Expired/out-of-stock |
| Success | `#16A34A` | In-stock/confirmed |

### Typography

Recommended:

- Use **Inter** or **Manrope** only.
- Remove display serif from most UI.
- Use 14–16px body, 13px metadata, 20–32px page headings.
- Avoid giant landing-page typography except on homepage.

Why: the serif + gradients currently push it toward a template/AI look. A clean sans makes the product feel more operational and real.

### Layout system

- Header: solid white, 56–64px, not pill-shaped floating glass.
- Search bar: one clear large card, not over-styled.
- Cards: 12–16px radius, 1px border, subtle shadow only on hover.
- Tables: denser, more professional, sticky headers where useful.
- Maps: real map is a feature, not a background decoration.
- Dashboards: admin/pharmacy pages should look like tools, not marketing pages.

### Motion style

Use Motion.dev only for:

- Result list loading/reveal.
- Map pin highlight when card is focused.
- Modal enter/exit.
- Toast/status feedback.
- Reservation timeline state transitions.

Avoid:

- Floating hero objects.
- Continuous decorative loops.
- Big scroll animations.
- Excessive blur/filter animation.

---

## 5. Page-by-page target design

### Homepage

Current issue: feels like a generic AI SaaS landing page.

Target:

1. Plain header with logo, Find Medicine, Upload Prescription, For Pharmacies, Sign in.
2. Location strip at top or inside hero: “Delivering / searching near Patna”.
3. Hero search:
   - Medicine/salt input.
   - Area/location input.
   - Auto-detect button.
   - Search CTA.
4. Four intent cards:
   - Search medicine.
   - Upload prescription.
   - Nearby pharmacies.
   - Refill saved medicine.
5. Real map preview with nearest verified pharmacies.
6. Simple how-it-works: Search → Compare → Hold → Pick up.
7. Pharmacy CTA as restrained B2B section.

### Search page

Current issue: visually improved but still stylized.

Target:

- GoodRx-like comparison page.
- Left or top filters: medicine, dose/form, location, category, Rx/OTC, in-stock.
- Results should be compact and comparable:
  - price
  - stock
  - distance
  - open status
  - verified badge
  - hold CTA
- Map stays visible on desktop.
- On mobile, map collapses behind a “Map” tab/button.

### Medicine/result card

Target card hierarchy:

1. Medicine name + strength.
2. Salt/composition.
3. Price and MRP.
4. Pharmacy name + verified.
5. Distance + open status.
6. Stock count.
7. Actions: Hold, Save, Directions.

Avoid over-badging. Use two or three status labels max.

### Pharmacy profile

Current issue: decorative cover section.

Target:

- Business listing style.
- Pharmacy name, verified, rating, open status.
- Address, phone, directions.
- Inventory search within pharmacy.
- Reviews.
- Map card.
- Trust details: license verified, last inventory update.

### Account page

Target:

- Alto-inspired “Your medicines” experience.
- Upcoming holds first.
- Saved medicines second.
- Past reservations third.
- Refill reminders and family member support later.

### Pharmacy dashboard

Target:

- Professional back-office tool.
- Less glow, more clarity.
- KPI row.
- Urgent reservation queue.
- Low stock / expiring soon list.
- Inventory table.
- Export/report actions.

### Admin dashboard

Target:

- Compliance/control room but restrained.
- Pending verification queue first.
- Network health stats.
- Recent holds.
- Audit log.
- Documents checklist.

---

## 6. Concrete redesign principles

1. **Search is the product.** Do not bury it under brand theatre.
2. **Real data beats decoration.** Map, stock, price and hours should be the visual interest.
3. **Use location as a persistent object.** Show it, remember it, make it editable.
4. **Rx trust must be explicit.** If Rx is required, explain next step.
5. **Make results comparable.** Align prices, distance and CTA positions.
6. **Use motion to confirm state.** Never animate simply because the page looks empty.
7. **Design for anxious users.** Medicine search often happens under stress; reduce cognitive load.
8. **Design for pharmacists at work.** Dashboards must be dense, fast and predictable.
9. **Do not mimic coupon/e-commerce clutter.** Borrow workflows, not banner noise.
10. **Avoid fake futuristic language.** Prefer simple copy: “Find”, “Hold”, “Pick up”, “Verified”.

---

## 7. What should be changed in the current code next

### Immediate visual cleanup

- Remove mesh backgrounds and most gradients.
- Replace floating pill nav with a normal sticky header.
- Reduce radius scale.
- Reduce shadow/glow intensity.
- Remove decorative hero mockup.
- Make homepage map/search the hero visual.
- Convert marketing sections into utility sections.
- Replace “Clinical Command” copy.
- Use Inter/Manrope sans-first typography.

### Product UX upgrades to pair with the redesign

- Persistent location memory.
- Reservation timeline with expiry countdown.
- Same-salt alternatives.
- Upload prescription entry point, even if initially “coming soon” or a request form.
- Clear “last updated” / “listed by pharmacy” stock trust line.

---

## 8. Best final design option

If choosing one direction, choose:

> **GoodRx clarity + Alto calm + Indian pharmacy workflow.**

This will make MediFinder feel:

- More real.
- Less AI-generated.
- More trustworthy for patients.
- More useful for pharmacists.
- More differentiated than generic online pharmacy templates.

The app should look like a polished public-health utility with consumer-grade polish, not a SaaS demo.
