$ErrorActionPreference = "Stop"

$Endpoint = "http://localhost:4566"
$Region = "us-east-1"
$TableName = "producto_atributos"

aws dynamodb put-item `
  --table-name $TableName `
  --item file://producto-7.json `
  --endpoint-url $Endpoint `
  --region $Region

aws dynamodb put-item `
  --table-name $TableName `
  --item file://producto-14.json `
  --endpoint-url $Endpoint `
  --region $Region

Write-Host "Carga DynamoDB completada correctamente."
