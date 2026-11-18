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
  const [registro, setRegistro] = useState(null) // null = iniciar sesión; objeto = datos de la cuenta nueva

  async function entrar(e) {
    e?.preventDefault()
    setOcupado(true)
    setError('')
    try {
      onEntrar(registro
        ? await api('/auth/registro', { method: 'POST', body: { ...registro, correo, contrasena } })
        : await api('/auth/login', { method: 'POST', body: { correo, contrasena } }))
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
          {registro && (
            <>
              <label>
                Nombre de la persona u organización
                <input value={registro.nombre} required minLength={2}
                  onChange={(e) => setRegistro({ ...registro, nombre: e.target.value })} />
              </label>
              <label>
                Participo como
                <select value={registro.rol} onChange={(e) => setRegistro({ ...registro, rol: e.target.value })}>
                  <option value="DONANTE">Donante</option>
                  <option value="RECEPTOR">Receptor</option>
                </select>
              </label>
            </>
          )}
          <label>
            Correo
            <input type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} required
              autoComplete="username" />
          </label>
          <label>
            Contraseña
            <input type="password" value={contrasena} onChange={(e) => setContrasena(e.target.value)} required
              minLength={registro ? 8 : undefined} autoComplete={registro ? 'new-password' : 'current-password'} />
          </label>
          <Aviso mensaje={error} />
          <button type="submit" disabled={ocupado}>
            {ocupado ? 'Enviando…' : registro ? 'Crear cuenta' : 'Iniciar sesión'}
          </button>
          <button type="button" className="enlace"
            onClick={() => setRegistro(registro ? null : { nombre: '', rol: 'DONANTE' })}>
            {registro ? 'Ya tengo cuenta: iniciar sesión' : '¿No tienes cuenta? Regístrate'}
          </button>
          {registro && <p className="pequeno tenue">Tu cuenta quedará pendiente hasta que un administrador la verifique.</p>}
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
