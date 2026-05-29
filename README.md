# Procesamiento distribuido Cloud Native con Workers Docker, Message Queues y Cliente en JavaScriptInstrucciones de prueba local

## Procesamiento distribuido de imágenes
> Se sube una imagen JPG y se observa en tiempo real cómo 4 workers independientes la procesan en paralelo: redimensiona, genera miniatura, aplica filtro gris y convierte a PNG.
---

## ¿Qué hace?
Cuando subes una imagen, el sistema:
1. Genera una URL prefirmada de S3 y sube el archivo directamente desde el navegador.
2. S3 notifica a SQS (4 colas independientes, una por tipo de tarea).
3. Cada worker Docker consume su cola, descarga la imagen, la procesa y sube el resultado a S3.
4. El estado de cada worker se actualiza en Redis en tiempo real.
5. El frontend recibe actualizaciones vía **Server-Sent Events (SSE)** sin hacer polling.
---

### Flujo detallado
```
Usuario sube JPG
       │
       ▼
FastAPI genera URL prefirmada S3
       │
       ▼
Navegador sube directamente a S3 ──► S3 notifica a 4 colas SQS en paralelo
       │                                          │
       ▼                               ┌──────────┴──────────┐
SSE abre conexión                      │ Cada worker (Docker) │
/events/{filename}                     │  1. Recibe mensaje   │
       │                               │  2. r.set("en proceso")│
       ▼                               │  3. Descarga de S3   │
FastAPI lee Redis                      │  4. Procesa imagen   │
cada 1 segundo          ◄──────────────│  5. Sube resultado   │
       │                               │  6. r.set("completada")│
       ▼                               └─────────────────────┘
Envía evento al cliente
(JSON con estado de los 4 workers)
       │
       ▼
UI actualiza cards en tiempo real
```
---

## Tecnologías
| Componente   | Tecnología                              |
|--------------|-----------------------------------------|
| API          | FastAPI + Uvicorn                       |
| Frontend     | HTML/CSS/JS vanilla + SSE               |
| Message bus  | AWS SQS (long polling 20s)             |
| Event fan-out| AWS SNS → 4 colas SQS                  |
| Object store | AWS S3 (presigned POST)                 |
| State store  | Redis (key: `filename:worker`)          |
| Image proc.  | Pillow (PIL)                            |
| Containers   | Docker + Docker Compose                 |
---

##  Estructura del proyecto
```
worker-redis-image/
├── docker-compose.yml
│
├── fast-image-sse/          # Backend FastAPI + Frontend
│   ├── Dockerfile
│   ├── app.py               # API, SSE, presigned URLs
│   ├── static/
│   │   └── app.js           # Lógica del cliente, SSE consumer
│   └── templates/
│       └── index.html       # UI completa
│
└── worker-sqs/              # Workers de procesamiento
    ├── Dockerfile
    ├── worker.py            # Loop SQS, manejo de señales
    └── s3image.py           # Operaciones Pillow + S3
```
---

## Arquitectura
```
┌─────────────────────────────────────────────────────────────────┐
│                          NAVEGADOR                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  React UI  ──► POST /api/presigned-post                  │   │
│  │             ──► PUT S3 (direct upload)                   │   │
│  │             ◄── GET /events/{filename}  (SSE stream)     │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   FastAPI (Docker)       │
                    │   • /api/presigned-post  │
                    │   • /events/{filename}   │
                    │     StreamingResponse    │
                    └──────┬──────────┬────────┘
                           │          │
              ┌────────────▼─┐    ┌───▼──────────────┐
              │  Redis       │    │   AWS S3          │
              │  (estado de  │    │   velazquez-      │
              │   workers)   │    │   objects         │
              └────────────┬─┘    └───┬───────────────┘
                           │          │ S3 Event Notification
                           │          │
                           │    ┌─────▼──────────────────────┐
                           │    │         AWS SQS             │
                           │    │  ┌──────┐ ┌─────────┐      │
                           │    │  │Queue │ │  Queue  │      │
                           │    │  │resize│ │thumbnail│      │
                           │    │  └──┬───┘ └────┬────┘      │
                           │    │  ┌──┴───┐ ┌────┴────┐      │
                           │    │  │Queue │ │  Queue  │      │
                           │    │  │filter│ │ convert │      │
                           │    │  └──┬───┘ └────┬────┘      │
                           │    └─────┼──────────┼───────────┘
                           │          │          │
              ┌────────────┴──────────┼──────────┼──────────┐
              │          Workers Docker (×4)                  │
              │  ┌────────┐ ┌───────┐ ┌────────┐ ┌────────┐ │
              │  │ resize │ │ thumb │ │ filter │ │convert │ │
              │  │worker  │ │worker │ │worker  │ │worker  │ │
              │  └────────┘ └───────┘ └────────┘ └────────┘ │
              └───────────────────────────────────────────────┘
```
---


# Evidencias de ejecución distribuida

### 1. Interfaz principal del sistema 
Los 4 workers actualizan su estado independientemente conforme terminan.

<img width="366" height="571" alt="image" src="https://github.com/user-attachments/assets/abc1f5f6-47b5-44b9-af66-51192c92611d" />


### 2. Monitoreo en tiempo real con SSE
La consola del navegador muestra los eventos SSE enviados desde FastAPI. Cada worker actualiza su estado en Redis y el frontend recibe:
- pendiente
- en proceso
- completada
- 
<img width="1003" height="371" alt="image" src="https://github.com/user-attachments/assets/919a1278-877f-4e8b-be8a-fffd160a9b46" />


### 3. Almacenamiento en AWS S3
Las imágenes originales y procesadas son almacenadas automáticamente en diferentes carpetas dentro del bucket S3:
- imagenes/
- resize/
- thumbnail/
- gray/
- convert/
  
<img width="1112" height="355" alt="image" src="https://github.com/user-attachments/assets/06265d3d-2bcb-44e5-88e7-90bb4a424602" />

### 4. Resultado generado por el worker convert
El worker `convert` transforma automáticamente imágenes JPG a PNG y almacena el resultado en AWS S3.

<img width="1096" height="290" alt="image" src="https://github.com/user-attachments/assets/5c52aa89-9a99-49b0-82d9-d5a2a430aa87" />

