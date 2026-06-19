# Benchmark en RunPod (RTX 4090) — guía paso a paso

Objetivo: correr **el mismo análisis** (mismo video + mismas anotaciones) en una RTX 4090 en la
nube y comparar tiempos/calidad contra la RTX 5070 local. En la 4090 (Ada, toolchain maduro) se
desbloquea lo que aquí está bloqueado por sm_120: **`vos_optimized` (torch.compile de SAM2)**,
**NVENC** y (opcional) TensorRT — además de más VRAM (24 GB).

Costo estimado de la prueba completa: **&lt; $2** (4090 ≈ $0.35–0.69/h, facturación por segundo).

---

## Parte 1 — Preparación LOCAL (antes de pagar nada)

1. **Exportar las anotaciones del juego** (clics de balón, aros, landmarks, exemplars, jerseys):
   ```bash
   cd z:/code/basketball_analysis
   python basketball_analysis/tools/export_game_annotations.py \
       --game <GAME_ID> --out bench/annotations.json
   ```
2. **Copiar los modelos custom** desde el volumen del worker (los públicos se auto-descargan):
   ```bash
   mkdir -p bench/models
   docker compose cp worker-gpu:/app/engine/models/player_detector.pt        bench/models/
   docker compose cp worker-gpu:/app/engine/models/ball_detector__prev.pt    bench/models/
   docker compose cp worker-gpu:/app/engine/models/court_keypoint_detector.pt bench/models/
   ```
   *(SAM2/EfficientTAM, yolo11n-pose y EasyOCR se descargan solos en el pod.)*
3. **Tener a mano el video original** del juego (p. ej. `bench/game.mp4`). Si solo está en MinIO:
   descárgalo desde la UI del juego o desde la consola de MinIO (localhost:9001).

## Parte 2 — Crear el pod en RunPod

4. Cuenta en [runpod.io](https://www.runpod.io) → *Billing* → carga **$5–10**.
5. *Pods → Deploy*: GPU **RTX 4090** (Community Cloud = más barato; Secure = más fiable).
   - Template: **RunPod PyTorch 2.x (CUDA 12.x)** (ya trae torch con CUDA).
   - Disco del contenedor/volume: **60 GB**.
   - Habilita **SSH** (y/o Jupyter). Deploy.
6. Conéctate por SSH (RunPod muestra el comando exacto) o usa la Web Terminal.

## Parte 3 — Setup en el pod (una vez, ~10 min)

7. Sistema + código:
   ```bash
   apt-get update && apt-get install -y ffmpeg git
   # Repo privado: usa un token (Settings→Developer settings→PAT) o sube un zip con runpodctl
   git clone https://<TU_PAT>@github.com/<tu_usuario>/basketball_analysis.git /workspace/app
   cd /workspace/app/basketball_analysis
   ```
8. Dependencias del engine (torch ya viene en la imagen):
   ```bash
   grep -v "^torch" requirements.txt | pip install -r /dev/stdin
   pip install "git+https://github.com/facebookresearch/sam2.git" lap easyocr
   pip install "git+https://github.com/yformer/EfficientTAM.git"   # opcional: piloto ETAM
   ```
9. Subir video + modelos + anotaciones — en el pod ejecuta `runpodctl receive`, y en tu máquina:
   ```bash
   # instala runpodctl local (una vez): https://github.com/runpod/runpodctl/releases
   runpodctl send bench/game.mp4 bench/annotations.json bench/models/*
   # pega en el pod el código de recepción que te da el comando
   ```
   Coloca los modelos donde el engine los busca:
   ```bash
   mv player_detector.pt ball_detector__prev.pt court_keypoint_detector.pt \
      /workspace/app/basketball_analysis/models/
   ```

## Parte 4 — Configurar y correr el benchmark

10. Variables (replican el compose local + **desbloqueos de la 4090**):
    ```bash
    cd /workspace/app/basketball_analysis
    # ── espejo del compose local (paridad del experimento) ──
    export BA_DEVICE=cuda BA_YOLO_HALF=true BA_YOLO_BATCH_SIZE=32 BA_CHUNK_SIZE=3000
    export BA_PLAYER_MAX_H=1080 BA_PLAYER_IMGSZ=1280 BA_BALL_IMGSZ=960
    export BA_COURT_KP_IMGSZ=1536 BA_COURT_KP_BATCH_SIZE=24 BA_COURT_KP_SAMPLE_EVERY=2
    export BA_TRACKER=botsort BA_TRACK_STITCH=true BA_JERSEY_OCR=true
    export BA_POSE_TOPDOWN=true BA_HOOP_PROPAGATE=true BA_BALL_SAM2=true
    export BA_BALL_MAX_JUMP_PX=80 BA_BALL_DEBUG=true
    # ── desbloqueos 4090 (lo que estamos midiendo) ──
    export BA_SAM2_VOS_OPTIMIZED=true     # torch.compile de SAM2 (bloqueado en sm_120)
    export BA_VIDEO_ENCODER=nvenc         # encode H.264 por GPU (bloqueado en sm_120)
    export BA_SAM2_OFFLOAD_STATE=false BA_SAM2_CHUNK_IN_RAM=true
    export BA_SAM2_CHUNK=1500             # pods suelen tener 60GB+ RAM (chunk ≈ frames×12.6MB)
    ```
11. Correr:
    ```bash
    python tools/run_cloud_benchmark.py \
        --video /workspace/game.mp4 \
        --annotations /workspace/annotations.json \
        --ball-model models/ball_detector__prev.pt \
        --out-dir /workspace/bench_out
    ```
    Imprime cada etapa con tiempo acumulado y al final un **resumen por etapa + fuentes del
    balón** (`bench_out/benchmark.json`).

## Parte 5 — Resultados y cierre

12. Verifica en el log: `SAM2: vos_optimized (torch.compile) enabled` y
    `Annotated video encoded with h264_nvenc` (si alguno cae a fallback, anótalo — es parte del
    resultado).
13. Descarga resultados (desde el pod): `runpodctl send /workspace/bench_out/*` → recibe local.
14. **⏹ Stop / Terminate el pod** (Stop conserva el disco y sigue cobrando almacenamiento barato;
    Terminate borra todo). No lo dejes corriendo.
15. Compara contra el baseline local (RTX 5070, video 25.101 frames):

    | Etapa | Local 5070 | 4090 (anotar) |
    |---|---|---|
    | player_tracking | ~14 min | |
    | ball + SAM2 stride 1 | ~25–35 min | |
    | court keypoints | ~8 min | |
    | team assignment | ~5 min | |
    | pose | ~12 min | |
    | hoop | ~9 min | |
    | drawing + encode | ~8 min | |
    | **Total** | **~62–92 min** | |

    Calidad: misma cobertura/fuentes de balón (`Ball sources`), mismos eventos ≈ mismas anotaciones.

## Notas
- **Misma semilla de comparación**: usa el MISMO video y el MISMO `annotations.json` que la corrida local.
- El primer chunk de SAM2 con `vos_optimized` paga el costo de compilación (~1–3 min); se amortiza.
- Si el pod no tiene `ffmpeg` con NVENC (raro en Ubuntu 22.04), el código cae a libx264 sin romper.
- Para probar **EfficientTAM** en el mismo pod: re-ejecuta el paso 11 cambiando
  `--ball-model` no — basta exportar `BA_SAM2_CHECKPOINT=models/efficienttam_s.pt` y
  `BA_SAM2_CONFIG=configs/efficienttam/efficienttam_s.yaml` (se auto-descarga) y comparar.
- Costo: 2–3 h de pod (setup + 2 corridas) ≈ **$1–2**.
