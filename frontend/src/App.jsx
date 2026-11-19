import { useCallback, useEffect, useState } from 'react'
import { api, guardarSesion, leerSesion } from './api'
import { Aviso, useDatos } from './componentes/Comunes'
import Login from './pantallas/Login'
import { MisDonaciones, Publicar, Solicitudes } from './pantallas/Donante'
import { Buscar, MisReservas } from './pantallas/Receptor'
import Entregas from './pantallas/Entregas'
import Notificaciones from './pantallas/Notificaciones'
import { Auditoria, Categorias, Cuentas } from './pantallas/Admin'
import Necesidades from './pantallas/Necesidades'
import Tablero from './pantallas/Tablero'
import Trazabilidad from './pantallas/Trazabilidad'

const PESTANAS = {
  DONANTE: [
    ['solicitudes', 'Solicitudes', '🙋'],
    ['publicar', 'Publicar', '➕'],
    ['donaciones', 'Mis donaciones', '📦'],
    ['entregas', 'Entregas', '🤝'],
    ['avisos', 'Avisos', '🔔'],
  ],
  RECEPTOR: [
    ['buscar', 'Buscar', '🗺️'],
    ['necesidades', 'Pedir alimentos', '🙋'],
    ['reservas', 'Mis reservas', '📋'],
    ['entregas', 'Entregas', '🤝'],
    ['avisos', 'Avisos', '🔔'],
  ],
  ADMINISTRADOR: [
    ['tablero', 'Tablero', '📊'],
    ['cuentas', 'Cuentas', '✅'],
    ['categorias', 'Categorías', '🏷️'],
    ['auditoria', 'Auditoría', '📜'],
    ['trazabilidad', 'Trazabilidad', '🔎'],
    ['avisos', 'Avisos', '🔔'],
  ],
}

const pestanaDeHash = () => window.location.hash.replace('#', '')

export default function App() {
  const [sesion, setSesion] = useState(() => leerSesion())
  const [pestana, setPestana] = useState(pestanaDeHash)
  const [oferta, setOferta] = useState(null) // D-11: solicitud a la que responde el donante al publicar

  function ir(id) {
    window.location.hash = id
    setPestana(id)
  }

  const iniciar = (s) => {
    guardarSesion(s)
    setSesion(s)
    ir(PESTANAS[s.usuario.rol][0][0])
  }
  const salir = useCallback(() => {
    guardarSesion(null)
    setSesion(null)
  }, [])

  // D-06: el token lleva el estado de verificación; se renueva para reflejar la decisión del administrador.
  const refrescar = useCallback(async () => {
    try {
      const s = await api('/auth/refresh', { method: 'POST' })
      guardarSesion(s)
      setSesion(s)
    } catch {
      /* si el token venció, el evento sesion-vencida cierra la sesión */
    }
  }, [])

  useEffect(() => {
    const vencida = () => salir()
    const cambio = () => setPestana(pestanaDeHash())
    window.addEventListener('sesion-vencida', vencida)
    window.addEventListener('hashchange', cambio)
    return () => {
      window.removeEventListener('sesion-vencida', vencida)
      window.removeEventListener('hashchange', cambio)
    }
  }, [salir])

  useEffect(() => {
    if (sesion) refrescar()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const verificado = sesion?.usuario.estado_verificacion === 'APROBADA'
  useEffect(() => {
    if (!sesion || verificado) return
    const id = setInterval(refrescar, 10000)
    return () => clearInterval(id)
  }, [sesion, verificado, refrescar])

  const contador = useDatos(sesion ? '/notificaciones/no-leidas' : null, 5000)

  if (!sesion) return <Login onEntrar={iniciar} />

  const { usuario } = sesion
  const pestanas = PESTANAS[usuario.rol]
  const actual = pestanas.some(([id]) => id === pestana) ? pestana : pestanas[0][0]
  return (
    <div className="app">
      <header className="barra">
        <div>
          <strong>RedAlimenta</strong>
          <small>
            {usuario.nombre} · {usuario.rol.toLowerCase()}
          </small>
        </div>
        <button className="secundario" onClick={salir}>
          Salir
        </button>
      </header>

      {!verificado && (
        <Aviso
          tipo="info"
          mensaje={
            <>
              Tu cuenta está <b>{usuario.estado_verificacion}</b> de verificación: puedes mirar, pero no operar
              hasta que un administrador la apruebe.{' '}
              <button className="enlace" onClick={refrescar}>
                Actualizar estado
              </button>
            </>
          }
        />
      )}

      <main className="contenido">
        {actual === 'solicitudes' && (
          <Solicitudes onOfrecer={(n) => { setOferta(n); ir('publicar') }} />
        )}
        {actual === 'publicar' && (
          <Publicar oferta={oferta} onQuitarOferta={() => setOferta(null)}
            onPublicada={() => { setOferta(null); ir('donaciones') }} />
        )}
        {actual === 'donaciones' && <MisDonaciones />}
        {actual === 'buscar' && <Buscar onReservada={() => ir('reservas')} />}
        {actual === 'reservas' && <MisReservas />}
        {actual === 'entregas' && <Entregas />}
        {actual === 'avisos' && <Notificaciones onCambio={contador.recargar} />}
        {actual === 'cuentas' && <Cuentas />}
        {actual === 'auditoria' && <Auditoria />}
        {actual === 'categorias' && <Categorias />}
        {actual === 'necesidades' && <Necesidades />}
        {actual === 'tablero' && <Tablero />}
        {actual === 'trazabilidad' && <Trazabilidad />}
      </main>

      <nav className="pestanas">
        {pestanas.map(([id, texto, icono]) => (
          <button key={id} className={id === actual ? 'activa' : ''} onClick={() => ir(id)}>
            <span className="icono" aria-hidden>
              {icono}
            </span>
            {texto}
            {id === 'avisos' && contador.datos?.no_leidas > 0 && (
              <span className="insignia">{contador.datos.no_leidas}</span>
            )}
          </button>
        ))}
      </nav>
    </div>
  )
}
