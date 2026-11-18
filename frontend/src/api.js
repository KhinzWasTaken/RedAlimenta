// Cliente de la API REST del backend. El token JWT se guarda en memoria y en localStorage.
const CLAVE = 'redalimenta.sesion'

let token = null

export function leerSesion() {
  try {
    const s = JSON.parse(localStorage.getItem(CLAVE) || 'null')
    token = s?.token ?? null
    return s
  } catch {
    return null
  }
}

export function guardarSesion(sesion) {
  token = sesion?.token ?? null
  try {
    if (sesion) localStorage.setItem(CLAVE, JSON.stringify(sesion))
    else localStorage.removeItem(CLAVE)
  } catch {
    /* almacenamiento no disponible: la sesión vive solo en memoria */
  }
}

export class ErrorApi extends Error {
  constructor(mensaje, estado) {
    super(mensaje)
    this.estado = estado
  }
}

export async function api(ruta, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`/api${ruta}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  const datos = await res.json().catch(() => null)
  if (!res.ok) {
    let mensaje = datos?.detail ?? `Error ${res.status}`
    if (Array.isArray(mensaje)) mensaje = mensaje.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join('; ')
    if (res.status === 401 && token) window.dispatchEvent(new Event('sesion-vencida'))
    throw new ErrorApi(mensaje, res.status)
  }
  if (token && !ruta.startsWith('/usuarios/nombres')) await completarNombres(datos)
  return datos
}

// Cada servicio guarda solo identificadores de usuario (D-06). Los nombres públicos (sin datos personales)
// se piden a identity-service y se agregan como `donante`, `receptor` y `nombre` donde haga falta.
const nombres = new Map()

function recorrer(valor, visitar) {
  if (Array.isArray(valor)) valor.forEach((v) => recorrer(v, visitar))
  else if (valor && typeof valor === 'object') {
    visitar(valor)
    Object.values(valor).forEach((v) => recorrer(v, visitar))
  }
}

async function completarNombres(datos) {
  const faltan = new Set()
  recorrer(datos, (o) => {
    for (const id of [o.id_donante, o.id_receptor]) if (id && !nombres.has(id)) faltan.add(id)
    o.confirmaciones?.forEach((c) => c.id_usuario && !nombres.has(c.id_usuario) && faltan.add(c.id_usuario))
  })
  if (faltan.size) {
    try {
      const r = await api(`/usuarios/nombres?ids=${[...faltan].join(',')}`)
      Object.entries(r).forEach(([id, nombre]) => nombres.set(Number(id), nombre))
    } catch {
      /* sin nombres se muestra el identificador */
    }
  }
  const nombre = (id) => nombres.get(id) ?? `Usuario ${id}`
  recorrer(datos, (o) => {
    if (o.id_donante && o.donante === undefined) o.donante = nombre(o.id_donante)
    if (o.id_receptor && o.receptor === undefined) o.receptor = nombre(o.id_receptor)
    o.confirmaciones?.forEach((c) => (c.nombre = nombre(c.id_usuario)))
  })
}

// Todas las fechas se muestran en hora de Colombia, igual que los mensajes del servidor: «05/11/26 12:58»
const FORMATO = new Intl.DateTimeFormat('es-CO', {
  timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', year: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
export const fecha = (iso) => (iso ? FORMATO.format(new Date(iso)).replace(',', '') : '—')

export function restante(iso) {
  const ms = new Date(iso) - Date.now()
  if (ms <= 0) return 'vencido'
  const min = Math.floor(ms / 60000)
  return min >= 60 ? `${Math.floor(min / 60)} h ${min % 60} min` : `${min} min`
}

// Descarga un reporte (CSV) de la API con la sesión actual (S8-02)
export async function descargar(ruta, nombreArchivo) {
  const res = await fetch(`/api${ruta}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new ErrorApi(`No se pudo descargar (${res.status})`, res.status)
  const url = URL.createObjectURL(await res.blob())
  const enlace = Object.assign(document.createElement('a'), { href: url, download: nombreArchivo })
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}
