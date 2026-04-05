# Design System Document: Editorial Minimalism

## 1. Overview & Creative North Star
The Creative North Star for this design system is **"The Sustainable Atelier."** 

We are moving away from the "SaaS template" aesthetic to create a digital space that feels like a high-end editorial spread. This system balances the ruggedness of a "Deep Forest Green" with the airy sophistication of "Pale Mint." By utilizing intentional asymmetry, oversized typography scales, and a rejection of traditional borders, we establish a sense of trust through professional restraint rather than visual noise.

### The Editorial Edge
To break the standard grid, designers should favor:
- **Asymmetrical Breathing Room:** Large, purposeful gaps in the layout to guide the eye.
- **Overlapping Elements:** Allowing components (like marketplace cards or floating widgets) to subtly bleed into adjacent sections.
- **High-Contrast Scale:** Pairing massive `display-lg` headlines with significantly smaller, hyper-legible `label-md` metadata.

---

## 2. Colors & Surface Philosophy
This system uses a tonal approach to hierarchy. Depth is not a product of lines, but of light and material weight.

### The "No-Line" Rule
**Explicit Instruction:** Do not use 1px solid borders to section off content. 
Boundaries must be defined through background color shifts. A `surface-container-low` section sitting on a `surface` background provides all the structural integrity required without the visual clutter of a stroke.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers. Use the following tokens to create "nested" depth:
- **Base Layer:** `surface` (#f8faf8) for the main canvas.
- **Sub-Sections:** `surface-container-low` (#f2f4f2) for large background blocks.
- **Active Cards:** `surface-container-lowest` (#ffffff) to make elements "pop" forward.
- **Deep Insets:** `primary-container` (#002d1e) for high-impact callouts.

### The "Glass & Gradient" Rule
To elevate the experience, utilize **Glassmorphism** for floating elements (e.g., sticky headers or hovering tooltips). 
*   **Formula:** `surface` at 70% opacity + `backdrop-blur: 20px`.
*   **Signature Textures:** Use a subtle linear gradient from `primary` (#00160d) to `primary-container` (#002d1e) for main CTAs. This creates a "silky" depth that feels premium and custom.

---

## 3. Typography
The system utilizes a dual-type approach to balance authority with approachability.

*   **Display & Headlines (Plus Jakarta Sans):** These are the "voice" of the brand. Use `display-lg` for hero moments, intentionally breaking lines to create an editorial feel.
*   **Body & UI (Inter):** Chosen for its mathematical precision. Inter handles the "work" of the system—form labels, data widgets, and marketplace descriptions—ensuring that even at `body-sm`, the trust remains unbroken.
*   **Hierarchy Note:** Always maintain a minimum 2-step jump in the scale between a headline and its sub-text to preserve the editorial contrast.

---

## 4. Elevation & Depth
We eschew traditional "Drop Shadows" in favor of **Ambient Light Tunnelling**.

*   **The Layering Principle:** Stacking surface tiers is the primary method of elevation. A white card (`surface-container-lowest`) on a mint-tinted background (`surface-container-low`) creates a soft, natural lift.
*   **Ambient Shadows:** When a float is required, use extra-diffused shadows: `box-shadow: 0 20px 40px rgba(0, 22, 13, 0.06)`. The shadow color is a 6% opacity tint of the `primary` green, mimicking natural forest light.
*   **The "Ghost Border" Fallback:** If a border is required for accessibility in input fields, use `outline-variant` at 20% opacity. Never use 100% opaque borders.

---

## 5. Components

### Form Inputs
- **Style:** Large corner radius (`DEFAULT: 1rem`).
- **Surface:** Use `secondary-container` (#d7e3da) with zero border.
- **State:** On focus, transition the background to `surface-container-lowest` (#ffffff) and apply a "Ghost Border" of `primary` at 10%.

### Buttons
- **Primary:** Gradient fill (`primary` to `primary-container`), white text, `xl` roundedness (3rem).
- **Secondary:** Transparent with a `primary` text color. No border.
- **Tertiary/Marketplace:** `surface-container-highest` background with `on-surface` text.

### Step Indicators (The Process Step)
- **Accent:** Use `tertiary_fixed_dim` (#ffba20) exclusively for "Process" progress.
- **Logic:** Indicators should be horizontal pill shapes with `full` roundedness. Completed steps use `primary`, current steps use `tertiary`, and upcoming steps use `outline_variant`.

### Marketplace Cards & Admin Widgets
- **Rule:** Absolute prohibition of divider lines.
- **Separation:** Use vertical white space from the 16px/24px/32px spacing scale.
- **Visuals:** Images in cards must use `md` (1.5rem) corner radius. Use `surface-container-lowest` for the card body to ensure it sits "above" the site background.

---

## 6. Do’s and Don’ts

### Do:
- **Embrace White Space:** If a section feels crowded, double the padding.
- **Use Tonal Transitions:** Transition from a `Pale Mint` section to a `White` section to indicate a change in content.
- **Align to the Left:** Keep editorial text left-aligned to maintain a clean, "columnar" reading path.

### Don't:
- **Don't use pure black:** Use `primary` (#00160d) for all "black" text to keep the palette organic.
- **Don't use 1px borders:** Rely on background shifts or the 20% "Ghost Border" rule.
- **Don't use small corner radii:** Anything under `1rem` is too sharp for this system. Maintain the "Soft Minimalism" through `lg` and `xl` radii.
- **Don't use standard drop shadows:** Avoid the "floating on a cloud" look; keep shadows subtle, wide, and green-tinted.