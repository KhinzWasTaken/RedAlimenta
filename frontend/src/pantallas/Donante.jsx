import { useEffect, useMemo, useState } from 'react'
import { api, fecha, restante } from '../api'
import { Aviso, Estado, useAccion, useDatos, useEscritorio } from '../componentes/Comunes'
import Mapa, { CIUDADES } from '../componentes/Mapa'

// Las fechas se capturan y muestran en hora de Colombia (UTC-5), sin importar la zona del navegador
const enDias = (dias) => new Date(Date.now() + dias * 864e5 - 5 * 36e5).toISOString().slice(0, 16)
const aIsoBogota = (local) => new Date(`${local}:00-05:00`).toISOString()

const VACIO = {
  nombre_alimento: '',
  id_categoria: '',
  cantidad: '',
  unidad_medida: 'kg',
  fecha_vencimiento: enDias(2),
  condiciones_recogida: '',
  direccion_referencia: '',
  ciudad: 'Bogotá',
}

const UNIDADES = ['kg', 'litros', 'unidades', 'porciones', 'latas', 'paquetes']
const COLOR_URGENCIA = { CRITICA: '#c0392b', ALTA: '#e67e22', MEDIA: '#d9a400', BAJA: '#8a8f98' }

// `oferta`: solicitud (necesidad abierta) a la que responde esta donación (D-11); prellena el formulario.
export function Publicar({ onPublicada, oferta, onQuitarOferta }) {
  const categorias = useDatos('/categorias')
  const [f, setF] = useState(VACIO)
  const [punto, setPunto] = useState(null)
  useEffect(() => {
    if (!oferta) return
    setF((previo) => ({
      ...previo,
      id_categoria: String(oferta.id_categoria),
      cantidad: String(oferta.cantidad_requerida),
      unidad_medida: oferta.unidad_medida,
      ciudad: CIUDADES[oferta.ubicacion.ciudad] ? oferta.ubicacion.ciudad : previo.ciudad,
    }))
  }, [oferta])
  const escritorio = useEscritorio()
  const { ocupado, mensaje, setMensaje, ejecutar } = useAccion()
  const cambiar = (campo) => (e) => setF({ ...f, [campo]: e.target.value })

  async function publicar(e) {
    e.preventDefault()
    if (!punto) return setMensaje({ tipo: 'error', texto: 'Marca en el mapa el punto de recogida.' })
    if (!(Number(f.cantidad) > 0)) return setMensaje({ tipo: 'error', texto: 'La cantidad debe ser mayor que cero.' })
    if (new Date(aIsoBogota(f.fecha_vencimiento)) <= new Date())
      return setMensaje({ tipo: 'error', texto: 'La fecha de vencimiento debe ser futura.' })
    const r = await ejecutar(() =>
      api('/donaciones', {
        method: 'POST',
        body: {
          nombre_alimento: f.nombre_alimento,
          id_categoria: Number(f.id_categoria),
          cantidad: Number(f.cantidad),
          unidad_medida: f.unidad_medida,
          fecha_vencimiento: aIsoBogota(f.fecha_vencimiento),
          condiciones_recogida: f.condiciones_recogida || null,
          id_necesidad: oferta?.id_necesidad ?? null,
          ubicacion: {
            ...punto,
            direccion_referencia: f.direccion_referencia || null,
            ciudad: f.ciudad,
            departamento: CIUDADES[f.ciudad].departamento,
          },
        },
      }),
    )
    if (r) {
      setF(VACIO)
      setPunto(null)
      onPublicada?.()
    }
  }

  return (
    <section>
      <h2>Publicar donación</h2>
      {oferta && (
        <Aviso tipo="info" mensaje={
          <>
            Ofreciendo para la solicitud <b>«{oferta.descripcion}»</b> ({oferta.cantidad_requerida}{' '}
            {oferta.unidad_medida}, urgencia {oferta.nivel_urgencia}, {oferta.ubicacion.ciudad}). La donación quedará
            apartada para ese receptor mientras su solicitud siga abierta.{' '}
            <button className="enlace" type="button" onClick={onQuitarOferta}>Publicar para todos</button>
          </>
        } />
      )}
      <div className="publicar">
      <div className="publicar-mapa">
      <label>
        Ciudad
        <select value={f.ciudad} onChange={(e) => { setF({ ...f, ciudad: e.target.value }); setPunto(null) }}>
          {Object.keys(CIUDADES).map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <p className="tenue">Toca el mapa para marcar dónde se recoge.</p>
      <Mapa punto={punto} onClic={setPunto} etiquetaPunto="Punto de recogida" encuadrar={false}
        centro={CIUDADES[f.ciudad].centro} alto={escritorio ? 'calc(100vh - 260px)' : 260} />
      {punto && (
        <p className="tenue pequeno">
          Punto: {punto.lat}, {punto.lon}
        </p>
      )}
      </div>
      <form className="formulario" onSubmit={publicar}>
        <label>
          Alimento
          <input value={f.nombre_alimento} onChange={cambiar('nombre_alimento')} required minLength={2}
            placeholder="Ej.: Arroz, pan, leche" />
        </label>
        <label>
          Categoría
          <select value={f.id_categoria} onChange={cambiar('id_categoria')} required>
            <option value="">Elige…</option>
            {categorias.datos?.map((c) => (
              <option key={c.id_categoria} value={c.id_categoria}>
                {c.nombre_categoria}
              </option>
            ))}
          </select>
        </label>
        <div className="dos">
          <label>
            Cantidad
            <input type="number" min="0.01" step="any" value={f.cantidad} onChange={cambiar('cantidad')} required />
          </label>
          <label>
            Unidad
            <select value={f.unidad_medida} onChange={cambiar('unidad_medida')}>
              {[...new Set([...UNIDADES, f.unidad_medida])].map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Vence (hora de Colombia)
          <input type="datetime-local" value={f.fecha_vencimiento} onChange={cambiar('fecha_vencimiento')} required />
        </label>
        <label>
          Dirección de referencia
          <input value={f.direccion_referencia} onChange={cambiar('direccion_referencia')}
            placeholder="Ej.: Cra 7 # 45-10, Chapinero" />
        </label>
        <label>
          Condiciones de recogida
          <input value={f.condiciones_recogida} onChange={cambiar('condiciones_recogida')}
            placeholder="Horario, cadena de frío…" />
        </label>
        <Aviso mensaje={mensaje?.texto} tipo={mensaje?.tipo} onCerrar={() => setMensaje(null)} />
        <button type="submit" disabled={ocupado}>
          {ocupado ? 'Publicando…' : oferta ? 'Ofrecer donación' : 'Publicar donación'}
        </button>
      </form>
      </div>
    </section>
  )
}

export function MisDonaciones() {
  const donaciones = useDatos('/donaciones/mias', 8000)
  const reservas = useDatos('/reservas/mias', 8000)
  const recargar = async () => {
    await Promise.all([donaciones.recargar(), reservas.recargar()])
  }
  const { ocupado, mensaje, setMensaje, ejecutar } = useAccion(recargar)
  const activa = (id) =>
    reservas.datos?.find(
      (r) => r.donacion.id_donacion === id && ['PENDIENTE', 'CONFIRMADA'].includes(r.estado_reserva),
    )
  const post = (ruta) => () => api(ruta, { method: 'POST' })

  return (
    <section>
      <div className="encabezado">
        <h2>Mis donaciones</h2>
        <button className="secundario" onClick={recargar}>
          Actualizar
        </button>
      </div>
      <Aviso mensaje={mensaje?.texto} tipo={mensaje?.tipo} onCerrar={() => setMensaje(null)} />
      <Aviso mensaje={donaciones.error} />
      {donaciones.datos?.length === 0 && <p className="tenue">Aún no has publicado donaciones.</p>}
      <div className="rejilla">
      {donaciones.datos?.map((d) => {
        const r = activa(d.id_donacion)
        return (
          <article key={d.id_donacion} className="tarjeta">
            <div className="encabezado">
              <h3>{d.nombre_alimento}</h3>
              <Estado valor={d.estado_donacion} />
            </div>
            <p>
              {d.cantidad} {d.unidad_medida} · {d.categoria}
            </p>
            <p className="tenue pequeno">
              Vence {fecha(d.fecha_vencimiento)} · {d.ubicacion.direccion_referencia || 'Sin dirección'}
            </p>
            {d.necesidad && <p className="pequeno">🙋 Para la solicitud «{d.necesidad}»</p>}
            {r && (
              <div className="reserva-en-donacion">
                <p>
                  Reservada por <b>{r.receptor}</b> · reserva <Estado valor={r.estado_reserva} />
                </p>
                {r.estado_reserva === 'PENDIENTE' && (
                  <>
                    <p className="pequeno">
                      Confirma antes de {fecha(r.fecha_expiracion)} ({restante(r.fecha_expiracion)})
                    </p>
                    <div className="fila-botones">
                      <button disabled={ocupado}
                        onClick={() => ejecutar(post(`/reservas/${r.id_reserva}/confirmar`), 'Reserva confirmada; entrega programada.')}>
                        Confirmar reserva
                      </button>
                      <button className="secundario" disabled={ocupado}
                        onClick={() => ejecutar(post(`/reservas/${r.id_reserva}/cancelar`), 'Reserva rechazada.')}>
                        Rechazar
                      </button>
                      <button className="demo-btn" disabled={ocupado}
                        onClick={() => ejecutar(post(`/reservas/${r.id_reserva}/forzar-expiracion`), 'Reserva expirada (demo).')}>
                        ⏱ Forzar expiración
                      </button>
                    </div>
                  </>
                )}
                {r.estado_reserva === 'CONFIRMADA' && <p className="pequeno">Confirma la entrega en la pestaña Entregas.</p>}
              </div>
            )}
            {d.estado_donacion === 'DISPONIBLE' && (
              <button className="peligro" disabled={ocupado}
                onClick={() => ejecutar(post(`/donaciones/${d.id_donacion}/cancelar`), 'Donación cancelada.')}>
                Cancelar donación
              </button>
            )}
          </article>
        )
      })}
      </div>
    </section>
  )
}

// D-11: el donante ve lo que piden los receptores (necesidades abiertas) y ofrece una donación para una de ellas.
export function Solicitudes({ onOfrecer }) {
  const categorias = useDatos('/categorias')
  const [ciudad, setCiudad] = useState('Bogotá')
  const [categoria, setCategoria] = useState('')
  const [vista, setVista] = useState('mapa')
  const escritorio = useEscritorio()

  const ruta = useMemo(() => {
    const q = new URLSearchParams()
    if (ciudad) {
      const [lat, lon] = CIUDADES[ciudad].centro
      q.set('lat', lat)
      q.set('lon', lon)
      q.set('radio_km', 40)
    }
    if (categoria) q.set('id_categoria', categoria)
    return `/necesidades/abiertas?${q}`
  }, [ciudad, categoria])
  const solicitudes = useDatos(ruta, 15000)
  const lista = solicitudes.datos ?? []

  const marcadores = lista.map((n) => ({
    id: n.id_necesidad,
    etiqueta: `${n.descripcion} · ${n.nivel_urgencia}`,
    lat: n.ubicacion.lat,
    lon: n.ubicacion.lon,
    color: COLOR_URGENCIA[n.nivel_urgencia],
    popup: (
      <div className="popup">
        <b>{n.descripcion}</b>
        <br />
        {n.cantidad_requerida} {n.unidad_medida} · {n.categoria} · {n.nivel_urgencia}
        <br />
        <button onClick={() => onOfrecer(n)}>Ofrecer donación</button>
      </div>
    ),
  }))

  return (
    <section>
      <h2>Solicitudes de alimentos</h2>
      <p className="tenue">Lo que piden los receptores, la más urgente primero.</p>
      <div className="filtros dos">
        <label>
          Ciudad
          <select value={ciudad} onChange={(e) => setCiudad(e.target.value)}>
            {Object.keys(CIUDADES).map((c) => (
              <option key={c}>{c}</option>
            ))}
            <option value="">Todas</option>
          </select>
        </label>
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
      <Aviso mensaje={solicitudes.error} />

      <div className={escritorio ? 'mapa-y-lista' : ''}>
        {(escritorio || vista === 'mapa') && (
          <Mapa marcadores={marcadores} alto={escritorio ? 'calc(100vh - 290px)' : 380}
            centro={ciudad && !lista.length ? CIUDADES[ciudad].centro : undefined} />
        )}
        {(escritorio || vista === 'lista') && (
          <ol className="lista-resultados">
            {lista.length === 0 && <p className="tenue">No hay solicitudes abiertas con esos filtros.</p>}
            {lista.map((n) => (
              <li key={n.id_necesidad} className="tarjeta">
                <div className="encabezado">
                  <h3>{n.descripcion}</h3>
                  {n.distancia_km != null && <span className="distancia">{n.distancia_km.toFixed(1)} km</span>}
                </div>
                <p>
                  {n.cantidad_requerida} {n.unidad_medida} · {n.categoria} · urgencia{' '}
                  <b style={{ color: COLOR_URGENCIA[n.nivel_urgencia] }}>{n.nivel_urgencia}</b>
                </p>
                <p className="pequeno tenue">
                  {n.ubicacion.ciudad}
                  {n.fecha_limite && ` · la necesita antes de ${fecha(n.fecha_limite)}`}
                  {n.ofertas > 0 && ` · ${n.ofertas} ${n.ofertas === 1 ? 'oferta' : 'ofertas'} recibidas`}
                </p>
                <button onClick={() => onOfrecer(n)}>Ofrecer donación</button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  )
}
