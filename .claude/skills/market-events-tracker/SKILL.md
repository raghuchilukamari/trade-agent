---
name: market-events-tracker
description: >
  Tracks market events and their outcomes for given week.
---

## WORKFLOW
- Runs on sunday night to fetch market events for the upcoming week
- Runs every day from Monday-Friday, before market open and after market close to get updates on the events
- If you are running mid of the week, fetch and update events for the given week so far

### Step 1: Gather Event Data

If event data is not already in context, use `web_search` to find it:
- Search: `key market events week [DATE RANGE]`
- Extract: date, event name, brief note, event type (Macro / Fed / Inflation / Commodities / Catalyst / Earnings / OPEX / Central Bank / Intl Macro)
- Consolidate same-day events — collapse related items onto a single row per day

### Step 2: Build the HTML

Render events into the compact HTML template below. Key design rules:
- **Width:** 760px body, white background
- **Font:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`
- **Table:** 4 columns — **Day | Events | Type | Outcomes**
- **Table styling:** collapsed borders, 1px `#e5e7eb` outer border, `border-radius: 8px`, `overflow: hidden`
- **Rows:** `9px 12px` cell padding, `font-size: 12px`, tight `line-height: 1.45`
- **Separators:** `<div class="sep">` (5px height) between event groups within a cell
- **Consolidation:** Multiple macro releases on the same day → single line joined with `·`
- **Highlight rows:** Wednesday (highest vol) = `background: #fff9f9`, Friday OPEX/holiday = `background: #f9f8ff`
- **Day labels:** Wednesday = `color: #b91c1c`, Friday Quad Witching/holiday = `color: #4338ca`
- **Outcomes column:** Shows actual results for past events, "Pending" for future events. Color-code: `.outcome-up` (green `#166534`) for beats/positive, `.outcome-down` (red `#dc2626`) for misses/negative, `.outcome-neutral` (gray) for inline

### Step 3: Present

Call `present_files` with the output path.

---

## HTML TEMPLATE

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #ffffff;
    color: #111;
    padding: 20px;
    width: 720px;
  }
  .header { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
  .title  { font-size: 15px; font-weight: 600; color: #111827; letter-spacing: -0.01em; }
  .subtitle { font-size: 12px; color: #9ca3af; }
  table { width: 100%; border-collapse: collapse; border: 1px solid #e5e7eb;
          border-radius: 8px; overflow: hidden; font-size: 12px; }
  thead tr { background: #f9fafb; }
  th { padding: 7px 12px; text-align: left; font-size: 11px; font-weight: 600;
       color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em;
       border-bottom: 1px solid #e5e7eb; }
  td { padding: 9px 12px; vertical-align: top; border-bottom: 1px solid #f3f4f6;
       line-height: 1.45; }
  tr:last-child td { border-bottom: none; }
  .day-cell { font-weight: 600; font-size: 12px; white-space: nowrap;
              color: #374151; width: 90px; }
  .day-sub  { font-weight: 400; font-size: 10px; color: #9ca3af; margin-top: 1px; }
  .day-wed  { color: #b91c1c; }
  .day-fri  { color: #4338ca; }
  .event-name { font-weight: 500; color: #111827; font-size: 12px; line-height: 1.4; }
  .event-note { font-size: 11px; color: #9ca3af; margin-top: 1px; line-height: 1.35; }
  .outcome { font-size: 11px; color: #374151; line-height: 1.4; }
  .outcome-val { font-weight: 600; }
  .outcome-up { color: #166534; }
  .outcome-down { color: #dc2626; }
  .outcome-neutral { color: #6b7280; }
  .pending { font-size: 11px; color: #9ca3af; font-style: italic; }
  .sep { height: 5px; }
  .badges { white-space: nowrap; width: 90px; }
  .badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 10px;
           font-weight: 600; margin-bottom: 3px; letter-spacing: 0.01em; white-space: nowrap; }
  .b-red    { background: #fef2f2; color: #991b1b; }
  .b-amber  { background: #fffbeb; color: #92400e; }
  .b-blue   { background: #eff6ff; color: #1d4ed8; }
  .b-purple { background: #f5f3ff; color: #5b21b6; }
  .b-gray   { background: #f9fafb; color: #4b5563; border: 1px solid #e5e7eb; }
  .badge-row { display: flex; flex-direction: column; gap: 2px; }
</style>
</head>
<body>
<div class="header">
  <span class="title">Key Market Events</span>
  <span class="subtitle">[DATE RANGE]</span>
</div>
<table>
  <thead>
    <tr><th>Day</th><th>Events</th><th>Type</th><th>Outcomes</th></tr>
  </thead>
  <tbody>
    <!-- One <tr> per trading day -->
    <!-- Normal day (past — outcomes filled) -->
    <tr>
      <td class="day-cell">[Day Month DD]</td>
      <td>
        <div class="event-name">[Event 1] · [Event 2] · [Event 3]</div>
        <div class="sep"></div>
        <div class="event-name">[Standalone Event]</div>
        <div class="event-note">[Brief clarifying note]</div>
      </td>
      <td class="badges">
        <div class="badge-row">
          <span class="badge b-blue">Macro</span>
          <span class="badge b-gray">Earnings</span>
        </div>
      </td>
      <td class="outcome">
        <div>ISM: <span class="outcome-val outcome-up">52.7</span> (beat)</div>
        <div class="sep"></div>
        <div>NKE: EPS <span class="outcome-val outcome-down">$0.28 (-48% YoY)</span></div>
      </td>
    </tr>
    <!-- High-vol day (e.g. FOMC Wednesday) -->
    <tr style="background: #fff9f9;">
      <td class="day-cell day-wed">
        Wed [Month DD]
        <div class="day-sub">&nbsp;Highest vol day</div>
      </td>
      <td>...</td>
      <td class="badges">...</td>
      <td class="outcome">...</td>
    </tr>
    <!-- Future day (outcomes pending) -->
    <tr>
      <td class="day-cell">[Day Month DD]</td>
      <td>...</td>
      <td class="badges">...</td>
      <td class="outcome"><div class="pending">Pending</div></td>
    </tr>
    <!-- OPEX Friday -->
    <tr style="background: #f9f8ff;">
      <td class="day-cell day-fri">
        Fri [Month DD]
        <div class="day-sub">Quad Witching</div>
      </td>
      <td>
        <div class="event-name">Monthly OPEX + Quad Witching</div>
        <div class="event-note">No major data · Max gamma · Extreme volume · Avoid new positions</div>
      </td>
      <td class="badges">
        <div class="badge-row"><span class="badge b-purple">OPEX</span></div>
      </td>
      <td class="outcome"><div class="pending">Pending</div></td>
    </tr>
  </tbody>
</table>
</body>
</html>
```

---

## BADGE COLOR REFERENCE

| Badge class | Color | Use for |
|-------------|-------|---------|
| `b-red`     | Red   | Fed decisions, central bank rate decisions |
| `b-amber`   | Amber | Commodities (EIA crude, nat gas), inflation data |
| `b-blue`    | Blue  | Macro data releases (CPI, GDP, jobs, housing) |
| `b-purple`  | Purple | Catalysts (conferences, product launches), OPEX |
| `b-gray`    | Gray  | Earnings reports |

**Intl Macro** uses `b-blue`. **Central Bank** (non-Fed) uses `b-red`.

---

## DESIGN RULES

- **One row per trading day** — never split a day across multiple rows
- **Collapse related items** — e.g. "Empire State Mfg · Industrial Production · Capacity Utilization" on one line
- **Notes only when needed** — add `.event-note` only when the headline alone is ambiguous
- **Badge column width** — fixed at 90px (`width: 90px`), badges stack vertically in a flex column
- **Outcomes column** — past events show actuals with color-coded values (green beat / red miss); future events show italic "Pending". Align outcomes to their corresponding events using `.sep` dividers
- **No OPEX banner** — OPEX context lives only in the row's day label (`day-sub`) and event note
- **Market holidays** — Good Friday, half-days, etc. use the Friday highlight style (`background: #f9f8ff`, `day-fri` color). Note data releases to closed markets and flag deferred reaction (e.g., "NFP released to closed markets · Reaction deferred to Monday")
- **Output filename** — `market_events_[start-date]_[end-date].html` (e.g. `market_events_march_30_april_4_2026.html`)
- **Output path** — always `/media/SHARED/trade-data/market-events/`

---

## QUALITY CHECKLIST

- [ ] Events sourced from web search for the correct date range
- [ ] Same-day macro releases consolidated onto one line with `·`
- [ ] FOMC/Fed day row has `background: #fff9f9` and `Highest vol day` label
- [ ] OPEX/Quad Witching/Good Friday row has `background: #f9f8ff` and correct day color
- [ ] Badge colors match the reference table above
- [ ] Outcomes column filled for past events (color-coded), "Pending" for future events
- [ ] Market holidays noted with deferred reaction dates
- [ ] File saved to `/media/SHARED/trade-data/market-events/` with `.html` extension
