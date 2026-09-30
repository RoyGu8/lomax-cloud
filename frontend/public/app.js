/* ============================================================
   Lomax SA · Dashboard del catálogo
   ============================================================ */

const API_BASE = "/api";

// --------------------------- Referencias DOM ---------------------------
const form             = document.getElementById("productoForm");
const categoriaSelect  = document.getElementById("categoria");
const catalogo         = document.getElementById("catalogo");
const catalogoResumen  = document.getElementById("catalogoResumen");
const mensaje          = document.getElementById("mensaje");
const detalle          = document.getElementById("detalle");
const detalleContenido = document.getElementById("detalleContenido");
const btnActualizar    = document.getElementById("btnActualizar");
const btnSubmit        = document.getElementById("btnSubmit");
const btnReintentar    = document.getElementById("btnReintentar");
const btnCerrarDetalle = document.getElementById("btnCerrarDetalle");
const reintentoBox     = document.getElementById("reintentoBox");
const progreso         = document.getElementById("progreso");
const buscador         = document.getElementById("buscador");
const orden            = document.getElementById("orden");
const toast            = document.getElementById("toast");

// --------------------------- Estado local ---------------------------
let productosCache    = [];
let productoPendiente = null;
let toastTimer        = null;

// ============================================================
//   Utilidades
// ============================================================

function mostrarMensaje(texto, tipo = "info") {
    mensaje.textContent = texto;
    mensaje.classList.remove("success", "error");
    if (tipo === "success") mensaje.classList.add("success");
    if (tipo === "error")   mensaje.classList.add("error");
}

function mostrarToast(texto, tipo = "info", duracion = 3500) {
    toast.textContent = texto;
    toast.classList.remove("hidden", "success", "error");
    if (tipo === "success") toast.classList.add("success");
    if (tipo === "error")   toast.classList.add("error");

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add("hidden"), duracion);
}

function setError(campo, texto = "") {
    const label = document.querySelector(`[data-error-for="${campo}"]`);
    if (!label) return;
    label.textContent = texto;
    const parent = label.closest("label");
    if (parent) parent.classList.toggle("invalid", Boolean(texto));
}

function limpiarErrores() {
    document.querySelectorAll(".field-error").forEach(el => el.textContent = "");
    document.querySelectorAll("label.invalid").forEach(el => el.classList.remove("invalid"));
}

function setProgreso(paso, estado = "active") {
    progreso.classList.remove("hidden");
    progreso.querySelectorAll(".progress-step").forEach(el => {
        const n = Number(el.dataset.step);
        el.classList.remove("active", "done", "error");
        if (n < paso) el.classList.add("done");
        if (n === paso) el.classList.add(estado);
    });
}

function resetProgreso() {
    progreso.classList.add("hidden");
    progreso.querySelectorAll(".progress-step").forEach(el =>
        el.classList.remove("active", "done", "error")
    );
}

function setFormDisabled(disabled) {
    form.querySelectorAll("input, textarea, select, button").forEach(el => {
        el.disabled = disabled;
    });
}

// --------------------------- Decodificador DynamoDB ---------------------------
function decodeDynamoValue(value) {
    if (!value || typeof value !== "object") return value;
    if (value.S    !== undefined) return value.S;
    if (value.N    !== undefined) return Number(value.N);
    if (value.BOOL !== undefined) return value.BOOL;
    if (value.NULL !== undefined) return null;
    if (value.M    !== undefined) return decodeDynamoMap(value.M);
    if (value.L    !== undefined) return value.L.map(decodeDynamoValue);
    return value;
}

function decodeDynamoMap(map) {
    const out = {};
    for (const [k, v] of Object.entries(map || {})) {
        out[k] = decodeDynamoValue(v);
    }
    return out;
}

// --------------------------- Formateo ---------------------------
function formatearBs(valor) {
    return new Intl.NumberFormat("es-BO", {
        style: "currency",
        currency: "BOB",
        minimumFractionDigits: 2,
    }).format(Number(valor) || 0);
}

function formatearAtributo(valor) {
    if (valor === null || valor === undefined) return "—";
    if (typeof valor === "object") return JSON.stringify(valor);
    if (typeof valor === "boolean") return valor ? "Sí" : "No";
    return String(valor);
}

// ============================================================
//   Carga de categorías
// ============================================================

async function cargarCategorias() {
    try {
        const response = await fetch(`${API_BASE}/categorias`);
        if (!response.ok) throw new Error("No se pudieron cargar las categorías.");

        const categorias = await response.json();

        categoriaSelect.innerHTML = '<option value="">Seleccione…</option>';
        categorias.forEach(cat => {
            const option = document.createElement("option");
            option.value = cat.categoria_id;
            option.textContent = cat.nombre || cat.categoria_nombre || `Categoría ${cat.categoria_id}`;
            categoriaSelect.appendChild(option);
        });

    } catch (err) {
        categoriaSelect.innerHTML = '<option value="">Error al cargar</option>';
        mostrarMensaje(err.message, "error");
    }
}

// ============================================================
//   Catálogo
// ============================================================

function renderSkeleton() {
    catalogo.innerHTML = "";
    for (let i = 0; i < 6; i++) {
        const sk = document.createElement("div");
        sk.className = "skeleton-card";
        sk.innerHTML = `
            <div class="sk-img"></div>
            <div class="sk-line"></div>
            <div class="sk-line short"></div>
        `;
        catalogo.appendChild(sk);
    }
}

async function cargarCatalogo() {
    renderSkeleton();

    try {
        const response = await fetch(`${API_BASE}/productos`);
        if (!response.ok) throw new Error("No se pudo cargar el catálogo.");

        productosCache = await response.json();
        aplicarFiltrosYRender();

    } catch (err) {
        catalogo.innerHTML = `<div class="empty">${err.message}</div>`;
        catalogoResumen.textContent = "—";
    }
}

function aplicarFiltrosYRender() {
    const q = (buscador?.value || "").trim().toLowerCase();
    const ordenSel = orden?.value || "recientes";

    let lista = [...productosCache];

    if (q) {
        lista = lista.filter(p =>
            (p.nombre || "").toLowerCase().includes(q) ||
            (p.codigo || "").toLowerCase().includes(q)
        );
    }

    lista.sort((a, b) => {
        switch (ordenSel) {
            case "nombre":
                return (a.nombre || "").localeCompare(b.nombre || "");
            case "precio-asc":
                return Number(a.precio) - Number(b.precio);
            case "precio-desc":
                return Number(b.precio) - Number(a.precio);
            case "recientes":
            default:
                return Number(b.producto_id) - Number(a.producto_id);
        }
    });

    renderCatalogo(lista);
}

function renderCatalogo(productos) {
    catalogoResumen.textContent = productos.length
        ? `${productos.length} producto(s) publicado(s)`
        : "Sin resultados";

    if (!productos.length) {
        catalogo.innerHTML = `<div class="empty">No hay productos publicados que coincidan.</div>`;
        return;
    }

    catalogo.innerHTML = "";

    productos.forEach(producto => {
        const card = document.createElement("article");
        card.className = "card";
        card.tabIndex = 0;

        const imagenUrl = `${API_BASE}/productos/${producto.producto_id}/imagen`;

        card.innerHTML = `
            <div class="card-img-wrap">
                <img
                    src="${imagenUrl}"
                    alt="${escapeHtml(producto.nombre)}"
                    loading="lazy"
                    onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 200 200%22><rect width=%22200%22 height=%22200%22 fill=%22%23eef1f5%22/><text x=%22100%22 y=%22105%22 text-anchor=%22middle%22 fill=%22%2394a3b8%22 font-family=%22Arial%22 font-size=%2214%22>Sin imagen</text></svg>'"
                >
            </div>
            <div class="card-content">
                <div class="categoria">${escapeHtml(producto.categoria_nombre || "")}</div>
                <h3>${escapeHtml(producto.nombre)}</h3>
                <div class="precio">${formatearBs(producto.precio)}</div>
            </div>
        `;

        card.addEventListener("click", () => cargarDetalle(producto.producto_id));
        card.addEventListener("keydown", e => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                cargarDetalle(producto.producto_id);
            }
        });

        catalogo.appendChild(card);
    });
}

function escapeHtml(str) {
    return String(str ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

// ============================================================
//   Detalle
// ============================================================

async function cargarDetalle(productoId) {
    try {
        const response = await fetch(`${API_BASE}/productos/${productoId}`);
        if (!response.ok) throw new Error("No se pudo obtener el detalle.");

        const producto = await response.json();
        const atributos = decodeDynamoMap(producto.atributos || {});

        const badgeClass = producto.estado === "PUBLICADO"
            ? "badge-publicado"
            : "badge-pendiente";

        const atributosHtml = Object.keys(atributos).length
            ? `<div class="atributos-lista">
                ${Object.entries(atributos).map(([k, v]) => `
                    <div class="atributo-item">
                        <span class="k">${escapeHtml(k)}</span>
                        <span class="v">${escapeHtml(formatearAtributo(v))}</span>
                    </div>
                `).join("")}
               </div>`
            : `<p class="muted">Sin atributos registrados.</p>`;

        detalleContenido.innerHTML = `
            <div class="detalle-grid">
                <div>
                    ${producto.miniatura_key
                        ? `<img src="${API_BASE}/productos/${producto.producto_id}/imagen"
                                alt="${escapeHtml(producto.nombre)}">`
                        : `<div class="empty">Sin imagen disponible</div>`}
                </div>

                <div class="detalle-info">
                    <h3>${escapeHtml(producto.nombre)}</h3>
                    <p><strong>Código</strong> ${escapeHtml(producto.codigo)}</p>
                    <p><strong>Descripción</strong> ${escapeHtml(producto.descripcion)}</p>
                    <p><strong>Precio</strong> ${formatearBs(producto.precio)}</p>
                    <p><strong>Estado</strong>
                        <span class="badge ${badgeClass}">${escapeHtml(producto.estado)}</span>
                    </p>

                    <div class="atributos">
                        <h4>Atributos</h4>
                        ${atributosHtml}
                    </div>
                </div>
            </div>
        `;

        detalle.classList.remove("hidden");
        detalle.scrollIntoView({ behavior: "smooth", block: "start" });

    } catch (err) {
        mostrarToast(err.message, "error");
    }
}

btnCerrarDetalle?.addEventListener("click", () => detalle.classList.add("hidden"));

// ============================================================
//   Validación del formulario
// ============================================================

function validarFormulario() {
    limpiarErrores();
    let valido = true;

    const codigo      = document.getElementById("codigo").value.trim();
    const nombre      = document.getElementById("nombre").value.trim();
    const descripcion = document.getElementById("descripcion").value.trim();
    const precio      = Number(document.getElementById("precio").value);
    const categoriaId = Number(categoriaSelect.value);
    const atributosRaw= document.getElementById("atributos").value.trim();
    const archivo     = document.getElementById("imagen").files[0];

    if (!codigo) {
        setError("codigo", "El código es obligatorio.");
        valido = false;
    }

    if (!nombre) {
        setError("nombre", "El nombre es obligatorio.");
        valido = false;
    }

    if (!descripcion) {
        setError("descripcion", "La descripción es obligatoria.");
        valido = false;
    }

    if (!Number.isFinite(precio) || precio < 0) {
        setError("precio", "El precio debe ser un número mayor o igual a 0.");
        valido = false;
    }

    if (!categoriaId) {
        setError("categoria", "Debe seleccionar una categoría.");
        valido = false;
    }

    try {
        const parsed = JSON.parse(atributosRaw);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            throw new Error();
        }
    } catch {
        setError("atributos", "Los atributos deben ser un objeto JSON válido.");
        valido = false;
    }

    if (!archivo) {
        setError("imagen", "Debe seleccionar una imagen.");
        valido = false;
    } else {
        const tiposOk = ["image/jpeg", "image/png"];
        const maxBytes = 5 * 1024 * 1024;
        if (!tiposOk.includes(archivo.type)) {
            setError("imagen", "Solo se permiten archivos JPEG o PNG.");
            valido = false;
        } else if (archivo.size > maxBytes) {
            setError("imagen", "La imagen supera el límite de 5 MB.");
            valido = false;
        }
    }

    return valido;
}

// ============================================================
//   Flujo de registro
// ============================================================

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    reintentoBox.classList.add("hidden");
    productoPendiente = null;

    if (!validarFormulario()) {
        mostrarMensaje("Revisa los campos marcados en rojo.", "error");
        return;
    }

    setFormDisabled(true);
    btnSubmit.textContent = "Procesando…";
    mostrarMensaje("");

    const codigo      = document.getElementById("codigo").value.trim();
    const nombre      = document.getElementById("nombre").value.trim();
    const descripcion = document.getElementById("descripcion").value.trim();
    const precio      = Number(document.getElementById("precio").value);
    const categoriaId = Number(categoriaSelect.value);
    const atributos   = JSON.parse(document.getElementById("atributos").value);
    const archivo     = document.getElementById("imagen").files[0];

    let productoId = null;

    try {
        // --- Paso 1: crear producto ---
        setProgreso(1);
        mostrarMensaje("Registrando producto en RDS + DynamoDB…");

        const resCrear = await fetch(`${API_BASE}/productos`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                codigo,
                nombre,
                descripcion,
                precio,
                categoria_id: categoriaId,
                atributos,
            }),
        });

        const dataCrear = await resCrear.json();

        if (!resCrear.ok) {
            if (resCrear.status === 409) {
                throw Object.assign(new Error("Ese código de producto ya existe."), { campo: "codigo" });
            }
            if (resCrear.status === 400) {
                throw new Error(dataCrear.detail?.error || "Datos inválidos.");
            }
            throw new Error(dataCrear.detail?.error || "No se pudo registrar el producto.");
        }

        productoId = dataCrear.producto_id;
        productoPendiente = productoId;

        // --- Paso 2: subir imagen ---
        setProgreso(2);
        mostrarMensaje(`Producto ${productoId} creado como PENDIENTE. Subiendo imagen…`);

        const formData = new FormData();
        formData.append("imagen", archivo);

        setProgreso(3);
        const resImagen = await fetch(`${API_BASE}/productos/${productoId}/imagen`, {
            method: "POST",
            body: formData,
        });

        const dataImagen = await resImagen.json();

        if (!resImagen.ok) {
            if (resImagen.status === 413) throw new Error("La imagen supera el límite de 5 MB.");
            if (resImagen.status === 415) throw new Error("Formato no permitido (solo JPEG/PNG).");
            if (resImagen.status === 502 || resImagen.status === 503) {
                throw Object.assign(
                    new Error(dataImagen.detail?.error || "Fallo al procesar la imagen."),
                    { pendiente: true }
                );
            }
            throw new Error(dataImagen.detail?.error || "No se pudo procesar la imagen.");
        }

        // --- Paso 4: publicado ---
        setProgreso(4);
        await new Promise(r => setTimeout(r, 250));

        mostrarMensaje(`Producto ${productoId} publicado correctamente.`, "success");
        mostrarToast("Producto publicado", "success");

        form.reset();
        document.getElementById("atributos").value = '{"tipo":"producto"}';
        resetProgreso();

        await cargarCatalogo();

    } catch (err) {
        // Marca el paso actual como error
        progreso.querySelectorAll(".progress-step").forEach(el => {
            if (el.classList.contains("active")) {
                el.classList.remove("active");
                el.classList.add("error");
            }
        });

        mostrarMensaje(err.message, "error");
        mostrarToast(err.message, "error");

        if (err.campo) setError(err.campo, err.message);

        if (err.pendiente && productoPendiente) {
            reintentoBox.classList.remove("hidden");
        }
    } finally {
        setFormDisabled(false);
        btnSubmit.textContent = "Registrar producto";
    }
});

// ============================================================
//   Reintento de imagen pendiente
// ============================================================

btnReintentar?.addEventListener("click", async () => {
    if (!productoPendiente) return;

    btnReintentar.disabled = true;
    btnReintentar.textContent = "Reintentando…";

    try {
        const res = await fetch(`${API_BASE}/productos/${productoPendiente}/reprocesar`, {
            method: "POST",
        });

        const data = await res.json().catch(() => ({}));

        if (res.status === 409) {
            throw new Error("No existe una imagen original guardada para reintentar.");
        }

        if (!res.ok) {
            throw new Error(data.detail?.error || "No se pudo reintentar el procesamiento.");
        }

        mostrarMensaje(`Producto ${productoPendiente} publicado tras reintento.`, "success");
        mostrarToast("Producto publicado", "success");

        reintentoBox.classList.add("hidden");
        productoPendiente = null;
        resetProgreso();

        await cargarCatalogo();

    } catch (err) {
        mostrarMensaje(err.message, "error");
        mostrarToast(err.message, "error");
    } finally {
        btnReintentar.disabled = false;
        btnReintentar.textContent = "Reintentar procesamiento";
    }
});

// ============================================================
//   Eventos auxiliares
// ============================================================

btnActualizar.addEventListener("click", cargarCatalogo);
buscador?.addEventListener("input", aplicarFiltrosYRender);
orden?.addEventListener("change", aplicarFiltrosYRender);

// ============================================================
//   Arranque
// ============================================================

cargarCategorias();
cargarCatalogo();