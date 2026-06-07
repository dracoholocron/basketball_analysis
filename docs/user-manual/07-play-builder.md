# Play Builder

## What is this

The Play Builder is a digital whiteboard for diagramming basketball plays. Draw player routes, add arrows for passes and cuts, create multi-frame sequences, and export to PDF.

## How to open it

Click **Play Builder** in the sidebar, or navigate to `/play-builder`.

![Play Builder canvas](./screenshots/17-play-builder-canvas.png)

## Step by step

### 1. Use the Tool Palette

- **Select** (arrow) — click and drag players to reposition them
- **Player** — click to add a teammate (blue)
- **Opponent** — click to add a defender (red/violet)
- **Pass / Cut / Dribble / Screen** — draw arrows showing movement
- **Free Draw** — draw freeform paths

### 2. Filter the Play Library

Use the filters on the left:
- **Type** (Offense/Defense/Special)
- **Pace** (half-court, transition, BLOB, SLOB)
- **Tag** (vs Zone, vs Man, Out of Bounds, etc.)

### 3. Add Frames for Multi-Step Plays

Click **Add Frame** to create a second canvas showing the continuation of the play.
- Each frame can have its own player positions and notes
- Click **▶ Animate** to preview the play in sequence

![Multi-frame view](./screenshots/19-play-builder-frames.png)

### 4. Add Notes

Each frame has a **Notes** field at the bottom. Use it to write coaching cues for that moment in the play.

### 5. Import PDF

Click **Import PDF** to add a play from a PDF file. The filename becomes the play name.

### 6. Export

- **Export PDF** — saves all frames as a PDF (one frame per page for complex plays)
- **Export PNG** — saves the current canvas as an image

## Tips
- Use "vs Zone" tag to organize your zone-specific plays
- Quick Add buttons (Team / Opp) add default players instantly without clicking the tool first
- Undo/Redo (Ctrl+Z / Ctrl+Y) work as expected

## Common pitfalls
- "My play doesn't save" → Click the save button or wait for auto-save after 1 second
- "PDF export is blank" → Make sure there are players or arrows on the canvas
