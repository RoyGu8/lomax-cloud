import io
import json
import os
import uuid
from decimal import Decimal

import boto3
import psycopg2
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field


app = FastAPI(
    title="Lomax API",
    version="1.0.0",
)


# ---------------------------------------------------------
# Configuración
# ---------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "host.docker.internal")
DB_PORT = int(os.getenv("DB_PORT", "7001"))
DB_NAME = os.getenv("DB_NAME", "lomax")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "LomaxDB2026!")

AWS_ENDPOINT_URL = os.getenv(
    "AWS_ENDPOINT_URL",
    "http://host.docker.internal:4566",
)
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

DYNAMODB_TABLE = os.getenv(
    "DYNAMODB_TABLE",
    "producto_atributos",
)
ORIGINAL_BUCKET = os.getenv(
    "ORIGINAL_BUCKET",
    "lomax-originales",
)
THUMBNAIL_BUCKET = os.getenv(
    "THUMBNAIL_BUCKET",
    "lomax-miniaturas",
)
LAMBDA_FUNCTION = os.getenv(
    "LAMBDA_FUNCTION",
    "lomax-image-processor",
)

MAX_IMAGE_SIZE = 5 * 1024 * 1024


# ---------------------------------------------------------
# Clientes AWS/FLOCI
# ---------------------------------------------------------

dynamodb = boto3.client(
    "dynamodb",
    endpoint_url=AWS_ENDPOINT_URL,
    region_name=AWS_REGION,
)

s3 = boto3.client(
    "s3",
    endpoint_url=AWS_ENDPOINT_URL,
    region_name=AWS_REGION,
)

lambda_client = boto3.client(
    "lambda",
    endpoint_url=AWS_ENDPOINT_URL,
    region_name=AWS_REGION,
)


# ---------------------------------------------------------
# Modelo POST /productos
# ---------------------------------------------------------

class ProductoCreate(BaseModel):
    codigo: str = Field(min_length=1, max_length=50)
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str = Field(min_length=1)
    precio: Decimal = Field(ge=0)
    categoria_id: int = Field(gt=0)
    atributos: dict


# ---------------------------------------------------------
# Utilidades
# ---------------------------------------------------------

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def get_dynamodb_item(producto_id):
    response = dynamodb.get_item(
        TableName=DYNAMODB_TABLE,
        Key={
            "producto_id": {
                "S": str(producto_id)
            }
        },
    )

    return response.get("Item")


def verify_publication(producto_id):
    """
    Verifica que DynamoDB tenga los atributos y que la
    miniatura exista realmente en S3.
    """

    item = get_dynamodb_item(producto_id)

    if not item:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No existe el registro de atributos",
                "paso": "verificación DynamoDB",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
            },
        )

    estado_imagen = item.get(
        "estado_imagen",
        {}
    ).get("S", "")

    atributos = item.get("atributos")

    miniatura_key = item.get(
        "miniatura_key",
        {}
    ).get("S", "")

    if estado_imagen != "LISTA":
        raise HTTPException(
            status_code=503,
            detail={
                "error": "La imagen no está lista",
                "paso": "verificación DynamoDB",
                "producto_id": producto_id,
                "estado_imagen": estado_imagen,
                "estado_rds": "PENDIENTE",
            },
        )

    if not atributos:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No existen atributos del producto",
                "paso": "verificación DynamoDB",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
            },
        )

    if not miniatura_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "DynamoDB no contiene miniatura_key",
                "paso": "verificación DynamoDB",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
            },
        )

    try:
        s3.head_object(
            Bucket=THUMBNAIL_BUCKET,
            Key=miniatura_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "La miniatura no existe en S3",
                "paso": "verificación S3 miniatura",
                "producto_id": producto_id,
                "miniatura_key": miniatura_key,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    return item


def publish_product(producto_id):
    """
    Cambia RDS a PUBLICADO únicamente después de verificar
    DynamoDB y S3.
    """

    verify_publication(producto_id)

    try:
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE productos
                    SET estado = 'PUBLICADO'
                    WHERE producto_id = %s
                    """,
                    (producto_id,),
                )

                if cursor.rowcount == 0:
                    conn.rollback()
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "error": "Producto no encontrado",
                            "paso": "actualización RDS",
                            "producto_id": producto_id,
                        },
                    )

                conn.commit()

        finally:
            conn.close()

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo actualizar el estado en RDS",
                "paso": "UPDATE productos PUBLICADO",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )


def invoke_image_lambda(producto_id, original_key):
    event = {
        "producto_id": str(producto_id),
        "bucket": ORIGINAL_BUCKET,
        "key": original_key,
    }

    try:
        response = lambda_client.invoke(
            FunctionName=LAMBDA_FUNCTION,
            InvocationType="RequestResponse",
            Payload=json.dumps(event).encode("utf-8"),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo invocar Lambda",
                "paso": "invocación Lambda",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    try:
        payload = response["Payload"].read()

        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        result = json.loads(payload)

        if isinstance(result, dict) and "body" in result:
            body = result["body"]

            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except Exception:
                    pass

            result["body"] = body

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Respuesta inválida de Lambda",
                "paso": "respuesta Lambda",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    status_code = result.get("statusCode", 500)

    if status_code != 200:
        error_detail = result.get(
            "error",
            result.get("body", result),
        )

        raise HTTPException(
            status_code=503,
            detail={
                "error": "Lambda no pudo procesar la imagen",
                "paso": "procesamiento Lambda",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": error_detail,
            },
        )

    return result


# ---------------------------------------------------------
# Rutas
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "lomax-backend",
    }


@app.get("/categorias")
def obtener_categorias():
    try:
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT categoria_id, nombre
                    FROM categorias
                    ORDER BY categoria_id
                    """
                )

                categorias = [
                    {
                        "categoria_id": row[0],
                        "nombre": row[1],
                    }
                    for row in cursor.fetchall()
                ]

            return categorias

        finally:
            conn.close()

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar RDS",
                "paso": "GET /categorias",
                "detalle": str(exc),
            },
        )


@app.post("/productos", status_code=201)
def crear_producto(producto: ProductoCreate):

    try:
        conn = get_db_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo conectar con RDS",
                "paso": "POST /productos - conexión RDS",
                "detalle": str(exc),
            },
        )

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT categoria_id
                FROM categorias
                WHERE categoria_id = %s
                """,
                (producto.categoria_id,),
            )

            if cursor.fetchone() is None:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "La categoría no existe",
                        "paso": "POST /productos - validación categoría",
                        "categoria_id": producto.categoria_id,
                    },
                )

            cursor.execute(
                """
                SELECT producto_id
                FROM productos
                WHERE codigo = %s
                """,
                (producto.codigo,),
            )

            if cursor.fetchone() is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "El código de producto ya existe",
                        "paso": "POST /productos - validación código",
                        "codigo": producto.codigo,
                    },
                )

            cursor.execute(
                """
                INSERT INTO productos
                    (codigo, nombre, descripcion, precio,
                     categoria_id, estado)
                VALUES
                    (%s, %s, %s, %s, %s, 'PENDIENTE')
                RETURNING producto_id
                """,
                (
                    producto.codigo,
                    producto.nombre,
                    producto.descripcion,
                    producto.precio,
                    producto.categoria_id,
                ),
            )

            producto_id = cursor.fetchone()[0]
            conn.commit()

    except HTTPException:
        conn.rollback()
        raise

    except psycopg2.Error as exc:
        conn.rollback()

        if getattr(exc, "pgcode", None) == "23505":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "El código de producto ya existe",
                    "paso": "POST /productos - inserción RDS",
                    "codigo": producto.codigo,
                },
            )

        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo crear el producto en RDS",
                "paso": "POST /productos - inserción RDS",
                "detalle": str(exc),
            },
        )

    finally:
        conn.close()

    try:
        atributos_dynamodb = {}

        for clave, valor in producto.atributos.items():
            if isinstance(valor, bool):
                atributos_dynamodb[clave] = {
                    "BOOL": valor
                }
            elif isinstance(valor, (int, float, Decimal)):
                atributos_dynamodb[clave] = {
                    "N": str(valor)
                }
            elif valor is not None:
                atributos_dynamodb[clave] = {
                    "S": str(valor)
                }

        dynamodb.put_item(
            TableName=DYNAMODB_TABLE,
            Item={
                "producto_id": {
                    "S": str(producto_id)
                },
                "tipo": {
                    "S": "producto"
                },
                "atributos": {
                    "M": atributos_dynamodb
                },
                "imagen_original_key": {
                    "S": ""
                },
                "miniatura_key": {
                    "S": ""
                },
                "estado_imagen": {
                    "S": "PENDIENTE"
                },
            },
            ConditionExpression="attribute_not_exists(producto_id)",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo crear el registro de atributos",
                "paso": "POST /productos - DynamoDB",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    return {
        "producto_id": producto_id,
        "estado": "PENDIENTE",
    }


@app.post("/productos/{producto_id}/imagen")
async def cargar_imagen(
    producto_id: int,
    imagen: UploadFile = File(...),
):
    # -----------------------------------------------------
    # 1. Verificar producto
    # -----------------------------------------------------

    try:
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT producto_id, estado
                    FROM productos
                    WHERE producto_id = %s
                    """,
                    (producto_id,),
                )

                producto = cursor.fetchone()

        finally:
            conn.close()

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar el producto",
                "paso": "POST /productos/{id}/imagen - RDS",
                "producto_id": producto_id,
                "detalle": str(exc),
            },
        )

    if producto is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Producto no encontrado",
                "paso": "POST /productos/{id}/imagen",
                "producto_id": producto_id,
            },
        )

    # -----------------------------------------------------
    # 2. Verificar tipo MIME
    # -----------------------------------------------------

    allowed_types = {
        "image/jpeg": "jpg",
        "image/png": "png",
    }

    if imagen.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail={
                "error": "Formato no permitido",
                "paso": "validación de imagen",
                "permitidos": ["image/jpeg", "image/png"],
                "content_type": imagen.content_type,
            },
        )

    # -----------------------------------------------------
    # 3. Leer y validar tamaño
    # -----------------------------------------------------

    data = await imagen.read()

    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "La imagen supera el límite de 5 MB",
                "paso": "validación tamaño imagen",
                "tamano_bytes": len(data),
                "maximo_bytes": MAX_IMAGE_SIZE,
            },
        )

    if len(data) == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "El archivo está vacío",
                "paso": "validación de imagen",
            },
        )

    # -----------------------------------------------------
    # 4. Validar firma del archivo
    # -----------------------------------------------------

    is_jpeg = data.startswith(b"\xff\xd8\xff")
    is_png = data.startswith(b"\x89PNG\r\n\x1a\n")

    if imagen.content_type == "image/jpeg" and not is_jpeg:
        raise HTTPException(
            status_code=415,
            detail={
                "error": "El contenido no corresponde a un JPEG válido",
                "paso": "validación de imagen",
            },
        )

    if imagen.content_type == "image/png" and not is_png:
        raise HTTPException(
            status_code=415,
            detail={
                "error": "El contenido no corresponde a un PNG válido",
                "paso": "validación de imagen",
            },
        )

    # -----------------------------------------------------
    # 5. Crear clave determinística
    # -----------------------------------------------------

    extension = allowed_types[imagen.content_type]

    original_key = (
        f"originales/{producto_id}/"
        f"imagen.{extension}"
    )

    # -----------------------------------------------------
    # 6. Guardar original en S3
    # -----------------------------------------------------

    try:
        s3.put_object(
            Bucket=ORIGINAL_BUCKET,
            Key=original_key,
            Body=data,
            ContentType=imagen.content_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo guardar la imagen original",
                "paso": "S3 originales",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    # -----------------------------------------------------
    # 7. Actualizar DynamoDB con original
    # -----------------------------------------------------

    try:
        dynamodb.update_item(
            TableName=DYNAMODB_TABLE,
            Key={
                "producto_id": {
                    "S": str(producto_id)
                }
            },
            UpdateExpression=(
                "SET imagen_original_key = :original, "
                "estado_imagen = :estado"
            ),
            ExpressionAttributeValues={
                ":original": {
                    "S": original_key
                },
                ":estado": {
                    "S": "PENDIENTE"
                },
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo actualizar DynamoDB",
                "paso": "DynamoDB - imagen original",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    # -----------------------------------------------------
    # 8. Invocar Lambda
    # -----------------------------------------------------

    invoke_image_lambda(
        producto_id,
        original_key,
    )

    # -----------------------------------------------------
    # 9. Verificar DynamoDB + miniatura S3
    # -----------------------------------------------------

    item = verify_publication(producto_id)

    miniatura_key = item.get(
        "miniatura_key",
        {}
    ).get("S", "")

    # -----------------------------------------------------
    # 10. Publicar en RDS
    # -----------------------------------------------------

    publish_product(producto_id)

    return {
        "producto_id": producto_id,
        "estado": "PUBLICADO",
        "imagen_original_key": original_key,
        "miniatura_key": miniatura_key,
    }

@app.post("/productos/{producto_id}/reprocesar")
def reprocesar_imagen(producto_id: int):

    # -----------------------------------------------------
    # 1. Verificar que el producto exista en RDS
    # -----------------------------------------------------

    try:
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT producto_id, estado
                    FROM productos
                    WHERE producto_id = %s
                    """,
                    (producto_id,),
                )

                producto = cursor.fetchone()

        finally:
            conn.close()

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar el producto",
                "paso": "POST /productos/{id}/reprocesar - RDS",
                "producto_id": producto_id,
                "detalle": str(exc),
            },
        )

    if producto is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Producto no encontrado",
                "paso": "POST /productos/{id}/reprocesar",
                "producto_id": producto_id,
            },
        )

    # -----------------------------------------------------
    # 2. Buscar la imagen original en DynamoDB
    # -----------------------------------------------------

    try:
        item = get_dynamodb_item(producto_id)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar DynamoDB",
                "paso": "POST /productos/{id}/reprocesar - DynamoDB",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    if not item:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "No existe registro de atributos",
                "paso": "POST /productos/{id}/reprocesar",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
            },
        )

    original_key = item.get(
        "imagen_original_key",
        {}
    ).get("S", "")

    if not original_key:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "No existe imagen original para reprocesar",
                "paso": "POST /productos/{id}/reprocesar",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
            },
        )

    # -----------------------------------------------------
    # 3. Verificar que el original exista en S3
    # -----------------------------------------------------

    try:
        s3.head_object(
            Bucket=ORIGINAL_BUCKET,
            Key=original_key,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "La imagen original no existe en S3",
                "paso": "POST /productos/{id}/reprocesar - S3",
                "producto_id": producto_id,
                "imagen_original_key": original_key,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    # -----------------------------------------------------
    # 4. Marcar procesamiento como PENDIENTE
    # -----------------------------------------------------

    try:
        dynamodb.update_item(
            TableName=DYNAMODB_TABLE,
            Key={
                "producto_id": {
                    "S": str(producto_id)
                }
            },
            UpdateExpression="SET estado_imagen = :estado",
            ExpressionAttributeValues={
                ":estado": {
                    "S": "PENDIENTE"
                }
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo actualizar el estado en DynamoDB",
                "paso": "DynamoDB - reprocesamiento",
                "producto_id": producto_id,
                "estado_rds": "PENDIENTE",
                "detalle": str(exc),
            },
        )

    # -----------------------------------------------------
    # 5. Invocar Lambda nuevamente
    # -----------------------------------------------------

    invoke_image_lambda(
        producto_id,
        original_key,
    )

    # -----------------------------------------------------
    # 6. Verificar miniatura + atributos
    # -----------------------------------------------------

    item = verify_publication(producto_id)

    miniatura_key = item.get(
        "miniatura_key",
        {}
    ).get("S", "")

    # -----------------------------------------------------
    # 7. Publicar únicamente después de verificar todo
    # -----------------------------------------------------

    publish_product(producto_id)

    return {
        "producto_id": producto_id,
        "estado": "PUBLICADO",
        "imagen_original_key": original_key,
        "miniatura_key": miniatura_key,
        "reprocesado": True,
    }

@app.get("/productos")
def listar_productos():

    try:
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        p.producto_id,
                        p.codigo,
                        p.nombre,
                        p.descripcion,
                        p.precio,
                        p.categoria_id,
                        c.nombre AS categoria_nombre,
                        p.fecha_creacion,
                        p.estado
                    FROM productos p
                    INNER JOIN categorias c
                        ON c.categoria_id = p.categoria_id
                    WHERE p.estado = 'PUBLICADO'
                    ORDER BY p.producto_id
                    """
                )

                rows = cursor.fetchall()

        finally:
            conn.close()

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar los productos",
                "paso": "GET /productos - RDS",
                "detalle": str(exc),
            },
        )

    productos = []

    for row in rows:

        producto_id = row[0]

        try:
            item = get_dynamodb_item(producto_id)

        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "No se pudo consultar DynamoDB",
                    "paso": "GET /productos - DynamoDB",
                    "producto_id": producto_id,
                    "detalle": str(exc),
                },
            )

        if not item:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "No existe información de atributos",
                    "paso": "GET /productos - DynamoDB",
                    "producto_id": producto_id,
                },
            )

        atributos = item.get(
            "atributos",
            {}
        ).get("M", {})

        miniatura_key = item.get(
            "miniatura_key",
            {}
        ).get("S", "")

        productos.append(
            {
                "producto_id": row[0],
                "codigo": row[1],
                "nombre": row[2],
                "descripcion": row[3],
                "precio": float(row[4]),
                "categoria_id": row[5],
                "categoria": row[6],
                "fecha_creacion": row[7].isoformat()
                    if row[7]
                    else None,
                "estado": row[8],
                "atributos": atributos,
                "miniatura_key": miniatura_key,
            }
        )

    return productos

@app.get("/productos/{producto_id}")
def obtener_producto(producto_id: int):

    # -----------------------------------------------------
    # 1. Consultar producto en RDS
    # -----------------------------------------------------

    try:
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        p.producto_id,
                        p.codigo,
                        p.nombre,
                        p.descripcion,
                        p.precio,
                        p.categoria_id,
                        c.nombre AS categoria_nombre,
                        p.fecha_creacion,
                        p.estado
                    FROM productos p
                    INNER JOIN categorias c
                        ON c.categoria_id = p.categoria_id
                    WHERE p.producto_id = %s
                    """,
                    (producto_id,),
                )

                row = cursor.fetchone()

        finally:
            conn.close()

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar RDS",
                "paso": "GET /productos/{id} - RDS",
                "producto_id": producto_id,
                "detalle": str(exc),
            },
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Producto no encontrado",
                "paso": "GET /productos/{id}",
                "producto_id": producto_id,
            },
        )

    # -----------------------------------------------------
    # 2. Consultar atributos en DynamoDB
    # -----------------------------------------------------

    try:
        item = get_dynamodb_item(producto_id)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar DynamoDB",
                "paso": "GET /productos/{id} - DynamoDB",
                "producto_id": producto_id,
                "detalle": str(exc),
            },
        )

    atributos = {}
    imagen_original_key = ""
    miniatura_key = ""
    estado_imagen = ""

    if item:
        atributos = item.get(
            "atributos",
            {}
        ).get("M", {})

        imagen_original_key = item.get(
            "imagen_original_key",
            {}
        ).get("S", "")

        miniatura_key = item.get(
            "miniatura_key",
            {}
        ).get("S", "")

        estado_imagen = item.get(
            "estado_imagen",
            {}
        ).get("S", "")

    # -----------------------------------------------------
    # 3. Construir respuesta
    # -----------------------------------------------------

    return {
        "producto_id": row[0],
        "codigo": row[1],
        "nombre": row[2],
        "descripcion": row[3],
        "precio": float(row[4]),
        "categoria_id": row[5],
        "categoria": row[6],
        "fecha_creacion": row[7].isoformat()
            if row[7]
            else None,
        "estado": row[8],
        "atributos": atributos,
        "imagen_original_key": imagen_original_key,
        "miniatura_key": miniatura_key,
        "estado_imagen": estado_imagen,
    }

@app.get("/productos/{producto_id}/imagen")
def obtener_imagen(producto_id: int):

    # -----------------------------------------------------
    # 1. Verificar producto en RDS
    # -----------------------------------------------------

    try:
        conn = get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT producto_id
                    FROM productos
                    WHERE producto_id = %s
                    """,
                    (producto_id,),
                )

                producto = cursor.fetchone()

        finally:
            conn.close()

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar RDS",
                "paso": "GET /productos/{id}/imagen - RDS",
                "producto_id": producto_id,
                "detalle": str(exc),
            },
        )

    if producto is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Producto no encontrado",
                "paso": "GET /productos/{id}/imagen",
                "producto_id": producto_id,
            },
        )

    # -----------------------------------------------------
    # 2. Obtener miniatura desde DynamoDB
    # -----------------------------------------------------

    try:
        item = get_dynamodb_item(producto_id)

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No se pudo consultar DynamoDB",
                "paso": "GET /productos/{id}/imagen - DynamoDB",
                "producto_id": producto_id,
                "detalle": str(exc),
            },
        )

    if not item:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "No existe información de imagen",
                "paso": "GET /productos/{id}/imagen",
                "producto_id": producto_id,
            },
        )

    miniatura_key = item.get(
        "miniatura_key",
        {}
    ).get("S", "")

    if not miniatura_key:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "La miniatura no está disponible",
                "paso": "GET /productos/{id}/imagen",
                "producto_id": producto_id,
            },
        )

    # -----------------------------------------------------
    # 3. Recuperar miniatura desde S3
    # -----------------------------------------------------

    try:
        response = s3.get_object(
            Bucket=THUMBNAIL_BUCKET,
            Key=miniatura_key,
        )

        image_bytes = response["Body"].read()

        content_type = response.get(
            "ContentType",
            "application/octet-stream",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "La miniatura no está disponible en S3",
                "paso": "GET /productos/{id}/imagen - S3",
                "producto_id": producto_id,
                "miniatura_key": miniatura_key,
                "detalle": str(exc),
            },
        )

    # -----------------------------------------------------
    # 4. Devolver bytes
    # -----------------------------------------------------

    return Response(
        content=image_bytes,
        media_type=content_type,
    )
