# Scenario: Training — Shooting Form Analysis

**Audience**: Coach, trainer, or player development staff  
**Time required**: 5-10 minutes to set up; ~10 minutes for analysis  
**Goal**: Get objective feedback on a player's shooting mechanics from practice video

---

## Step 1: Create a Training Session

1. Click **Training** in the sidebar
2. Click **New Session**
3. Enter the drill name (e.g. "Free Throw Practice — John")
4. Click **Create**

---

## Step 2: Upload the Video Clip

1. On the Training list, find your session
2. Click the **Upload Video** button next to it
3. Select the video file (MP4, max ~500MB recommended)
4. Wait for the upload to complete — status changes to "uploaded"

---

## Step 3: Run Pose Analysis

1. Click on the session to open its detail page
2. Click **Run Pose Analysis**
3. Status changes to "analyzing" — wait 2-5 minutes

The AI analyzes every video frame to detect:
- All body joints (shoulder, elbow, wrist, hip, knee, ankle)
- Ball position and hoop location (when visible)
- Joint angles at key moments

---

## Step 4: Review the Results

Once complete, the detail page shows:

**Video with Overlay**: Toggle between Bounding Box view and Skeleton view to see the AI's tracking. The player's skeleton is drawn frame by frame.

**Average Joint Angles (HUD)**:
| Metric | What it means |
|--------|--------------|
| Elbow L / Elbow R | Arm bend at release — ideally 85-95° |
| Knee L / Knee R | Leg bend at jump — ideally 150-170° at peak |
| Hip L / Hip R | Hip angle, indicates forward lean |
| Torso Lean | How much the body tilts forward — ideally < 5° |
| Back Angle | Spine alignment |
| Release Angle | Ball angle at release — ideally 45-55° for optimal arc |

**Frame-by-Frame Table**: Scroll down to see exact metrics for each video frame.

---

## Step 5: Discuss with the Player

1. Enable **Coach Mode** for a simpler view
2. Focus on 1-2 metrics that are most out of range
3. Show the skeleton overlay at the specific frame where the issue occurs
4. Record your feedback in the Session Notes (coming soon)

---

## Tips
- Use a tripod or fixed camera at 45° angle for best pose detection results
- The AI works best when the player's full body is visible in the frame
- Upload clips of 30-90 seconds for fastest analysis; longer clips take proportionally longer
- Compare multiple sessions over time to track improvement

## Common pitfalls
- "Analysis status stuck at 'analyzing'" → This may indicate the GPU worker is offline; notify your administrator
- "Skeleton looks incorrect" → The AI may have confused two players; try a clip where only one player is visible
- "Release angle shows 0°" → Ball was not visible in enough frames; ensure the ball appears clearly in the clip

## Next step
→ [Back to Manual Home](../README.md)
