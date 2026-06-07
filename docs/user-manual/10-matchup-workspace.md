# Matchup Workspace

## What is this

The Matchup Workspace is the all-in-one preparation hub for a specific game. It connects scouting, simulation, plays, live tracking, and notes into a single tabbed interface so you don't have to jump between modules.

Think of it as your **game folder** — everything for one matchup, in one place.

## How to open it

Click **Matchup Workspace** in the sidebar, or navigate to `/matchups`. Then click on a specific matchup.

![Matchup Workspace tabs](./screenshots/26-matchup-workspace-tabs.png)

## Step by step

### 1. Overview Tab

Shows:
- **Win Probability ring** (from last simulation)
- **5-step Weekly Prep progress** — Scouting → Simulation → Game Plan → Plays → Tracker
- **Top 3 Priority Keys** (if you've pinned them in Game Day)

Click any prep step to jump directly to that module.

### 2. Scouting Tab

Quick access link to the full Scouting Report for this matchup's opponent.

### 3. Simulation Tab

Quick access link to Game Day simulation for this matchup.

### 4. Plays Tab

Shows all plays linked to this matchup. A play is linked when you open it in Play Builder with a matchup selected.

Click **Open Play Builder** to create or edit plays, then link them back.

### 5. Live Tracker Tab

Shows the last 10 game events for this matchup, with a direct link to the full Game Tracker.

### 6. Notes Tab

A free-text field that **auto-saves** every second. Use it for:
- Game plan summaries
- Opponent tendencies
- Player matchup reminders
- Pre-game talk points

### Sidebar (right panel)

Always visible alongside any tab:
- **Win Probability** ring with link to simulation
- **Top 3 Priorities** mini list
- **Event Heatmap** link

## Tips
- Use the **?tab=plays** URL parameter to deep-link directly to the Plays tab (e.g. from a shared message)
- Notes auto-save, so you can type freely without worrying about losing work
- The win probability ring updates when you re-run the simulation in Game Day

## Common pitfalls
- "Plays tab is empty" → Link plays to this matchup by opening them in Play Builder while the matchup is selected
- "Tracker tab shows no events" → Go to the Game Tracker and make sure you selected this matchup
- "Prep steps never turn green" → Each step requires completing an action: generate a scouting report (step 1), run a simulation (step 2), add notes (step 3), link plays (step 4), log events (step 5)

## Next step
→ [Coach Mode](./12-coach-mode.md)
