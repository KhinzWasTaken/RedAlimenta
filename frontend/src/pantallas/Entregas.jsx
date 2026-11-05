import { api, fecha } from '../api'
import { Aviso, Estado, useAccion, useDatos } from '../componentes/Comunes'

export default function Entregas() {
  const reservas = useDatos('/reservas/mias', 5000)
  const { ocupado, mensaje, setMensaje, ejecutar } = useAccion(reservas.recargar)
  const conEntrega = reservas.datos?.filter((r) => r.entrega) ?? []

  const confirmar = (r, estado) => {
    let observaciones = null
    if (estado === 'CON_INCIDENCIA') {
      observaciones = window.prompt('Describe la incidencia:')
      if (!observaciones) return
    }
    ejecutar(
      () => api(`/entregas/${r.entrega.id_entrega}/confirmar`, {
        method: 'POST',
        body: { estado_confirmacion: estado, observaciones },
      }),
      (x) => x.donacion.estado_donacion === 'ENTREGADA'
        ? '¡Entrega completada! La donación quedó ENTREGADA.'
        : estado === 'CON_INCIDENCIA' ? 'Incidencia registrada.' : 'Confirmación registrada; falta la otra parte.',
    )
  }

  return (
    <section>
      <div className="encabezado">
        <h2>Confirmaciones de entrega</h2>
        <button className="secundario" onClick={reservas.recargar}>
          Actualizar
        </button>
      </div>
      <p className="tenue pequeno">La donación pasa a ENTREGADA solo cuando donante y receptor confirman.</p>
      <Aviso mensaje={mensaje?.texto} tipo={mensaje?.tipo} onCerrar={() => setMensaje(null)} />
      <Aviso mensaje={reservas.error} />
      {reservas.datos && conEntrega.length === 0 && (
        <p className="tenue">No hay entregas todavía. Aparecen cuando el donante confirma una reserva.</p>
      )}
      <div className="rejilla">
      {conEntrega.map((r) => {
        const e = r.entrega
        const de = (rol) => e.confirmaciones.find((c) =>
          rol === 'receptor' ? c.id_usuario === r.id_receptor : c.id_usuario === r.donacion.id_donante)
        const abierta = ['PROGRAMADA', 'CON_INCIDENCIA'].includes(e.estado_entrega)
        return (
          <article key={e.id_entrega} className="tarjeta">
            <div className="encabezado">
              <h3>{r.donacion.nombre_alimento}</h3>
              <Estado valor={e.estado_entrega} />
            </div>
            <p className="pequeno">
              {r.donacion.cantidad} {r.donacion.unidad_medida} · de {r.donacion.donante} para {r.receptor}
            </p>
            <ul className="confirmaciones">
              {['donante', 'receptor'].map((rol) => {
                const c = de(rol)
                return (
                  <li key={rol}>
                    {c ? (c.estado_confirmacion === 'CONFIRMADA' ? '✅' : '⚠️') : '⏳'} {rol}
                    {c ? ` · ${c.estado_confirmacion.replace('_', ' ')} ${fecha(c.fecha_confirmacion)}` : ' · pendiente'}
                    {c?.observaciones ? ` · «${c.observaciones}»` : ''}
                  </li>
                )
              })}
            </ul>
            <p className="pequeno tenue">
              Donación <Estado valor={r.donacion.estado_donacion} /> · reserva <Estado valor={r.estado_reserva} />
            </p>
            {abierta && !e.yo_confirme && (
              <div className="fila-botones">
                <button disabled={ocupado} onClick={() => confirmar(r, 'CONFIRMADA')}>
                  Confirmar entrega
                </button>
                <button className="secundario" disabled={ocupado} onClick={() => confirmar(r, 'CON_INCIDENCIA')}>
                  Reportar incidencia
                </button>
              </div>
            )}
            {abierta && e.yo_confirme && <p className="pequeno">Ya confirmaste; esperando a la otra parte.</p>}
          </article>
        )
      })}
      </div>
    </section>
  )
}
