# Correo y adjuntos {#e-mail-si-atasamente}
## Objetivo {#la-ce-foloseste}
Redacta mensaje nuevo editable con descripción completa y envíalo mediante Outlook Classic (predeterminado) o Gmail con contraseña de aplicación. Sin Reply/ReplyAll ni lectura de bandeja de entrada. Editar el mensaje no cambia la tarea.
## Dónde encontrarlo {#unde-il-gasesti}
**Ctrl+M**, **Organizar → Correo desde tarea…**, **Más → Redactar correo…** o **Archivos → Adjuntar al correo…**.
## Tutorial H: descripción completa y documentos {#tutorial-h-descriere-completa-si-documente-alese}
1. Ante cambios sin guardar, elige descripción actual (predeterminado), última guardada o Cancelar; no guarda otros metadatos.
2. Rellena Para, CC, Asunto. Nunca envíes realmente a direcciones ficticias del tutorial.
3. Edita Mensaje; texto completo, saltos y acentos se conservan sin el antiguo límite de 600 caracteres. Actualizar no lo regenera.
4. Elige los [adjuntos](#atasamente) necesarios.
5. **Abrir borrador en Outlook** para revisar o **Enviar**; confirma destinatarios, asunto, número y tamaño de adjuntos.
## Adjuntos {#atasamente}
Añadir archivos… permite selección múltiple; Desde archivos de la tarea/proyecto… incluye documentos manuales. Quitar del correo solo cambia selección. Nombres iguales en rutas distintas son documentos distintos. No se comprimen/adjuntan directorios automáticamente. Se verifican de nuevo antes de entregar; rechazar un adjunto detiene todo sin envío parcial.
## Resultados y guardado {#rezultate-si-salvare}
Borrador abierto no es enviado. Entregado a Outlook significa que Send regresó correctamente, no recepción. Comprueba Bandeja de salida/Enviados. El diario registra resultado y nombres, no cuerpo completo.
## Errores y precauciones {#erori-si-greseli-frecvente}
Intro no envía. Los errores conservan formulario. Tras tiempo agotado/resultado incierto, comprueba Outlook antes de **He comprobado en Outlook…** y reintenta explícitamente; nunca automáticamente. Un fallo de diario no justifica reenviar. El formulario no es un borrador persistente al cerrar la aplicación. [Outlook](guide:setari#outlook-classic-si-lucru-offline).

## Configurar Gmail {#gmail-configurare}
Outlook Classic sigue siendo el proveedor predeterminado. Abre **Configuración → Integraciones → Correo electrónico** o **Configurar Gmail…** en el formulario. Introduce la dirección de Gmail/Google Workspace (se admiten dominios propios) y un nombre visible opcional. No se ofrecen remitentes arbitrarios ni alias sin verificar.

Activa la verificación en dos pasos en tu cuenta de Google y genera manualmente una contraseña de aplicación en el navegador en `https://myaccount.google.com/apppasswords`, mediante **¿Cómo obtengo una contraseña de aplicación?**. Introduce esa contraseña enmascarada, no la habitual ni códigos de verificación. Solo se eliminan los espacios de presentación. Las políticas de la organización, Advanced Protection u otras restricciones pueden impedir su creación. Cambiar la contraseña de Google puede revocarla. No es OAuth ni «Sign in with Google».

**Recordar de forma segura en este equipo** usa el Administrador de credenciales de Windows. El secreto no se incluye en el espacio de trabajo, JSON, registro ni copias de seguridad. Sin almacenamiento seguro, permanece solo en la memoria de la sesión y debe introducirse tras reiniciar. **Guardar configuración de correo** modifica únicamente el perfil del equipo, no las ediciones de tareas. Si no se puede borrar una credencial antigua, se conservan el aviso y su referencia para eliminarla después.

**Probar conexión** verifica TLS y autenticación sin enviar mensajes ni guardar campos. El éxito no garantiza la aceptación ni la entrega de un correo. **Eliminar credenciales** borra el secreto local y los metadatos; revoca la contraseña por separado desde tu cuenta de Google.

## Envío de Gmail y resultados {#gmail-trimitere}
En el mismo formulario elige **Enviar mediante → Gmail — dirección de la cuenta**. Cambiar de proveedor o configurarlo conserva Para, CC, asunto, cuerpo y adjuntos. El calendario de Outlook no cambia. Gmail no necesita Outlook; el envío y la prueba requieren internet, mientras el resto de FocusDesk funciona sin conexión.

**Enviar** pide confirmar la cuenta y el mensaje. SMTP usa `smtp.gmail.com:465`, TLS verificado y tiempos de espera, nunca una conexión sin cifrar. Se leen todos los documentos antes de entregarlos; un archivo ausente o ilegible bloquea un mensaje incompleto.

**Mensaje aceptado por el servidor de Gmail para enviarlo** no confirma entrega ni lectura. La aceptación parcial muestra destinatarios aceptados/rechazados y códigos SMTP. **Preparar solo los destinatarios rechazados…** quita a los ya aceptados y requiere una nueva confirmación de envío. No hay reenvío automático ni cambio a Outlook. Una desconexión durante la entrega puede dejar un resultado incierto: comprueba Gmail/destinatarios antes de **He comprobado Gmail…**. Cambiar de proveedor no desbloquea el reenvío.

SMTP no crea borradores en Gmail web. **Guardar como .eml (local)…** crea un archivo local con cuerpo y adjuntos, sin enviar ni sincronizar. **Abrir borrador en Outlook** solo está disponible para Outlook. El registro conserva proveedor, cuenta, destinatarios, asunto, momento, Message-ID y nombres de archivos, nunca el secreto ni la conversación SMTP. Un fallo del registro después de la aceptación no justifica reenviar.

Comprueba por separado internet/DNS, tiempo de espera, TLS/certificados, autenticación, destinatarios y límites. Los códigos no siempre distinguen una contraseña incorrecta, revocada o una política de la cuenta. Los errores conservan el formulario; no desactives TLS para evitarlos.
