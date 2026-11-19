# Matriz de trazabilidad y pruebas de aceptación (S8-07)

Cada requerimiento funcional (RF) y cada regla de negocio del documento de los Sprints 0–3 apunta a las filas
del plan (`docs/contexto/plan-sprints-4-8.md`, sección 6) que lo implementan y a las pruebas que lo demuestran.
Notación de las pruebas: `servicio/archivo::prueba` (carpeta `tests/` de `services/<servicio>-service` o de `dwh`).

`python scripts/trazabilidad.py` comprueba que cada prueba citada existe; con `--ejecutar` además las corre.
Las comprobaciones de sistema completo son scripts que se ejecutan con el sistema levantado.

## Requerimientos funcionales

| RF | Qué exige | Filas del plan | Pruebas |
| --- | --- | --- | --- |
| RF1 Usuarios, autenticación y verificación | CRUD de cuentas, verificación como flujo de estados, JWT, roles | S4-03, S4-09, S5-03, S5-04, S5-05, S5-16, S5-20 | `identity/test_api::test_registro_y_login_con_jwt`, `identity/test_api::test_el_token_vence`, `identity/test_api::test_ruta_de_administrador_responde_403_a_un_donante`, `identity/test_api::test_perfil_propio`, `identity/test_consultas::test_desactivar_no_borra_la_fila`, `identity/test_consultas::test_verificacion_resuelta_no_vuelve_a_pendiente`, `identity/test_consultas::test_solo_un_administrador_resuelve`, `identity/test_esquema::test_correo_unico_sin_distinguir_mayusculas` |
| RF2 Donaciones | Crear, consultar, actualizar y cancelar (la cancelación es un cambio de estado) | S4-04, S4-10, S5-06, S5-17 | `catalog/test_consultas::test_crud_de_donacion`, `catalog/test_api::test_solo_donantes_verificados_publican`, `catalog/test_api::test_modificar_y_cancelar_solo_el_dueno`, `catalog/test_esquema::test_cantidad_positiva_y_vencimiento_posterior` |
| RF3 Necesidades | Los receptores publican y actualizan las suyas | S4-04, S4-10, S5-07, S5-18 | `catalog/test_consultas::test_crud_de_necesidades_solo_las_propias`, `catalog/test_api::test_necesidades_solo_las_propias` |
| RF3 Solicitudes (D-11) | Los donantes ven las necesidades abiertas y ofrecen una donación apartada para ese receptor | D-11 | `catalog/test_api::test_solicitudes_d11_donante_ofrece_y_solo_el_receptor_reserva`, `fulfillment/test_api::test_donacion_ofrecida_para_una_solicitud_solo_la_reserva_su_receptor`, `notification/test_api::test_cada_evento_llega_al_destinatario_correcto` |
| RF4 Búsqueda geoespacial y priorización | Distancia, disponibilidad, urgencia y vencimiento (D-07, D-08) | S4-10, S5-08, S5-18 | `catalog/test_consultas::test_busqueda_ordenada_por_distancia_en_metros`, `catalog/test_consultas::test_busqueda_excluye_vencidas_y_aplica_filtros`, `catalog/test_consultas::test_puntaje_d08_verificado_a_mano`, `catalog/test_consultas::test_referencia_por_necesidad_d07`, `catalog/test_api::test_busqueda_con_distancia_y_puntaje`, `catalog/test_esquema::test_postgis_y_indice_espacial` |
| RF5 Reservas | Una sola reserva activa por donación, aun con concurrencia (D-02) | S4-05, S4-11, S5-10, S5-11, S6-04, S6-08 | `fulfillment/test_concurrencia::test_indice_unico_parcial_en_la_base`, `fulfillment/test_concurrencia::test_20_conexiones_simultaneas_solo_una_reserva_activa`, `fulfillment/test_api::test_dos_solicitudes_simultaneas_201_y_409`, `fulfillment/test_api::test_si_catalog_rechaza_la_reserva_queda_cancelada`, `fulfillment/test_api::test_si_catalog_esta_caido_no_quedan_reservas_huerfanas`, `fulfillment/test_api::test_solo_el_donante_confirma_y_cancelar_libera` |
| RF6 Entregas y confirmación | ENTREGADA solo con la confirmación del donante y del receptor; incidencias | S4-05, S5-12, S5-19 | `fulfillment/test_transacciones::test_entrega_requiere_las_dos_confirmaciones`, `fulfillment/test_api::test_entrega_con_las_dos_confirmaciones`, `fulfillment/test_api::test_incidencia_queda_registrada` |
| RF7 Notificaciones | Avisos de cambios importantes al destinatario correcto | S4-06, S5-14, S5-19, S6-05 | `notification/test_api::test_cada_evento_llega_al_destinatario_correcto`, `notification/test_api::test_bandeja_leer_archivar_y_contador`, `notification/test_api::test_evento_repetido_no_duplica_notificaciones`, `notification/test_consultas::test_solo_el_destinatario_la_modifica` |
| RF8 Automatización de expiraciones y vencimientos | Tareas periódicas idempotentes (D-09) | S4-11, S5-13, S6-07 | `fulfillment/test_transacciones::test_expiracion_en_lote_libera_solo_las_vencidas`, `fulfillment/test_transacciones::test_reservar_con_plazo_d09`, `fulfillment/test_api::test_tareas_idempotentes_expiran_avisan_y_concilian`, `catalog/test_consultas::test_vencer_donaciones_es_idempotente` |
| RF9 Indicadores y reportes | Cifras consolidadas, reportes filtrables con exportación, cobertura por región | S7-01 a S7-07, S8-01 a S8-04 | `analytics/test_indicadores::test_resumen_igual_a_consulta_manual`, `analytics/test_indicadores::test_series_filtros_y_granularidad`, `analytics/test_indicadores::test_cobertura_por_region_lista_para_el_mapa`, `analytics/test_indicadores::test_csv_con_los_mismos_totales_que_la_pantalla`, `dwh/test_almacen::test_indicadores_iguales_a_consulta_manual`, `dwh/test_almacen::test_carga_historica_repetible_y_con_conteos_iguales`, `dwh/test_almacen::test_sinteticos_coherentes_y_deterministas`, `dwh/test_almacen::test_calidad_detecta_problemas` |
| RF10 Auditoría y trazabilidad | Reconstruir cada operación; registros no modificables | S4-03, S5-05, S5-15, S6-09, S8-05 | `identity/test_esquema::test_auditoria_inmutable_incluso_para_el_dueno`, `identity/test_esquema::test_rol_de_aplicacion_no_modifica_ni_borra_auditoria`, `identity/test_api::test_verificacion_por_el_administrador_queda_auditada`, `identity/test_api::test_el_consumidor_audita_eventos_de_otros_servicios`, `identity/test_api::test_evento_repetido_no_se_audita_dos_veces`, `analytics/test_historial::test_guarda_sin_duplicar_y_consulta`, `analytics/test_historial::test_historial_inmutable`, `catalog/test_api::test_identificador_de_correlacion_viaja_hasta_el_evento` |

## Reglas de negocio (Sprint 1)

| Regla | Filas del plan | Pruebas |
| --- | --- | --- |
| Solo usuarios registrados, autenticados y verificados publican, registran necesidades y reservan | S5-03, S5-06, S5-07, S5-10 | `catalog/test_api::test_solo_donantes_verificados_publican`, `fulfillment/test_api::test_solo_receptores_verificados_reservan`, `catalog/test_api::test_necesidades_solo_las_propias` |
| Cada usuario tiene un rol con permisos específicos | S5-03 | `identity/test_api::test_ruta_de_administrador_responde_403_a_un_donante`, `catalog/test_api::test_categorias_las_mantiene_el_administrador` |
| Toda donación tiene información válida (alimento, cantidad, ubicación, vencimiento cuando corresponda) | S4-04 | `catalog/test_esquema::test_cantidad_positiva_y_vencimiento_posterior`, `catalog/test_api::test_solo_donantes_verificados_publican` |
| Solo se reservan donaciones disponibles y vigentes | S4-10, S5-10 | `catalog/test_consultas::test_no_se_reserva_una_donacion_vencida`, `catalog/test_esquema::test_la_base_rechaza_transiciones_ilegales` |
| Una sola reserva activa por donación | S4-05, S4-11, S5-10, S6-08 | `fulfillment/test_concurrencia::test_20_conexiones_simultaneas_solo_una_reserva_activa`, `fulfillment/test_api::test_dos_solicitudes_simultaneas_201_y_409` |
| Toda reserva pendiente expira y se libera automáticamente | S4-11, S5-13 | `fulfillment/test_transacciones::test_expiracion_en_lote_libera_solo_las_vencidas`, `fulfillment/test_transacciones::test_no_se_confirma_fuera_de_plazo` |
| Los receptores modifican solo sus propias necesidades | S5-07 | `catalog/test_consultas::test_crud_de_necesidades_solo_las_propias` |
| La búsqueda considera ubicación, distancia, disponibilidad, urgencia y vencimiento | S4-10, S5-08 | `catalog/test_consultas::test_puntaje_d08_verificado_a_mano`, `catalog/test_consultas::test_busqueda_excluye_vencidas_y_aplica_filtros` |
| Entregada solo con la confirmación de donante y receptor | S5-12 | `fulfillment/test_transacciones::test_entrega_requiere_las_dos_confirmaciones` |
| Notificaciones de cambios en donaciones, reservas y entregas | S5-14 | `notification/test_api::test_cada_evento_llega_al_destinatario_correcto` |
| Los cambios de estado se registran para auditoría | S5-05, S5-15 | `identity/test_api::test_el_consumidor_audita_eventos_de_otros_servicios`, `analytics/test_historial::test_guarda_sin_duplicar_y_consulta` |
| Datos personales protegidos, solo para personas autorizadas (Ley 1581) | S8-06 | `identity/test_api::test_ruta_de_administrador_responde_403_a_un_donante`, `analytics/test_indicadores::test_solo_el_administrador_y_almacen_configurado`, `dwh/test_almacen::test_carga_historica_repetible_y_con_conteos_iguales`, `notification/test_consultas::test_solo_el_destinatario_la_modifica` |

## Comprobaciones de sistema completo

| Qué | Filas | Cómo |
| --- | --- | --- |
| Flujo principal de extremo a extremo con eventos reales | S5-21, S6-02 | `python scripts/e2e.py --base http://localhost:8080` |
| Catalog caído: 503 sin reservas huérfanas | S6-04 | `python scripts/resiliencia.py` |
| 20 reservas simultáneas contra dos réplicas | S6-08 | `python scripts/carga_reservas.py --base http://localhost:8080` |
| Conciliación entre bases | D-06 | `python scripts/bd.py verificar` |
| Seguridad y datos personales | S8-06 | `python scripts/revisar_seguridad.py --bases` |
| Contratos y gateway al día con el código | S5-01, S6-03 | `python scripts/contratos.py --revisar`, `python scripts/gateway.py --revisar` |
