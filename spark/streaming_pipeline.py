"""
SentimentStream - Pipeline de Spark Structured Streaming
--------------------------------------------------------
Lee el dataset 'dataset_sentimientos_500.csv' simulando un flujo en
micro-lotes, aplica un pipeline NLP (limpieza, tokenización, stopwords
en español, HashingTF, IDF y Naive Bayes) y persiste los resultados
en MongoDB.

Curso: Big Data - Institución Universitaria de Envigado (2026-1)
"""

import os
import re
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType
from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.feature import (
    RegexTokenizer,
    StopWordsRemover,
    HashingTF,
    IDF,
    StringIndexer,
    IndexToString,
)
from pyspark.ml.classification import NaiveBayes
from pymongo import MongoClient


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
DATASET_PATH = os.environ.get("DATASET_PATH", "/app/data/dataset_sentimientos_500.csv")
INPUT_STREAM_DIR = os.environ.get("INPUT_STREAM_DIR", "/app/data/stream_input")
CHECKPOINT_DIR = os.environ.get("CHECKPOINT_DIR", "/app/data/checkpoint")
MODEL_PATH = os.environ.get("MODEL_PATH", "/app/data/model_nb")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.environ.get("MONGO_DB", "sentimentstream")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "sentiments")

# Stopwords básicas en español (lista representativa).
SPANISH_STOPWORDS = [
    "a", "al", "algo", "algunas", "algunos", "ante", "antes", "como", "con",
    "contra", "cual", "cuando", "de", "del", "desde", "donde", "durante", "e",
    "el", "ella", "ellas", "ellos", "en", "entre", "era", "erais", "eran",
    "eras", "eres", "es", "esa", "esas", "ese", "eso", "esos", "esta", "estaba",
    "estabais", "estaban", "estabas", "estad", "estada", "estadas", "estado",
    "estados", "estamos", "estando", "estar", "estaremos", "estará", "estarán",
    "estarás", "estaré", "estaréis", "estaría", "estaríais", "estaríamos",
    "estarían", "estarías", "estas", "este", "estemos", "esto", "estos", "estoy",
    "estuve", "estuviera", "estuvierais", "estuvieran", "estuvieras", "estuvieron",
    "estuviese", "estuvieseis", "estuviesen", "estuvieses", "estuvimos",
    "estuviste", "estuvisteis", "estuviéramos", "estuviésemos", "estuvo", "está",
    "estábamos", "estáis", "están", "estás", "esté", "estéis", "estén", "estés",
    "fue", "fuera", "fuerais", "fueran", "fueras", "fueron", "fuese", "fueseis",
    "fuesen", "fueses", "fui", "fuimos", "fuiste", "fuisteis", "fuéramos",
    "fuésemos", "ha", "habida", "habidas", "habido", "habidos", "habiendo",
    "habremos", "habrá", "habrán", "habrás", "habré", "habréis", "habría",
    "habríais", "habríamos", "habrían", "habrías", "habéis", "había", "habíais",
    "habíamos", "habían", "habías", "han", "has", "hasta", "hay", "haya",
    "hayamos", "hayan", "hayas", "hayáis", "he", "hemos", "hube", "hubiera",
    "hubierais", "hubieran", "hubieras", "hubieron", "hubiese", "hubieseis",
    "hubiesen", "hubieses", "hubimos", "hubiste", "hubisteis", "hubiéramos",
    "hubiésemos", "hubo", "la", "las", "le", "les", "lo", "los", "me", "mi",
    "mis", "mucho", "muchos", "muy", "más", "mí", "mía", "mías", "mío", "míos",
    "nada", "ni", "no", "nos", "nosotras", "nosotros", "nuestra", "nuestras",
    "nuestro", "nuestros", "o", "os", "otra", "otras", "otro", "otros", "para",
    "pero", "poco", "por", "porque", "que", "quien", "quienes", "qué", "se",
    "sea", "seamos", "sean", "seas", "ser", "seremos", "será", "serán", "serás",
    "seré", "seréis", "sería", "seríais", "seríamos", "serían", "serías",
    "seáis", "si", "sido", "siendo", "sin", "sobre", "sois", "somos", "son",
    "soy", "su", "sus", "suya", "suyas", "suyo", "suyos", "sí", "también",
    "tanto", "te", "tendremos", "tendrá", "tendrán", "tendrás", "tendré",
    "tendréis", "tendría", "tendríais", "tendríamos", "tendrían", "tendrías",
    "tened", "tenemos", "tenga", "tengamos", "tengan", "tengas", "tengo",
    "tengáis", "tenida", "tenidas", "tenido", "tenidos", "teniendo", "tenéis",
    "tenía", "teníais", "teníamos", "tenían", "tenías", "ti", "tiene", "tienen",
    "tienes", "todo", "todos", "tu", "tus", "tuve", "tuviera", "tuvierais",
    "tuvieran", "tuvieras", "tuvieron", "tuviese", "tuvieseis", "tuviesen",
    "tuvieses", "tuvimos", "tuviste", "tuvisteis", "tuviéramos", "tuviésemos",
    "tuvo", "tuya", "tuyas", "tuyo", "tuyos", "tú", "un", "una", "uno", "unos",
    "vosotras", "vosotros", "vuestra", "vuestras", "vuestro", "vuestros", "y",
    "ya", "yo", "él", "éramos",
]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def crear_spark(app_name: str = "SentimentStream") -> SparkSession:
    """Crea y devuelve la SparkSession del proyecto."""
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )


def limpiar_texto_udf():
    """UDF para normalizar el texto: minúsculas, sin acentos básicos ni símbolos."""
    def _limpiar(texto):
        if texto is None:
            return ""
        t = texto.lower()
        t = re.sub(r"http\S+", " ", t)
        t = re.sub(r"[^a-záéíóúñü\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    return F.udf(_limpiar, StringType())


# ---------------------------------------------------------------------------
# Entrenamiento del modelo
# ---------------------------------------------------------------------------
def entrenar_modelo(spark: SparkSession) -> PipelineModel:
    """
    Entrena el pipeline NLP + Naive Bayes sobre el CSV completo.
    Se asume que el CSV tiene columnas 'texto' y 'sentimiento'.
    """
    df = (
        spark.read.option("header", True)
        .option("multiLine", True)
        .option("escape", '"')
        .csv(DATASET_PATH)
    )

    # Normalización de nombres de columnas esperadas.
    cols = {c.lower(): c for c in df.columns}
    col_texto = cols.get("texto", list(df.columns)[0])
    col_label = cols.get("sentimiento", list(df.columns)[1])

    df = df.select(
        F.col(col_texto).alias("texto"),
        F.col(col_label).alias("sentimiento"),
    ).dropna()

    df = df.withColumn("texto_limpio", limpiar_texto_udf()(F.col("texto")))

    tokenizer = RegexTokenizer(
        inputCol="texto_limpio", outputCol="tokens", pattern="\\s+"
    )
    remover = StopWordsRemover(
        inputCol="tokens", outputCol="tokens_filtrados", stopWords=SPANISH_STOPWORDS
    )
    hashing_tf = HashingTF(
        inputCol="tokens_filtrados", outputCol="tf", numFeatures=2048
    )
    idf = IDF(inputCol="tf", outputCol="features")
    indexer = StringIndexer(inputCol="sentimiento", outputCol="label")
    nb = NaiveBayes(featuresCol="features", labelCol="label")

    pipeline = Pipeline(stages=[tokenizer, remover, hashing_tf, idf, indexer, nb])
    modelo = pipeline.fit(df)

    modelo.write().overwrite().save(MODEL_PATH)
    print(f"[SentimentStream] Modelo entrenado y guardado en {MODEL_PATH}")
    return modelo


def cargar_o_entrenar_modelo(spark: SparkSession) -> PipelineModel:
    """Carga el modelo si existe, de lo contrario lo entrena."""
    try:
        modelo = PipelineModel.load(MODEL_PATH)
        print(f"[SentimentStream] Modelo cargado desde {MODEL_PATH}")
        return modelo
    except Exception:
        print("[SentimentStream] No se encontró modelo previo. Entrenando...")
        return entrenar_modelo(spark)


# ---------------------------------------------------------------------------
# Persistencia en MongoDB
# ---------------------------------------------------------------------------
def escribir_en_mongo(batch_df, batch_id):
    """Función foreachBatch: persiste cada micro-lote en MongoDB."""
    registros = [r.asDict() for r in batch_df.collect()]
    if not registros:
        return

    client = MongoClient(MONGO_URI)
    coleccion = client[MONGO_DB][MONGO_COLLECTION]
    documentos = []
    for r in registros:
        documentos.append(
            {
                "texto_original": r.get("texto"),
                "sentimiento_predicho": r.get("sentimiento_predicho"),
                "confianza": float(r.get("confianza", 0.0)),
                "timestamp": datetime.utcnow(),
            }
        )
    coleccion.insert_many(documentos)
    client.close()
    print(f"[SentimentStream] Batch {batch_id}: {len(documentos)} docs insertados")


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------
def preparar_directorio_streaming():
    """
    Copia el CSV original al directorio observado por Structured Streaming
    para simular la llegada de datos en micro-lotes.
    """
    os.makedirs(INPUT_STREAM_DIR, exist_ok=True)
    destino = os.path.join(INPUT_STREAM_DIR, "lote_inicial.csv")
    if not os.path.exists(destino):
        import shutil
        shutil.copy(DATASET_PATH, destino)
        print(f"[SentimentStream] CSV copiado a {destino} para streaming")


def ejecutar_streaming(spark: SparkSession, modelo: PipelineModel):
    """Lanza el job de Structured Streaming en micro-lotes."""
    esquema = StructType(
        [
            StructField("texto", StringType(), True),
            StructField("sentimiento", StringType(), True),
        ]
    )

    stream_df = (
        spark.readStream.schema(esquema)
        .option("header", True)
        .option("multiLine", True)
        .option("maxFilesPerTrigger", 1)
        .csv(INPUT_STREAM_DIR)
    )

    stream_df = stream_df.withColumn("texto_limpio", limpiar_texto_udf()(F.col("texto")))

    predicciones = modelo.transform(stream_df)

    # Recuperar etiqueta original a partir del índice predicho.
    indexer_model = [s for s in modelo.stages if hasattr(s, "labels")][0]
    etiquetas = indexer_model.labels
    label_converter = IndexToString(
        inputCol="prediction",
        outputCol="sentimiento_predicho",
        labels=etiquetas,
    )
    predicciones = label_converter.transform(predicciones)

    # Confianza: máximo de la probabilidad.
    @F.udf(returnType="double")
    def max_prob(v):
        try:
            return float(max(v.toArray()))
        except Exception:
            return 0.0

    predicciones = predicciones.withColumn("confianza", max_prob(F.col("probability")))
    salida = predicciones.select("texto", "sentimiento_predicho", "confianza")

    query = (
        salida.writeStream.foreachBatch(escribir_en_mongo)
        .option("checkpointLocation", CHECKPOINT_DIR)
        .outputMode("append")
        .start()
    )

    print("[SentimentStream] Streaming iniciado. Esperando datos...")
    query.awaitTermination()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    spark = crear_spark()
    spark.sparkContext.setLogLevel("WARN")

    modelo = cargar_o_entrenar_modelo(spark)
    preparar_directorio_streaming()
    ejecutar_streaming(spark, modelo)


if __name__ == "__main__":
    main()
