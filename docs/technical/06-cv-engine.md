# CV Engine — Player Tracking & Pose Estimation

## Overview

The Computer Vision (CV) engine runs as a **Celery GPU worker** and processes two types of tasks:
1. **Game video tracking** — detects players and assigns bounding boxes + team labels
2. **Training pose analysis** — detects body joints and calculates shooting form metrics

## Technology

- **Model**: YOLOv8-pose (`ultralytics` library)
- **Input**: MP4 video files (downloaded from MinIO)
- **Output (tracking)**: JSONL file where each line is `{"frame": N, "players": [{"track_id": X, "bbox": [...], "team": 1|2}]}`
- **Output (pose)**: PostgreSQL rows in `pose_keypoints` and `shooting_form_metrics` tables

## Tracking Pipeline

```
Video (MinIO) → Frame extraction → YOLOv8 detection → ByteTrack tracking
→ Team classification (jersey color clustering) → JSONL output → MinIO upload
→ Update job status to "done"
```

### Frame Extraction

Uses `cv2.VideoCapture` to read frames. Processing is done at:
- Full FPS for short clips (< 5 min)
- Every 2nd frame for longer videos to reduce GPU memory

### Player Detection

YOLOv8 detects `person` class objects. Detection threshold: `conf=0.35`.

### Tracking

ByteTrack maintains consistent `track_id` across frames, even when players briefly leave the frame.

### Team Classification

K-means clustering (k=2) on jersey pixel colors within each detected bounding box. Works best when the two teams have clearly different colors.

### Output Format (tracks JSONL)

```json
{"frame": 0, "players": [{"track_id": 1, "bbox": [100, 50, 250, 350], "team": 1}, ...]}
{"frame": 1, "players": [...]}
```

## Pose Estimation Pipeline

```
Training video (MinIO) → Frame extraction → YOLOv8-pose detection → Keypoint extraction
→ Joint angle calculation → PostgreSQL insert → Status update to "done"
```

### Keypoints Detected

YOLOv8-pose detects 17 COCO keypoints:
nose, left_eye, right_eye, left_ear, right_ear, left_shoulder, right_shoulder,
left_elbow, right_elbow, left_wrist, right_wrist, left_hip, right_hip,
left_knee, right_knee, left_ankle, right_ankle

### Angle Calculation

Joint angles are computed using the dot product formula on 3-point vectors (proximal bone → joint → distal bone).

### GPU Memory Requirements

| Task | Min VRAM |
|------|----------|
| Game tracking (720p) | 4 GB |
| Game tracking (1080p) | 6 GB |
| Pose estimation | 2 GB |

## Stub Implementation

When no GPU is available, the `run_pose_analysis_task` generates **synthetic pose data** for development/testing. The stub simulates realistic joint angle distributions so the frontend can be tested without GPU hardware.

To use real CV processing, replace the stub in `api/app/worker/gpu_tasks.py` with the full YOLOv8 pipeline and ensure `ultralytics` is installed in the GPU worker container.

## Performance

- Tracking: ~5-8 FPS on GTX 1080; ~15-20 FPS on RTX 3080
- Pose estimation: ~10-15 FPS per person on GTX 1080
