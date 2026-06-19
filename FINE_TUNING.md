# Guía de fine-tuning de detectores (balón, jugadores, etc.)

Cómo re-entrenar un detector **sin degradar la calidad** del análisis. Complementa
[MODEL_VERSIONS.md](MODEL_VERSIONS.md) (versionado/activación) y
[basketball_analysis/training_notebooks/BALL_DETECTION_IMPROVEMENT.md](basketball_analysis/training_notebooks/BALL_DETECTION_IMPROVEMENT.md).

> **Lección aprendida (A/B 2026-06-11).** Un fine-tune del detector de balón sobre
> **pseudo-etiquetas de SAM2** *regresó* la detección real (fusión 73.4 % con `large`)
> frente al detector **original**. La mejor configuración siguió siendo
> **balón original + SAM2 `base_plus` → 91 % de cobertura**. La causa: el set de
> validación también eran pseudo-etiquetas, así que el mAP "mejoró" sobre datos
> sesgados mientras la detección real empeoraba. **Nunca actives un modelo cuya mejora
> solo se midió contra pseudo-etiquetas.**

---

## Las 4 reglas

### 1. Set de validación REAL + comparación antes de activar
- Etiqueta **a mano** un set de validación pequeño (50–200 frames) con cajas reales,
  de **videos representativos** (distintas canchas, iluminación, distancia de cámara).
- Este set **no** debe contener pseudo-etiquetas ni frames usados en entrenamiento.
- Antes de activar, compara el candidato contra el **modelo activo** sobre ESE set
  (mismo `imgsz`, `conf`, IoU). Mide precision/recall/mAP **y** la métrica de producto
  (p. ej. **% de cobertura de balón** end-to-end, no solo mAP del detector).
- **Activa solo si mejora o iguala** en el set real. El versionado deja el candidato
  **inactivo** por defecto justo para esto (ver MODEL_VERSIONS.md).

### 2. Filtrar las pseudo-etiquetas
Las pseudo-labels (SAM2/YOLO automáticas) traen ruido. Antes de entrenar:
- **Umbral de confianza** alto (descarta detecciones dudosas).
- **Tamaño plausible**: el balón ocupa un rango acotado de px a 720p; descarta cajas
  demasiado grandes/pequeñas o con relación de aspecto no-cuadrada.
- **Consenso SAM2 ∩ YOLO**: quédate con frames donde ambos coinciden (IoU alto) →
  etiquetas mucho más limpias que cualquiera por separado.
- **Coherencia temporal**: descarta saltos imposibles de posición entre frames vecinos.
- Revisa visualmente una muestra antes de lanzar el entrenamiento.

### 3. Entrenamiento suave (anti-olvido catastrófico)
Re-entrenar agresivo sobre un dominio estrecho hace que el modelo **olvide** lo que ya
sabía. Para preservar la calidad general:
- **LR bajo** y pocas **épocas** (empieza con ~20–30).
- **Freeze del backbone** (entrena solo la cabeza de detección) cuando el dominio nuevo
  es pequeño.
- **Mezcla el dominio original**: incluye datos del set con que se entrenó el modelo
  base, no solo los frames nuevos, para no sobreajustar.
- Augmentations moderadas; vigila VRAM (ver nota de hardware abajo).

### 4. Active learning (etiqueta donde el modelo falla)
- Prioriza etiquetar **frames donde el modelo ACTIVO falla** (baja confianza,
  detecciones intermitentes, huecos largos donde SAM2 tuvo que rellenar).
- Esos frames aportan mucha más señal por etiqueta que frames "fáciles" que el modelo
  ya resuelve. Itera: entrena → mide en el set real → añade los nuevos casos difíciles.

---

## Flujo recomendado
1. Recolecta candidatos de pseudo-etiquetas (SAM2/YOLO) + frames difíciles del activo.
2. **Filtra** (regla 2). Aparta un **set de validación real** etiquetado a mano (regla 1).
3. Entrena **suave** (regla 3) — `finetune_ball_detector` ya usa `workers=0` (evita el
   error de procesos daemónicos) y defaults conservadores de VRAM.
4. El resultado se registra **inactivo** como `ball_detector__ft_<fecha>.pt`.
5. **Compara** candidato vs activo en el set real (regla 1). % cobertura end-to-end incluido.
6. Solo si mejora/iguala → **Activar** en *Admin → Modelos*. Si no, déjalo inactivo.
7. Para revertir: activa la versión anterior (1 clic, sin reconstruir el worker).

## Notas de hardware (RTX 5070, 12 GB)
- Configuraciones que han causado **CUDA OOM**: `imgsz=1280 / batch=16` y `imgsz=960 /
  batch=8` en runs largos. Estable: **`imgsz=640 / batch=6 / epochs=30`** (mAP50 ≈ 0.66
  en el último run).
- `workers=0` es **obligatorio** dentro del worker Celery (los procesos daemónicos no
  pueden tener hijos). No lo quites.
- Si un run se dispara a ~80 h o ~12 GB, **revócalo** y baja `imgsz`/`batch`.
