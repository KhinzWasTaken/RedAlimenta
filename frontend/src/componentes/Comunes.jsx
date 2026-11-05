import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

export function Estado({ valor }) {
  return <span className={`estado estado-${(valor || '').toLowerCase()}`}>{(valor || '').replace('_', ' ')}</span>
}

export function Aviso({ mensaje, tipo = 'error', onCerrar }) {
  if (!mensaje) return null
  return (
    <div className={`aviso aviso-${tipo}`} role={tipo === 'error' ? 'alert' : 'status'}>
      <span>{mensaje}</span>
      {onCerrar && (
        <button className="cerrar" onClick={onCerrar} aria-label="Cerrar">
          ×
        </button>
      )}
    </div>
  )
}

// Carga una ruta de la API y expone recargar(); opcionalmente se refresca cada `cada` ms.
export function useDatos(ruta, cada = 0) {
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const recargar = useCallback(async () => {
    if (!ruta) return
    try {
      setDatos(await api(ruta))
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [ruta])
  useEffect(() => {
    recargar()
    if (!cada) return
    const id = setInterval(recargar, cada)
    return () => clearInterval(id)
  }, [recargar, cada])
  return { datos, error, recargar, setError }
}

// Ejecuta una acción, muestra el error o el mensaje de éxito y llama a `despues`.
export function useAccion(despues) {
  const [ocupado, setOcupado] = useState(false)
  const [mensaje, setMensaje] = useState(null)
  const ejecutar = async (fn, exito) => {
    setOcupado(true)
    setMensaje(null)
    try {
      const r = await fn()
      if (exito) setMensaje({ tipo: 'ok', texto: typeof exito === 'function' ? exito(r) : exito })
      await despues?.()
      return r
    } catch (e) {
      setMensaje({ tipo: 'error', texto: `${e.estado ? `(${e.estado}) ` : ''}${e.message}` })
    } finally {
      setOcupado(false)
    }
  }
  return { ocupado, mensaje, setMensaje, ejecutar }
}

// true en pantallas anchas (escritorio); se actualiza al cambiar el tamaño de la ventana.
export function useEscritorio(consulta = '(min-width: 1024px)') {
  const [coincide, setCoincide] = useState(() => window.matchMedia(consulta).matches)
  useEffect(() => {
    const mq = window.matchMedia(consulta)
    const cambio = () => setCoincide(mq.matches)
    mq.addEventListener('change', cambio)
    return () => mq.removeEventListener('change', cambio)
  }, [consulta])
  return coincide
}
