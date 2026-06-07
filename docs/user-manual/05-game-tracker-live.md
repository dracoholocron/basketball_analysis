# Game Tracker (Live)

## What is this

The Game Tracker is your courtside tool for logging every play in real time. It shows:
- Live scoreboard with a game clock
- Timeout counters for both teams
- A clickable court diagram to place events
- **Game Plan Alignment** panel showing whether your Top 3 priorities are working
- **Halftime Re-sim** to get updated AI adjustments at the half

## How to open it

Click **Game Tracker** in the sidebar, or navigate to `/game-tracker`.

![Game Tracker 3-column layout](./screenshots/10-game-tracker-3col.png)

## Step by step

### 1. Select a Matchup

Use the dropdown at the top to choose which matchup you're tracking.

### 2. Manage the Clock

The center panel shows the game clock in `MM:SS` format.

- **▶ Play** — starts the clock countdown
- **⏸ Pause** — stops the clock
- **⏭ Next Period** — advances to the next half/quarter and resets the clock
- **↩ Reset** — resets to full period time

### 3. Log Game Events

Click anywhere on the court diagram. A panel appears asking:
- **Which team?** (T1 = Your Team, T2 = Opponent)
- **What happened?** (2pt Made, 3pt Made, FT Made, Missed, Assist, Turnover, Rebound, Block, Steal, Foul)

After logging a missed shot, a **Follow-Up modal** appears for 15 seconds, letting you quickly log an offensive or defensive rebound and assign it to a player by jersey number.

![Follow-Up Modal](./screenshots/12-followup-modal.png)

### 4. Track Roster Stats

The left panel shows **Your Team's** roster with live points/rebounds/assists per player.  
The right panel shows the **Opponent's** roster stats.

### 5. Game Plan Alignment (Right panel)

If you pinned Top 3 priorities in Game Day, the alignment panel shows each one with a status badge:
- 🟢 **REINFORCED** — you're executing this key successfully
- 🔴 **DRIFTING** — this key is slipping; time to adjust
- ⚪ **IN_FLOW** — neutral, not enough data yet

![Plan Alignment](./screenshots/13-plan-alignment.png)

### 6. Halftime Re-sim

At halftime, click **Halftime Re-sim** to:
1. Re-run 500 simulated games using first-half data
2. Get updated win probability
3. Receive 2-3 AI-generated **halftime adjustments** with HIGH/MEDIUM/LOW priority

![Halftime Adjustments](./screenshots/14-halftime-adjustments.png)

In **Coach Mode**, adjustments appear as short, direct commands without statistical rationale.

### 7. View Event History

Click **History** to see the last 20 logged events in reverse order.

## Tips
- Use the **Event Heatmap** button to see a full shot chart after the game
- If you mislog an event, click **Undo** to remove the last entry
- Switch between "Shots", "Heat", and "Both" views using the toggle above the court

## Common pitfalls
- "Game Plan Alignment panel is empty" → Pin at least 1 priority key in Game Day first
- "Halftime Re-sim fails" → You need at least 1 game event logged before running it
- "Clock doesn't stop automatically" → You must click Pause manually; the clock runs independently of event logging

## Next step
→ [Event Heatmap](./06-event-heatmap.md)
