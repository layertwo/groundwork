# Dark Theme + Navbar UI Redesign

## Summary

Replace the current white theme with a dark theme and updated top navbar. Green accent color from the logo is used sparingly. Accounts table is grouped by OU, includes a search bar and email column.

## Visual Reference

Static preview: `docs/theme-preview-navbar.html`

## Theme

- **Dark-mode only** — remove the light `:root` theme, make dark the default
- **Background**: flat `#161616` (neutral charcoal), no gradient
- **Surface/cards/navbar**: `#1a1a1a` — slightly lighter than background for depth
- **Borders**: `rgba(255,255,255, 0.07)` — barely visible separation
- **Text hierarchy**:
  - Primary: `#e5e5e5`
  - Secondary: `#a3a3a3`
  - Muted/disabled: `#737373`
  - Dimmed (table headers, AWS IDs, emails): `#525252`

## Green Accent (Subtle)

Green appears in only these places:

| Element | Color | Notes |
|---------|-------|-------|
| Primary button | `#047857` | Hover: `#065f46` |
| Active nav icon | `#047857` | Only the icon, not the label |
| "Active" status badge | `#059669` text on `rgba(4,120,87,0.15)` bg | |
| Logo | Original gradients | `#34d399` through `#065f46` |

Everything else (links, text, hovers, user avatar) stays neutral gray.

## Layout: Top Navbar

Keep a top navbar (not sidebar). Restyle it to match the dark theme.

### Structure

```
+--logo--Groundwork--[Accounts] [Role Templates] [Jobs]----------[avatar username]--+
|                                                                                    |
|                        Page title                       [+ Action]                 |
|                                                                                    |
|                        [Search bar...........................]                     |
|                                                                                    |
|                        Card/table content                                          |
|                                                                                    |
+------------------------------------------------------------------------------------+
```

### Navbar contents

- **Left side**: Logo SVG (24px) + "Groundwork" text, then nav links with Lucide icons
  - `Building2` — Accounts (`/`)
  - `Shield` — Role Templates (new route, stub page)
  - `Activity` — Jobs (`/jobs`)
- **Right side**: User avatar circle (initials) + `display_name` from `UserInfo`, with dropdown for logout

### Nav item states

- Active: `rgba(255,255,255,0.06)` background, `#e5e5e5` text, icon colored `#047857`
- Inactive: `#737373` text, no background
- Hover: `rgba(255,255,255,0.05)` background, `#a3a3a3` text

### Navbar styling

- Height: 52px, sticky top
- Background: `#1a1a1a`
- Bottom border: `rgba(255,255,255, 0.07)`
- Content max-width not constrained (full-width bar), but main content area uses `max-width: 1100px` centered

## Accounts Table

### Grouped by OU

Instead of an OU column, accounts are grouped under OU section headers within the table:

- **OU header row**: spans all columns, folder icon + OU name, uppercase, dimmed text (`#525252`), subtle background (`rgba(255,255,255,0.02)`)
- Accounts belonging to that OU are listed below the header

### Columns

| Column | Style |
|--------|-------|
| Name | Link style (`#d4d4d4`, underline on hover) |
| Email | Dimmed text (`#525252`) — account root email |
| AWS Account ID | Monospace, dimmed (`#525252`) |
| Status | Badge — Active (green) or Provisioning (yellow) |
| Actions | Federate link (muted gray) |

### Search Bar

- Placed above the table card
- Full-width text input with magnifying glass icon
- Placeholder: "Search accounts..."
- Styled: `#1a1a1a` background, `rgba(255,255,255,0.07)` border, `#525252` placeholder
- Filters accounts client-side by name, email, AWS ID, or OU
- All table views (accounts, role templates, jobs) get a search bar with appropriate placeholder text

## Changes Required

### `index.css`

- Remove `:root` light theme block
- Make `.dark` values the only theme (move to `:root`)
- Update color values to match the palette above
- Remove sidebar CSS variables (no longer needed)

### `Layout.tsx`

- Restyle the existing `<header>` navbar to match dark theme
- Add logo SVG alongside "Groundwork" text
- Add Accounts and Role Templates nav links (currently only has Jobs)
- Show `user.display_name` instead of `user.email`
- Add Lucide icons to nav links
- Style active nav item based on current route

### `Dashboard.tsx`

- Remove the "Groundwork" hero/branding from the unauthenticated landing (navbar handles branding)
- Group accounts by OU with section headers instead of an OU column
- Add Email column to the accounts table
- Add search bar above the table (filters by name, email, AWS ID, OU)

### `AccountDetail.tsx`

- Add search bar above the roles table

### `JobList.tsx`

- Add search bar above the jobs table (in addition to existing status/type filters)

### Routing

- Add a `/role-templates` route placeholder (stub page) for the nav link
- Existing routes unchanged

### Backend

- Account `email` field needs to be returned in the accounts API response (verify it's already included in the schema; if not, add it)

## Out of Scope

- Theme toggle (light/dark switching) — this is dark-only
- Sidebar layout — using top navbar instead
- Changes to forms, dialogs, or non-table page content
