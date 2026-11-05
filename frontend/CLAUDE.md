# Frontend rules (Next.js App Router)

- Pages are client components under `app/(shell)/…`; data via `lib/api.ts` (`api()`), hooks in `lib/hooks.ts` (`useApi`, `useLiveEvents`, `useRefreshOn`).
- Design tokens live in `app/globals.css` (`@theme`) — use token classes (`bg-surface`, `text-ink-2`, `text-violet`, `text-cyan`, `text-gold`), never raw hex in components.
  See `docs/DESIGN_SYSTEM.md`. Serif (`font-serif`) only for headings and archive text; UI text stays sans.
- Status is never colour-only: use `StatusBadge` (icon + label). Charts: one axis, legend + direct labels (see the dataviz rules in docs).
- Never render HTML/SVG from the API with `dangerouslySetInnerHTML`; generated SVG goes through `<img src=data:…>` (`components/flare.tsx: SvgAsset`).
- Every feature shows honest empty/blocked states (e.g. "no AI provider configured") instead of fake content.
- Verify: `npx tsc --noEmit` and `npx next build`; then open the page against a running API.
