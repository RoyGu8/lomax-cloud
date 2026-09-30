# Saber Conocer: Síntesis Conceptual y Justificación Arquitectónica
**Asignatura:** Tecnologías Emergentes I  
**Proyecto:** Sistema de Catálogo Lomax SA (FLOCI / AWS)

---

## 1. Tablas Conceptuales

### 1.1 Cloud Computing
| Concepto | Definición | Relación con la Solución Lomax |
| :--- | :--- | :--- |
| **Características del Cloud Computing** | Autoservicio bajo demanda, acceso amplio a la red, asignación común de recursos (multi-tenant), elasticidad rápida y servicio medido. | Permite a Lomax aprovisionar cómputo, almacenamiento y bases de datos sin invertir en infraestructura física local. |
| **Escalabilidad vertical y horizontal** | *Vertical (Scale-up):* Aumentar CPU/RAM de un nodo. *Horizontal (Scale-out):* Añadir más instancias o Pods en paralelo. | Lomax utiliza escalabilidad horizontal en Kubernetes/EKS (1 a 3 réplicas del backend) para soportar mayor demanda sin límites de hardware único. |
| **Virtualización** | Tecnología que permite crear múltiples entornos simulados o recursos dedicados desde un único sistema de hardware físico (hipervisores tipo 1 y 2). | Es la base que permite ejecutar RDS, k3s y contenedores de manera aislada y reproducible. |
| **IaaS, PaaS y SaaS** | *IaaS:* Infraestructura como servicio (EC2, redes). *PaaS:* Plataforma administrada (RDS, Elastic Beanstalk). *SaaS:* Software final accesible vía web (Google Workspace, ERPs). | Lomax combina PaaS (RDS, DynamoDB) y Serverless/FaaS (AWS Lambda) para reducir la sobrecarga operativa de administración de servidores. |
| **Tipos de nube** | *Pública:* Propiedad de terceros (AWS). *Privada:* Dedicada a una sola organización. *Híbrida:* Conexión entre pública y privada. *Comunitaria:* Compartida por entidades afines. | La arquitectura está diseñada para nube pública (AWS) y emulada localmente con FLOCI para desarrollo y pruebas offline. |
| **Ventajas y limitaciones de los servicios cloud** | *Ventajas:* Reducción de CapEx, alta disponibilidad, escalabilidad global. *Limitaciones:* Dependencia de conectividad, riesgo de vendor lock-in y costos imprevistos por transferencia de datos. | Lomax aprovecha alta disponibilidad y almacenamiento duradero en S3, mitigando costos con miniaturas optimizadas. |

---

### 1.2 Contenedores
| Concepto | Definición | Relación con la Solución Lomax |
| :--- | :--- | :--- |
| **Concepto de contenedor** | Unidad estándar de software que empaqueta código y dependencias, compartiendo el kernel del SO anfitrión de forma aislada. | Permite que backend y frontend corran de forma idéntica en desarrollo local, FLOCI y producción. |
| **Imagen y contenedor** | *Imagen:* Plantilla inmutable de solo lectura con capas del sistema. *Contenedor:* Instancia viva y ejecutable de una imagen con una capa de lectura/escritura. | Las imágenes `lomax-backend:1.0` y `lomax-frontend:1.0` se construyen una vez y se despliegan en múltiples réplicas en EKS. |
| **Dockerfile** | Archivo de texto plano con instrucciones secuenciales (`FROM`, `COPY`, `RUN`, `CMD`) para construir una imagen Docker. | Utilizados para construir el backend FastAPI (`python:3.13-slim`) y el frontend Nginx (`nginx:alpine`). |
| **Redes de Docker** | Mecanismo que define cómo se comunican los contenedores (Bridge, Host, Overlay, None). En redes personalizadas existe resolución DNS interna por nombre. | Se configuró `floci-net` y `lomax-network` para permitir comunicación DNS entre FLOCI, el registro ECR, la base de datos y la API. |
| **Volúmenes** | Mecanismo de persistencia administrado por Docker fuera del ciclo de vida del contenedor (independiente del borrado del contenedor). | Utilizados por RDS (`floci-rds-...`) para retener datos de productos y categorías aunque se reinicien los contenedores. |
| **Docker Compose** | Herramienta para definir y ejecutar aplicaciones multi-contenedor mediante un archivo YAML declarativo (`docker-compose.yml`). | Orquesta localmente backend, frontend y proxy con variables de entorno y red compartida en un solo comando. |
| **Ventajas y limitaciones de Docker** | *Ventajas:* Ligereza frente a VMs, portabilidad, inicio en segundos. *Limitaciones:* Mismo kernel que el host (no mezcla Windows/Linux nativo), almacenamiento volátil por defecto. | Garantiza despliegues rápidos en Lomax pero requiere almacenamiento externo (S3, RDS, DynamoDB) para estado persistente. |

---

### 1.3 Kubernetes
| Concepto | Definición | Relación con la Solución Lomax |
| :--- | :--- | :--- |
| **Arquitectura básica** | Modelo maestro-trabajador: Control Plane (`kube-apiserver`, `etcd`, `controller-manager`, `scheduler`) y Worker Nodes (`kubelet`, `kube-proxy`, `container runtime`). | Base sobre la que opera Amazon EKS y k3s para orquestar la aplicación Lomax. |
| **Cluster** | Conjunto de máquinas (físicas o virtuales) coordinadas por Kubernetes para ejecutar cargas de trabajo en contenedores. | El clúster `lomax-eks` agrupa los recursos de cómputo donde se ejecutan los microservicios. |
| **Pod** | La unidad de ejecución más pequeña y básica en Kubernetes; alberga uno o más contenedores que comparten red (`localhost`) y volúmenes. | Cada réplica de `lomax-backend` y `lomax-frontend` corre en su propio Pod con IP interna asignada. |
| **Deployment** | Controlador declarativo que gestiona el ciclo de vida de los Pods, actualizaciones progresivas (rolling updates) y número deseado de réplicas. | Gestiona las réplicas del backend y frontend, permitiendo escalar de 1 a 3 sin caída del servicio. |
| **Service** | Abstracción que define un conjunto lógico de Pods y una política de acceso (ClusterIP, NodePort, LoadBalancer) con balanceo interno. | `lomax-backend-service` balancea el tráfico entre las 3 réplicas del backend; `lomax-frontend-service` expone la interfaz. |
| **Escalamiento** | Capacidad de variar la cantidad de Pods (HPA horizontal o manual vía `kubectl scale`) según demanda de CPU/memoria o tráfico. | Demostrado con el escalamiento de 1 a 3 réplicas de `lomax-backend` distribuyendo peticiones. |
| **Autorrecuperación (Self-Healing)** | Capacidad del controlador de recrear automáticamente Pods que fallan o son eliminados para mantener el estado deseado. | Demostrado al eliminar un Pod y verificar que Kubernetes creó inmediatamente un reemplazo con nuevo UID sin interrumpir el catálogo. |

---

### 1.4 AWS
| Servicio | Definición | Justificación y Rol en Lomax SA |
| :--- | :--- | :--- |
| **RDS (Relational Database Service)** | Servicio administrado de bases de datos relacionales (PostgreSQL en nuestro caso) con soporte transaccional ACID y restricciones relacionales. | Almacena datos estructurados críticos: `categorias` y `productos` (código único, nombre, precio >= 0, estado `PENDIENTE`/`PUBLICADO`). Rechaza inconsistencias transaccionales. |
| **DynamoDB** | Base de datos NoSQL de documentos y clave-valor, ultra rápida y escalable, con esquema flexible sin columnas predefinidas. | Almacena atributos variables de productos heterogéneos (teclados con retroiluminación/distribución vs monitores con pulgadas/resolución) y claves/estados de imágenes sin alterar tablas relacionales. |
| **S3 (Simple Storage Service)** | Almacenamiento de objetos duradero, de alta disponibilidad y diseñado para albergar cualquier volumen de datos no estructurados. | Buckets dedicados: `lomax-originales` (fotografías subidas) y `lomax-miniaturas` (versiones reducidas a 300x300 para carga veloz del catálogo). |
| **Lambda** | Servicio de cómputo Serverless (FaaS) que ejecuta código en respuesta a eventos sin aprovisionar ni administrar servidores. | Función `lomax-image-processor`: procesa síncronamente la imagen original, valida JPEG/PNG <= 5MB, genera miniatura determinista proporcional y actualiza DynamoDB. |
| **ECR (Elastic Container Registry)** | Registro de contenedores Docker privado, seguro y de alto rendimiento gestionado por AWS. | Repositorios `lomax-backend` y `lomax-frontend` que almacenan las imágenes construidas con versiones inmutables identificadas por digest. |
| **EKS (Elastic Kubernetes Service)** | Servicio administrado de Kubernetes en AWS que elimina la complejidad de operar el Control Plane. | Ejecuta la aplicación Lomax con tolerancia a fallos, balanceo de carga, autorrecuperación y escalado dinámico de pods. |
