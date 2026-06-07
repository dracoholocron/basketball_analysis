# Admin

## What is this

The Admin section is where you set up the foundational data: organizations, seasons, teams, players, and box scores. These are the building blocks for simulations and scouting reports.

## How to open it

Click **Settings** in the sidebar, or navigate to `/admin`.

![Admin dashboard](./screenshots/28-admin-dashboard.png)

## Sections

### Organizations
Your top-level entity. Most setups have one organization (e.g. "Springfield University Athletics").

### Seasons
Create a season (e.g. "2024-25") to group all games played in that period.

### Teams
Create team entries for both your own team(s) and opponent teams. Each team needs a name.

### Players
Add players to teams with: name, jersey number, position. Players appear in the Game Tracker roster panels and Key Matchup tables.

### Box Scores
Import or manually enter game box scores. These are the statistical foundation for:
- Monte Carlo simulation
- Keys to Victory
- Scouting reports

To import, go to **Admin → Box Scores → Import CSV**. The CSV format requires columns: `player_name, pts, reb, ast, stl, blk, tov, fg_made, fg_att, fg3_made, fg3_att, ft_made, ft_att`.

## Tips
- Create opponent teams even if you don't have their roster — you can still generate scouting reports from box scores
- The more box scores you upload (at least 5 games per team), the more accurate the simulation
