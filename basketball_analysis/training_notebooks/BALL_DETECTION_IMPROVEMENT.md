# Mejorar la detección del balón

## Diagnóstico

En footage amateur al aire libre el detector raw acierta solo ~50% de los frames
(ej. log: `25101 frames`, `3343 frames in long gaps`, `recovered 2560/3343` con SAHI;
el resto se rellena por interpolación). El modelo `yolo11_multiclass.pt` se entrenó
con un dataset Roboflow (`Basketball-Players-17`) cuyo dominio (cancha interior,
balón grande, iluminación uniforme) no coincide con:

- balón pequeño / lejano,
- motion blur por movimiento rápido,
- cancha exterior con zonas pintadas de colores,
- sombras duras / contraluz.

Esto es un **gap de dominio**: tuning de confianza/SAHI da mejoras marginales; el
arreglo de fondo es **fine-tune** del detector con frames de este tipo de footage.

## Caso balón gris (medición empírica)

En un video con **balón gris** se midió la detección cruda de
`ball_detector_model.pt` (muestreo de 800 frames a 720p):

| conf | frames con balón |
|------|------------------|
| >0.10 | 76.9% |
| >0.25 | 50.1% |
| >0.35 | 39.5% |

Confianza media cuando detecta: 0.387 (máx 0.861). Conclusión: el balón gris **sí**
se detecta, pero a confianza más baja que un balón naranja → bajar el umbral
recupera mucha cobertura. No es "nula"; era el umbral 0.25 + el tope de
interpolación lo que lo hacía desaparecer.

## Mejoras ya aplicadas (algorítmicas, sin reentrenar)

- `BA_BALL_DETECTOR_CONF=0.15` (de 0.25 → sube la detección cruda ~50%→~65-70%).
- SAHI `BA_BALL_SAHI_TILE=640`, `BA_BALL_SAHI_OVERLAP=0.25` (el tile 512 resultó
  PEOR: 550 vs 672/1100 recuperados, y más lento).
- Tope de interpolación `BA_BALL_MAX_INTERP_GAP=15` (~0.5s a 30fps): los gaps
  largos ya **no** se rellenan con una línea recta falsa.
- **Kalman** (`BA_BALL_KALMAN=true`): suaviza el centro y predice trayectoria por
  velocidad en gaps cortos (no recta).
- **Bridging visual CSRT** (`BA_BALL_VISUAL_TRACK`, default OFF): tracker
  color-agnóstico para puentear gaps largos donde el balón es visible pero no
  detectado. Activar solo si tras conf+Kalman la cobertura sigue baja (riesgo de
  drift en balón gris sobre cancha gris).

## Énfasis para el fine-tune: variedad de color del balón

El gap principal es de **dominio de color/apariencia**: el detector rinde mejor con
balones naranja. Para el fine-tune (sección A abajo) es **clave incluir balón gris**
y otros colores/condiciones de este footage, no solo más cantidad de frames.

## Módulo de anotación de balón (SAM2) — doble propósito

UI `/games/[id]/annotate-ball`: el usuario marca el balón con clicks en pocos
frames (y "no visible" donde no está). Guardado en `ball_annotations`. Un mismo
set de clicks sirve para:

1. **Tracking inmediato** (`basketball_analysis/ball_sam2/sam2_ball_tracker.py`):
   SAM2 propaga los clicks fwd+bwd por todo el video (color-agnóstico → balón
   gris). En `main.py` se **fusiona** con YOLO (YOLO donde concuerda/es preciso;
   SAM2 rellena gaps y resuelve desacuerdos). Gated por `BA_BALL_SAM2`; si sam2 no
   está, cae al path YOLO. Checkpoint `sam2.1_hiera_small.pt` (auto-descarga).
2. **Auto-labels → fine-tune** (`ball_sam2/export_dataset.py`): las cajas
   propagadas (score alto) + negativos se exportan a formato YOLO acumulativo.
   Reentrenar con el notebook de abajo (`yolo train ... data=<out_dir>/data.yaml
   imgsz=1280`) y hacer swap del `.pt`. Anotar ~10 frames rinde cientos de labels.

## Trabajo más profundo pendiente

### A. Fine-tune del detector (mayor impacto)

1. **Exportar frames difíciles.** Reusar los stubs del pipeline:
   `stubs/ball_track_stubs.pkl` indica en qué frames no hubo balón. Extraer esos
   frames del video original (a 720p, como corre el pipeline) para etiquetar.
   Opcional: añadir un volcado de crops en `BallTracker.refill_missing_with_sahi`
   detrás de un env var `BA_BALL_DUMP_GAPS=1`.
2. **Etiquetar en Roboflow** la clase `Ball` sobre ~500–1500 frames variados
   (distintos partidos, distancias, iluminación, motion blur). Mantener el mismo
   esquema de 7 clases del dataset actual o un dataset solo-balón.
3. **Fine-tune** partiendo del checkpoint actual, reusando
   [`basketball_ball_training.ipynb`](basketball_ball_training.ipynb) (ya incluye
   augmentations de motion blur). Sugerido:
   `yolo task=detect mode=train model=models/yolo11_multiclass.pt data=data.yaml
   epochs=80 imgsz=1280 mosaic=1.0 close_mosaic=10`.
   `imgsz=1280` ayuda a objetos pequeños como el balón.
4. **Reemplazar** el `.pt` en el volumen `models_data` y comparar la tasa de
   detección raw (`detected` vs `missing_before_sahi` en los logs) antes/después.

### B. Tracking temporal (Kalman) — mejora algorítmica diferida

Hoy cada frame se detecta de forma independiente y los gaps se interpolan
linealmente. Un filtro de velocidad constante (`cv2.KalmanFilter`) que suavice el
centro del balón y prediga a través de gaps cortos:

- reduce el jitter del bbox,
- mejora la detección de posesión/pases (centros más estables),
- da una predicción físicamente plausible en gaps cortos (parábola/velocidad)
  en vez de recta.

Se posterga porque interactúa con `remove_wrong_detections` e
`interpolate_ball_positions` y requiere tuning cuidadoso para no degradar el
seguimiento en jugadas rápidas. Implementarlo junto con (A) y medir contra la
misma métrica de tasa raw.
