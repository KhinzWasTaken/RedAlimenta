import { useState } from 'react'
import { api, fecha } from '../api'
import { Aviso, Estado, useAccion, useDatos } from '../componentes/Comunes'

export function Cuentas() {
  const usuarios = useDatos('/admin/usuarios', 8000)
  const [observaciones, setObservaciones] = useState({})
  const { ocupado, mensaje, setMensaje, ejecutar } = useAccion(usuarios.recargar)

  const resolver = (u, decision) =>
    ejecutar(
      () => api(`/admin/verificaciones/${u.verificacion.id_verificacion}`, {
        method: 'POST',
        body: { decision, observaciones: observaciones[u.id_usuario] || null },
      }),
      `${u.nombre}: ${decision}`,
    )

  return (
    <section>
      <div className="encabezado">
        <h2>Verificación de cuentas</h2>
        <button className="secundario" disabled={ocupado}
          onClick={() => ejecutar(() => api('/admin/tareas/ejecutar', { method: 'POST' }),
            (r) => `Tareas: ${r.reservas_expiradas} reservas expiradas, ${r.donaciones_vencidas} donaciones vencidas, ${r.avisos_por_vencer} avisos.`)}>
          Ejecutar tareas
        </button>
      </div>
      <Aviso mensaje={mensaje?.texto} tipo={mensaje?.tipo} onCerrar={() => setMensaje(null)} />
      <Aviso mensaje={usuarios.error} />
      {usuarios.datos?.map((u) => (
        <article key={u.id_usuario} className="tarjeta">
          <div className="encabezado">
            <h3>{u.nombre}</h3>
            <Estado valor={u.verificacion?.estado_verificacion} />
          </div>
          <p className="pequeno">
            {u.rol.toLowerCase()} · {u.correo_electronico} · cuenta {u.estado_cuenta.toLowerCase()}
          </p>
          <p className="pequeno tenue">
            Solicitada {fecha(u.verificacion?.fecha_solicitud)}
            {u.verificacion?.fecha_resolucion && ` · resuelta ${fecha(u.verificacion.fecha_resolucion)}`}
            {u.verificacion?.observaciones && ` · «${u.verificacion.observaciones}»`}
          </p>
          {u.verificacion?.estado_verificacion === 'PENDIENTE' && (
            <>
              <input placeholder="Observación (opcional)" value={observaciones[u.id_usuario] || ''}
                onChange={(e) => setObservaciones({ ...observaciones, [u.id_usuario]: e.target.value })} />
              <div className="fila-botones">
                <button disabled={ocupado} onClick={() => resolver(u, 'APROBADA')}>
                  Aprobar
                </button>
                <button className="peligro" disabled={ocupado} onClick={() => resolver(u, 'RECHAZADA')}>
                  Rechazar
                </button>
              </div>
            </>
          )}
        </article>
      ))}
    </section>
  )
}

const ENTIDADES = ['', 'donacion', 'reserva', 'entrega', 'verificacion', 'necesidad']

export function Auditoria() {
  const [entidad, setEntidad] = useState('')
  const auditoria = useDatos(`/admin/auditoria?limite=300${entidad ? `&entidad=${entidad}` : ''}`, 5000)

  return (
    <section>
      <div className="encabezado">
        <h2>Auditoría</h2>
        <select value={entidad} onChange={(e) => setEntidad(e.target.value)} aria-label="Entidad">
          {ENTIDADES.map((e) => (
            <option key={e} value={e}>
              {e || 'Todas las entidades'}
            </option>
          ))}
        </select>
      </div>
      <p className="tenue pequeno">Registro de solo inserción: cada cambio de estado con quién, cuándo y qué cambió.</p>
      <Aviso mensaje={auditoria.error} />
      <div className="tabla-scroll">
        <table className="tabla">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Acción</th>
              <th>Entidad</th>
              <th>Cambio</th>
              <th>Actor</th>
            </tr>
          </thead>
          <tbody>
            {auditoria.datos?.map((a) => (
              <tr key={a.id_auditoria}>
                <td>{fecha(a.fecha_operacion)}</td>
                <td>{a.accion_realizada}</td>
                <td>
                  {a.entidad_afectada} #{a.id_registro_afectado}
                </td>
                <td className="cambio">
                  {a.valor_nuevo?.startsWith('{') ? (
                    <span className="tenue">{a.valor_anterior} (sin cambio)</span>
                  ) : (
                    <>
                      {a.valor_anterior ?? '∅'} → <b>{a.valor_nuevo}</b>
                    </>
                  )}
                </td>
                <td>{a.actor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
