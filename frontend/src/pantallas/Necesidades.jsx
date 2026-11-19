import { useState } from 'react'
import { api, fecha } from '../api'
import { Aviso, Estado, useAccion, useDatos } from '../componentes/Comunes'
import Mapa, { CIUDADES } from '../componentes/Mapa'

const VACIA = { descripcion: '', id_categoria: '', cantidad_requerida: '', unidad_medida: 'kg', nivel_urgencia: 'MEDIA',
  ciudad: 'Bogotá', direccion_referencia: '' }

// Receptor: pedir alimentos (RF3, D-11). Cada necesidad abierta la ven los donantes como una solicitud y pueden
// ofrecer una donación apartada para este receptor; también alimenta la búsqueda y la prioridad (D-05, D-07).
export default function Necesidades() {
  const necesidades = useDatos('/necesidades/mias')
  const categorias = useDatos('/categorias')
  const [f, setF] = useState(VACIA)
  const [punto, setPunto] = useState(null)
  const { ocupado, mensaje, setMensaje, ejecutar } = useAccion(necesidades.recargar)
  const cambiar = (campo) => (e) => setF({ ...f, [campo]: e.target.value })

  async function registrar(e) {
    e.preventDefault()
    if (!punto) return setMensaje({ tipo: 'error', texto: 'Marca en el mapa dónde se atiende a la población.' })
    const r = await ejecutar(() => api('/necesidades', {
      method: 'POST',
      body: {
        descripcion: f.descripcion, id_categoria: Number(f.id_categoria),
        cantidad_requerida: Number(f.cantidad_requerida), unidad_medida: f.unidad_medida,
        nivel_urgencia: f.nivel_urgencia,
        ubicacion: { ...punto, ciudad: f.ciudad, departamento: CIUDADES[f.ciudad].departamento,
          direccion_referencia: f.direccion_referencia || null },
      },
    }), 'Solicitud publicada: los donantes ya pueden verla.')
    if (r) {
      setF(VACIA)
      setPunto(null)
    }
  }

  return (
    <section>
      <h2>Mis solicitudes de alimentos</h2>
      <p className="tenue">
        Los donantes ven tus solicitudes abiertas y pueden ofrecerte una donación. Cuando lo hagan recibirás un
        aviso y la donación aparecerá primero en <b>Buscar</b>, apartada para ti.
      </p>
      <Aviso mensaje={mensaje?.texto} tipo={mensaje?.tipo} onCerrar={() => setMensaje(null)} />
      <Aviso mensaje={necesidades.error} />
      <div className="rejilla">
        {necesidades.datos?.map((n) => (
          <article key={n.id_necesidad} className="tarjeta">
            <div className="encabezado">
              <h3>{n.descripcion}</h3>
              <Estado valor={n.estado_necesidad} />
            </div>
            <p>{n.cantidad_requerida} {n.unidad_medida} · {n.categoria} · urgencia <b>{n.nivel_urgencia}</b></p>
            <p className="pequeno tenue">{n.ubicacion.direccion_referencia} · {n.ubicacion.ciudad}
              {n.fecha_limite && ` · hasta ${fecha(n.fecha_limite)}`}</p>
            {n.ofertas > 0 && (
              <p className="pequeno"><b>🎁 {n.ofertas} {n.ofertas === 1 ? 'donación ofrecida' : 'donaciones ofrecidas'}</b>
                {n.estado_necesidad === 'ABIERTA' && ' · búscala en Buscar'}</p>
            )}
            {n.estado_necesidad === 'ABIERTA' && (
              <div className="fila-botones">
                <button className="secundario" disabled={ocupado}
                  onClick={() => ejecutar(() => api(`/necesidades/${n.id_necesidad}/cerrar`, { method: 'POST' }),
                    'Necesidad cerrada.')}>Cerrar (cubierta)</button>
                <button className="peligro" disabled={ocupado}
                  onClick={() => ejecutar(() => api(`/necesidades/${n.id_necesidad}/cancelar`, { method: 'POST' }),
                    'Necesidad cancelada.')}>Cancelar</button>
              </div>
            )}
          </article>
        ))}
      </div>

      <h2>Pedir alimentos</h2>
      <label>
        Ciudad
        <select value={f.ciudad} onChange={(e) => { setF({ ...f, ciudad: e.target.value }); setPunto(null) }}>
          {Object.keys(CIUDADES).map((c) => <option key={c}>{c}</option>)}
        </select>
      </label>
      <Mapa punto={punto} onClic={setPunto} etiquetaPunto="Punto de atención" encuadrar={false}
        centro={CIUDADES[f.ciudad].centro} alto={240} />
      <form className="formulario" onSubmit={registrar}>
        <label>Descripción
          <input value={f.descripcion} onChange={cambiar('descripcion')} required minLength={2}
            placeholder="Ej.: Arroz para 120 almuerzos diarios" />
        </label>
        <label>Categoría
          <select value={f.id_categoria} onChange={cambiar('id_categoria')} required>
            <option value="">Elige…</option>
            {categorias.datos?.map((c) => <option key={c.id_categoria} value={c.id_categoria}>{c.nombre_categoria}</option>)}
          </select>
        </label>
        <div className="dos">
          <label>Cantidad
            <input type="number" min="0.01" step="any" value={f.cantidad_requerida}
              onChange={cambiar('cantidad_requerida')} required />
          </label>
          <label>Unidad
            <select value={f.unidad_medida} onChange={cambiar('unidad_medida')}>
              {['kg', 'litros', 'unidades', 'porciones', 'latas', 'paquetes'].map((u) => <option key={u}>{u}</option>)}
            </select>
          </label>
        </div>
        <label>Urgencia
          <select value={f.nivel_urgencia} onChange={cambiar('nivel_urgencia')}>
            {['BAJA', 'MEDIA', 'ALTA', 'CRITICA'].map((u) => <option key={u}>{u}</option>)}
          </select>
        </label>
        <label>Dirección de referencia
          <input value={f.direccion_referencia} onChange={cambiar('direccion_referencia')} />
        </label>
        <button type="submit" disabled={ocupado}>Publicar solicitud</button>
      </form>
    </section>
  )
}
