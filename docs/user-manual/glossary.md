# Glossary

## Basketball IQ Platform — Key Terms

---

**Box Score**  
A statistical summary of a basketball game: points, rebounds, assists, steals, blocks, turnovers, and field goal attempts for each player. Used to train the simulation model.

**Coach Mode**  
A UI toggle that converts technical statistics into plain, locker-room-friendly language. Activating it hides complex numbers and shows phrases like "6 wins in 10" instead of "62% win probability."

**DRIFTING**  
A status badge in the Game Plan Alignment panel meaning your team is falling away from this key during the game. Time to make an adjustment.

**Event Heatmap**  
A visual representation of shot locations on the court, colored by frequency. Hot zones (red) indicate areas where many shots were attempted.

**Follow-Up Modal**  
A pop-up that appears after logging a missed shot, allowing you to quickly record the rebound (offensive or defensive) and the player responsible.

**Game Plan Alignment**  
A real-time panel in the Game Tracker that compares your pre-game priorities (set in Game Day) to live game stats. Shows REINFORCED, DRIFTING, or IN_FLOW for each priority.

**IN_FLOW**  
A status badge meaning a key is running neutrally — not clearly working well or poorly yet. Usually seen early in the game.

**Joint Angle**  
The angle formed at a body joint (e.g. elbow, knee). Measured in degrees. Used in shooting form analysis to evaluate player mechanics.

**Key to Victory**  
A statistical factor identified by logistic regression as strongly correlated with winning or losing. Examples: "Limit opponent assists", "Win the rebounding margin by 5+".

**Logistic Regression**  
A mathematical model used to calculate win probability. The platform uses it to weigh each Key to Victory's importance based on historical box score data.

**Matchup**  
A game preparation record linking your team to an opponent. Contains the simulation, scouting report, plays, notes, and live game events for a specific game.

**Matchup Workspace**  
A tabbed hub that brings together scouting, simulation, plays, live tracker, and notes for a single matchup.

**Monte Carlo Simulation**  
A method that runs 1,000 random simulated games using your team's statistics to estimate win probability. Named after the Monte Carlo casino due to its randomness.

**Pose Estimation**  
AI technology that detects and maps body joints (shoulder, elbow, knee, etc.) from video frames. Used in the Training module to analyze shooting mechanics.

**Priority Key**  
One of up to 3 Keys to Victory that you pin (mark as highest importance). Priority Keys appear prominently in the Game Tracker alignment panel and Matchup Workspace.

**REINFORCED**  
A status badge meaning your team is executing this key successfully during the live game. Keep it up.

**Release Angle**  
The angle at which the ball leaves a shooter's hands. Optimal basketball release angle for a free throw is approximately 45-55° for maximum arc and margin of error.

**Self-Scout Mode**  
A toggle (bottom of sidebar) that flips the Game Day perspective so you can analyze how opponents see your own team's tendencies and weaknesses.

**Scouting Report**  
An AI-generated analysis of an opponent's tendencies, strengths, and weaknesses based on their uploaded box scores.

**Weekly Rhythm**  
The 5-step framework for preparing each game: Scouting → Simulation → Game Plan → Plays → Tracker. Shown as a progress stepper in the Dashboard and Matchup Workspace.

**Win Probability**  
The percentage of simulated games (out of 1,000) in which your team wins. A higher number favors your team; 50% means even odds.

**YOLOv8-pose**  
The AI model used for player tracking and pose estimation. YOLO stands for "You Only Look Once" — a fast, real-time object detection architecture.
