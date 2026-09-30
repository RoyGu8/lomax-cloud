# Lomax SA - Sistema de Catálogo y Registro de Productos Cloud

Proyecto integrador de **Cloud Computing, Docker, Kubernetes y AWS (emulado en FLOCI)** para la comercialización y consulta centralizada de productos tecnológicos con fotografías y atributos variables.

---

## 🚀 Arquitectura y Servicios
- **Frontend & Reverse Proxy:** HTML5, CSS3, JavaScript modular servido por **Nginx** (puerto 8080 en Docker / 30080 en EKS). Enruta `/` a interfaz y `/api/` al backend.
- **Backend API:** **FastAPI (Python 3.13)** en puerto 8000 con endpoints RESTful, validación Pydantic, manejo de estados transaccionales e idempotencia.
- **Relational Database (RDS):** **PostgreSQL 16** en puerto 7001 para categorías y productos (`PENDIENTE` / `PUBLICADO`), integridad referencial y restricciones CHECK/UNIQUE.
- **NoSQL Database (DynamoDB):** Tabla `producto_atributos` en FLOCI (puerto 4566) para atributos variables heterogéneos y metadatos de imágenes por `producto_id`.
- **Object Storage (S3):** Buckets `lomax-originales` y `lomax-miniaturas` en FLOCI.
- **Serverless (Lambda):** Función `lomax-image-processor` con Pillow para generación determinista de miniaturas (máximo 300 × 300 píxeles, manteniendo proporción).
- **Container Registry (ECR):** Repositorios `lomax-frontend` y `lomax-backend` en FLOCI.
- **Orquestación (EKS):** Clúster Kubernetes `lomax-eks` en puerto 6500 con escalado a 3 réplicas del backend y autorrecuperación de Pods demostrada.

---

## 📂 Estructura del Repositorio
```text
├── backend/                  # Código fuente de la API FastAPI y Dockerfile
│   ├── app/main.py           # Endpoints y lógica de negocio
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # Interfaz de usuario y configuración Nginx
│   ├── public/               # HTML, CSS, JS del catálogo y formulario
│   ├── nginx/nginx.conf      # Reverse proxy /api/
│   └── Dockerfile
├── database/                 # Scripts SQL y DynamoDB
│   ├── rds/                  # 01_schema.sql, 02_seed.sql, 03_tests.sql
│   └── dynamodb/             # create-table.ps1, seed.ps1, tests.ps1
├── stage3/                   # S3 y Lambda
│   ├── lambda/               # lambda_function.py, Dockerfile, paquetes
│   └── imagenes/             # Imágenes de prueba (originales y miniaturas)
├── k8s/                      # Manifiestos de Kubernetes para EKS
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── backend.yaml          # Deployment y Service (3 réplicas)
│   └── frontend.yaml         # Deployment, Nginx ConfigMap y Service NodePort
├── docs/                     # Documentación técnica y conceptual
│   ├── saber-conocer.md      # Tablas conceptuales completas y justificación
│   └── etapa-1-arquitectura.md # Diagrama y flujos detallados
├── scripts/                  # Scripts automatizados
│   ├── publish_all_products.py # Publicación de los 20+ productos con fotos
│   └── verificar_todo.ps1    # Script maestro de pruebas E1 a E7
├── docker-compose.yml        # Orquestación local frontend + backend + proxy
├── kubeconfig.yaml           # Configuración de acceso al clúster EKS
└── README.md
```

---

## ⚡ Cómo Ejecutar las Pruebas de Verificación (E1 a E7)

### Opción 1: Ejecución Total Automatizada (Recomendada)
Abre PowerShell en la raíz del proyecto y ejecuta:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verificar_todo.ps1
```
Este script ejecutará secuencialmente y mostrará en consola:
- **E1:** Estado de contenedores y servicios en FLOCI (S3, DynamoDB, Lambda, ECR, EKS).
- **E2:** Consultas a RDS (20+ productos en 3 categorías) y get-item en DynamoDB.
- **E3:** Listado de buckets S3 y validación de redimensionamiento de Lambda (1200x800 -> 300x200).
- **E4:** Prueba de endpoints de la API (códigos 200, 201, 409 por duplicado, obtención de bytes de imagen).
- **E5:** Prueba de acceso al frontend (puerto 8080) y proxy `/api/`.
- **E6:** Tablas de `ecr describe-images` con tags y SHA256 digests.
- **E7:** Nodos y Pods en EKS, 3 réplicas del backend atendiendo tráfico, autorrecuperación y prueba interna.

---

### Opción 2: Verificaciones Manuales Paso a Paso

#### 1. Verificación E2: Persistencia en RDS y DynamoDB
```powershell
# Consultar productos en RDS a través del backend
docker exec lomax-backend python -c "import psycopg2; conn = psycopg2.connect(host='host.docker.internal', port=7001, dbname='lomax', user='admin', password='LomaxDB2026!'); cur = conn.cursor(); cur.execute('SELECT count(*) FROM productos WHERE estado = \'PUBLICADO\''); print('Publicados:', cur.fetchone()[0]); conn.close()"

# Consultar item en DynamoDB
aws dynamodb get-item --table-name producto_atributos --key '{\"producto_id\":{\"S\":\"1\"}}' --endpoint-url http://localhost:4566
```

#### 2. Verificación E3: S3 y Lambda
```powershell
# Listar miniaturas generadas determinísticamente por Lambda
aws --endpoint-url http://localhost:4566 s3 ls s3://lomax-miniaturas/miniaturas/ --recursive

# Ver dimensiones del test de Lambda
Get-Content .\stage3\lambda\resultado-lomax-image-processor.json
```

#### 3. Verificación E4: Backend y Endpoints
```powershell
# Categorías (200 OK)
curl.exe -i http://localhost:8000/categorias

# Catálogo completo combinado (200 OK)
curl.exe http://localhost:8000/productos

# Descarga de imagen procesada desde API (200 OK image/png)
curl.exe -i http://localhost:8000/productos/1/imagen

# Rechazo de código duplicado (409 Conflict)
curl.exe -i -X POST http://localhost:8000/productos -H "Content-Type: application/json" -d "{\"codigo\":\"PER-001\",\"nombre\":\"Duplicado\",\"descripcion\":\"x\",\"precio\":10,\"categoria_id\":1,\"atributos\":{}}"
```

#### 4. Verificación E5: Frontend y Catálogo Web
Abre tu navegador en:
```text
http://localhost:8080
```
- Podrás ver las tarjetas con miniaturas, nombres, precios y categorías de los 20+ productos publicados.
- Al hacer clic en una tarjeta, se despliega el panel de detalle con atributos específicos (resolución/pulgadas para pantallas, conexión/distribución para teclados).
- Puedes registrar nuevos productos y subir imágenes desde el formulario.

#### 5. Verificación E6: Publicación en ECR
```powershell
aws --endpoint-url http://localhost:4566 ecr describe-images --repository-name lomax-frontend --output table
aws --endpoint-url http://localhost:4566 ecr describe-images --repository-name lomax-backend --output table
```

#### 6. Verificación E7: Kubernetes / EKS
```powershell
# Ver estado de Pods (3 réplicas de backend)
kubectl get pods,svc,deploy -o wide

# Ver distribución de logs entre las 3 réplicas
kubectl logs -l app=lomax,tier=backend --tail 5 --prefix

# Probar autorrecuperación (eliminar un Pod y ver su reemplazo inmediato con nuevo UID)
kubectl delete pod -l app=lomax,tier=backend --wait=false
kubectl get pods -l app=lomax,tier=backend -w
```
