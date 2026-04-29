# SentimentStream

**Pipeline integrado de análisis de sentimientos en tiempo real con Spark, MongoDB y Flask**

- Curso: **Big Data**
- Institución: **Institución Universitaria de Envigado**
- Periodo: **2026-1**
- Modalidad: Individual o en pareja
- Dataset: `data/dataset_sentimientos_500.csv` (idioma: español, 500 registros)

---

## 1. Descripción General

SentimentStream es una solución end-to-end para el análisis automático de sentimientos en español que integra:

1. **Spark Structured Streaming** — ingesta de datos en micro-lotes desde archivos CSV.
2. **Pipeline NLP con PySpark ML** — limpieza de texto, tokenización, eliminación de stopwords en español, extracción de características (HashingTF, IDF) y clasificación con Naive Bayes.
3. **Persistencia en MongoDB** — almacenamiento de cada predicción con metadatos.
4. **API REST con Flask** — tres endpoints para consulta y predicción en tiempo real.
5. **Orquestación containerizada** — Docker Compose para levantar todos los servicios.
6. **Pipeline CI/CD** — Jenkinsfile para automatización.
7. **Preparado para BI** — datos listos para visualización en Power BI.

---

## 2. Estructura del Repositorio

```
SentimentStream/
├── api/
│   ├── app.py                          # API REST Flask
│   └── requirements.txt                # Dependencias Python API
├── spark/
│   └── streaming_pipeline.py           # Job de streaming y entrenamiento
├── infra/
│   ├── docker-compose.yml              # Orquestación de servicios
│   └── Jenkinsfile                     # Pipeline CI/CD Jenkins
├── data/
│   ├── dataset_sentimientos_500.csv    # Dataset de entrenamiento
│   ├── model_nb/                       # Modelo entrenado (Spark ML)
│   ├── stream_input/                   # Directorio para streaming
│   └── checkpoint/                     # Checkpoint de Structured Streaming
├── docs/
│   └── README.md                       # Este archivo
└── sentimentstream/                    # Entorno virtual Python
```

---

## 3. Componente 1: Pipeline Spark (Streaming & Entrenamiento)

**Archivo:** `spark/streaming_pipeline.py`

### Fases del Pipeline ML

El modelo implementa un pipeline de 6 etapas:

1. **Limpieza de texto (UDF personalizado)**
   - Conversión a minúsculas
   - Eliminación de URLs (regex: `http\S+`)
   - Eliminación de caracteres especiales (solo se conservan: a-z, á-é-í-ó-ú-ñ, espacios)
   - Normalización de espacios múltiples

2. **Tokenización (`RegexTokenizer`)**
   - Separación por espacios en blanco
   - Salida: columna `tokens`

3. **Eliminación de stopwords (`StopWordsRemover`)**
   - Lista amplia de stopwords en español (200+ palabras)
   - Salida: columna `tokens_filtrados`

4. **Vectorización (`HashingTF`)**
   - 2048 características (feature buckets)
   - Salida: columna `tf` (term frequency)

5. **IDF (Inverse Document Frequency)**
   - Reescalado de frecuencias por importancia global
   - Salida: columna `features` (TF-IDF)

6. **Clasificación (`NaiveBayes`)**
   - Modelo probabilístico multinomial
   - Entrada: `features` (TF-IDF)
   - Salida: `prediction` (índice), `probability` (vector de probabilidades)

### Entrenamiento del Modelo

```python
modelo = cargar_o_entrenar_modelo(spark)  # Carga si existe, entrena si no
```

- Lee `DATASET_PATH` completo
- Normaliza nombres de columnas (`texto`, `sentimiento`)
- Aplica todas las etapas del pipeline
- Persiste el modelo en `MODEL_PATH` (`/app/data/model_nb`)

### Streaming en Tiempo Real

```python
ejecutar_streaming(spark, modelo)
```

- Observa `INPUT_STREAM_DIR` (`/app/data/stream_input`)
- Lee archivos CSV conforme llegan (máx 1 archivo por trigger)
- Aplica el modelo entrenado a cada micro-lote
- Convierte índices predichos a etiquetas de sentimiento
- Calcula confianza como el máximo de probabilidades
- Persiste resultados en MongoDB mediante `foreachBatch(escribir_en_mongo)`

**Checkpoint:** Stored Streaming guarda estado en `/app/data/checkpoint` para garantizar exactitud.

---

## 4. Componente 2: API REST (Flask)

**Archivo:** `api/app.py`  
**Dependencias:** Ver `api/requirements.txt` (Flask 3.0.3, PyMongo 4.8.0, PySpark 3.5.1, NumPy)

### Base URL
```
http://<IP_LOCAL>:5000
```

### Endpoints

#### 1. GET `/sentiments` — Listar predicciones

Obtiene todas las predicciones almacenadas en MongoDB, ordenadas por timestamp descendente.

**Parámetros opcionales:**
- `sentimiento` (string): Filtrar por sentimiento predicho (`positivo`, `negativo`, `neutro`, etc.)

**Respuesta:**
```json
{
  "total": 45,
  "resultados": [
    {
      "_id": "507f1f77bcf86cd799439011",
      "texto_original": "Me encantó el servicio",
      "sentimiento_predicho": "positivo",
      "confianza": 0.89,
      "timestamp": "2026-04-29T10:30:45.123456"
    }
  ]
}
```

**Ejemplos:**
```bash
# Todas las predicciones
curl http://localhost:5000/sentiments

# Solo sentimientos negativos
curl "http://localhost:5000/sentiments?sentimiento=negativo"
```

---

#### 2. GET `/stats` — Estadísticas globales

Devuelve métricas agregadas: total de documentos, distribución por sentimiento y confianza promedio.

**Respuesta:**
```json
{
  "total_documentos": 500,
  "distribucion_sentimientos": {
    "positivo": 250,
    "negativo": 150,
    "neutro": 100
  },
  "confianza_promedio": 0.82
}
```

**Ejemplo:**
```bash
curl http://localhost:5000/stats
```

---

#### 3. POST `/predict` — Inferencia en tiempo real

Realiza predicción sobre un texto nuevo. Carga el modelo de forma perezosa (lazy loading) para optimizar memoria.

**Body (JSON):**
```json
{
  "texto": "Este producto es excelente, lo recomiendo"
}
```

**Respuesta exitosa (200):**
```json
{
  "texto": "Este producto es excelente, lo recomiendo",
  "sentimiento_predicho": "positivo",
  "confianza": 0.91
}
```

**Respuesta error (400 - texto vacío):**
```json
{
  "error": "Debe enviarse el campo 'texto' (string)"
}
```

**Respuesta error (500 - fallo en predicción):**
```json
{
  "error": "Error en la predicción",
  "detalle": "..."
}
```

**Ejemplo:**
```bash
curl -X POST http://localhost:5000/predict \
     -H "Content-Type: application/json" \
     -d '{"texto":"Estoy muy feliz con mis compras"}'
```

**Flujo interno:**
1. Valida que `texto` sea string no vacío
2. Initializa/carga modelo Spark (si no está en memoria)
3. Crea DataFrame con el texto
4. Aplica limpieza de texto (UDF)
5. Transforma usando el pipeline entrenado
6. Extrae sentimiento y confianza
7. **Guarda resultado en MongoDB** con timestamp actual
8. Devuelve respuesta al cliente

---

### Configuración API

**Variables de entorno:**
```python
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.environ.get("MONGO_DB", "sentimentstream")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "sentiments")
MODEL_PATH = os.environ.get("MODEL_PATH", "/app/data/model_nb")
```

**Host & Port:**
```python
app.run(host="0.0.0.0", port=5000, debug=False)
```
- `0.0.0.0` → Escucha en todas las interfaces (accesible desde otros PCs de la red)
- `5000` → Puerto por defecto Flask

---

## 5. Base de Datos (MongoDB)

**Conexión:** `mongodb://mongo:27017`  
**Base de datos:** `sentimentstream`  
**Colección:** `sentiments`

### Esquema de documento

```json
{
  "_id": ObjectId("..."),
  "texto_original": "Me encantó el servicio",
  "sentimiento_predicho": "positivo",
  "confianza": 0.89,
  "timestamp": ISODate("2026-04-29T10:30:45.123Z")
}
```

---

## 6. Docker Compose - Orquestación

**Archivo:** `infra/docker-compose.yml`

### Servicios

| Servicio | Imagen | Puerto | Descripción |
|----------|--------|--------|-------------|
| `mongo` | `mongo:6.0` | 27017 | Base de datos |
| `spark` | `apache/spark:3.5.0` | — | Job de streaming (batch processing) |
| `api` | `python:3.10-slim` | 5000 | API REST Flask |

### Ejecución

```bash
cd infra
docker-compose up --build
```

**Logs útiles:**
```bash
docker-compose logs -f spark      # Ver streaming en tiempo real
docker-compose logs -f api        # Ver requests a API
docker-compose logs -f mongo      # Ver eventos MongoDB
```

**Detener servicios:**
```bash
docker-compose down              # Detiene y elimina contenedores
docker-compose down -v           # + elimina volúmenes (datos MongoDB)
```

---

## 7. Acceso desde otros PCs en la red

El API está configurado para ser accesible desde cualquier PC en la misma red local.

**Pasos:**

1. Obtener IP local de tu PC (donde corre el contenedor):
   ```bash
   hostname -I
   # Resultado: 192.168.1.100 (por ejemplo)
   ```

2. Desde otro PC, acceder a:
   ```
   http://192.168.1.100:5000/stats
   http://192.168.1.100:5000/sentiments
   http://192.168.1.100:5000/predict (POST)
   ```

**Nota:** Usa la **IP de tu PC** (donde corre el API), no la del otro PC.

---

## 8. Pipeline Jenkins (CI/CD)

**Archivo:** `infra/Jenkinsfile`

Etapas:
1. **Checkout** — Clonar repositorio
2. **Validación** — Verificar estructura de archivos
3. **Build** — Construir imágenes Docker
4. **Deploy** — Levantar servicios con Docker Compose
5. **Health Check** — Probar disponibilidad del API

---

## 9. Visualización en Power BI

**Conector:** MongoDB (mediante ODBC o conector personalizado)

**Connection String:**
```
mongodb://mongo:27017/sentimentstream
```

**Colección:** `sentiments`

**Visualizaciones recomendadas:**

1. **Gráfico de dona** — Distribución de sentimientos
2. **Gráfico de línea** — Evolución temporal de predicciones
3. **Tabla** — Últimas predicciones (`texto_original`, `sentimiento_predicho`, `confianza`, `timestamp`)
4. **KPI Card** — Confianza promedio

---

## 10. Variables de Entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `DATASET_PATH` | `/app/data/dataset_sentimientos_500.csv` | Ruta CSV de entrenamiento |
| `INPUT_STREAM_DIR` | `/app/data/stream_input` | Directorio observado por Streaming |
| `MODEL_PATH` | `/app/data/model_nb` | Ruta de persistencia del modelo |
| `MONGO_URI` | `mongodb://mongo:27017` | Conexión a MongoDB |
| `MONGO_DB` | `sentimentstream` | Base de datos |
| `MONGO_COLLECTION` | `sentiments` | Colección |

---

## 11. Ejecución completa (paso a paso)

### Opción A: Con Docker Compose (recomendado)

```bash
# 1. Navegar a la carpeta del proyecto
cd /home/cristian/Desktop/SentimentStream

# 2. Levantar servicios
cd infra
docker-compose up --build

# 3. Esperar a que Spark termine entrenamiento
# (ver logs: docker-compose logs -f spark)

# 4. Probar API desde otra terminal
curl http://localhost:5000/stats
```

### Opción B: Local (sin Docker)

```bash
# 1. Activar venv
source sentimentstream/bin/activate

# 2. Instalar dependencias
pip install -r api/requirements.txt
pip install pyspark==3.5.1

# 3. Iniciar MongoDB local (si no está corriendo)
mongod

# 4. Entrenar modelo y streaming (en una terminal)
python spark/streaming_pipeline.py

# 5. Iniciar API (en otra terminal)
cd api
python app.py
```

---

## 12. Notas y Consideraciones

- **Lazy Loading del Modelo:** El modelo Spark se carga en memoria solo cuando se llama a `/predict`, optimizando arranque de la API.
- **Exactitud en Streaming:** Checkpoint garantiza que no hay duplicados ni pérdida de datos.
- **Stopwords:** Lista personalizada de 200+ stopwords en español en `streaming_pipeline.py`.
- **Confianza:** Calculada como el máximo valor en el vector de probabilidades del modelo.
- **Timestamp:** Siempre en UTC para consistencia.
- **CORS:** El API permite acceso desde cualquier origen (`0.0.0.0`).
