# Ajustes e integraciones {#setari-si-integrari}
## Objetivo {#la-ce-foloseste}
Configura trabajo e integraciones opcionales. Las funciones locales no requieren Outlook ni cuentas en la nube.
## Dónde encontrarlo {#unde-il-gasesti}
**Ajustes** o **Herramientas → Ajustes…**: General, Colegas, Horario de trabajo, Copia de seguridad, Versiones y VS Code, Outlook.
## Configuración {#pasi-pentru-configurare}
1. General: nombre, zona horaria y máximo de prioridades diarias.
2. **Idioma**: Română, English, Deutsch, Français, Español. Aplicar al reiniciar guarda solo el perfil; reinicia manualmente cuando quieras. No afecta borradores ni temporizador.
3. Revisa días, horarios, pausas y excepciones: influyen en planificación, no inician trabajo.
4. Configura ubicaciones accesibles y Guardar.
## Colegas y solicitante {#colegi-si-solicitant}
Cargar colegas desde Excel… lee primera hoja .xlsx: nombre en A, código en B sin dominio. El selector sigue la convención existente de dirección. Importar sustituye lista inmediatamente, separado de Guardar ajustes; importación inválida conserva la anterior. Solicitante se guarda con tarea.
## Outlook Classic y sin conexión {#outlook-classic-si-lucru-offline}
COM requiere Outlook Classic y pywin32 incluido; New Outlook no lo admite. Importación de metadatos solo lectura, notas locales. Calendario de reservas y origen de reuniones distintos. Envío explícito. Save/Send local no confirma Exchange/entrega; ICS requiere importación. Sin Outlook siguen tareas, temporizador, informes, notas y reuniones manuales. Sin backend oculto en la nube.
## Errores frecuentes {#greseli-frecvente}
Idioma y zona horaria independientes. Fechas día primero; usa YYYY-MM-DD para entrada inequívoca. ISO persistente intacto. No cambies zona para reparar totales. [Errores](guide:probleme).
