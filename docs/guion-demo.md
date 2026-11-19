# Guion de demostración (S8-09) · 8 minutos, cuatro actores

## Antes de empezar (5 minutos antes)

```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env --profile app down -v
```

```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env --profile app up -d --build
```

Espera a que el servicio `etl` termine la carga inicial (unos 20 s después de arrancar) y abre
**http://localhost:8080** en dos ventanas (o una normal y otra de incógnito) para alternar usuarios. Ten a mano
otra terminal en la raíz del repositorio. Contraseña de todos los usuarios: `demo123`.

| Actor | Usuario |
| --- | --- |
| Administrador | admin@redalimenta.co |
| Donante (Bogotá) | donante@redalimenta.co |
| Receptor (Bogotá, **pendiente** de verificación) | receptor@redalimenta.co |
| Receptor (Medellín, verificado) | receptor.medellin@redalimenta.co |
| Sistema | Tareas automáticas (botón "forzar expiración" y "Ejecutar tareas") |

## Recorrido

| Min | Actor | Qué hacer | Qué decir |
| --- | --- | --- | --- |
| 0:00 | — | Mostrar la arquitectura (`docs/arquitectura/soa.md`): 5 servicios, 6 bases, RabbitMQ, gateway | "Cada servicio es dueño de sus datos; se hablan por eventos y una sola llamada directa." |
| 0:45 | Receptor | Entrar como receptor de Bogotá: aviso de cuenta PENDIENTE; intentar reservar → no puede | "Solo los usuarios verificados operan." |
| 1:15 | Administrador | *Cuentas* → aprobar al Comedor Comunitario Esperanza | "La verificación es un flujo de estados auditado." |
| 1:45 | Donante | *Publicar*: ciudad Bogotá, tocar el mapa en el sur, "Lentejas", Granos y enlatados, 50 kg, vence en 1 día | "La ubicación es un punto PostGIS; el donante marca dónde se recoge." |
| 2:30 | Receptor | *Actualizar estado*; *Buscar*: la necesidad CRÍTICA de arroz como punto; las Lentejas salen primero con su distancia y puntaje | "Distancia en metros con PostGIS y prioridad D-08: 40 % urgencia, 35 % cercanía, 25 % vencimiento." |
| 3:15 | Receptor | *Reservar* → plazo de 2 horas | "Si dos receptores reservan a la vez, la base decide: uno 201, el otro 409." Mostrar en la terminal: `python scripts/carga_reservas.py --base http://localhost:8080` (20 solicitudes, una sola gana) |
| 4:00 | Sistema | En *Mis reservas*, **⏱ Forzar expiración** → la donación vuelve a DISPONIBLE; reservar de nuevo | "Las tareas automáticas expiran reservas y vencen donaciones sin intervención." |
| 4:30 | Donante | *Mis donaciones* → **Confirmar reserva**; *Entregas* → **Confirmar entrega** → sigue RESERVADA | "Una confirmación no basta." |
| 5:00 | Receptor | *Entregas* → **Confirmar entrega** → ENTREGADA; *Avisos* | "Cada cambio de estado generó su notificación por evento." |
| 5:30 | Administrador | *Trazabilidad*: donación con el número de las Lentejas → auditoría y eventos con su identificador de correlación | "Reconstruimos quién cambió qué y cuándo; la auditoría es de solo inserción." |
| 6:15 | Administrador | *Tablero*: tarjetas, serie por mes (pico tras el terremoto del 10 de agosto), mapa de cobertura, filtro por Antioquia, CSV | "Indicadores del RF9 sobre el almacén en estrella; 50.000 donaciones sintéticas marcadas como tales; el CSV trae los mismos números." |
| 7:15 | — | Terminal: `python scripts/resiliencia.py` (catalog caído → 503 sin reservas huérfanas) | "Diseñado para fallar bien." |
| 7:45 | — | Cierre: `python scripts/trazabilidad.py` (65 pruebas citadas, todas existen) y `docs/trazabilidad.md` | "Cada requerimiento y regla apunta a una prueba que pasa." |

## Si algo falla en vivo

- Volver a cero: los dos comandos de "Antes de empezar".
- El tablero sale vacío: la carga del almacén no terminó; `docker compose ... logs etl`.
- Sin internet no se ve el fondo del mapa; los puntos y todo lo demás siguen funcionando.
