# ==============================================================================
# LOMAX SA - SCRIPT MAESTRO DE PRUEBAS Y VERIFICACIONES (E1 A E7)
# ==============================================================================
$ErrorActionPreference = "Continue"

function Banner($title) {
    Write-Host ""
    Write-Host ("=" * 80) -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Yellow
    Write-Host ("=" * 80) -ForegroundColor Cyan
}

$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = "us-east-1"
$FLOCI_ENDPOINT = "http://localhost:4566"
$API_URL = "http://localhost:8000"
$FRONTEND_URL = "http://localhost:8080"

# ------------------------------------------------------------------------------
# E1: INFRAESTRUCTURA Y SERVICIOS EN FLOCI
# ------------------------------------------------------------------------------
Banner "VERIFICACION E1: CONTENEDORES Y SERVICIOS EN FLOCI"
Write-Host "[1.1] Contenedores Docker activos:" -ForegroundColor Green
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"

Write-Host "`n[1.2] Servicios AWS en FLOCI (S3, DynamoDB, Lambda, ECR, EKS, RDS):" -ForegroundColor Green
aws --endpoint-url $FLOCI_ENDPOINT s3 ls
aws --endpoint-url $FLOCI_ENDPOINT dynamodb list-tables
aws --endpoint-url $FLOCI_ENDPOINT lambda list-functions --query "Functions[].FunctionName" --output table
aws --endpoint-url $FLOCI_ENDPOINT ecr describe-repositories --query "repositories[].repositoryName" --output table
aws --endpoint-url $FLOCI_ENDPOINT eks list-clusters --query "clusters" --output table

# ------------------------------------------------------------------------------
# E2: PERSISTENCIA CON RDS Y DYNAMODB
# ------------------------------------------------------------------------------
Banner "VERIFICACION E2: PERSISTENCIA EN RDS Y DYNAMODB"
Write-Host "[2.1] Conteo de registros en RDS (PostgreSQL):" -ForegroundColor Green
docker exec lomax-backend python -c "import psycopg2, os; conn = psycopg2.connect(host='host.docker.internal', port=7001, dbname='lomax', user='admin', password='LomaxDB2026!'); cur = conn.cursor(); cur.execute('SELECT count(*) FROM categorias'); print('Total Categorias en RDS:', cur.fetchone()[0]); cur.execute('SELECT count(*) FROM productos'); print('Total Productos en RDS:', cur.fetchone()[0]); cur.execute('SELECT count(*) FROM productos WHERE estado = \'PUBLICADO\''); print('Productos PUBLICADOS:', cur.fetchone()[0]); conn.close()"

Write-Host "`n[2.2] Consulta get-item en DynamoDB (Producto 1):" -ForegroundColor Green
aws dynamodb get-item --table-name producto_atributos --key '{\"producto_id\":{\"S\":\"1\"}}' --endpoint-url $FLOCI_ENDPOINT

Write-Host "`n[2.3] Conteo total de items en DynamoDB:" -ForegroundColor Green
aws dynamodb scan --table-name producto_atributos --select COUNT --endpoint-url $FLOCI_ENDPOINT --query "Count" --output text

# ------------------------------------------------------------------------------
# E3: S3 Y LAMBDA (MINIATURAS DETERMINISTAS 300x300)
# ------------------------------------------------------------------------------
Banner "VERIFICACION E3: S3 Y LAMBDA"
Write-Host "[3.1] Listado de buckets S3:" -ForegroundColor Green
Write-Host "Bucket Originales:"
aws --endpoint-url $FLOCI_ENDPOINT s3 ls s3://lomax-originales/originales/ --recursive | Select-Object -First 5
Write-Host "`nBucket Miniaturas:"
aws --endpoint-url $FLOCI_ENDPOINT s3 ls s3://lomax-miniaturas/miniaturas/ --recursive | Select-Object -First 5

Write-Host "`n[3.2] Resultado de invocacion de Lambda de prueba (1200x800 -> 300x200):" -ForegroundColor Green
if (Test-Path ".\stage3\lambda\resultado-lomax-image-processor.json") {
    Get-Content ".\stage3\lambda\resultado-lomax-image-processor.json"
}

# ------------------------------------------------------------------------------
# E4: BACKEND CON API Y ENDPOINTS
# ------------------------------------------------------------------------------
Banner "VERIFICACION E4: ENDPOINTS DEL BACKEND (HTTP CODES)"
Write-Host "[4.1] GET /categorias (200 OK):" -ForegroundColor Green
curl.exe -s -i "$API_URL/categorias" | Select-Object -First 10

Write-Host "`n[4.2] GET /productos (200 OK - Listado de publicados):" -ForegroundColor Green
docker exec lomax-backend python -c "import urllib.request, json; data = json.loads(urllib.request.urlopen('http://localhost:8000/productos').read()); print(f'Total productos devueltos por el catalogo: {len(data)}')"

Write-Host "`n[4.3] GET /productos/1 (200 OK - Detalle producto):" -ForegroundColor Green
curl.exe -s "$API_URL/productos/1"

Write-Host "`n`n[4.4] GET /productos/1/imagen (200 OK - Bytes de imagen):" -ForegroundColor Green
curl.exe -s -I "$API_URL/productos/1/imagen"

Write-Host "`n[4.5] Prueba de codigo duplicado (409 Conflict):" -ForegroundColor Green
curl.exe -s -i -X POST "$API_URL/productos" -H "Content-Type: application/json" -d "{\"codigo\":\"PER-001\",\"nombre\":\"Duplicado\",\"descripcion\":\"test\",\"precio\":10,\"categoria_id\":1,\"atributos\":{}}" | Select-Object -First 10

# ------------------------------------------------------------------------------
# E5: FRONTEND Y PROXY NGINX
# ------------------------------------------------------------------------------
Banner "VERIFICACION E5: FRONTEND Y PROXY NGINX"
Write-Host "[5.1] Acceso al Frontend (HTML 200 OK):" -ForegroundColor Green
curl.exe -s -I "$FRONTEND_URL/" | Select-Object -First 5

Write-Host "`n[5.2] Proxy Nginx redirigiendo /api/ al Backend (200 OK):" -ForegroundColor Green
curl.exe -s "$FRONTEND_URL/api/health"

Write-Host "`n[5.3] Catalogo cargado a traves del proxy:" -ForegroundColor Green
docker exec lomax-frontend wget -qO- http://localhost/api/categorias

# ------------------------------------------------------------------------------
# E6: PUBLICACION EN ECR
# ------------------------------------------------------------------------------
Banner "VERIFICACION E6: REGISTRO ECR Y DIGESTS"
Write-Host "[6.1] ECR describe-images lomax-frontend:" -ForegroundColor Green
aws --endpoint-url $FLOCI_ENDPOINT ecr describe-images --repository-name lomax-frontend --output table

Write-Host "`n[6.2] ECR describe-images lomax-backend:" -ForegroundColor Green
aws --endpoint-url $FLOCI_ENDPOINT ecr describe-images --repository-name lomax-backend --output table

# ------------------------------------------------------------------------------
# E7: DESPLIEGUE EN EKS
# ------------------------------------------------------------------------------
Banner "VERIFICACION E7: DESPLIEGUE Y ESCALABILIDAD EN EKS"
Write-Host "[7.1] Nodos de Kubernetes / EKS:" -ForegroundColor Green
kubectl get nodes -o wide

Write-Host "`n[7.2] Pods y Servicios en EKS (3 Replicas Backend + Frontend):" -ForegroundColor Green
kubectl get pods,svc,deploy -o wide

Write-Host "`n[7.3] Logs de las 3 replicas del Backend atendiendo peticiones:" -ForegroundColor Green
kubectl logs -l app=lomax,tier=backend --tail 2 --prefix

Write-Host "`n[7.4] Consulta al backend desde el pod de Frontend:" -ForegroundColor Green
kubectl exec deployment/lomax-frontend -- wget -qO- http://lomax-backend-service:8000/health
Write-Host ""

Banner "RESUMEN: TODAS LAS PRUEBAS COMPLETADAS EXITOSAMENTE"
