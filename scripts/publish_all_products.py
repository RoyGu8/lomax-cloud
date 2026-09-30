import os
import sys
import json
import boto3
import urllib.request
import urllib.error

API_URL = "http://localhost:8000"
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
DYNAMODB_TABLE = "producto_atributos"

dynamodb = boto3.client(
    "dynamodb",
    endpoint_url=AWS_ENDPOINT_URL,
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)

# Definición de atributos para los 20 productos iniciales
PRODUCTOS_ATRIBUTOS = {
    # Periféricos (IDs 1 a 7) - Set de atributos: Periféricos (conexión, distribución, retroiluminación, etc.)
    1: {"tipo": "periferico", "subtipo": "hub", "conexion": "USB-C", "puertos": "7 en 1", "velocidad": "10 Gbps"},
    2: {"tipo": "periferico", "subtipo": "webcam", "resolucion": "1080p", "fps": 60, "conexion": "USB-A", "microfono": "dual"},
    3: {"tipo": "periferico", "subtipo": "audio", "conexion": "USB", "cancelacion_ruido": True, "impedancia_ohm": 32},
    4: {"tipo": "periferico", "subtipo": "mouse", "sensor": "Optico 16000 DPI", "conexion": "USB", "rgb": True, "botones": 6},
    5: {"tipo": "periferico", "subtipo": "teclado", "conexion": "Inalambrico 2.4GHz", "distribucion": "Espanol", "bateria_horas": 120},
    6: {"tipo": "periferico", "subtipo": "mouse", "conexion": "Inalambrico Bluetooth", "sensor": "Optico 4000 DPI", "ergonomico": True},
    7: {"tipo": "periferico", "subtipo": "teclado", "conexion": "USB / Bluetooth", "distribucion": "Espanol ISO", "retroiluminacion": "RGB", "switches": "Mecanico Brown"},

    # Monitores (IDs 8 a 14) - Set de atributos: Pantallas (pulgadas, resolución, frecuencia, panel)
    8: {"tipo": "monitor", "pulgadas": 15.6, "resolucion": "1920x1080", "frecuencia_hz": 60, "panel": "IPS", "portatil": True},
    9: {"tipo": "monitor", "pulgadas": 27.0, "resolucion": "3840x2160 (4K)", "frecuencia_hz": 60, "panel": "IPS Profesional", "espacio_color": "sRGB 99%"},
    10: {"tipo": "monitor", "pulgadas": 22.0, "resolucion": "1920x1080", "frecuencia_hz": 75, "panel": "VA", "entradas": "HDMI, VGA"},
    11: {"tipo": "monitor", "pulgadas": 34.0, "resolucion": "3440x1440 (UWQHD)", "frecuencia_hz": 144, "panel": "Curvo 1500R VA", "hdr": True},
    12: {"tipo": "monitor", "pulgadas": 27.0, "resolucion": "2560x1440 (QHD)", "frecuencia_hz": 165, "panel": "Fast IPS", "tiempo_respuesta_ms": 1},
    13: {"tipo": "monitor", "pulgadas": 27.0, "resolucion": "2560x1440 (QHD)", "frecuencia_hz": 75, "panel": "IPS", "usb_hub": True},
    14: {"tipo": "monitor", "pulgadas": 24.0, "resolucion": "1920x1080 (FHD)", "frecuencia_hz": 100, "panel": "IPS", "tiempo_respuesta_ms": 4},

    # Almacenamiento (IDs 15 a 20) - Set de atributos: Almacenamiento (capacidad, interfaz, velocidad, formato)
    15: {"tipo": "almacenamiento", "subtipo": "pendrive", "capacidad_gb": 128, "interfaz": "USB 3.2 Gen 1", "carcasa": "Metalica"},
    16: {"tipo": "almacenamiento", "subtipo": "hdd_externo", "capacidad_tb": 2, "interfaz": "USB 3.0", "formato": "2.5 pulgadas"},
    17: {"tipo": "almacenamiento", "subtipo": "hdd_externo", "capacidad_tb": 1, "interfaz": "USB 3.0", "formato": "2.5 pulgadas"},
    18: {"tipo": "almacenamiento", "subtipo": "ssd_nvme", "capacidad_tb": 2, "interfaz": "PCIe 4.0 NVMe M.2", "lectura_mb_s": 7000},
    19: {"tipo": "almacenamiento", "subtipo": "ssd_nvme", "capacidad_tb": 1, "interfaz": "PCIe 4.0 NVMe M.2", "lectura_mb_s": 5000},
    20: {"tipo": "almacenamiento", "subtipo": "ssd_sata", "capacidad_gb": 500, "interfaz": "SATA III 2.5 pulgadas", "lectura_mb_s": 550},
}

def convert_to_dynamo_map(d):
    mapped = {}
    for k, v in d.items():
        if isinstance(v, bool):
            mapped[k] = {"BOOL": v}
        elif isinstance(v, (int, float)):
            mapped[k] = {"N": str(v)}
        elif isinstance(v, str):
            mapped[k] = {"S": v}
        else:
            mapped[k] = {"S": str(v)}
    return {"M": mapped}

def ensure_dynamo_attributes():
    print("-> Verificando y cargando atributos en DynamoDB...")
    for prod_id, attrs in PRODUCTOS_ATRIBUTOS.items():
        try:
            # Comprobar si ya existe
            res = dynamodb.get_item(
                TableName=DYNAMODB_TABLE,
                Key={"producto_id": {"S": str(prod_id)}}
            )
            item = res.get("Item")
            if not item:
                dynamodb.put_item(
                    TableName=DYNAMODB_TABLE,
                    Item={
                        "producto_id": {"S": str(prod_id)},
                        "tipo": {"S": attrs.get("tipo", "producto")},
                        "atributos": convert_to_dynamo_map(attrs),
                        "imagen_original_key": {"S": ""},
                        "miniatura_key": {"S": ""},
                        "estado_imagen": {"S": "PENDIENTE"},
                    }
                )
                print(f"   [+] DynamoDB: Creado item para producto {prod_id}")
            else:
                # Asegurar que tenga el mapa de atributos
                dynamodb.update_item(
                    TableName=DYNAMODB_TABLE,
                    Key={"producto_id": {"S": str(prod_id)}},
                    UpdateExpression="SET atributos = :attr",
                    ExpressionAttributeValues={":attr": convert_to_dynamo_map(attrs)}
                )
                print(f"   [✓] DynamoDB: Atributos actualizados para producto {prod_id}")
        except Exception as e:
            print(f"   [!] Error en DynamoDB para {prod_id}: {e}")

def upload_images(image_path):
    print(f"-> Subiendo imágenes para los 20 productos usando {image_path}...")
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="imagen"; filename="producto.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + img_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    for prod_id in range(1, 21):
        url = f"{API_URL}/productos/{prod_id}/imagen"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                print(f"   [✓] Producto {prod_id} publicado con éxito: {data.get('miniatura_key')}")
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8")
            print(f"   [!] Error HTTP {e.code} en producto {prod_id}: {err}")
        except Exception as e:
            print(f"   [!] Error general en producto {prod_id}: {e}")

if __name__ == "__main__":
    ensure_dynamo_attributes()
    sample_img = "/app/cohete.png" if os.path.exists("/app/cohete.png") else os.path.join(os.path.dirname(__file__), "..", "stage3", "imagenes", "cohete.png")
    upload_images(sample_img)
    print("\nProceso de publicación de los 20 productos completado.")
