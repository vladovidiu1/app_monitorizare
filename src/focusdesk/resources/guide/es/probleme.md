# Problemas frecuentes y limitaciones {#probleme-frecvente-si-limitari}
## No encuentro tarea finalizada {#nu-gasesc-un-task-finalizat}
Usa Finalizadas/Cerradas y filtros adecuados; también Archivo. Los enlaces a proyecto no cambian pertenencia. [Reabrir/nuevo requisito](guide:cerinte) son distintos.
## No se guardó la descripción {#descrierea-nu-s-a-pastrat}
La guía cambia borrador; Guardar/Ctrl+S persiste. Cancelar editor ampliado restaura texto inicial. Diario requiere añadir explícitamente; [notas de reunión](guide:intalniri) autoguardadas.
## No aparece documento nuevo {#un-document-nou-nu-apare}
Comprueba raíz Archivos, expande y Actualizar/F5. Carpetas inaccesibles pueden mostrar lista antigua sin probar disponibilidad. Enlaces/junctions no se recorren automáticamente. [Archivos](guide:fisiere).
## Más programado que trabajado {#vad-programat-dar-nu-am-lucrat-atat}
Reserva no es trabajo. Duración guardada y tiempo en vivo separados; reuniones no añaden trabajo. Revisa filtros y corrige solo sesiones terminadas identificables. [Reglas](guide:activitate).
## Outlook no responde o falta módulo {#outlook-nu-raspunde-sau-lipseste-un-modul}
Usa Outlook Classic, respeta políticas de empresa. `ModuleNotFoundError: win32timezone` indica pywin32 incompleto; el ejecutable necesita reconstruirse correctamente, no solo instalar paquetes Python aparte. Tras timeout de Send revisa ventanas, Borradores, Bandeja de salida y Enviados antes de reintentar. Éxito COM no prueba entrega. [Errores de correo](guide:email#erori-si-greseli-frecvente).
## Guardado rechazado o cambios externos {#salvare-refuzata-sau-modificari-externe}
Protege borradores. F5 conserva controles de conflicto; no sobrescribas archivos a ciegas. Otro proceso puede imponer solo lectura por bloqueo. Comprobar integridad informa problemas sin eliminar automáticamente.
## Rendimiento y seguridad {#limite-de-performanta-si-siguranta}
Reconstrucción inicial de índices/búsqueda global de descripciones puede leer más. Archivos recorre carpetas abiertas; guía solo documentación incluida. Índices eliminables, pero no sustituyen copias. Sin SQL/SQLite ni sincronización en nube.
## Comprueba en tu equipo {#ce-trebuie-verificat-pe-calculatorul-tau}
Outlook real/políticas COM, asociaciones, VS Code, junctions, DPI nativo y ejecutable Windows dependen del entorno. Backend falso y escalado Linux no los certifican. No se puede cancelar a la fuerza una llamada de red bloqueada con seguridad. Prueba restauraciones en datos temporales; copia carpetas externas por separado.
