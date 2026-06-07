# Guía: Entrenar Modelos Reales y Analizar Videos

> **Estado del stack al momento de esta guía**
> | Servicio | URL | Estado |
> |---|---|---|
> | UI (Next.js) | http://localhost:4000 | Activo |
> | API (FastAPI) | http://localhost:8000/docs | Activo |
> | MinIO Console | http://localhost:9001 | Activo |
> | GitHub | https://github.com/dracoholocron/basketball_analysis | Sincronizado |

---

## Paso 0 — Verificar que el stack está corriendo

Abrir PowerShell en `C:\code\basketball_analysis` y ejecutar:

```powershell
cd C:\code\basketball_analysis
docker compose --profile dev ps
```

Todos los servicios deben aparecer como `healthy` o `Up`. Si alguno está caído:

```powershell
docker compose --profile dev up -d
```

Verificar GPU dentro del worker:

```powershell
docker compose exec worker-gpu nvidia-smi
# Debe mostrar: NVIDIA GeForce RTX 5070, CUDA 12.8
```

---

## Paso 1 — Obtener la Roboflow API Key

1. Ir a **https://roboflow.com** → iniciar sesión (o crear cuenta gratuita)
2. Ir a **Settings → API Keys** (esquina superior derecha del dashboard)
3. Copiar la clave que empieza con `rf_...`

El plan gratuito es suficiente para descargar los datasets que se usarán:
- `workspace-5ujvu / basketball-players-fy4c2-vfsuv / v17` (jugadores + balón)
- `fyp-3bwmg / reloc2-den7l / v1` (keypoints de cancha)

---

## Paso 2 (G3) — Entrenar los 3 modelos reales

> **Tiempo estimado:** 3-4 horas en RTX 5070 con todos los modelos  
> **Requisito:** Roboflow API Key del paso anterior

### 2.1 Activar el entorno virtual

```powershell
cd C:\code\basketball_analysis
.\.venv\Scripts\Activate.ps1
```

El prompt debe cambiar a `(.venv) PS C:\code\basketball_analysis>`.

### 2.2 Verificar dependencias

```powershell
python -c "import torch; print('PyTorch', torch.__version__); print('CUDA disponible:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0))"
```

Salida esperada:
```
PyTorch 2.7.0+cu128
CUDA disponible: True
GPU: NVIDIA GeForce RTX 5070
```

Si CUDA no está disponible, reinstalar torch:
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

### 2.3 Lanzar el entrenamiento

```powershell
$env:ROBOFLOW_API_KEY = "rf_TU_CLAVE_AQUI"
.\scripts\train_models.ps1
```

El script hará todo automáticamente:
1. Descarga dataset de jugadores y balón desde Roboflow
2. Entrena `player_detector.pt` (~30 min)
3. Entrena `ball_detector_model.pt` (~60 min)
4. Descarga dataset de keypoints de cancha
5. Entrena `court_keypoint_detector.pt` (~2-3 hrs)
6. Copia los `best.pt` a `basketball_analysis\models\`

**Tiempos por modelo (RTX 5070 12 GB):**

| Modelo | Arquitectura | Épocas | Batch | Tiempo |
|---|---|---|---|---|
| `player_detector.pt` | yolov5l6u | 100 | 8 | ~30 min |
| `ball_detector_model.pt` | yolov5l6u | 250 | auto | ~60 min |
| `court_keypoint_detector.pt` | yolov8x-pose | 500 | 16 | ~2-3 hrs |

### 2.4 Opciones para acelerar (si hay falta de memoria GPU)

Reducir épocas del modelo de cancha (suficiente para converger):
```powershell
.\scripts\train_models.ps1 -CourtEpochs 300 -CourtBatch 8
```

Entrenar solo un modelo específico:
```powershell
# Solo player y ball, saltar cancha por ahora:
.\scripts\train_models.ps1 -SkipCourt

# Solo cancha (si player y ball ya están):
.\scripts\train_models.ps1 -SkipPlayer -SkipBall
```

### 2.5 Verificar los modelos entrenados

```powershell
Get-ChildItem basketball_analysis\models\*.pt | Select-Object Name, @{N='MB';E={[math]::Round($_.Length/1MB,1)}}
```

Salida esperada:
```
Name                         MB
----                         --
player_detector.pt           94
ball_detector_model.pt       94
court_keypoint_detector.pt   280
```

> Si los archivos pesan ~6 MB son los **dummy models** (yolov8n), no los reales.

---

## Paso 3 (G3.b) — Activar los modelos reales en el worker

```powershell
.\scripts\deploy_models.ps1 -DisableDummyMode
```

Este script:
1. Copia los 3 `.pt` al volumen Docker del worker (`/app/engine/models/`)
2. Pone `BA_DUMMY_MODELS=false` en el `.env`
3. Reinicia el worker automáticamente

Verificar que el worker recargó:
```powershell
docker compose logs worker-gpu --tail 20
```

Debe aparecer una línea como:
```
[INFO] Loading model: /app/engine/models/player_detector.pt
```

---

## Paso 4 (G4.b) — Analizar videos reales

Los videos están en:
```
C:\code\SmartBasket\basketball-highlight-agent\videos\input\
  20260511_151008.mp4   (11.7 min, 2400x1080, 1698 MB)
  20260511_152417.mp4   ( 4.2 min, 2400x1080,  602 MB)

C:\code\SmartBasket\basketball-highlight-agent\videos\scaled\
  20260511_152417.mp4   ( 4.2 min, 1280x576,   160 MB)  ← YA ESCALADO
```

### Opción A — Subir por la UI (recomendado para primera prueba)

1. Abrir **http://localhost:4000**
2. Iniciar sesión: `admin@test.com` / `Test1234!`
3. Ir a **Admin** → crear una Season (si no existe la del seed)
4. Ir a **Games** → **New Game**:
   - Season: seleccionar del dropdown
   - Location: `Cancha Escolar`
   - Court Level: `fiba_juvenil`
   - Team 1 Jersey: descripción del uniforme del video (ej. `white jersey`)
   - Team 2 Jersey: descripción del otro equipo (ej. `dark blue jersey`)
5. Hacer clic en **Create**
6. Abrir el juego → **Choose Video** → seleccionar `20260511_152417.mp4` (el de 4 min escalado)
7. Hacer clic en **Analyze**
8. Monitorear el progreso en la barra o en **http://localhost:4000/jobs**

**Tiempo estimado de procesamiento** del video de 4 min (7,445 frames a ~30 FPS):
- Con modelos reales en RTX 5070: ~8-15 minutos
- El video de 12 min tomará proporcionalmente más (~25-45 min)

### Opción B — Subir por CLI (batch)

```powershell
# Primero obtener el Season UUID desde Admin o seed
# (aparece en la tabla de Seasons en http://localhost:4000/admin)
$SEASON_ID = "UUID-DEL-SEED-AQUI"

python scripts\ingest_folder.py `
  --folder "C:\code\SmartBasket\basketball-highlight-agent\videos\scaled" `
  --season-id $SEASON_ID `
  --court-level fiba_juvenil `
  --jersey1 "white jersey" `
  --jersey2 "dark blue jersey" `
  --poll
```

Con `--poll` el script espera y muestra el progreso de cada job hasta que terminen.

### Escalar el video de 12 min (si no está escalado todavía)

```powershell
python scripts\downscale_video.py `
  --input "C:\code\SmartBasket\basketball-highlight-agent\videos\input\20260511_151008.mp4" `
  --output "C:\code\SmartBasket\basketball-highlight-agent\videos\scaled\20260511_151008.mp4" `
  --height 576
```

Tarda ~3-4 minutos (OpenCV, sin GPU).

---

## Paso 5 (G7) — Benchmark con modelos reales

Después de entrenar y desplegar los modelos reales:

```powershell
cd C:\code\basketball_analysis
.\.venv\Scripts\Activate.ps1

python bench\run_bench.py `
  --player_model basketball_analysis\models\player_detector.pt `
  --ball_model basketball_analysis\models\ball_detector_model.pt `
  --court_model basketball_analysis\models\court_keypoint_detector.pt `
  --n_frames 200 `
  --batch_size 8 `
  --out bench\report.json `
  --update-baseline
```

El resultado queda en `bench\baseline.json` y `bench\report.json`.

**FPS esperados con modelos reales en RTX 5070:**

| Modelo | FPS esperado | ms/frame |
|---|---|---|
| `player_detector.pt` (yolov5l6u) | ~120-180 | ~6-8 |
| `ball_detector_model.pt` (yolov5l6u) | ~130-190 | ~5-8 |
| `court_keypoint_detector.pt` (yolov8x-pose) | ~30-60 | ~17-33 |

Comparado con los dummy (yolov8n): player=540, ball=480, court=446 FPS — los reales serán 3-10x más lentos pero detectan correctamente.

---

## Paso 6 — Hacer commit de los resultados y push

```powershell
cd C:\code\basketball_analysis
git add bench\baseline.json bench\report.json README.md
git commit -m "bench: real model baseline on RTX 5070"
git push
```

---

## Troubleshooting

### Worker no detecta GPU después de deploy

```powershell
docker compose restart worker-gpu
docker compose exec worker-gpu python -c "import torch; print(torch.cuda.is_available())"
```

### Error de memoria GPU durante entrenamiento (`CUDA out of memory`)

```powershell
# Reducir batch size y tamaño de imagen:
.\scripts\train_models.ps1 -CourtBatch 8 -PlayerBatch 4
```

### El job falla con error en `/jobs`

Ver el mensaje de error exacto en **http://localhost:4000/jobs** (columna Details).
También ver logs del worker:

```powershell
docker compose logs worker-gpu --tail 50
```

### Reiniciar el stack completo

```powershell
docker compose --profile dev down
docker compose --profile dev up -d
docker compose exec api alembic upgrade head
docker compose exec api python seed.py
```

### Ver métricas de un video procesado

1. Ir a **http://localhost:4000/games** → abrir el juego
2. Ver gráficos de posesión, pases, intercepciones
3. Tabla de jugadores: distancia recorrida, velocidad máxima, frames con posesión
4. Botón **Download annotated video** para descargar el video con overlays

---

## Checklist de estado

- [x] Stack levantado (api, worker, db, redis, minio, frontend)
- [x] UI accesible en http://localhost:4000
- [x] Código en GitHub: https://github.com/dracoholocron/basketball_analysis
- [x] Video de 4 min escalado a 576p (160 MB, listo para subir)
- [ ] Roboflow API Key obtenida
- [ ] Modelos reales entrenados (`player`, `ball`, `court`)
- [ ] Modelos desplegados en worker (`deploy_models.ps1`)
- [ ] Video de 4 min analizado con modelos reales
- [ ] Video de 12 min escalado y analizado
- [ ] Benchmark ejecutado y baseline actualizado
