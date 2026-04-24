# SentimentStream

**Pipeline integrado de análisis de sentimientos en tiempo real**

- Curso: **Big Data**
- Institución: **Institución Universitaria de Envigado**
- Periodo: **2026-1**
- Modalidad: Individual o en pareja
- Dataset: `data/dataset_sentimientos_500.csv` (idioma: español)

---

## 1. Descripción

SentimentStream integra de extremo a extremo:

1. **Spark Structured Streaming** — ingesta del CSV en micro-lotes.
2. **Procesamiento NLP con PySpark** — limpieza, tokenización, stopwords en español, HashingTF, IDF y Naive Bayes.
3. **Persistencia en MongoDB** — cada predicción se almacena con texto original, sentimiento, confianza y timestamp.
4. **API REST con Flask** — endpoints `/sentiments`, `/stats`, `/predict`.
5. **Orquestación con Docker Compose**.
6. **Pipeline básico con Jenkins** (`Jenkinsfile`).
7. **Visualización en Power BI** sobre la colección de MongoDB.

---

## 2. Estructura del repositorio

```
/spark
  └── streaming_pipeline.py
/api
  ├── app.py
  └── requirements.txt
/infra
  ├── docker-compose.yml
  └── Jenkinsfile
/data
  └── dataset_sentimientos_500.csv
/docs
  └── README.md
```

---

## 3. Pipeline de procesamiento (PySpark)

Etapas obligatorias implementadas en `spark/streaming_pipeline.py`:

1. Limpieza de texto (minúsculas, sin URLs ni símbolos).
2. Tokenización (`RegexTokenizer`).
3. Eliminación de stopwords en español (`StopWordsRemover`).
4. Vectorización con `HashingTF`.
5. `IDF`.
6. Clasificación con `NaiveBayes`.

El modelo entrenado se persiste en `MODEL_PATH` y se reutiliza tanto por el job de streaming como por el endpoint `/predict` de la API.

---

## 4. Persistencia en MongoDB

- Base de datos: `sentimentstream`
- Colección: `sentiments`
- Esquema de cada documento:

```json
{
  "texto_original": "string",
  "sentimiento_predicho": "string",
  "confianza": 0.0,
  "timestamp": "ISODate"
}
```

---

## 5. API REST (Flask)

Base URL: `http://localhost:5000`

| Método | Endpoint        | Descripción                                                      |
|--------|-----------------|------------------------------------------------------------------|
| GET    | `/sentiments`   | Listado de predicciones. Filtros: `sentimiento`, `limit`.        |
| GET    | `/stats`        | Total de documentos, distribución y confianza promedio.          |
| POST   | `/predict`      | Inferencia sobre texto nuevo. Body: `{"texto": "..."}`.          |

Ejemplo:

```bash
curl -X POST http://localhost:5000/predict \
     -H "Content-Type: application/json" \
     -d '{"texto":"Me encantó el servicio"}'
```

---

## 6. Ejecución con Docker Compose

Desde la carpeta raíz del proyecto:

```bash
cd infra
docker compose up --build
```

Servicios levantados:

- `mongo` → `localhost:27017`
- `spark` → ejecuta `streaming_pipeline.py`
- `api`   → `localhost:5000`

---

## 7. Pipeline Jenkins

`infra/Jenkinsfile` contiene un pipeline declarativo con etapas:

1. Checkout
2. Validación de estructura
3. Build de los servicios
4. Despliegue con Docker Compose
5. Health check de la API

---

## 8. Visualización en Power BI

Conexión recomendada: **MongoDB ODBC / conector personalizado** apuntando a la colección `sentimentstream.sentiments`.

Visualizaciones mínimas:

- Distribución de sentimientos (gráfico de barras o dona).
- Evolución temporal (línea sobre `timestamp`).
- Tabla de predicciones recientes (`texto_original`, `sentimiento_predicho`, `confianza`, `timestamp`).

---

## 9. Variables de entorno relevantes

| Variable            | Por defecto                                      |
|---------------------|--------------------------------------------------|
| `DATASET_PATH`      | `/app/data/dataset_sentimientos_500.csv`         |
| `INPUT_STREAM_DIR`  | `/app/data/stream_input`                         |
| `MODEL_PATH`        | `/app/data/model_nb`                             |
| `MONGO_URI`         | `mongodb://mongo:27017`                          |
| `MONGO_DB`          | `sentimentstream`                                |
| `MONGO_COLLECTION`  | `sentiments`                                     |
