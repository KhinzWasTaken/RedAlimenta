import { useState } from 'react'
import { api, fecha } from '../api'
import { Aviso } from '../componentes/Comunes'

// Historial y auditoría (S8-05): el administrador reconstruye quién cambió qué y cuándo.
// Une la auditoría de identity (actor con nombre) y el historial de eventos de analytics (servicio de origen
// e identificador de correlación de cada operación).
const ENTIDADES = ['donacion', 'reserva', 'entrega', 'necesidad', 'verificacion', 'usuario']

function cambio(anterior, nuevo) {
  if (nuevo?.startsWith?.('{')) return `${anterior ?? '∅'} (sin cambio de estado)`
  return `${anterior ?? '∅'} → ${nuevo ?? '∅'}`
}

export default function Trazabilidad() {
  const [entidad, setEntidad] = useState('donacion')
  const [id, setId] = useState('')
  const [idUsuario, setIdUsuario] = useState('')
  const [resultado, setResultado] = useState(null)
  const [error, setError] = useState('')

  async function buscarEntidad(e) {
    e.preventDefault()
    try {
      const [auditoria, historial] = await Promise.all([
        api(`/admin/auditoria?entidad=${entidad}&id_registro=${id}&limite=500`),
        api(`/historial/entidades/${entidad}?id_entidad=${id}`),
      ])
      setResultado({ titulo: `${entidad} #${id}`, auditoria: [...auditoria].reverse(), historial })
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  async function buscarUsuario(e) {
    e.preventDefault()
    try {
      const [auditoria, historial] = await Promise.all([
        api(`/admin/auditoria?id_usuario=${idUsuario}&limite=500`),
        api(`/historial/usuarios/${idUsuario}`),
      ])
      setResultado({ titulo: `usuario #${idUsuario}`, auditoria: [...auditoria].reverse(), historial })
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <h2>Trazabilidad</h2>
      <p className="tenue pequeno">Quién cambió qué y cuándo, a partir de los registros de solo inserción.</p>
      <div className="filtros-tablero">
        <form className="fila-botones" onSubmit={buscarEntidad}>
          <select value={entidad} onChange={(e) => setEntidad(e.target.value)} aria-label="Entidad">
            {ENTIDADES.map((x) => <option key={x}>{x}</option>)}
          </select>
          <input type="number" min="1" placeholder="Número" value={id} onChange={(e) => setId(e.target.value)} required />
          <button type="submit">Ver historia</button>
        </form>
        <form className="fila-botones" onSubmit={buscarUsuario}>
          <input type="number" min="1" placeholder="Id de usuario" value={idUsuario}
            onChange={(e) => setIdUsuario(e.target.value)} required />
          <button type="submit" className="secundario">Actividad de un usuario</button>
        </form>
      </div>
      <Aviso mensaje={error} />
      {resultado && (
        <>
          <h3>Auditoría de {resultado.titulo} ({resultado.auditoria.length})</h3>
          <div className="tabla-scroll">
            <table className="tabla">
              <thead><tr><th>Fecha</th><th>Acción</th><th>Registro</th><th>Cambio</th><th>Actor</th></tr></thead>
              <tbody>
                {resultado.auditoria.map((a) => (
                  <tr key={a.id_auditoria}>
                    <td>{fecha(a.fecha_operacion)}</td><td>{a.accion_realizada}</td>
                    <td>{a.entidad_afectada} #{a.id_registro_afectado}</td>
                    <td className="cambio">{cambio(a.valor_anterior, a.valor_nuevo)}</td><td>{a.actor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Eventos (historial de analytics, {resultado.historial.length})</h3>
          <div className="tabla-scroll">
            <table className="tabla">
              <thead><tr><th>Fecha</th><th>Evento</th><th>Registro</th><th>Cambio</th><th>Servicio</th><th>Correlación</th></tr></thead>
              <tbody>
                {resultado.historial.map((h) => (
                  <tr key={h.id_evento}>
                    <td>{fecha(h.fecha)}</td><td>{h.tipo}</td><td>{h.entidad} #{h.id_entidad}</td>
                    <td className="cambio">{cambio(h.estado_anterior, h.estado_nuevo)}</td><td>{h.origen}</td>
                    <td className="pequeno"><code>{h.id_correlacion?.slice(0, 12) ?? '—'}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
