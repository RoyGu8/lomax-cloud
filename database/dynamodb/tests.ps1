$ErrorActionPreference = "Stop"

$Endpoint = "http://localhost:4566"
$Region = "us-east-1"
$TableName = "producto_atributos"

Write-Host "=== GET producto 7 ==="
aws dynamodb get-item `
  --table-name $TableName `
  --key file://key-producto-7.json `
  --endpoint-url $Endpoint `
  --region $Region

Write-Host ""
Write-Host "=== GET producto 14 ==="
aws dynamodb get-item `
  --table-name $TableName `
  --key file://key-producto-14.json `
  --endpoint-url $Endpoint `
  --region $Region

Write-Host ""
Write-Host "=== COUNT TOTAL ==="
aws dynamodb scan `
  --table-name $TableName `
  --select COUNT `
  --endpoint-url $Endpoint `
  --region $Region
