# ==============================================================================
# SCRIPT DE PUESTA EN MARCHA EN OTRA MAQUINA (LOMAX SA)
# ==============================================================================
$ErrorActionPreference = "Continue"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  INICIANDO PLATAFORMA LOMAX CLOUD EN NUEVA MAQUINA" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan

$ROOT_DIR = (Get-Location).Path
$FLOCI_DATA = Join-Path $ROOT_DIR "floci-data"

# 1. Configurar credenciales dummy para AWS CLI
Write-Host "`n[1/7] Configurando perfil AWS CLI local..." -ForegroundColor Green
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = "us-east-1"
aws configure set aws_access_key_id test
aws configure set aws_secret_access_key test
aws configure set default.region us-east-1

# 2. Iniciar FLOCI si no está corriendo
Write-Host "`n[2/7] Verificando e iniciando contenedor FLOCI..." -ForegroundColor Green
$flociRunning = docker ps --filter "name=floci" --filter "status=running" -q
if (-not $flociRunning) {
    docker rm -f floci 2>$null
    docker run -d `
      --name floci `
      --restart unless-stopped `
      -p 4566:4566 `
      -p 7001-7099:7001-7099 `
      -v "${FLOCI_DATA}:/app/data" `
      -v /var/run/docker.sock:/var/run/docker.sock `
      -e FLOCI_STORAGE_MODE=persistent `
      -e FLOCI_STORAGE_PERSISTENT_PATH=/app/data `
      -e FLOCI_SERVICES_ECR_URI_STYLE=path `
      floci/floci:latest
    Start-Sleep -Seconds 8
} else {
    Write-Host "FLOCI ya se encuentra en ejecucion." -ForegroundColor Gray
}

# 3. Iniciar registro ECR y conectar red
Write-Host "`n[3/7] Configurando red y registro ECR..." -ForegroundColor Green
docker start floci-ecr-registry 2>$null
docker network create floci-net 2>$null
docker network connect floci-net floci 2>$null
docker network connect floci-net floci-ecr-registry 2>$null

# 4. Iniciar contenedor de base de datos RDS si está detenido
Write-Host "`n[4/7] Verificando contenedor RDS PostgreSQL..." -ForegroundColor Green
$rdsContainer = docker ps -a --filter "name=floci-rds" --format "{{.Names}}" | Select-Object -First 1
if ($rdsContainer) {
    docker start $rdsContainer | Out-Null
    Write-Host "   Contenedor RDS activo: $rdsContainer" -ForegroundColor Gray
} else {
    Write-Host "RDS será inicializado por FLOCI bajo demanda en el puerto 7001." -ForegroundColor Gray
}

# ------------------------------------------------------------------
# PASO 4.5: Inicializar la base de datos lomax en RDS
# ------------------------------------------------------------------
Write-Host "`n[4.5/7] Inicializando base de datos lomax en RDS..." -ForegroundColor Green

# Refrescar el nombre del contenedor RDS (por si FLOCI lo recreó)
$rdsContainer = docker ps --filter "name=floci-rds" --format "{{.Names}}" | Select-Object -First 1

if (-not $rdsContainer) {
    Write-Host "   [!] No se encontro contenedor RDS. Saltando inicializacion." -ForegroundColor Yellow
} else {
    # Esperar a que PostgreSQL acepte conexiones
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        docker exec -e PGPASSWORD=LomaxDB2026! $rdsContainer pg_isready -U admin -d postgres *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }

    if (-not $ready) {
        Write-Host "   [!] RDS no respondio a tiempo. Saltando inicializacion." -ForegroundColor Yellow
    } else {
        # Crear la base lomax si no existe
        $existe = docker exec -e PGPASSWORD=LomaxDB2026! $rdsContainer `
            psql -U admin -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='lomax'"
        if ($existe -ne "1") {
            docker exec -e PGPASSWORD=LomaxDB2026! $rdsContainer `
                psql -U admin -d postgres -c "CREATE DATABASE lomax;" | Out-Null
            Write-Host "   [OK] Base 'lomax' creada" -ForegroundColor Gray
        } else {
            Write-Host "   [OK] Base 'lomax' ya existe" -ForegroundColor Gray
        }

        # Copiar y ejecutar schema + seed
        docker cp .\database\rds\01_schema.sql "${rdsContainer}:/tmp/01_schema.sql" | Out-Null
        docker cp .\database\rds\02_seed.sql   "${rdsContainer}:/tmp/02_seed.sql"   | Out-Null
        docker exec -e PGPASSWORD=LomaxDB2026! $rdsContainer `
            psql -U admin -d lomax -f /tmp/01_schema.sql | Out-Null
        docker exec -e PGPASSWORD=LomaxDB2026! $rdsContainer `
            psql -U admin -d lomax -f /tmp/02_seed.sql   | Out-Null
        Write-Host "   [OK] Schema y datos iniciales aplicados en RDS" -ForegroundColor Gray
    }
}

# ------------------------------------------------------------------
# PASO 4.6: Construir y registrar la imagen de Lambda en FLOCI
# ------------------------------------------------------------------
Write-Host "`n[4.6/7] Registrando imagen de Lambda en FLOCI..." -ForegroundColor Green

# Verificar que la imagen exista; si no, construirla
$imgExists = docker images -q lomax-image-processor:latest
if (-not $imgExists) {
    if (Test-Path ".\stage3\lambda\Dockerfile") {
        Write-Host "   Construyendo imagen lomax-image-processor..." -ForegroundColor Gray
        Push-Location .\stage3\lambda
        docker build -t lomax-image-processor:latest . | Out-Null
        Pop-Location
        Write-Host "   [OK] Imagen construida" -ForegroundColor Gray
    } else {
        Write-Host "   [!] No se encontro stage3\lambda\Dockerfile" -ForegroundColor Yellow
    }
} else {
    Write-Host "   [OK] Imagen lomax-image-processor ya existe" -ForegroundColor Gray
}

# Registrar/actualizar la Lambda en FLOCI
aws --endpoint-url=http://localhost:4566 lambda update-function-code `
    --function-name lomax-image-processor `
    --image-uri lomax-image-processor:latest *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   [OK] Lambda 'lomax-image-processor' registrada en FLOCI" -ForegroundColor Gray
} else {
    Write-Host "   [!] No se pudo registrar la Lambda. Revisa que FLOCI este arriba." -ForegroundColor Yellow
}

# 5. Iniciar Backend y Frontend con Docker Compose
Write-Host "`n[5/7] Levantando Backend y Frontend..." -ForegroundColor Green
docker-compose up -d

# 6. Iniciar clúster EKS y configurar kubectl
Write-Host "`n[6/7] Inicializando clúster EKS..." -ForegroundColor Green
docker start floci-eks-lomax-eks 2>$null
docker network connect floci-net floci-eks-lomax-eks 2>$null

# Si el clúster k3s se recreó con otro puerto o certificado, actualizar kubeconfig
if (Test-Path "kubeconfig.yaml") {
    $userKubeDir = Join-Path $HOME ".kube"
    if (-not (Test-Path $userKubeDir)) { New-Item -ItemType Directory -Path $userKubeDir -Force | Out-Null }
    Copy-Item -Path "kubeconfig.yaml" -Destination (Join-Path $userKubeDir "config") -Force
    Write-Host "Kubeconfig actualizado en $userKubeDir\config" -ForegroundColor Gray
}

# Aplicar manifiestos k8s
Start-Sleep -Seconds 3
kubectl apply -f k8s/configmap.yaml 2>$null
kubectl apply -f k8s/secret.yaml 2>$null
kubectl apply -f k8s/backend.yaml 2>$null
kubectl apply -f k8s/frontend.yaml 2>$null

# 7. Asegurar que los 20 productos estén publicados en el catálogo
Write-Host "`n[7/7] Verificando publicaciones en el catálogo..." -ForegroundColor Green
docker cp scripts/publish_all_products.py lomax-backend:/app/publish_all_products.py 2>$null
docker cp stage3/imagenes/cohete.png lomax-backend:/app/cohete.png 2>$null
docker exec lomax-backend python /app/publish_all_products.py

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "  SISTEMA LOMAX LISTO PARA USAR" -ForegroundColor Yellow
Write-Host "  Frontend Web:  http://localhost:8080" -ForegroundColor Green
Write-Host "  Backend API:   http://localhost:8000" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Ejecuta 'powershell .\scripts\verificar_todo.ps1' para correr todas las pruebas." -ForegroundColor Gray