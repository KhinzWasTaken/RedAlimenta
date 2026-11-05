import { useState } from 'react'
import { api, fecha, restante } from '../api'
import { Aviso, Estado, useAccion, useDatos, useEscritorio } from '../componentes/Comunes'
import Mapa from '../componentes/Mapa'

const enDias = (dias) => {
  const d = new Date(Date.now() + dias * 864e5)
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

const VACIO = {
  nombre_alimento: '',
  id_categoria: '',
  cantidad: '',
  unidad_medida: 'kg',
  fecha_vencimiento: enDias(2),
  condiciones_recogida: '',
  direccion_referencia: '',
}

export function Publicar({ onPublicada }) {
  const categorias = useDatos('/categorias')
  const [f, setF] = useState(VACIO)
  const [punto, setPunto] = useState(null)
  const escritorio = useEscritorio()
  const { ocupado, mensaje, setMensaje, ejecutar } = useAccion()
  const cambiar = (campo) => (e) => setF({ ...f, [campo]: e.target.value })

  async function publicar(e) {
    e.preventDefault()
    if (!punto) return setMensaje({ tipo: 'error', texto: 'Marca en el mapa el punto de recogida.' })
    if (!(Number(f.cantidad) > 0)) return setMensaje({ tipo: 'error', texto: 'La cantidad debe ser mayor que cero.' })
    if (new Date(f.fecha_vencimiento) <= new Date())
      return setMensaje({ tipo: 'error', texto: 'La fecha de vencimiento debe ser futura.' })
    const r = await ejecutar(() =>
      api('/donaciones', {
        method: 'POST',
        body: {
          nombre_alimento: f.nombre_alimento,
          id_categoria: Number(f.id_categoria),
          cantidad: Number(f.cantidad),
          unidad_medida: f.unidad_medida,
          fecha_vencimiento: new Date(f.fecha_vencimiento).toISOString(),
          condiciones_recogida: f.condiciones_recogida || null,
          ubicacion: { ...punto, direccion_referencia: f.direccion_referencia || null, ciudad: 'Bogotá' },
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
      <div className="publicar">
      <div className="publicar-mapa">
      <p className="tenue">Toca el mapa para marcar dónde se recoge.</p>
      <Mapa punto={punto} onClic={setPunto} alto={escritorio ? 'calc(100vh - 260px)' : 260} />
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
              {['kg', 'litros', 'unidades', 'porciones', 'latas', 'paquetes'].map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Vence
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
          {ocupado ? 'Publicando…' : 'Publicar donación'}
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
