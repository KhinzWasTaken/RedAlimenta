import { useEffect, useMemo, useState } from 'react'
import { api, fecha, restante } from '../api'
import { Aviso, Estado, useAccion, useDatos, useEscritorio } from '../componentes/Comunes'
import Mapa from '../componentes/Mapa'

const URGENCIAS = ['BAJA', 'MEDIA', 'ALTA', 'CRITICA']

// Verde (alta prioridad) → amarillo → gris (baja)
const colorPuntaje = (p) => (p >= 0.55 ? '#1f7a4d' : p >= 0.35 ? '#d9a400' : '#8a8f98')

function Prioridad({ p, nivel }) {
  return (
    <p className="pequeno tenue">
      Puntaje <b>{p.puntaje.toFixed(2)}</b> = 0,40·urgencia {p.urgencia.toFixed(2)}
      {nivel ? ` (${nivel})` : ''} + 0,35·cercanía {p.cercania.toFixed(2)} + 0,25·vencimiento{' '}
      {p.vencimiento.toFixed(2)}
    </p>
  )
}

export function Buscar({ onReservada }) {
  const categorias = useDatos('/categorias')
  const necesidades = useDatos('/necesidades/mias')
  const [referencia, setReferencia] = useState('') // id_necesidad o 'mapa'
  const [punto, setPunto] = useState(null)
  const [categoria, setCategoria] = useState('')
  const [orden, setOrden] = useState('prioridad')
  const [vista, setVista] = useState('mapa')
  const escritorio = useEscritorio()
  const [resultado, setResultado] = useState(null)
  const [error, setError] = useState('')

  // La más urgente primero: es el punto de referencia por defecto (D-07)
  const abiertas = useMemo(
    () =>
      (necesidades.datos ?? [])
        .filter((n) => n.estado_necesidad === 'ABIERTA')
        .sort((a, b) => URGENCIAS.indexOf(b.nivel_urgencia) - URGENCIAS.indexOf(a.nivel_urgencia)),
    [necesidades.datos],
  )
  useEffect(() => {
    if (!referencia && abiertas.length) setReferencia(String(abiertas[0].id_necesidad))
  }, [abiertas, referencia])

  const consulta = useMemo(() => {
    const q = new URLSearchParams({ orden })
    if (categoria) q.set('id_categoria', categoria)
    if (referencia === 'mapa') {
      if (!punto) return null
      q.set('lat', punto.lat)
      q.set('lon', punto.lon)
    } else if (referencia) q.set('id_necesidad', referencia)
    else return null
    return `/donaciones/disponibles?${q}`
  }, [orden, categoria, referencia, punto])

  async function buscar() {
    if (!consulta) return
    try {
      setResultado(await api(consulta))
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }
  useEffect(() => {
    buscar()
  }, [consulta]) // eslint-disable-line react-hooks/exhaustive-deps

  const { ocupado, mensaje, setMensaje, ejecutar } = useAccion(buscar)
  async function reservar(d) {
    const r = await ejecutar(
      () => api('/reservas', { method: 'POST', body: { id_donacion: d.id_donacion } }),
      (r) => `Reservaste «${d.nombre_alimento}». El donante debe confirmar antes de ${fecha(r.fecha_expiracion)}`,
    )
    if (r) setTimeout(() => onReservada?.(), 1800)
  }

  const lista = resultado?.resultados ?? []
  const centro = resultado ? [resultado.punto.lat, resultado.punto.lon] : null
  const marcadores = lista.map((d) => ({
    id: d.id_donacion,
    lat: d.ubicacion.lat,
    lon: d.ubicacion.lon,
    color: colorPuntaje(d.prioridad.puntaje),
    popup: (
      <div className="popup">
        <b>{d.nombre_alimento}</b>
        <br />
        {d.cantidad} {d.unidad_medida} · {d.distancia_km.toFixed(1)} km
        <br />
        Puntaje {d.prioridad.puntaje.toFixed(2)} · vence {fecha(d.fecha_vencimiento)}
        <br />
        <button disabled={ocupado} onClick={() => reservar(d)}>
          Reservar
        </button>
      </div>
    ),
  }))

  return (
    <section>
      <h2>Donaciones disponibles</h2>
      <div className="filtros">
        <label>
          Punto de búsqueda
          <select value={referencia} onChange={(e) => setReferencia(e.target.value)}>
            {abiertas.map((n) => (
              <option key={n.id_necesidad} value={n.id_necesidad}>
                Mi necesidad: {n.descripcion} ({n.nivel_urgencia})
              </option>
            ))}
            <option value="mapa">Tocar un punto en el mapa</option>
          </select>
        </label>
        <div className="dos">
          <label>
            Categoría
            <select value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              <option value="">Todas</option>
              {categorias.datos?.map((c) => (
                <option key={c.id_categoria} value={c.id_categoria}>
                  {c.nombre_categoria}
                </option>
              ))}
            </select>
          </label>
          <label>
            Ordenar por
            <select value={orden} onChange={(e) => setOrden(e.target.value)}>
              <option value="prioridad">Prioridad (D-08)</option>
              <option value="distancia">Distancia</option>
            </select>
          </label>
        </div>
      </div>

      {!escritorio && (
      <div className="segmentado" role="tablist">
        {['mapa', 'lista'].map((v) => (
          <button key={v} className={vista === v ? 'activa' : ''} onClick={() => setVista(v)}>
            {v === 'mapa' ? 'Mapa' : `Lista (${lista.length})`}
          </button>
        ))}
      </div>
      )}

      <Aviso mensaje={mensaje?.texto} tipo={mensaje?.tipo} onCerrar={() => setMensaje(null)} />
      <Aviso mensaje={error} />
      {referencia === 'mapa' && !punto && <Aviso tipo="info" mensaje="Toca el mapa para elegir el punto de búsqueda." />}

      <div className={escritorio ? 'mapa-y-lista' : ''}>
      {(escritorio || vista === 'mapa') && (
        <Mapa
          marcadores={marcadores}
          punto={resultado?.punto || punto}
          centro={centro}
          onClic={referencia === 'mapa' ? setPunto : undefined}
          alto={escritorio ? 'calc(100vh - 290px)' : 380}
        />
      )}

      {(escritorio || vista === 'lista') && (
        <ol className="lista-resultados">
          {escritorio && <p className="tenue pequeno">{lista.length} resultados · {orden === 'prioridad' ? 'mayor prioridad primero' : 'más cercanas primero'}</p>}
          {lista.length === 0 && <p className="tenue">No hay donaciones disponibles con esos filtros.</p>}
          {lista.map((d) => (
            <li key={d.id_donacion} className="tarjeta">
              <div className="encabezado">
                <h3>{d.nombre_alimento}</h3>
                <span className="distancia">{d.distancia_km.toFixed(1)} km</span>
              </div>
              <p>
                {d.cantidad} {d.unidad_medida} · {d.categoria} · {d.donante}
              </p>
              <p className="pequeno tenue">
                Vence {fecha(d.fecha_vencimiento)} · {d.ubicacion.direccion_referencia}
              </p>
              <Prioridad p={d.prioridad} nivel={d.nivel_urgencia} />
              <button disabled={ocupado} onClick={() => reservar(d)}>
                Reservar
              </button>
            </li>
          ))}
        </ol>
      )}
      </div>
    </section>
  )
}

export function MisReservas() {
  const reservas = useDatos('/reservas/mias', 5000)
  const { ocupado, mensaje, setMensaje, ejecutar } = useAccion(reservas.recargar)
  const post = (ruta) => () => api(ruta, { method: 'POST' })

  return (
    <section>
      <div className="encabezado">
        <h2>Mis reservas</h2>
        <button className="secundario" onClick={reservas.recargar}>
          Actualizar
        </button>
      </div>
      <Aviso mensaje={mensaje?.texto} tipo={mensaje?.tipo} onCerrar={() => setMensaje(null)} />
      <Aviso mensaje={reservas.error} />
      {reservas.datos?.length === 0 && <p className="tenue">Aún no tienes reservas.</p>}
      <div className="rejilla">
      {reservas.datos?.map((r) => (
        <article key={r.id_reserva} className="tarjeta">
          <div className="encabezado">
            <h3>{r.donacion.nombre_alimento}</h3>
            <Estado valor={r.estado_reserva} />
          </div>
          <p>
            {r.donacion.cantidad} {r.donacion.unidad_medida} · {r.donacion.donante}
          </p>
          <p className="pequeno tenue">
            Recoger en {r.donacion.ubicacion.direccion_referencia}
            {r.donacion.condiciones_recogida && ` · ${r.donacion.condiciones_recogida}`}
          </p>
          {r.estado_reserva === 'PENDIENTE' && (
            <>
              <p className="pequeno">
                Esperando confirmación del donante. Plazo: {fecha(r.fecha_expiracion)} (
                {restante(r.fecha_expiracion)})
              </p>
              <div className="fila-botones">
                <button className="secundario" disabled={ocupado}
                  onClick={() => ejecutar(post(`/reservas/${r.id_reserva}/cancelar`), 'Reserva cancelada.')}>
                  Cancelar reserva
                </button>
                <button className="demo-btn" disabled={ocupado}
                  onClick={() => ejecutar(post(`/reservas/${r.id_reserva}/forzar-expiracion`),
                    'Reserva expirada (demo): la donación volvió a estar disponible.')}>
                  ⏱ Forzar expiración
                </button>
              </div>
            </>
          )}
          {r.estado_reserva === 'CONFIRMADA' && (
            <p className="pequeno">El donante confirmó. Confirma la entrega en la pestaña Entregas.</p>
          )}
        </article>
      ))}
      </div>
    </section>
  )
}
