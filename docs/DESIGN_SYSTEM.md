# Design system — dark technomysticism

A command center for an intelligence that keeps an archive: obsidian surfaces, violet for G-SUS, cyan for the
Demonkoncernen machinery, antique gold for the archive, serif headings like manuscript titles — and every number and
status readable at a glance.

## Tokens (`frontend/app/globals.css`, Tailwind 4 `@theme`)

| Token | Value | Use |
|---|---|---|
| `bg` | `#0c0b11` | obsidian page background |
| `surface`, `surface-2` | `#15141c`, `#1e1d28` | panels, hover/active rows |
| `line`, `line-strong` | `#2a2937`, `#3b3950` | borders, inputs |
| `ink`, `ink-2`, `ink-3` | `#ecebf4`, `#c2c0d3`, `#8e8ba3` | primary / secondary / tertiary text — contrast on `bg` 16.6 : 1, 11.0 : 1, 5.9 : 1 (all above WCAG AA 4.5 : 1) |
| `violet`, `violet-dim` | `#a78bfa` (7.2 : 1), `#4b3d85` | primary actions, G-SUS, focus, selection |
| `cyan` | `#22d3ee` (10.8 : 1) | live data, offline indicator, Demonkoncernen infrastructure |
| `gold`, `bronze`, `olive`, `parchment` | `#c9a227`, … | Archive, Field Operations, primary-source evidence |
| `good`, `warning`, `serious`, `critical` | `#0ca30c`, `#fab219`, `#ec835a`, `#d03b3b` | status — always with icon + label |
| `series-1..3` | `#3987e5`, `#d95926`, `#199e70` | chart series |

Fonts: sans (Inter / system) for UI, serif (Iowan Old Style / Palatino / Georgia) **only** for page titles, the sigil
wordmark and archive text, mono (JetBrains Mono / system) for kickers, IDs, model keys and tables of code. No webfonts
are fetched at runtime.

## Rules

* Use token classes (`bg-surface`, `text-ink-2`, `text-violet`), never raw hex in components (charts pass hex to
  Recharts because SVG attributes cannot read Tailwind classes).
* **Status is never colour alone:** `StatusBadge` (icon + label), `EvidenceBadge` (glyph + words).
* Honest states: empty, blocked and "not configured" are shown as such — never placeholder content that looks real.
  Demo data is badged `DEMO`.
* Charts: one unit per axis, legend + direct labels, stacked only when parts sum to a meaningful total
  (e.g. calls per day: local vs external).
* Tables scroll horizontally inside their card; the page itself must not (verified 0 px overflow at iPhone 13 width
  on DAEMON CORE and Settings).
* Never render API-provided HTML/SVG with `dangerouslySetInnerHTML`; generated SVG goes through `<img src=data:…>`.

## Components (`frontend/components`)

`ui.tsx` (PageHeader, Card, Stat, Button, StatusBadge, EvidenceBadge, Table, Field, Empty, ErrorBanner), `shell.tsx`
(sigil, grouped navigation, header with DAEMON mode/profile/model indicator, emergency stop), `charts.tsx`,
`flare.tsx`, `users.tsx` (user management, password change).
