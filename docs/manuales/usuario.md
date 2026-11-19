# Manual de usuario de RedAlimenta

RedAlimenta conecta a quienes tienen alimentos para donar con quienes los necesitan, cerca y a tiempo.
Funciona en el navegador del celular o del computador. Este manual explica qué hace cada tipo de usuario.

## Entrar

1. Abre la dirección que te dio el administrador (en la demostración, `http://localhost:8080`).
2. Escribe tu correo y contraseña y pulsa **Iniciar sesión**.
3. ¿No tienes cuenta? Pulsa **¿No tienes cuenta? Regístrate**, escribe tu nombre u organización, elige si
   participas como **donante** o **receptor**, tu correo y una contraseña de al menos 8 caracteres.

Las cuentas nuevas quedan **pendientes de verificación**: puedes mirar, pero no publicar ni reservar hasta
que un administrador te apruebe. Cuando ocurra recibirás un aviso; pulsa **Actualizar estado** o vuelve a
entrar.

## Donante

| Pestaña | Para qué |
| --- | --- |
| **Solicitudes** | Lo que piden los receptores, en mapa y lista, la más urgente primero; filtra por ciudad y categoría. **Ofrecer donación** abre Publicar con los datos de la solicitud: la donación queda apartada para ese receptor mientras su solicitud siga abierta. |
| **Publicar** | Elige la ciudad, toca el mapa donde se recoge el alimento y completa qué es, la categoría, la cantidad y unidad, hasta cuándo es apto (hora de Colombia), una dirección de referencia y las condiciones de recogida. |
| **Mis donaciones** | Ves cada donación con su estado. Mientras está **DISPONIBLE** puedes cancelarla. Cuando un receptor la reserva, aparece **Confirmar reserva** o **Rechazar**; tienes **2 horas** para confirmar o la reserva expira y la donación vuelve a estar disponible. |
| **Entregas** | Cuando entregues el alimento, pulsa **Confirmar entrega** (o **Reportar incidencia** si algo salió mal). La donación queda ENTREGADA cuando confirman tú y el receptor. |
| **Avisos** | Notificaciones de reservas, entregas y vencimientos. Tócalas para marcarlas como leídas. |

## Receptor

| Pestaña | Para qué |
| --- | --- |
| **Buscar** | Elige como punto de búsqueda una de tus necesidades (o toca el mapa). Verás las donaciones disponibles en el mapa y en la lista, con su distancia y un **puntaje de prioridad** que combina la urgencia de tu necesidad (40 %), la cercanía (35 %) y lo pronto que vence (25 %). Puedes filtrar por categoría y ordenar por prioridad o distancia. Pulsa **Reservar**. |
| **Pedir alimentos** | Publica una solicitud con lo que necesitas (descripción, categoría, cantidad, urgencia y punto en el mapa). Los donantes la ven y pueden ofrecerte una donación: recibirás un aviso y aparecerá primero en Buscar, marcada 🎁 y apartada para ti. Cierra la solicitud cuando quede cubierta. |
| **Mis reservas** | Ves si el donante ya confirmó y el tiempo que le queda. Puedes cancelar la reserva. |
| **Entregas** | Cuando recibas el alimento, pulsa **Confirmar entrega** o **Reportar incidencia**. |
| **Avisos** | Notificaciones. |

Una donación solo puede tener **una reserva activa**: si dos receptores la reservan a la vez, uno la obtiene
y el otro ve el mensaje "Esta donación ya tiene una reserva activa".

## Administrador

| Pestaña | Para qué |
| --- | --- |
| **Tablero** | Indicadores de la plataforma: donaciones, reservas, entregas finalizadas, proporción de alimentos cancelados o vencidos y volumen distribuido; serie en el tiempo por día, mes o año; mapa y tabla de cobertura por ciudad. Filtra por fechas, departamento, ciudad, categoría y si se incluyen los datos sintéticos. Los botones **CSV** descargan exactamente lo que se ve. |
| **Cuentas** | Aprueba o rechaza la verificación de cada cuenta (con una observación). **Ejecutar tareas** corre ahora las tareas automáticas. |
| **Categorías** | Crea categorías de alimentos o corrige su nombre. |
| **Auditoría** | Registro de solo inserción de todos los cambios: quién, qué y cuándo. |
| **Trazabilidad** | Escribe el número de una donación, reserva o entrega (o de un usuario) y ve su historia completa: la auditoría y los eventos de cada servicio con su identificador de correlación. |

## El sistema (cuarto actor)

Sin que nadie lo pida, RedAlimenta: expira las reservas que el donante no confirmó en 2 horas y libera la
donación; marca como VENCIDAS las donaciones que pasaron su fecha; avisa 24 horas antes de que una donación
venza; y corrige diferencias entre servicios. Todo queda en la auditoría como hecho por "Sistema".
