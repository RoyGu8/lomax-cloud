-- P3 - Pruebas de restricciones RDS

-- PRUEBA 1: inserción válida
INSERT INTO productos
    (codigo, nombre, descripcion, precio, categoria_id, estado)
SELECT
    'TEST-VALIDO',
    'Producto de prueba válido',
    'Registro utilizado para comprobar una inserción válida.',
    100.00,
    categoria_id,
    'PENDIENTE'
FROM categorias
WHERE nombre = 'Periféricos';

-- PRUEBA 2: código duplicado
-- Debe ser rechazada por la restricción UNIQUE de productos.codigo.
INSERT INTO productos
    (codigo, nombre, descripcion, precio, categoria_id, estado)
SELECT
    'TEST-VALIDO',
    'Producto duplicado',
    'Este registro debe ser rechazado.',
    150.00,
    categoria_id,
    'PENDIENTE'
FROM categorias
WHERE nombre = 'Periféricos';

-- PRUEBA 3: precio negativo
-- Debe ser rechazada por CHECK (precio >= 0).
INSERT INTO productos
    (codigo, nombre, descripcion, precio, categoria_id, estado)
SELECT
    'TEST-NEGATIVO',
    'Producto con precio negativo',
    'Este registro debe ser rechazado.',
    -10.00,
    categoria_id,
    'PENDIENTE'
FROM categorias
WHERE nombre = 'Periféricos';

-- PRUEBA 4: categoría inexistente
-- Debe ser rechazada por la FK productos.categoria_id.
INSERT INTO productos
    (codigo, nombre, descripcion, precio, categoria_id, estado)
VALUES
    ('TEST-CATEGORIA', 'Producto con categoría inexistente',
     'Este registro debe ser rechazado.', 50.00, 999999, 'PENDIENTE');
