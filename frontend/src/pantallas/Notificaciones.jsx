import { api, fecha } from '../api'
import { Aviso, useAccion, useDatos } from '../componentes/Comunes'

export default function Notificaciones({ onCambio }) {
  const bandeja = useDatos('/notificaciones', 5000)
  const recargar = async () => {
    await bandeja.recargar()
    onCambio?.()
  }
  const { mensaje, setMensaje, ejecutar } = useAccion(recargar)
  const post = (ruta) => () => api(ruta, { method: 'POST' })

  return (
    <section className="seccion-angosta">
      <div className="encabezado">
        <h2>Notificaciones</h2>
        <button className="secundario" onClick={() => ejecutar(post('/notificaciones/leer-todas'))}>
          Marcar todas leídas
        </button>
      </div>
      <Aviso mensaje={mensaje?.texto} tipo={mensaje?.tipo} onCerrar={() => setMensaje(null)} />
      <Aviso mensaje={bandeja.error} />
      {bandeja.datos?.length === 0 && <p className="tenue">No tienes notificaciones.</p>}
      <ul className="notificaciones">
        {bandeja.datos?.map((n) => (
          <li key={n.id_notificacion} className={n.estado_notificacion === 'NO_LEIDA' ? 'no-leida' : ''}>
            <div
              className="cuerpo"
              onClick={() => n.estado_notificacion === 'NO_LEIDA' && ejecutar(post(`/notificaciones/${n.id_notificacion}/leer`))}
            >
              <p>{n.mensaje}</p>
              <p className="pequeno tenue">
                {fecha(n.fecha_creacion)} · {n.tipo_notificacion}
              </p>
            </div>
            <button className="enlace" aria-label="Archivar"
              onClick={() => ejecutar(post(`/notificaciones/${n.id_notificacion}/archivar`))}>
              Archivar
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
