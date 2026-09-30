INSERT INTO categorias (nombre)
VALUES
    ('Periféricos'),
    ('Monitores'),
    ('Almacenamiento')
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO productos
    (codigo, nombre, descripcion, precio, categoria_id, estado)
SELECT
    v.codigo,
    v.nombre,
    v.descripcion,
    v.precio,
    c.categoria_id,
    'PENDIENTE'
FROM (
    VALUES
        ('PER-001', 'Teclado mecánico RGB', 'Teclado mecánico con iluminación RGB y conexión USB.', 249.90, 'Periféricos'),
        ('PER-002', 'Mouse inalámbrico', 'Mouse inalámbrico ergonómico con sensor óptico.', 89.90, 'Periféricos'),
        ('PER-003', 'Teclado inalámbrico', 'Teclado inalámbrico compacto para oficina.', 129.90, 'Periféricos'),
        ('PER-004', 'Mouse gaming', 'Mouse para gaming con sensor óptico de alta precisión.', 159.90, 'Periféricos'),
        ('PER-005', 'Audífonos USB', 'Audífonos estéreo con micrófono integrado y conexión USB.', 119.90, 'Periféricos'),
        ('PER-006', 'Webcam Full HD', 'Cámara web Full HD para videoconferencias.', 199.90, 'Periféricos'),
        ('PER-007', 'Hub USB-C', 'Hub USB-C multipuerto para conectar periféricos.', 149.90, 'Periféricos'),

        ('MON-001', 'Monitor 24 pulgadas', 'Monitor Full HD de 24 pulgadas para oficina.', 899.90, 'Monitores'),
        ('MON-002', 'Monitor 27 pulgadas', 'Monitor QHD de 27 pulgadas para productividad.', 1299.90, 'Monitores'),
        ('MON-003', 'Monitor gaming 27 pulgadas', 'Monitor gaming QHD de 27 pulgadas con alta frecuencia.', 1699.90, 'Monitores'),
        ('MON-004', 'Monitor ultrawide 34 pulgadas', 'Monitor ultrawide de 34 pulgadas para productividad.', 2299.90, 'Monitores'),
        ('MON-005', 'Monitor 22 pulgadas', 'Monitor Full HD de 22 pulgadas para oficina.', 749.90, 'Monitores'),
        ('MON-006', 'Monitor profesional 27 pulgadas', 'Monitor de 27 pulgadas orientado a diseño y contenido.', 1899.90, 'Monitores'),
        ('MON-007', 'Monitor portátil 15 pulgadas', 'Monitor portátil de 15 pulgadas para trabajo móvil.', 999.90, 'Monitores'),

        ('ALM-001', 'SSD 500 GB', 'Unidad SSD de 500 GB para almacenamiento rápido.', 299.90, 'Almacenamiento'),
        ('ALM-002', 'SSD 1 TB', 'Unidad SSD de 1 TB para almacenamiento de alto rendimiento.', 499.90, 'Almacenamiento'),
        ('ALM-003', 'SSD 2 TB', 'Unidad SSD de 2 TB para almacenamiento de gran capacidad.', 899.90, 'Almacenamiento'),
        ('ALM-004', 'Disco externo 1 TB', 'Disco externo de 1 TB para respaldo de información.', 329.90, 'Almacenamiento'),
        ('ALM-005', 'Disco externo 2 TB', 'Disco externo de 2 TB para respaldo y transporte de datos.', 449.90, 'Almacenamiento'),
        ('ALM-006', 'Memoria USB 128 GB', 'Memoria USB de 128 GB para almacenamiento portátil.', 79.90, 'Almacenamiento')
) AS v(codigo, nombre, descripcion, precio, categoria_nombre)
JOIN categorias c
    ON c.nombre = v.categoria_nombre
ON CONFLICT (codigo) DO NOTHING;
