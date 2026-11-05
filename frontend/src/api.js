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
    if (res.status === 401) window.dispatchEvent(new Event('sesion-vencida'))
    throw new ErrorApi(mensaje, res.status)
  }
  return datos
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
