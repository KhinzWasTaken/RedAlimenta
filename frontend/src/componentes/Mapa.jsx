import { useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

export const BOGOTA = [4.65, -74.1]
// Ciudades con datos semilla: centro del mapa y departamento que se envía a la API
export const CIUDADES = {
  'Bogotá': { departamento: 'Cundinamarca', centro: [4.65, -74.1] },
  'Medellín': { departamento: 'Antioquia', centro: [6.25, -75.57] },
  'Cali': { departamento: 'Valle del Cauca', centro: [3.44, -76.52] },
}

function Centrar({ centro }) {
  const mapa = useMap()
  useEffect(() => {
    if (centro) mapa.setView(centro, 12, { animate: false })
  }, [centro?.[0], centro?.[1]]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

function AlHacerClic({ onClic }) {
  useMapEvents({ click: (e) => onClic?.({ lat: +e.latlng.lat.toFixed(6), lon: +e.latlng.lng.toFixed(6) }) })
  return null
}

// Encuadra todos los puntos visibles cada vez que cambian (resultados de búsqueda, punto elegido).
function Encuadrar({ puntos, clave }) {
  const mapa = useMap()
  useEffect(() => {
    if (!puntos.length) return
    if (puntos.length === 1) mapa.setView(puntos[0], Math.max(mapa.getZoom(), 13), { animate: false })
    else mapa.fitBounds(puntos, { padding: [36, 36], maxZoom: 14, animate: false })
  }, [clave]) // eslint-disable-line react-hooks/exhaustive-deps
  // El contenedor puede cambiar de tamaño (pestañas, ventana): recalcula para no dejar zonas grises
  useEffect(() => {
    const id = setTimeout(() => mapa.invalidateSize(), 150)
    return () => clearTimeout(id)
  })
  return null
}

// Mapa de OpenStreetMap. `marcadores`: [{id, lat, lon, color, radio, popup, etiqueta}]; `punto`: {lat, lon}.
export default function Mapa({ marcadores = [], punto, etiquetaPunto = 'Punto elegido', onClic, alto = 320,
  encuadrar = true, centro }) {
  const [sinFondo, setSinFondo] = useState(false)
  const puntos = useMemo(
    () => [...marcadores.map((m) => [m.lat, m.lon]), ...(punto ? [[punto.lat, punto.lon]] : [])],
    [marcadores, punto],
  )
  const clave = puntos.map((p) => p.join(',')).join(';')

  return (
    <div className="mapa" style={{ height: alto }}>
      <MapContainer center={BOGOTA} zoom={11} scrollWheelZoom style={{ height: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
          eventHandlers={{ tileerror: () => setSinFondo(true), tileload: () => setSinFondo(false) }}
        />
        <AlHacerClic onClic={onClic} />
        {encuadrar && <Encuadrar puntos={puntos} clave={clave} />}
        <Centrar centro={centro} />
        {marcadores.map((m) => (
          <CircleMarker key={m.id} center={[m.lat, m.lon]} radius={m.radio || 9}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: m.color || '#1f7a4d', fillOpacity: 0.95 }}>
            {m.etiqueta && <Tooltip direction="top" offset={[0, -8]}>{m.etiqueta}</Tooltip>}
            {m.popup && <Popup>{m.popup}</Popup>}
          </CircleMarker>
        ))}
        {punto && (
          <CircleMarker center={[punto.lat, punto.lon]} radius={11}
            pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#1c64c8', fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -10]} permanent>{etiquetaPunto}</Tooltip>
          </CircleMarker>
        )}
      </MapContainer>
      {sinFondo && (
        <div className="mapa-aviso">Sin conexión al mapa base de OpenStreetMap; los puntos siguen siendo válidos.</div>
      )}
    </div>
  )
}
