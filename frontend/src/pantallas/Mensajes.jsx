import { useCallback, useEffect, useRef, useState } from 'react'
import { api, fecha, leerSesion } from '../api'
import { Aviso, Estado, useDatos, useEscritorio } from '../componentes/Comunes'

// D-12: chat entre donante y receptor de una donación, para pactar la entrega y resolver dudas.
// La conversación se abre sola cuando el receptor reserva o el donante ofrece para una solicitud.
export default function Mensajes({ donacionInicial, onCambio }) {
  const conversaciones = useDatos('/conversaciones', 5000)
  const [elegida, setElegida] = useState(null)
  const escritorio = useEscritorio()
  const lista = conversaciones.datos ?? []

  // Si se llegó desde una donación o reserva, abrir su conversación (la abierta, si hay varias)
  useEffect(() => {
    if (!donacionInicial || !conversaciones.datos) return
    const deLaDonacion = lista.filter((c) => c.id_donacion === donacionInicial)
    const c = deLaDonacion.find((x) => x.estado_conversacion === 'ABIERTA') ?? deLaDonacion[0]
    if (c) setElegida(c.id_conversacion)
  }, [donacionInicial, conversaciones.datos]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (escritorio && !elegida && lista.length) setElegida(lista[0].id_conversacion)
  }, [escritorio, elegida, lista])

  const actual = lista.find((c) => c.id_conversacion === elegida)
  const alLeer = useCallback(() => {
    conversaciones.recargar()
    onCambio?.()
  }, [conversaciones.recargar, onCambio]) // eslint-disable-line react-hooks/exhaustive-deps

  const verLista = escritorio || !actual
  return (
    <section>
      <h2>Mensajes</h2>
      <Aviso mensaje={conversaciones.error} />
      {conversaciones.datos && lista.length === 0 && (
        <p className="tenue">
          Aún no tienes conversaciones. Se abren solas cuando un receptor reserva una de tus donaciones, cuando
          reservas una donación o cuando un donante ofrece una donación para tu solicitud.
        </p>
      )}
      <div className={escritorio ? 'chat-rejilla' : ''}>
        {verLista && lista.length > 0 && (
          <ul className="chat-lista">
            {lista.map((c) => (
              <li key={c.id_conversacion}>
                <button className={`chat-item ${c.id_conversacion === elegida ? 'activa' : ''}`}
                  onClick={() => setElegida(c.id_conversacion)}>
                  <span className="chat-item-titulo">
                    <b>{contraparte(c)}</b>
                    {c.no_leidos > 0 && <span className="insignia">{c.no_leidos}</span>}
                  </span>
                  <span className="pequeno">
                    {c.nombre_alimento}
                    {c.estado_conversacion === 'CERRADA' && ' · cerrada'}
                  </span>
                  <span className="pequeno tenue chat-vista-previa">
                    {c.ultimo_mensaje ? c.ultimo_mensaje.texto : 'Sin mensajes todavía'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {actual && (
          <Chat key={actual.id_conversacion} conversacion={actual} onLeer={alLeer}
            onVolver={escritorio ? undefined : () => setElegida(null)} />
        )}
      </div>
    </section>
  )
}

const contraparte = (c) => (c.mi_papel === 'DONANTE' ? c.receptor : c.donante)

function Chat({ conversacion: c, onLeer, onVolver }) {
  const yo = leerSesion()?.usuario.id_usuario
  const [mensajes, setMensajes] = useState([])
  const [estado, setEstado] = useState(c.estado_conversacion)
  const [texto, setTexto] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const ultimo = useRef(0)
  const fondo = useRef(null)

  const traer = useCallback(async () => {
    try {
      const r = await api(`/conversaciones/${c.id_conversacion}/mensajes?despues_de=${ultimo.current}`)
      setEstado(r.estado_conversacion)
      if (r.mensajes.length) {
        ultimo.current = r.mensajes.at(-1).id_mensaje
        setMensajes((previos) => [...previos, ...r.mensajes])
        if (r.mensajes.some((m) => m.id_autor !== yo)) {
          await api(`/conversaciones/${c.id_conversacion}/leer`, { method: 'POST' })
          onLeer?.()
        }
      }
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [c.id_conversacion, yo, onLeer])

  useEffect(() => {
    traer()
    const id = setInterval(traer, 3000)
    return () => clearInterval(id)
  }, [traer])

  useEffect(() => {
    fondo.current?.scrollIntoView({ block: 'end' })
  }, [mensajes.length])

  async function enviar(e) {
    e.preventDefault()
    if (!texto.trim()) return
    setEnviando(true)
    try {
      await api(`/conversaciones/${c.id_conversacion}/mensajes`, { method: 'POST', body: { texto } })
      setTexto('')
      await traer()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const abierta = estado === 'ABIERTA'
  return (
    <div className="chat tarjeta">
      <div className="chat-cabecera">
        {onVolver && (
          <button className="secundario" onClick={onVolver} aria-label="Volver a la lista">
            ←
          </button>
        )}
        <div>
          <b>{contraparte(c)}</b>
          <div className="pequeno tenue">
            {c.nombre_alimento} · {c.mi_papel === 'DONANTE' ? 'receptor' : 'donante'}
            {c.origen === 'OFERTA' && ' · ofrecida para su solicitud'}
          </div>
        </div>
        <Estado valor={estado} />
      </div>

      <div className="chat-mensajes">
        {mensajes.length === 0 && (
          <p className="tenue pequeno">
            Escribe para acordar la hora y el lugar de entrega, o para preguntar por el alimento.
          </p>
        )}
        {mensajes.map((m) => (
          <div key={m.id_mensaje} className={`burbuja ${m.id_autor === yo ? 'mia' : 'suya'}`}>
            <span>{m.texto}</span>
            <small>{fecha(m.fecha_envio)}</small>
          </div>
        ))}
        <div ref={fondo} />
      </div>

      <Aviso mensaje={error} onCerrar={() => setError('')} />
      {abierta ? (
        <form className="chat-escribir" onSubmit={enviar}>
          <input value={texto} onChange={(e) => setTexto(e.target.value)} maxLength={1000}
            placeholder="Escribe un mensaje…" aria-label="Mensaje" />
          <button type="submit" disabled={enviando || !texto.trim()}>
            Enviar
          </button>
        </form>
      ) : (
        <p className="tenue pequeno">
          Conversación cerrada: la reserva o la donación terminó. Puedes leer lo acordado.
        </p>
      )}
    </div>
  )
}
