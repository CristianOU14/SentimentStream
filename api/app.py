"""
SentimentStream - API REST (Flask)
----------------------------------
Expone los resultados del pipeline de análisis de sentimientos
almacenados en MongoDB y permite realizar inferencia sobre nuevos
textos utilizando el modelo entrenado por Spark.

Endpoints:
    GET  /sentiments  -> listado con filtros (sentimiento, limit)
    GET  /stats       -> métricas y distribución
    POST /predict     -> inferencia sobre texto nuevo
"""

import os
from datetime import datetime

from flask import Flask, jsonify, request
from pymongo import MongoClient


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.environ.get("MONGO_DB", "sentimentstream")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "sentiments")
MODEL_PATH = os.environ.get("MODEL_PATH", "/app/data/model_nb")

app = Flask(__name__)
_mongo_client = MongoClient(MONGO_URI)
_coleccion = _mongo_client[MONGO_DB][MONGO_COLLECTION]

# Carga perezosa del modelo Spark para /predict.
_spark = None
_modelo = None


def _obtener_modelo():
    """Inicializa Spark y carga el PipelineModel solo cuando se necesita."""
    global _spark, _modelo
    if _modelo is None:
        from pyspark.sql import SparkSession
        from pyspark.ml import PipelineModel

        _spark = (
            SparkSession.builder.appName("SentimentStreamAPI")
            .config("spark.sql.shuffle.partitions", "2")
            .getOrCreate()
        )
        _spark.sparkContext.setLogLevel("WARN")
        _modelo = PipelineModel.load(MODEL_PATH)
    return _spark, _modelo


def _serializar(doc):
    """Convierte un documento de Mongo a un dict JSON-serializable."""
    doc["_id"] = str(doc["_id"])
    ts = doc.get("timestamp")
    if isinstance(ts, datetime):
        doc["timestamp"] = ts.isoformat()
    return doc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.route("/sentiments", methods=["GET"])
def listar_sentimientos():
    """
    Devuelve un listado de predicciones almacenadas.
    Filtros opcionales:
        - sentimiento: positivo | negativo | neutro
        - limit: número máximo de registros (por defecto 50)
    """
    sentimiento = request.args.get("sentimiento")
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50

    filtro = {}
    if sentimiento:
        filtro["sentimiento_predicho"] = sentimiento

    cursor = _coleccion.find(filtro).sort("timestamp", -1).limit(limit)
    resultados = [_serializar(d) for d in cursor]
    return jsonify({"total": len(resultados), "resultados": resultados})


@app.route("/stats", methods=["GET"])
def estadisticas():
    """Devuelve métricas globales y distribución por sentimiento."""
    total = _coleccion.count_documents({})

    pipeline_distribucion = [
        {"$group": {"_id": "$sentimiento_predicho", "cantidad": {"$sum": 1}}}
    ]
    distribucion = {
        d["_id"]: d["cantidad"] for d in _coleccion.aggregate(pipeline_distribucion)
    }

    pipeline_confianza = [
        {"$group": {"_id": None, "promedio": {"$avg": "$confianza"}}}
    ]
    promedio = list(_coleccion.aggregate(pipeline_confianza))
    confianza_promedio = promedio[0]["promedio"] if promedio else 0.0

    return jsonify(
        {
            "total_documentos": total,
            "distribucion_sentimientos": distribucion,
            "confianza_promedio": confianza_promedio,
        }
    )

@app.route("/predict", methods=["POST"])
def predecir():
    data = request.get_json(silent=True) or {}
    texto = data.get("texto")

    if not texto or not isinstance(texto, str):
        return jsonify({"error": "Debe enviarse el campo 'texto' (string)"}), 400

    try:
        spark, modelo = _obtener_modelo()
        df = spark.createDataFrame([(texto,)], ["texto"])

        from pyspark.sql import functions as F
        from pyspark.sql.types import StringType
        import re

        def _limpiar(t):
            if t is None:
                return ""
            t = t.lower()
            t = re.sub(r"http\S+", " ", t)
            t = re.sub(r"[^a-záéíóúñü\s]", " ", t)
            return re.sub(r"\s+", " ", t).strip()

        limpiar_udf = F.udf(_limpiar, StringType())
        df = df.withColumn("texto_limpio", limpiar_udf(F.col("texto")))

        pred = modelo.transform(df).collect()[0]

        # Obtener etiquetas de forma segura
        indexer_model = next((s for s in modelo.stages if hasattr(s, "labels")), None)

        if not indexer_model:
            return jsonify({"error": "No se encontraron etiquetas en el modelo"}), 500

        etiquetas = indexer_model.labels
        sentimiento = etiquetas[int(pred["prediction"])]

        probs = pred["probability"]
        confianza = float(max(probs.toArray() if hasattr(probs, "toArray") else probs))

        return jsonify({
            "texto": texto,
            "sentimiento_predicho": sentimiento,
            "confianza": confianza,
        })

    except Exception as e:
        return jsonify({
            "error": "Error en la predicción",
            "detalle": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
