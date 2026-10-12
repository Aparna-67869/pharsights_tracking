# Frontend and UX

Next.js 15 (App Router) + TypeScript + Tailwind + Recharts, styled to feel like
an enterprise console (Azure Portal / Datadog / Power BI lineage) rather than a
consumer app. Presenting only what needs a decision is the design goal; the
layouts are built for scanning.

## Routes

| Route | Purpose |
| --- | --- |
| `/login` | Credential sign-in; stores the JWT and redirects into the app |
| `/` | Executive dashboard: KPI strip, charts, recent high-priority activity |
| `/ftf` | Paragraph IV filings with filters, trend chart, export |
| `/pte` | PTE applications and certificates, extension analytics |
| `/pde` | Approved active moieties, yearly trend, sponsor distribution |
| `/orange-book` | Products, patents, exclusivity, and supplement edition compare |
| `/changes` | Change history with before/after drill-down |
| `/alerts` | Alert queue with acknowledge/resolve and delivery history |
| `/copilot` | Conversational AI with citations and suggested questions |
| `/search` | Global search and the 360-degree product view |
| `/graph` | Knowledge graph explorer |
| `/sources` | Source health, document versions, run history |

Every module page follows the same shape: **KPI strip → filter bar → chart →
table → export**. Consistency means a user learns the platform once.

## Component inventory

```
components/
├── ui/          Button, Card, Badge, Input, Tabs, Skeleton   (primitives)
├── layout/      AppShell, Sidebar, AuthGate, CommandPalette
├── common/      KpiCard, InsightCard                          (domain widgets)
├── charts/      Recharts wrappers (line, bar, heatmap, timeline)
├── tables/      DataTable — sortable, filterable, paginated, exportable
└── providers/   React Query, theme, auth, and realtime providers
```

`DataTable` is the workhorse: server-side pagination and filtering via React
Query, column visibility, CSV export that reuses the current filter, and
row-click drill-down. `InsightCard` renders the AI impact analysis — what
changed, why it matters, priority, and recommended action — as the primary
reading unit.

## State and data fetching

- **React Query** owns all server state: caching, background refetch, and
  retries. Hooks in `src/hooks/` wrap each endpoint so components never build
  URLs.
- **Zustand-free by design**: UI state that must persist (saved views, theme) is
  server-backed through the API, not local storage, so a view configured on one
  machine is available on another.
- **Live updates** arrive over the `/ws/events` WebSocket; incoming events
  invalidate the relevant React Query keys, so the dashboard updates without
  polling.

## Visual language

- **Theme**: dark and light, toggled and persisted per user. Dark is the default
  for the trading-desk feel; light is tuned for printed/exported reports.
- **Glassmorphism cards**: translucent surfaces with a subtle border and blur,
  layered over a deep background. Used for KPI and insight cards, not for dense
  tables, where contrast wins.
- **Color as meaning**: the priority bands drive the palette — Critical (red),
  High (amber), Medium (blue), Low (slate). The same colors appear on badges,
  chart series, and alert rows so a user reads severity at a glance.
- **Density**: compact tables, tabular numerals for counts and dates, and
  consistent spacing so scan paths are vertical and predictable.
- **Typography**: a single sans family; a monospace face for identifiers
  (patent numbers, application numbers, NCT ids) so they are copy-safe.

## Responsiveness

- Desktop-first, since the primary user works at a desk with wide tables.
- Tablet: the sidebar collapses to icons; charts reflow to full width.
- Mobile: the dashboard and alerts are usable (KPI cards stack, tables scroll
  horizontally); the graph explorer is desktop-only by intent.

## Accessibility

- Semantic landmarks and headings; keyboard-navigable command palette
  (`Ctrl/Cmd-K`).
- Color is never the only severity signal — every priority badge carries its
  label as text.
- Focus states are visible; contrast meets WCAG AA in both themes.

## Export and saved views

- Every module table exports CSV using the active filter, so "what I see is what
  I export".
- Saved views persist filters, visible columns, and layout server-side and can
  be shared or set as a personal default — this is the "custom dashboard"
  requirement.
