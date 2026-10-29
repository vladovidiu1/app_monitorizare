# Entender Actividad {#activitate-intelegerea-dashboardului}
## Objetivo {#la-ce-foloseste}
Dashboard, calendario mensual, tablas y CSV comparten un modelo de cálculo sin duplicar trabajo padre/subtareas.
## Dónde encontrarlo {#unde-il-gasesti}
**Actividad**; **Calendario mensual · Ctrl+D** abre la vista secundaria.
## Tutorial J: comprobar trabajo registrado {#tutorial-j-verifica-timpul-lucrat}
1. Elige 7/30/90 días, Mes actual, Intervalo personalizado o Todo el historial.
2. Proyecto o Sin proyecto; aplica fechas personalizadas explícitamente.
3. Compara Trabajo registrado y Programado, sin sumarlos como trabajo.
4. Selecciona día/proyecto; **Quitar detalle** o **Restablecer filtros**.
5. Intro/doble clic en sesión abre tarea; volver conserva contexto.
6. **Exportar CSV** respeta filtros e incluye definiciones, acentos y protección ante fórmulas Excel.
## Interpretar indicadores {#cum-interpretezi-cardurile}
Trabajo registrado suma actual_seconds una vez por sesión, incluidas tareas finalizadas/archivadas/ausentes. Día de inicio real, o inicio programado si falta, en zona del espacio. Tiempo en vivo sin guardar separado. Programado cuenta reservas admisibles, sin cancelled/missed. Las reuniones no aumentan ninguno.
Finalizadas cuenta tareas distintas con transición done en el período; reabrir/refinalizar no duplica. No se inventa historial desde updated_at. Atrasadas ahora y estados son actuales, igual que pertenencia a proyectos. Períodos grandes se agrupan en semanas/meses, con granularidad visible.
## Guardado y errores frecuentes {#salvare-si-greseli-frecvente}
Los filtros no cambian sesiones. Exportar escribe explícitamente el archivo elegido. Corrige solo sesiones terminadas identificables y vuelve a comprobar. Las horas no bastan para medir productividad. [Sesiones](guide:sesiuni).
