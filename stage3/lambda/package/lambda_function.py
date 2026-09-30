import io
import os
import json
import boto3
from PIL import Image

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
)

dynamodb = boto3.client(
    "dynamodb",
    endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
)

DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "producto_atributos")
THUMBNAIL_BUCKET = os.environ.get("THUMBNAIL_BUCKET", "lomax-miniaturas")
MAX_SIZE = 5 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png"}


def update_state(producto_id, original_key, estado, miniatura_key="", error=None):
    expression = (
        "SET imagen_original_key = :original, "
        "miniatura_key = :miniatura, "
        "estado_imagen = :estado"
    )

    values = {
        ":original": {"S": original_key},
        ":miniatura": {"S": miniatura_key},
        ":estado": {"S": estado},
    }

    if error:
        expression += ", error_detalle = :error"
        values[":error"] = {"S": str(error)[:500]}

    dynamodb.update_item(
        TableName=DYNAMODB_TABLE,
        Key={"producto_id": {"S": str(producto_id)}},
        UpdateExpression=expression,
        ExpressionAttributeValues=values,
    )


def lambda_handler(event, context):
    producto_id = str(event["producto_id"])
    bucket = event["bucket"]
    original_key = event["key"]

    try:
        response = s3.get_object(
            Bucket=bucket,
            Key=original_key
        )

        content_length = response.get("ContentLength", 0)

        if content_length > MAX_SIZE:
            raise ValueError("La imagen supera el límite de 5 MB")

        data = response["Body"].read()

        if len(data) > MAX_SIZE:
            raise ValueError("La imagen supera el límite de 5 MB")

        image = Image.open(io.BytesIO(data))
        image.verify()

        image = Image.open(io.BytesIO(data))

        if image.format not in ALLOWED_FORMATS:
            raise ValueError("Formato no permitido. Solo JPEG y PNG")

        extension = ALLOWED_FORMATS[image.format]

        width, height = image.size

        if width <= 0 or height <= 0:
            raise ValueError("Dimensiones de imagen inválidas")

        image.thumbnail((300, 300), Image.Resampling.LANCZOS)

        if image.format == "JPEG":
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            output_format = "JPEG"
            content_type = "image/jpeg"
        else:
            if image.mode not in ("RGB", "RGBA", "L"):
                image = image.convert("RGBA")
            output_format = "PNG"
            content_type = "image/png"

        output = io.BytesIO()
        image.save(output, format=output_format)
        output.seek(0)

        filename = original_key.split("/")[-1]
        base_name = filename.rsplit(".", 1)[0]
        thumbnail_key = f"miniaturas/{producto_id}/{base_name}-thumb.{extension}"

        s3.put_object(
            Bucket=THUMBNAIL_BUCKET,
            Key=thumbnail_key,
            Body=output.getvalue(),
            ContentType=content_type,
        )

        update_state(
            producto_id,
            original_key,
            "LISTA",
            thumbnail_key
        )

        return {
            "statusCode": 200,
            "producto_id": producto_id,
            "estado_imagen": "LISTA",
            "imagen_original_key": original_key,
            "miniatura_key": thumbnail_key,
            "dimensiones_original": {
                "width": width,
                "height": height
            },
            "dimensiones_miniatura": {
                "width": image.width,
                "height": image.height
            }
        }

    except Exception as exc:
        update_state(
            producto_id,
            original_key,
            "ERROR",
            "",
            str(exc)
        )

        return {
            "statusCode": 500,
            "producto_id": producto_id,
            "estado_imagen": "ERROR",
            "error": str(exc)
        }
