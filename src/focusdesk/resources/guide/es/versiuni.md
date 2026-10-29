# Versiones, checkpoints y código {#versiuni-checkpointuri-si-acces-la-cod}
## Objetivo {#la-ce-foloseste}
Un checkpoint es copia local de archivos admisibles guardados para comparar/restaurar. Git es distinto y opcional; no se ejecutan scripts.
## Dónde encontrarlo {#unde-il-gasesti}
**Versiones** de tarea; origen en [Archivos](guide:fisiere), exclusiones/límites en **Ajustes → Versiones y VS Code**.
## Crear checkpoint {#pasi-pentru-un-checkpoint}
1. Guarda archivos en el editor externo.
2. Revisa raíz propia/heredada/compartida.
3. Descripción y **Guardar checkpoint**.
4. Archivos incluidos…, Comparar con actual/anterior.
5. Prefiere **Restaurar en carpeta independiente…** fuera del origen activo.
## Resultado y guardado {#rezultatul-si-salvarea}
Archivo comprimido/manifiesto respetan exclusiones y límites; contenido idéntico puede no generar otra copia. Restauración separada no cambia origen. Sobrescribir origen… es una acción distinta, confirmada y protegida.
## Automatización y Git {#automatizari-si-git}
Checkpoints al terminar/diarios requieren configuración y origen válido. La programación funciona solo con FocusDesk abierto. Git ofrece status/log/diff y commits manuales de archivos elegidos, sin push/reset/checkout automático.
## Errores frecuentes {#greseli-frecvente}
Checkpoint no es copia completa del espacio. Asociar carpeta externa no cambia cobertura. Distingue versiones y trabajo de cada [requisito](guide:cerinte#folder-de-cod-comun).
