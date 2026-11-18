import { useMemo, useState } from 'react'
import { descargar, fecha } from '../api'
import { Aviso, useDatos } from '../componentes/Comunes'
import Mapa from '../componentes/Mapa'

// Tablero del administrador (S8-04) sobre la API de indicadores (S8-01 a S8-03). Solo funcionalidad:
// el diseño visual se revisará después.
const INDICADORES = {
  donaciones_registradas: 'Donaciones registradas',
  reservas_gestionadas: 'Reservas gestionadas',
  entregas_finalizadas: 'Entregas finalizadas',
  proporcion_canceladas_vencidas: 'Proporción canceladas o vencidas',
}
const numero = (v) => Number(v ?? 0).toLocaleString('es-CO')
const porcentaje = (v) => `${(Number(v ?? 0) * 100).toFixed(1)} %`

function Barras({ puntos, granularidad, proporcion }) {
  if (!puntos?.length) return <p className="tenue">Sin datos para el periodo.</p>
  const max = Math.max(...puntos.map((p) => p.valor || 0)) || 1
  const ancho = 720
  const alto = 220
  const barra = ancho / puntos.length
  const etiqueta = (p) => (granularidad === 'anio' ? p.periodo.slice(0, 4) : granularidad === 'mes' ? p.periodo.slice(0, 7) : p.periodo)
  const cada = Math.ceil(puntos.length / 12)
  return (
    <svg viewBox={`0 0 ${ancho} ${alto + 40}`} className="grafica" role="img" aria-label="Serie del indicador">
      {puntos.map((p, i) => {
        const h = ((p.valor || 0) / max) * alto
        return (
          <g key={p.periodo}>
            <rect x={i * barra + 1} y={alto - h} width={Math.max(barra - 2, 1)} height={h} fill="var(--primario)">
              <title>{`${etiqueta(p)}: ${proporcion ? porcentaje(p.valor) : numero(p.valor)}`}</title>
            </rect>
            {i % cada === 0 && (
              <text x={i * barra + barra / 2} y={alto + 16} fontSize="11" textAnchor="middle" fill="currentColor">
                {etiqueta(p)}
              </text>
            )}
          </g>
        )
      })}
      <text x="4" y="12" fontSize="11" fill="currentColor">máx. {proporcion ? porcentaje(max) : numero(max)}</text>
    </svg>
  )
}

export default function Tablero() {
  const hoy = new Date().toISOString().slice(0, 10)
  const [f, setF] = useState({ desde: '2025-01-01', hasta: hoy, departamento: '', ciudad: '', id_categoria: '',
    incluir_sinteticos: true })
  const [indicador, setIndicador] = useState('donaciones_registradas')
  const [granularidad, setGranularidad] = useState('mes')
  const [errorDescarga, setErrorDescarga] = useState('')
  const opciones = useDatos('/indicadores/filtros')

  const consulta = useMemo(() => {
    const q = new URLSearchParams({ desde: f.desde, hasta: f.hasta, incluir_sinteticos: f.incluir_sinteticos })
    for (const k of ['departamento', 'ciudad', 'id_categoria']) if (f[k]) q.set(k, f[k])
    return q.toString()
  }, [f])
  const resumen = useDatos(`/indicadores/resumen?${consulta}`)
  const serie = useDatos(`/indicadores/serie?${consulta}&indicador=${indicador}&granularidad=${granularidad}`)
  const cobertura = useDatos(`/indicadores/cobertura?${consulta}`)
  const cambiar = (campo) => (e) =>
    setF({ ...f, [campo]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
      ...(campo === 'departamento' ? { ciudad: '' } : {}) })
  const bajar = (reporte, extra = '') =>
    descargar(`/reportes/${reporte}.csv?${consulta}${extra}`, `redalimenta-${reporte}.csv`)
      .then(() => setErrorDescarga(''), (e) => setErrorDescarga(e.message))

  const r = resumen.datos
  const ciudades = opciones.datos?.ciudades.filter((c) => !f.departamento || c.departamento === f.departamento) ?? []
  const maxDonaciones = Math.max(1, ...(cobertura.datos ?? []).map((c) => c.donaciones))
  const marcadores = (cobertura.datos ?? []).filter((c) => c.latitud != null).map((c) => ({
    id: `${c.departamento}-${c.ciudad}`, lat: c.latitud, lon: c.longitud,
    radio: 6 + 22 * Math.sqrt(c.donaciones / maxDonaciones),
    color: c.tasa_entrega >= 0.6 ? '#1f7a4d' : c.tasa_entrega >= 0.45 ? '#d9a400' : '#b3261e',
    etiqueta: `${c.ciudad}: ${numero(c.donaciones)} donaciones · ${porcentaje(c.tasa_entrega)} entregadas`,
  }))

  return (
    <section>
      <div className="encabezado">
        <h2>Tablero de indicadores</h2>
        <div className="fila-botones">
          <button className="secundario" onClick={() => bajar('resumen')}>CSV resumen</button>
          <button className="secundario" onClick={() => bajar('serie', `&indicador=${indicador}&granularidad=${granularidad}`)}>CSV serie</button>
          <button className="secundario" onClick={() => bajar('cobertura')}>CSV cobertura</button>
        </div>
      </div>
      <Aviso mensaje={errorDescarga || resumen.error} />
      <div className="filtros-tablero">
        <label>Desde<input type="date" value={f.desde} onChange={cambiar('desde')} /></label>
        <label>Hasta<input type="date" value={f.hasta} onChange={cambiar('hasta')} /></label>
        <label>Departamento
          <select value={f.departamento} onChange={cambiar('departamento')}>
            <option value="">Todos</option>
            {opciones.datos?.departamentos.map((d) => <option key={d}>{d}</option>)}
          </select>
        </label>
        <label>Ciudad
          <select value={f.ciudad} onChange={cambiar('ciudad')}>
            <option value="">Todas</option>
            {ciudades.map((c) => <option key={`${c.departamento}-${c.ciudad}`}>{c.ciudad}</option>)}
          </select>
        </label>
        <label>Categoría
          <select value={f.id_categoria} onChange={cambiar('id_categoria')}>
            <option value="">Todas</option>
            {opciones.datos?.categorias.map((c) => <option key={c.id_categoria} value={c.id_categoria}>{c.nombre_categoria}</option>)}
          </select>
        </label>
        <label className="casilla">
          <input type="checkbox" checked={f.incluir_sinteticos} onChange={cambiar('incluir_sinteticos')} />
          Incluir datos sintéticos
        </label>
      </div>

      {r && (
        <div className="tarjetas-resumen">
          <article className="tarjeta"><p className="tenue">Donaciones registradas</p><h3>{numero(r.donaciones_registradas)}</h3></article>
          <article className="tarjeta"><p className="tenue">Reservas gestionadas</p><h3>{numero(r.reservas_gestionadas)}</h3></article>
          <article className="tarjeta"><p className="tenue">Entregas finalizadas</p><h3>{numero(r.entregas_finalizadas)}</h3></article>
          <article className="tarjeta"><p className="tenue">Canceladas o vencidas</p><h3>{porcentaje(r.proporcion_canceladas_vencidas)}</h3></article>
          <article className="tarjeta">
            <p className="tenue">Volumen distribuido</p>
            {r.volumen_distribuido.length === 0 && <p>—</p>}
            {r.volumen_distribuido.map((v) => <p key={v.unidad_medida}><b>{numero(Math.round(v.cantidad))}</b> {v.unidad_medida}</p>)}
          </article>
        </div>
      )}
      {r?.ultima_carga && (
        <p className="pequeno tenue">
          Datos del almacén: última carga {r.ultima_carga.tipo} el {fecha(r.ultima_carga.fin)}
          {r.ultima_carga.reglas_fallidas ? ` · ${r.ultima_carga.reglas_fallidas} reglas de calidad fallidas` : ' · calidad aprobada'}
        </p>
      )}

      <div className="encabezado">
        <h3>Serie en el tiempo</h3>
        <div className="fila-botones">
          <select value={indicador} onChange={(e) => setIndicador(e.target.value)} aria-label="Indicador">
            {Object.entries(INDICADORES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={granularidad} onChange={(e) => setGranularidad(e.target.value)} aria-label="Granularidad">
            <option value="dia">Por día</option>
            <option value="mes">Por mes</option>
            <option value="anio">Por año</option>
          </select>
        </div>
      </div>
      <div className="tarjeta">
        <Barras puntos={serie.datos?.puntos} granularidad={granularidad} proporcion={indicador === 'proporcion_canceladas_vencidas'} />
      </div>

      <h3>Cobertura por región</h3>
      <p className="pequeno tenue">Tamaño = donaciones; color = tasa de entrega (verde ≥ 60 %, amarillo ≥ 45 %, rojo menor).</p>
      <Mapa marcadores={marcadores} alto={380} />
      <div className="tabla-scroll">
        <table className="tabla">
          <thead>
            <tr><th>Departamento</th><th>Ciudad</th><th>Donaciones</th><th>Entregadas</th><th>Perdidas</th><th>Tasa de entrega</th></tr>
          </thead>
          <tbody>
            {cobertura.datos?.map((c) => (
              <tr key={`${c.departamento}-${c.ciudad}`}>
                <td>{c.departamento}</td><td>{c.ciudad}</td><td>{numero(c.donaciones)}</td>
                <td>{numero(c.entregadas)}</td><td>{numero(c.perdidas)}</td><td>{porcentaje(c.tasa_entrega)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
