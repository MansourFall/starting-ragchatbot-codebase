# Frontend Changes: Dark/Light Theme Toggle

## Summary

Added a dark/light theme toggle button that allows users to switch between themes, with the preference persisted via `localStorage`.

---

## Files Modified

### `frontend/index.html`
- Added a `<button id="themeToggle" class="theme-toggle">` element immediately after `<body>`, positioned in the top-right corner via `position: fixed`.
- The button contains two inline SVG icons:
  - `.icon-moon` — shown in dark mode (default), indicating "switch to light"
  - `.icon-sun` — shown in light mode, indicating "switch to dark"
- Includes `aria-label` and `title` attributes for accessibility and keyboard navigation.
- Bumped CSS cache-buster version: `style.css?v=11` → `?v=12`
- Bumped JS cache-buster version: `script.js?v=10` → `?v=11`

### `frontend/style.css`
- Added `transition` properties to the universal `*, *::before, *::after` reset rule so all theme-sensitive properties animate smoothly (0.3s ease) when toggling.
- Extended `:root` with two new custom properties used by the toggle button:
  - `--theme-toggle-bg`
  - `--theme-toggle-color`
  - `--theme-toggle-hover-bg`
- Added a complete `[data-theme="light"]` block with light-mode overrides for all CSS custom properties:
  - `--background`: `#f8fafc` (near-white)
  - `--surface`: `#ffffff`
  - `--surface-hover`: `#e2e8f0`
  - `--text-primary`: `#0f172a` (dark for contrast)
  - `--text-secondary`: `#475569`
  - `--border-color`: `#cbd5e1`
  - `--assistant-message`: `#f1f5f9`
  - `--shadow`: lighter `rgba(0,0,0,0.1)` version
  - `--welcome-bg`: `#dbeafe`
  - Toggle-specific vars set to light grays
- Added `.theme-toggle` button styles:
  - `position: fixed; top: 1rem; right: 1rem; z-index: 1000`
  - 40×40 px circular button with border, background, and shadow from CSS variables
  - Hover: subtle scale + shadow
  - Focus: 3px `focus-ring` outline (accessible)
  - Active: slight scale-down
- Added icon visibility rules:
  - `.icon-moon` visible by default (dark mode); hidden in `[data-theme="light"]`
  - `.icon-sun` hidden by default; visible in `[data-theme="light"]`

### `frontend/script.js`
- Added `themeToggle` to the DOM element declarations.
- Called `initTheme()` during `DOMContentLoaded` (before `createNewSession`) to apply the saved preference immediately on load.
- Added `themeToggle.addEventListener('click', toggleTheme)` in `setupEventListeners()`.
- Added three new functions:
  - **`initTheme()`** — reads `localStorage.getItem('theme')` (defaulting to `'dark'`) and calls `applyTheme()`.
  - **`toggleTheme()`** — reads the current `data-theme` attribute on `<html>`, flips it, calls `applyTheme()`, and saves the new value to `localStorage`.
  - **`applyTheme(theme)`** — sets `document.documentElement.setAttribute('data-theme', theme)` and updates the button's `aria-label` to reflect the action it will take next.

---

## Behaviour

- Default theme is **dark** (matches the existing design).
- Clicking the toggle button switches between dark and light themes with a 0.3s CSS transition on all color properties.
- The chosen theme is persisted in `localStorage` under the key `theme` and restored on next page load.
- The toggle button is keyboard-focusable and screen-reader-friendly via `aria-label`.
