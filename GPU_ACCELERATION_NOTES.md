# Aceleración GPU del pipeline — intentos, bloqueos y cómo reintentar

Bitácora de los intentos de acelerar el pipeline **sin perder calidad** y por qué varios quedaron
bloqueados por el entorno. Pensado para **reintentar tras actualizar driver NVIDIA / librerías**.
Última evaluación: **2026-06-11**.

## Entorno (importante para el diagnóstico)
- **GPU**: NVIDIA RTX 5070 12 GB — **Blackwell, compute capability `sm_120`** (muy nueva).
- **Host**: Windows 11 + **WSL2** + Docker Desktop (datos en `Z:\dockerData`).
- **Imagen worker** (`worker/Dockerfile`): `pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime`.
- **Clave del diagnóstico**: PyTorch base **sí** soporta sm_120 → el pipeline (YOLO/SAM2 en `.pt`)
  corre bien. Lo que falla son las **librerías auxiliares de aceleración**, cuyos binarios aún no
  traen kernels para sm_120 (estado de junio 2026).

## Baseline de referencia (para medir mejoras futuras)
Video de prueba: 11.989 frames (~720p), ~**42–45 min** total. Perfil GPU por etapa (RTX 5070):

| Etapa | Tiempo | GPU% | Nota |
|---|---|---|---|
| player_tracking (BoT-SORT, imgsz 1280) | ~6.6 min | ~25% | track 1-frame + GMC en CPU |
| ball detect (imgsz 960) | ~2.4 min | ~45% | |
| court keypoints (imgsz 1536) | ~4.5 min | ~65% (picos 100) | **VRAM al tope ~11.7 GB** |
| **SAM2 balón** (chunk 500, stride 1) | **~14 min** | ~45% (sierra 88/5) | **cuello real, secuencial** |
| team assignment (FashionCLIP coseno) | ~1–2 min | ~30% | decode-skip |
| pose (top-down) | ~5–7 min | ~43% | |
| hoop detect + propagación OF | ~4.2 min | 2ª mitad ~9% | OF en CPU |
| drawing + encode (libx264) | ~5.4 min | ~8% | dibujo por-frame en CPU |

Calidad de referencia: **cobertura de balón 91%** (balón original + SAM2 base_plus), coseno de equipos
activo, eventos correctos. Cualquier optimización debe **mantener** esto.

---

## ✅ Lo que SÍ funcionó (en producción, calidad idéntica)
- **Prefetch de decodificación** (`utils/video_utils.iter_video_frames_prefetch`): hilo lector + cola
  acotada que solapa decode con cómputo GPU. Adoptado en player detect/track, ball detect, hoop
  detect, pose y el flujo óptico de movimiento global. Mismos frames → resultados idénticos.
- **SAHI selectivo** (`trackers/ball_tracker.refill_missing_with_sahi`): decodifica **solo** los frames
  de huecos largos (antes decodificaba todo el video). Idéntico resultado, mucho menos decode.
- **SAM2 doble-buffer** (`ball_sam2/sam2_ball_tracker.py`): el productor escribe el siguiente chunk
  mientras la GPU procesa el actual. Quedó (no hace daño), aunque su ganancia es marginal porque el
  hueco real es el `init_state` por chunk, no la escritura.

---

## ❌ Bloqueados por sm_120 / WSL (reintentar con drivers/libs nuevos)

### 1. NVENC (encode H.264 por GPU)
- **Qué**: re-encode del video anotado con `h264_nvenc` en vez de libx264 (etapa de ~5 min con GPU ~8%).
- **Error 1** (sin capability): `Cannot load libnvidia-encode.so.1`.
  **Fix aplicado**: añadir `video` a `NVIDIA_DRIVER_CAPABILITIES` (`compute,utility,video`) en
  `docker-compose.yml` (worker-gpu y worker-sam3lab). Eso expuso la lib.
- **Error 2** (tras exponer la lib): `The minimum required Nvidia driver for nvenc is (unknown) or
  newer` → `Error initializing output stream ... h264_nvenc`. El driver no expone la API NVENC para
  esta GPU/SDK.
- **Estado**: fijado `BA_VIDEO_ENCODER=libx264` (el código intenta nvenc y cae a libx264).
- **Cómo reintentar**: poner `BA_VIDEO_ENCODER=nvenc` y probar dentro del worker:
  `ffmpeg -f lavfi -i testsrc=duration=1:size=256x256:rate=10 -c:v h264_nvenc -f null -`
  (returncode 0 = funciona). El `NVIDIA_DRIVER_CAPABILITIES` con `video` ya está puesto.
- **Techo esperado**: bajo — el grueso de "drawing" es el dibujo por-frame en CPU, no el encode.

### 2. SAM2 `vos_optimized` (torch.compile / Triton)
- **Qué**: `build_sam2_video_predictor(..., vos_optimized=True)` compila los componentes pesados de
  SAM2 → "major speedup" en propagación, **mismos pesos**. Atacaría el cuello de ~14 min.
- **Error**: `collect2: error: ld returned 1 exit status` — Triton no enlaza (referencia a
  `/usr/lib/wsl/drivers/...`). Peor: el compile es **perezoso** (durante la propagación), así que la
  excepción tumbaba SAM2 **entero** → **regresión de cobertura** (sin fusión SAM2).
- **Estado**: `BA_SAM2_VOS_OPTIMIZED=false` por defecto (settings + compose). Hay `try/except` en el
  build, pero NO cubre el fallo perezoso de propagación → por eso default OFF.
- **Cómo reintentar**: cuando Triton enlace en este entorno, poner `BA_SAM2_VOS_OPTIMIZED=true`.
  **Antes de confiar**, validar que SAM2 corra completo y la cobertura siga 91% (el modo de fallo es
  silencioso). Idealmente endurecer el código para reintentar con el predictor estándar si el compile
  falla en runtime.
- **Techo esperado**: alto si funciona (es el cuello principal).

### 3. TensorRT FP16 (detectores YOLO → `.engine`)
- **Qué**: exportar `player`/`ball`/`court`/`pose` a TensorRT FP16 (`export_tensorrt_engine`,
  `POST /models/export-tensorrt/{role}`, botón en *Admin → Modelos*). `YOLO(path)` carga `.engine`
  transparente; el registro de modelos lo activa/revierte en 1 clic.
- **Dato positivo**: TensorRT **11.0.0.114 instaló y `Init CUDA` OK** en sm_120 (no rechazó la GPU).
- **Error A — court (modelo de keypoints), `dynamic=True`**: ONNXRuntime
  `FAIL: Concat node '/model.12/Concat' ... Non concat axis dimensions must match: Axis 2 has
  mismatched dimensions of 1 and 2` (quirk de export de modelos keypoint con ejes dinámicos).
- **Error B — ball (detector plano)**: `CUDA error: no kernel image is available for execution on the
  device` → los binarios de `tensorrt-cu12` / `onnxruntime-gpu` **no traen kernels sm_120**.
- **Estado**: tarea/endpoint/botón **latentes**. Deps **NO horneadas** en la imagen (eran ~4.3 GB y no
  funcionan); el bloque está comentado en `worker/Dockerfile`. La tarea tiene parámetro `dynamic`
  (default True).
- **Cómo reintentar** (cuando salga TensorRT/onnxruntime con sm_120):
  1. Descomentar el `RUN pip install ... tensorrt-cu12 onnx onnxslim onnxruntime-gpu
     nvidia-modelopt[onnx]` en `worker/Dockerfile` (fijar versiones con soporte sm_120) y rebuild.
  2. Disparar export por rol; **empezar por detectores planos** (`ball`, `player`) — los de keypoints
     (`court`, `pose`) pueden necesitar `dynamic=False` por el bug del `Concat` (ojo: batch estático
     debe casar con el batch real del pipeline; pose usa batch variable).
  3. Activar y **validar calidad** (mAP/eventos/cobertura) vs el `.pt` antes de dejarlo (ver
     [FINE_TUNING.md](FINE_TUNING.md)). Revertir = 1 clic.
- **Techo esperado**: medio — acelera solo las etapas de detección (~18 min combinados) a ~1.5–2×
  FP16 → ~6–9 min de ahorro (~15–20%). **No** toca SAM2 (~14 min) ni el dibujo (CPU).

---

## Checklist al actualizar driver NVIDIA / librerías
1. `nvidia-smi` en el worker: confirmar driver nuevo. Probar NVENC con el self-test de arriba → si OK,
   `BA_VIDEO_ENCODER=nvenc`.
2. Probar Triton: si compila, `BA_SAM2_VOS_OPTIMIZED=true` y validar SAM2 completo + cobertura 91%.
3. Rehornear deps TensorRT (Dockerfile) con versiones sm_120; exportar `ball` primero y validar.
4. Re-perfilar con `(.git/gpu_prof.sh → .git/gpu_profile.csv)` y comparar contra el baseline de arriba.
5. Mantener SIEMPRE el criterio: **misma cobertura de balón (91%), coseno de equipos y eventos**.

## Qué NO perseguir
- **SAM 3 para el balón**: ~3.4× más lento que SAM 2.1 en 1 objeto (~2921 vs ~857 ms/frame), 3.45 GB.
  Útil solo para prompts de texto/concepto y multi-objeto. Mantener SAM 2.1; SAM 3 queda en el lab.
