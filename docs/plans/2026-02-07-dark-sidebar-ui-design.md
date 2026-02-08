# Dark Theme + Sidebar Layout Redesign

## Summary

Replace the current white top-navbar layout with a dark theme and left sidebar navigation. Green accent color from the logo is used sparingly for key interactive elements only.

## Visual Reference

Static preview: `docs/theme-preview.html`

## Theme

- **Dark-mode only** — remove the light `:root` theme, make dark the default
- **Background**: flat `#161616` (neutral charcoal), no gradient
- **Surface/cards/sidebar**: `#1a1a1a` — slightly lighter than background for depth
- **Borders**: `rgba(255,255,255, 0.07)` — barely visible separation
- **Text hierarchy**:
  - Primary: `#e5e5e5`
  - Secondary: `#a3a3a3`
  - Muted/disabled: `#737373`
  - Dimmed (table headers, AWS IDs): `#525252`

## Green Accent (Subtle)

Green appears in only these places:

| Element | Color | Notes |
|---------|-------|-------|
| Primary button | `#047857` | Hover: `#065f46` |
| Active nav icon | `#047857` | Only the icon, not the label |
| "Active" status badge | `#059669` text on `rgba(4,120,87,0.15)` bg | |
| Logo | Original gradients | `#34d399` through `#065f46` |

Everything else (links, text, hovers, user avatar) stays neutral gray.

## Layout: Sidebar

Replace the top `<header>` navbar with a fixed left sidebar.

### Structure

```
+--sidebar(240px)--+--------main content---------+
| Logo + Groundwork|                              |
|-------------------|  Page title     [+ Action]  |
| Accounts          |                              |
| Role Templates    |  Card/table content          |
| Jobs              |                              |
|                   |                              |
|                   |                              |
|-------------------|                              |
| [avatar] username |                              |
+-------------------+------------------------------+
```

### Sidebar contents

1. **Header**: Logo SVG (28px) + "Groundwork" text, separated by bottom border
2. **Navigation**: Three links with Lucide icons
   - `Building2` — Accounts (`/`)
   - `Shield` — Role Templates (new route, currently not routed)
   - `Activity` — Jobs (`/jobs`)
3. **Footer**: User avatar circle (initials) + `display_name` from `UserInfo`, with dropdown for logout

### Collapsed state (small screens)

Sidebar collapses to icon-only (approx 56px wide). The "Groundwork" text, nav labels, and username text hide. Logo, nav icons, and avatar remain visible.

### Active state

- Active nav item: `rgba(255,255,255,0.06)` background, `#e5e5e5` text, icon colored `#047857`
- Inactive: `#737373` text, no background
- Hover: `rgba(255,255,255,0.05)` background, `#a3a3a3` text

## Changes Required

### `index.css`

- Remove `:root` light theme block
- Make `.dark` values the only theme (move to `:root`)
- Update color values to match the palette above
- Update sidebar CSS variables to match

### `Layout.tsx`

- Replace the `<header>` + horizontal nav with a sidebar layout
- Sidebar: logo header, nav links with icons, user footer with dropdown
- Main content: `<Outlet />` in a flex-grow container with padding
- Show `user.display_name` instead of `user.email`
- Responsive: collapse to icon-only below a breakpoint (e.g., `lg`)

### `Dashboard.tsx`

- Remove the "Groundwork" hero/branding from the unauthenticated landing (sidebar handles branding)
- The accounts table and "New Account" button remain as-is

### Routing

- Add a `/role-templates` route placeholder (can be a stub page) for the sidebar link
- Existing routes unchanged

## Out of Scope

- Theme toggle (light/dark switching) — this is dark-only
- Mobile hamburger menu — collapsible icon sidebar is sufficient
- Changes to page content, forms, dialogs, or API layer
