# Versionado de modelos (selección de versión activa)

Permite tener **varias versiones** de cada modelo y elegir cuál está **activa** desde la
UI admin, de modo que revertir a una versión anterior sea **un clic** (sin reconstruir
el worker).

## Roles versionados
`player` (detector de jugadores) · `ball` (detector de balón) · `court` (keypoints de
cancha) · `pose` (esqueleto YOLO). SAM 2.1 ya es seleccionable por análisis
(*Calidad de tracking de balón*); FashionCLIP queda fijo.

## Cómo funciona
- Los **archivos** de modelos viven en el volumen `models_data` del `worker-gpu`
  (un solo contenedor GPU). Versionar = **más archivos en disco**, no más memoria:
  **solo se carga la versión ACTIVA** de cada rol, y solo durante su etapa del pipeline.
- El registro está en la tabla **`model_versions`** (rol, archivo, origen, métricas,
  activo). **Una sola versión activa por rol.**
- En cada análisis, el worker resuelve la versión activa por rol y la usa
  (`run_pipeline` recibe las rutas). Sin activa → usa el default histórico.
- Revertir = **Activar** otra versión en la UI → aplica en el **próximo análisis**, sin
  recrear el worker (se lee de la DB por job).

## UI
**Admin → Modelos** (`/admin/models`): por rol, lista de versiones con su origen y
métricas; la activa marcada; botón **Activar**; botón **Re-escanear modelos**.

## Registro de versiones
- **Re-escanear** (`POST /models/scan` → tarea `scan_models`): registra los archivos
  `.pt` presentes en `models_data` (rol inferido por nombre) y activa el canónico de
  cada rol si no hay activa. Corre tras desplegar y cuando agregues archivos.
- **Fine-tune** (`finetune_ball_detector`): guarda el resultado como
  `models/ball_detector__ft_<fecha>.pt` (NO sobrescribe el activo) y lo registra
  **inactivo** con sus métricas (mAP50, etc.). Lo revisas en la UI y lo **activas**
  cuando quieras. Para revertir, activas la versión anterior.
  **Antes de activar un fine-tune, sigue [FINE_TUNING.md](FINE_TUNING.md)** (set de
  validación real + comparación contra el activo; no te fíes del mAP sobre pseudo-etiquetas).

## TensorRT FP16 (acelerar detectores sin perder calidad)
> **Estado en este entorno (RTX 5070 / Blackwell sm_120 + WSL, 2026-06): NO funcional aún.** El export
> instala y arranca, pero `tensorrt-cu12`/`onnxruntime-gpu` no traen kernels para sm_120 → `CUDA error:
> no kernel image is available for execution on the device` (mismo bloqueo que NVENC y Triton/torch.compile;
> PyTorch base sí soporta sm_120, por eso el pipeline corre). El `.pt` queda intacto. La tarea/endpoint/UI
> quedan **latentes**: reintentar cuando publiquen TensorRT/onnxruntime con sm_120 (y rehornear las deps
> en `worker/Dockerfile`). El resto de la guía aplica para una GPU/entorno soportado.

Los detectores (`player`/`ball`/`court`/`pose`) cargan con `YOLO(path)` de Ultralytics, que también
carga archivos **`.engine` (TensorRT)**. Para acelerar una etapa:
- **Admin → Modelos → botón «TensorRT FP16»** del rol (o `POST /models/export-tensorrt/{role}`) →
  tarea `export_tensorrt_engine` en el **worker-gpu** que exporta el `.pt` activo a
  `models/<role>__trt_fp16_<fecha>.engine` (`half=True`, `imgsz` del rol, `dynamic=True`) y lo
  registra **INACTIVO**.
- **Valida antes de activar** (ver [FINE_TUNING.md](FINE_TUNING.md)): corre un análisis con el engine
  activo y compara métricas/eventos/cobertura contra el `.pt`. FP16 mantiene mAP, pero confírmalo.
- Activar/revertir = 1 clic. **Los engines son específicos de GPU/driver/imgsz/batch**: si cambias de
  GPU o driver, regenéralos (la tarea de export, no `scan_models`). Requiere el paquete `tensorrt` en
  la imagen del worker; si falta, la tarea devuelve error y se sigue usando el `.pt`.

## Subir un modelo manualmente
Copia el `.pt` al volumen `models_data` (p.ej.
`docker cp mi_modelo.pt basketball_analysis-worker-gpu-1:/app/engine/models/ball_detector__exp.pt`)
y pulsa **Re-escanear**. Aparecerá como versión del rol correspondiente, lista para activar.

## Endpoints
- `GET /models` — versiones por rol (+ activa).
- `POST /models/{id}/activate` — activa esa versión (desactiva las demás del rol).
- `POST /models/scan` — re-escanea y registra archivos.
- `DELETE /models/{id}` — elimina el registro (no permite borrar la activa).
