# Comportamiento del análisis por tipo de video

Cómo se comporta el pipeline de SmartBasket según el tipo de grabación, y qué knobs
ajustar. Todos los knobs son variables `BA_*` en el servicio `worker-gpu` de
`docker-compose.yml`.

## Regímenes

### 1) Cámara estática / indoor (trípode, plano fijo)
- **Tracking:** `BA_TRACKER=botsort` (por defecto) funciona bien. La compensación de
  movimiento de cámara (GMC, `sparseOptFlow`) **degrada con gracia**: sin movimiento de
  cámara no hay nada que compensar (transformación ≈ identidad), así que NO hace falta
  cambiar a `bytetrack`. La fragmentación de IDs es baja.
- **OCR de dorsales:** suele leer bien si los jugadores ocupan suficientes píxeles.
- **Aro:** una sola marca por aro basta (cámara fija → caja estática correcta).

### 2) Cámara en paneo / sigue el balón
- **Tracking:** BoT-SORT+GMC es **clave** aquí — ByteTrack asume cámara estática y
  fragmenta masivamente al panear. El `track_buffer` alto (150) y el tracklet
  stitching (`BA_TRACK_STITCH`, gap 2.5s) recuperan identidades tras oclusiones.
- **Aro:** marca el **mismo** aro en varios momentos del paneo (selector "Aro 1/2");
  el pipeline interpola su posición por `frame_t`.

### 3) Planos lejanos / amateur (gran distancia, baja resolución del jugador)
- **Detección de jugadores:** sube `BA_PLAYER_MAX_H` (p.ej. 1080) y `BA_PLAYER_IMGSZ`
  (p.ej. 1280) para recuperar jugadores pequeños/lejanos.
- **OCR de dorsales:** es el régimen más difícil — el número rara vez es legible. El
  OCR lee en **resolución nativa** (no en los 720p del pipeline) y vota por tracklet.
  Knobs: `BA_JERSEY_OCR_SAMPLE_EVERY` (bajar a 5 → más muestreo) y
  `BA_JERSEY_OCR_MIN_VOTES` (2). Aun así muchos tracks quedarán **provisionales** (sin
  dorsal) → se mapean a mano en *Asignar jugadores* o se filtran por minutos.
- **Balón:** anota puntos de balón para activar SAM2 (propagación color-agnóstica).

## Consolidación de identidades (cómo baja el conteo)
`tracks crudos → BoT-SORT+GMC → tracklet stitching → filtro micro-tracks
(<BA_MIN_TRACK_SECONDS) → consolidación por (equipo, dorsal vía OCR)`.
Las identidades **con dorsal** se mapean al roster (`player_id`) y alimentan los
perfiles y la simulación. Las **provisionales** no inflan el uso diario: la tabla
ordena por minutos y el filtro "Solo con dorsal" las oculta.

## Cómo alimenta esto a equipos/jugadores/simulación
1. Análisis → `PlayerMetric` (CV) → consolidado por identidad.
2. *Asignar jugadores* (sin re-analizar) → setea `player_id`.
3. Al mapear / completar, se puebla `player_game_stats` (familia CV) por
   (jugador, juego), agregable por temporada en los perfiles.
4. La simulación (`matchups._get_team_stats`) combina el % de tiro del **box score**
   (autoridad) con **ritmo/posesiones y presión defensiva** derivados de CV.

## Versionado de modelos
La versión activa de cada modelo (player/ball/court/pose) se elige en **Admin → Modelos**;
revertir es un clic y aplica al próximo análisis. Detalle: [MODEL_VERSIONS.md](MODEL_VERSIONS.md).

## Tracking de balón (SAM 2.1) y piloto SAM 3
La calidad del tracking de balón es **seleccionable por análisis** (small/base_plus/large)
en el modal — afecta posesión/pases/tiros. Detalle y guía del piloto SAM 3 (prompt de
texto, servicio lab aislado) en [SAM_TRACKING.md](SAM_TRACKING.md).

## Tabla rápida de knobs

| Knob | Default | Subir si… |
|---|---|---|
| `BA_TRACKER` | `botsort` | (dejar; `bytetrack` solo para A/B) |
| `BA_TRACK_STITCH_MAX_GAP_S` | `2.5` | mucha fragmentación por oclusión |
| `BA_MIN_TRACK_SECONDS` | `0.5` | demasiados fragmentos falsos |
| `BA_JERSEY_OCR_SAMPLE_EVERY` | `5` | (bajar) más cobertura de dorsal, más costo |
| `BA_JERSEY_OCR_MIN_VOTES` | `2` | (subir) menos falsos positivos de dorsal |
| `BA_PLAYER_MAX_H` / `BA_PLAYER_IMGSZ` | `1080` / `1280` | jugadores lejanos no detectados |
