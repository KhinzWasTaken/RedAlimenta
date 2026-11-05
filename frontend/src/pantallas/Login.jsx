import { useState } from 'react'
import { api } from '../api'
import { Aviso } from '../componentes/Comunes'

const DEMO = [
  ['Donante', 'donante@redalimenta.co'],
  ['Receptor', 'receptor@redalimenta.co'],
  ['Administrador', 'admin@redalimenta.co'],
]

export default function Login({ onEntrar }) {
  const [correo, setCorreo] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [error, setError] = useState('')
  const [ocupado, setOcupado] = useState(false)

  async function entrar(e) {
    e?.preventDefault()
    setOcupado(true)
    setError('')
    try {
      onEntrar(await api('/auth/login', { method: 'POST', body: { correo, contrasena } }))
    } catch (err) {
      setError(err.message)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <div className="login">
      <div className="tarjeta">
        <h1>🥕 RedAlimenta</h1>
        <p className="tenue">Conecta donantes de alimentos con quienes los necesitan, cerca y a tiempo.</p>
        <form onSubmit={entrar} className="formulario">
          <label>
            Correo
            <input type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} required
              autoComplete="username" />
          </label>
          <label>
            Contraseña
            <input type="password" value={contrasena} onChange={(e) => setContrasena(e.target.value)} required
              autoComplete="current-password" />
          </label>
          <Aviso mensaje={error} />
          <button type="submit" disabled={ocupado}>
            {ocupado ? 'Entrando…' : 'Iniciar sesión'}
          </button>
        </form>
        <div className="demo">
          <p className="tenue">Usuarios de demostración (contraseña <code>demo123</code>):</p>
          <div className="fila-botones">
            {DEMO.map(([rol, c]) => (
              <button key={c} className="secundario" type="button"
                onClick={() => { setCorreo(c); setContrasena('demo123') }}>
                {rol}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
