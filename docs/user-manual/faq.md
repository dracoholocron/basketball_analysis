# Frequently Asked Questions

## Account & Login

**Q1: I forgot my password. How do I reset it?**  
Contact your team administrator. They can reset your password in Admin → Players/Users.

**Q2: Can I have multiple teams on one account?**  
Yes. Your account is linked to an organization, which can have multiple teams and seasons.

**Q3: I see "Session expired" — what does that mean?**  
Your login session timed out (typically after 24 hours). Just sign in again.

---

## Simulation & Keys to Victory

**Q4: Why is my win probability always 50%?**  
The simulation needs historical box scores to calculate meaningful probabilities. Upload box scores in Admin → Box Scores first.

**Q5: What are Keys to Victory based on?**  
They are derived from a logistic regression model trained on your uploaded box scores. The model identifies which statistics most strongly correlate with wins.

**Q6: Can I add my own Keys to Victory?**  
Not directly. Keys are auto-generated from your stats data. You can, however, pin which ones you consider most important using the 📌 pin button.

**Q7: Why do some keys show "↑ Boost" and others "↓ Risk"?**  
A **Boost** key (green) improves win probability when you execute it. A **Risk** key (red) hurts your chances when it happens — for example, high turnover rate.

**Q8: Can I pin more than 3 priority keys?**  
No. The maximum is 3. This is intentional — focusing on more than 3 keys during a game reduces effectiveness.

---

## Game Tracker

**Q9: Can I track a game on my phone?**  
Yes. The Game Tracker is mobile-friendly, though the 3-column layout collapses on smaller screens.

**Q10: I accidentally logged a wrong event. Can I undo it?**  
Yes. Click the **Undo** button in the toolbar to remove the most recent event.

**Q11: The Follow-Up modal disappeared before I could record the rebound.**  
The modal auto-dismisses after 15 seconds. You can manually log a rebound by clicking on the court and selecting "Rebound" for the appropriate team.

**Q12: Why doesn't the clock sync with the real game clock?**  
The game clock is manual — you control it with the Play/Pause buttons. It doesn't sync with TV broadcasts or shot clocks automatically.

---

## Video Analysis

**Q13: What video formats are supported?**  
MP4 is recommended. Most common formats (MOV, AVI, MKV) are also accepted but may have longer upload times.

**Q14: How long does video analysis take?**  
Typically 5-20 minutes for a full game (2-3 GB file). Short clips (< 5 minutes) analyze in 1-3 minutes.

**Q15: The tracking boxes don't look accurate for one player. Why?**  
Player tracking can be confused by similar jersey colors or when two players are very close together. This is a known limitation of single-camera tracking.

---

## Training & Pose Analysis

**Q16: The analysis status is stuck at "analyzing." What should I do?**  
This indicates the GPU worker may be offline. Contact your system administrator to restart the `basketball-gpu-worker` Docker service.

**Q17: What angle should I film from for best pose results?**  
A 45° side angle (player facing right or left, full body visible) gives the most accurate joint angle measurements. Avoid filming from directly behind or in front.

**Q18: Can I analyze multiple players in one clip?**  
Yes. The system detects all visible players and assigns each a person_id. The metrics table shows data per person per frame.

---

## Play Builder

**Q19: How do I add multiple frames to one play?**  
Click **Add Frame** in the Play Builder toolbar. You can add as many frames as needed to show a full play sequence. Use the **▶ Animate** button to preview the animation.

**Q20: How do I export a play to PDF?**  
Click **Export PDF** in the top right of the Play Builder. For multi-frame plays, it generates one page per frame (or a grid if ≤ 4 frames).
