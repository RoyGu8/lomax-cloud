aws dynamodb create-table `
  --table-name producto_atributos `
  --attribute-definitions AttributeName=producto_id,AttributeType=S `
  --key-schema AttributeName=producto_id,KeyType=HASH `
  --billing-mode PAY_PER_REQUEST `
  --endpoint-url http://localhost:4566 `
  --region us-east-1
