# J.A.R.V.I.S — Asistente de escritorio

## Novedades de esta versión

- Entrada unificada por voz y texto: ambos modos pasan por `interpretar_orden`.
- Panel de conversación integrado en el HUD, con historial durante la sesión.
- Envío de solicitudes con Enter y botón de micrófono para abrir la ventana de escucha.
- Respuestas visibles para las órdenes escritas y habladas.
- Detección de accesos directos `.lnk` del menú Inicio para ampliar el catálogo de aplicaciones que se pueden abrir.
- Nuevos comandos para administrador de tareas, información básica del sistema, gestión de ventanas, rutas locales y recordatorios.
- Apagado y reinicio requieren confirmación explícita.
- Cerrar aplicaciones intenta hacerlo sin forzar la terminación, permitiendo que Windows o la aplicación soliciten guardar cambios.
- Recordatorios y temporizadores funcionan localmente durante la sesión.
- Se mantiene Vosk para reconocimiento local y la voz existente.

## Chat lateral (nuevo)

- El chat vive en un panel a la derecha, en columna propia: nada se superpone con el HUD.
- Pestañas **CHAT** y **COMANDOS** (con filtro).
- Atajos rápidos (hora, clima, música, volumen, captura…), historial con ↑/↓, autocompletado con Tab, Shift+Enter para varias líneas.
- Historial persistente, búsqueda dentro de la conversación, copiar/repetir cada mensaje, botones SÍ/NO para confirmaciones, indicador de «procesando», exportar a `.txt` (carpeta `conversaciones`).
- Comandos locales del chat: `/ayuda /calc /nota /notas /borrarnota /borrarnotas /buscar /repetir /exportar /limpiar /comandos`.

## Control del equipo (nuevo)

Archivos (usa nombre, ruta completa, «el último zip de descargas» o carpetas conocidas: Descargas, Escritorio, Documentos, Imágenes, Vídeos, Música):
- Borrar → va a la **Papelera** (recuperable) y pide confirmación. «Borra X permanentemente» borra de verdad, con confirmación reforzada.
- Descomprimir (`.zip`, `.tar/.gz`, y `.7z/.rar` con el `tar` de Windows), comprimir, copiar, mover, renombrar, crear carpetas, buscar, listar, ver tamaño y **ordenar Descargas por tipo** (con confirmación).
- Protegido siempre: Windows, Program Files, ProgramData, raíces de unidad, tu carpeta personal, las carpetas Escritorio/Descargas… completas y la carpeta del asistente. Los accesos directos/enlaces no se borran.

Limpieza: temporales, caché de navegadores (Chrome, Edge, Brave, Opera, Firefox) y apps (Discord, VS Code, Slack, Teams), DNS, portapapeles, Papelera (confirma), «limpia mi pc» y «limpieza completa» (confirma). No toca cookies ni contraseñas.

Procesos y sistema: procesos que más memoria usan, cierre forzado (confirma), espacio en disco, IP, comprobar Internet, suspender, apagar pantalla, cerrar sesión (confirma).

Equivalencias: más alias de apps de Windows y sitios web (Claude, ChatGPT, Drive, Teams, PowerShell, Panel de control, Registro…). Enseña las tuyas: «aprende que el chisme es Discord» o `/alias el chisme = discord`; se guardan en `config.json` (`alias_apps`).

## Ejemplos

- `Abre el navegador`
- `Abre el administrador de tareas`
- `Maximiza la ventana`
- `Recuérdame en cinco minutos comprar leche`
- `Busca gatos en YouTube`
- `Qué clima hace`
- `Bloquea el equipo`
- `Reinicia el equipo` → solicita confirmación.

## Instalación

1. Extrae la carpeta completa en una ubicación permanente.
2. Ejecuta `instalar.bat`.
3. Para revisar micrófono y audio, ejecuta `diagnostico.bat`.
4. Ejecuta `microfonos.bat` para consultar los dispositivos disponibles.

## Funcionamiento local y límites

El reconocimiento de voz Vosk y el interpretador de órdenes son locales. Abrir aplicaciones, controlar Windows, temporizadores y recordatorios no requieren tokens de IA.

Edge TTS necesita conexión a Internet para generar su voz preferida; el asistente conserva la alternativa de voz de Windows. Las búsquedas y el acceso al clima abren el navegador y necesitan Internet.

Esta versión no incorpora un modelo conversacional general ni respuestas generativas ilimitadas: las solicitudes se interpretan mediante reglas locales y, cuando no se reconoce una intención, J.A.R.V.I.S pide reformularla. Esto evita depender de una API de IA de pago.
