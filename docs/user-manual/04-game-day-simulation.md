# Game Day & Simulation

## What is this

Game Day is where you prepare your game plan before tip-off. It runs a Monte Carlo simulation (1,000 virtual games) to estimate win probability, identifies your **Keys to Victory**, and lets you pin your **Top 3 Priorities** for the coaching staff to focus on.

**Monte Carlo simulation**: the platform plays out your game 1,000 times using your team's historical stats. The percentage shown is how often your team wins those simulated games.

## How to open it

Click **Game Day** in the sidebar, or navigate to `/game-day`.

![Game Day Keys](./screenshots/07-game-day-keys.png)

## Step by step

### 1. Select a Matchup

From the left panel, click a matchup name to load its data. If you haven't created one yet, click **New Matchup** in the top right.

### 2. Run the Simulation

Click **Run Simulation (1,000 games)**. This takes 3-10 seconds. You'll see:
- **Win Probability donut** — e.g. 62% means you win 6.2 out of 10 simulated games
- **Projected Score Range** — bar chart showing low/average/high scores for both teams

### 3. Review Keys to Victory

Below the simulation results, you'll see 5-8 **Keys to Victory** cards. Each one is a statistical factor that most influences the win probability.

Each card shows:
- **Title** — what the key is (e.g. "Limit opponent 3-point attempts")
- **↑ Boost / ↓ Risk** badge — green means doing this helps you win; red means it hurts
- **Impact bar** — wider = stronger effect on win probability
- **Toggle switch** — turn a key on/off to see how it changes the win probability

### 4. Pin Top 3 Priorities

Click the **📌 pin icon** on up to 3 keys to mark them as priorities. These appear:
- In the **Top 3 Priorities** panel at the top of the section
- In the **Game Tracker** as your Game Plan Alignment targets
- In the **Matchup Workspace** overview tab

To unpin, click the pin icon again.

![Priority pin](./screenshots/08-game-day-priority-pin.png)

### 5. Situational Adjustments

Click **Generate with AI** to get If→Then game adjustments (e.g. "If opponent goes on a 6-0 run → Call timeout and switch to zone defense").

### 6. Game Plan Notes

Four text areas let you write and auto-save:
- Rotation Plan
- Strategic Playbook
- Defensive Keys
- Coach Notes

## Tips
- **Self-Scout Mode** (bottom of sidebar) flips the perspective so you can analyze how opponents see you
- Pinning 3 keys and sharing them verbally with players before tip-off improves focus
- Re-run the simulation after uploading new box scores to get more accurate probabilities

## Common pitfalls
- "Keys to Victory are empty" → The simulation requires at least one box score for each team
- "I see 50% win probability" → No historical stats uploaded yet; add box scores in Admin → Box Scores

## Next step
→ [Game Tracker (Live)](./05-game-tracker-live.md)
