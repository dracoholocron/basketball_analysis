# Tracking de balón con SAM — checkpoints SAM 2.1 + piloto SAM 3

## SAM 2.1 (flujo de producción) — selector de checkpoint

El tracking de balón propaga los clics manuales con **SAM 2.1** color-agnóstico
(`basketball_analysis/ball_sam2/sam2_ball_tracker.py`). Ahora el checkpoint es
**seleccionable por análisis** desde el modal "Opciones de análisis"
(*Calidad de tracking de balón*), guardado en `Game.ball_tracking_quality`.

| Calidad | Checkpoint | VRAM aprox. | Cuándo usar |
|---|---|---|---|
| `small` (Rápido) | `sam2.1_hiera_small.pt` | ~bajo | clips cortos / pruebas rápidas |
| `base_plus` (Equilibrado, **default**) | `sam2.1_hiera_base_plus.pt` | medio | uso general en la RTX 5070 (12 GB) |
| `large` (Máxima) | `sam2.1_hiera_large.pt` | alto | máxima calidad; validar que no haga OOM junto al resto del pipeline |

- Los checkpoints se **auto-descargan** al volumen `models_data` la primera vez
  (`_CKPT_URLS` en `sam2_ball_tracker.py`).
- En el log de análisis: `SAM2 ball tracker checkpoint: …<archivo>`.
- A/B test: corre el mismo video con cada calidad y compara
  `Ball after SAM2 fusion: X%` + VRAM/tiempo. Si `large` hace OOM, baja a `base_plus`.

## SAM 3 (piloto experimental, aislado)

SAM 3 (Meta, nov 2025) trackea por **prompt de texto** ("basketball") sin clics.
Se corre en un **servicio lab separado** para no tocar producción.

### Prerrequisitos (una vez)
1. **Pesos gated:** solicita acceso a `sam3.pt` en Hugging Face (model card de SAM 3) y
   descarga el archivo.
2. Cópialo al volumen `sam3_models`:
   ```
   docker compose --profile lab create worker-sam3lab   # crea el contenedor/volumen
   docker cp sam3.pt basketball_analysis-worker-sam3lab-1:/app/sam3_models/sam3.pt
   ```

### Levantar el lab (opt-in)
```
docker compose --profile lab up -d --build worker-sam3lab
```
El servicio consume la cola `sam3lab` (el worker de producción **no** la consume).

### Uso
- UI: página **`/lab/sam3`** (marcada *experimental*) → elige juego, prompt de texto,
  ventana opcional → Ejecutar → reproduce el video anotado + **cobertura %**.
- API: `POST /lab/sam3/track {game_id, prompt, start_s, end_s}` → `{task_id}`;
  `GET /lab/sam3/result/{task_id}` → estado + URL presignada del mp4 + métricas.

### Limitaciones
- Es una **evaluación** (comparar cobertura/calidad vs SAM 2), no reemplaza el flujo.
- Corre **frame a frame** (detección por concepto) → pesado; usa ventanas cortas.
- Modelo grande (~3.4 GB); puede requerir ultralytics reciente (la imagen lo instala).
- Si faltan los pesos o SAM 3 no está disponible, devuelve un mensaje claro sin romper.
