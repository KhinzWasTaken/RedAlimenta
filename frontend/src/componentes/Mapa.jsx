import { useEffect } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

export const BOGOTA = [4.65, -74.1]

function AlHacerClic({ onClic }) {
  useMapEvents({ click: (e) => onClic?.({ lat: +e.latlng.lat.toFixed(6), lon: +e.latlng.lng.toFixed(6) }) })
  return null
}

function Centrar({ centro }) {
  const mapa = useMap()
  useEffect(() => {
    if (centro) mapa.setView(centro, mapa.getZoom())
  }, [centro?.[0], centro?.[1]]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

// Mapa de OpenStreetMap. `marcadores`: [{id, lat, lon, color, radio, popup}]; `punto`: {lat, lon} elegido.
export default function Mapa({ marcadores = [], punto, onClic, centro, alto = 320 }) {
  return (
    <div className="mapa" style={{ height: alto }}>
      <MapContainer center={centro || BOGOTA} zoom={11} scrollWheelZoom style={{ height: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <AlHacerClic onClic={onClic} />
        <Centrar centro={centro} />
        {punto && (
          <CircleMarker center={[punto.lat, punto.lon]} radius={10}
            pathOptions={{ color: '#0b5394', fillColor: '#3d85c6', fillOpacity: 0.9 }}>
            <Popup>Punto elegido</Popup>
          </CircleMarker>
        )}
        {marcadores.map((m) => (
          <CircleMarker key={m.id} center={[m.lat, m.lon]} radius={m.radio || 9}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: m.color || '#1f7a4d', fillOpacity: 0.95 }}>
            {m.popup && <Popup>{m.popup}</Popup>}
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
