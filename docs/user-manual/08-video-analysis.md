# Video Analysis

## What is this

Upload game film and Basketball IQ automatically tracks every player on the court using computer vision. You can then watch the annotated video with colored bounding boxes or skeleton overlays directly in the browser.

## How to open it

Click **Games & Video** in the sidebar, or navigate to `/games`.

![Videos list](./screenshots/21-videos-list.png)

## Step by step

### 1. Create or Select a Game

Click on a game from the list, or create a new one first.

### 2. Upload Video

Scroll to the "Upload Video" section → drag and drop your MP4 file or click to browse → click Upload.

An **Analysis Job** starts automatically. You can monitor its progress in **Analysis Jobs** (sidebar).

### 3. View the Annotated Video

Once the job is done, return to the game detail page:
- Click **Download Annotated Video** to save the file
- Click **View with Overlay** to play in-browser

![Video with overlay](./screenshots/22-video-with-overlay.png)

### 4. Overlay Controls

Toggle between:
- **Bounding Box** — colored rectangles around players
- **Skeleton** — joint-by-joint pose skeleton
- **Both** — combined

## Tips
- Best results with clear, high-resolution footage (1080p or higher)
- If you see tracking drift, it usually improves after the first 30 seconds as the model stabilizes
