"""Interpretador de órdenes en español; no depende del hardware del asistente."""

import datetime
import random
import re
import unicodedata
from difflib import SequenceMatcher, get_close_matches
from urllib.parse import quote_plus


ES_ALIAS = {
    "google chrome": "chrome", "cromo": "chrome", "crome": "chrome",
    "firefox": "firefox", "edge": "edge", "brave": "brave", "opera": "opera",
    "bloc de notas": "notepad", "notas": "notepad", "notepad": "notepad",
    "calculadora": "calculator", "explorador de archivos": "explorer",
    "explorador": "explorer", "archivos": "explorer",
    "configuracion": "settings", "ajustes": "settings",
    "terminal": "terminal", "consola": "terminal", "simbolo del sistema": "terminal",
    "visual studio code": "code", "codigo": "code", "paint": "paint",
    "word": "word", "excel": "excel", "camara": "camera",
    "whatsapp": "whatsapp", "guasap": "whatsapp", "wasap": "whatsapp",
    "discord": "discord", "telegram": "telegram", "steam": "steam",
    "spotify": "spotify", "spoty": "spotify", "espotify": "spotify",
    "espotifai": "spotify", "youtube": "youtube", "google": "google",
    "gmail": "gmail", "correo": "gmail", "netflix": "netflix",
    "github": "github", "facebook": "facebook", "instagram": "instagram",
    "mapas": "maps", "navegador": "browser", "internet": "browser",
}
ES_ALIAS.update({
    # navegadores
    "gugle chrome": "chrome", "google crome": "chrome", "gugle": "chrome", "crom": "chrome",
    "microsoft edge": "edge", "mozilla": "firefox", "mozilla firefox": "firefox", "fire fox": "firefox",
    "el navegador": "browser", "explorador de internet": "browser",
    # utilidades de Windows
    "block de notas": "notepad", "bloc": "notepad", "libreta": "notepad",
    "calculador": "calculator", "calcu": "calculator", "calc": "calculator",
    "mis archivos": "explorer", "carpetas": "explorer", "explorador de windows": "explorer",
    "configuracion de windows": "settings", "opciones de windows": "settings", "preferencias": "settings",
    "cmd": "terminal", "linea de comandos": "terminal", "simbolo de sistema": "terminal",
    "powershell": "powershell", "power shell": "powershell", "windows terminal": "wt", "terminal de windows": "wt",
    "panel de control": "control", "administrador de dispositivos": "devmgmt", "dispositivos": "devmgmt",
    "administrador de discos": "diskmgmt", "administracion de discos": "diskmgmt",
    "servicios": "services", "visor de eventos": "eventvwr", "monitor de recursos": "resmon",
    "informacion del sistema": "msinfo", "limpieza de disco": "cleanmgr", "liberador de espacio": "cleanmgr",
    "editor del registro": "regedit", "registro de windows": "regedit", "regedit": "regedit",
    "recortes": "snip", "herramienta de recorte": "snip", "herramienta recortes": "snip", "recortar pantalla": "snip",
    "reloj": "clock", "alarmas": "clock", "calendario": "calendar",
    "tienda": "store", "microsoft store": "store", "tienda de microsoft": "store",
    "fotos": "photos", "galeria": "photos", "grabadora": "recorder", "grabadora de voz": "recorder",
    "wordpad": "wordpad", "wor pad": "wordpad",
    # oficina y comunicación
    "outlook": "outlook", "power point": "powerpoint", "powerpoint": "powerpoint", "presentaciones": "powerpoint",
    "onenote": "onenote", "one note": "onenote", "teams": "teams", "microsoft teams": "teams",
    "zoom": "zoom", "slack": "slack", "xbox": "xbox", "vlc": "vlc", "reproductor de video": "vlc",
    "obs": "obs", "obs studio": "obs", "visual studio": "code", "vs code": "code", "vscode": "code",
    "ve es code": "code",
    # sitios web
    "chat gpt": "chatgpt", "chatgpt": "chatgpt", "claude": "claude", "twitter": "twitter", "equis": "twitter",
    "tiktok": "tiktok", "tik tok": "tiktok", "linkedin": "linkedin", "reddit": "reddit", "twitch": "twitch",
    "whatsapp web": "whatsappweb", "guasap web": "whatsappweb", "google drive": "drive", "drive": "drive",
    "google docs": "docs", "documentos de google": "docs", "traductor": "translate", "google traductor": "translate",
    "wikipedia": "wikipedia", "amazon": "amazon", "mercado libre": "mercadolibre", "mercadolibre": "mercadolibre",
    "disney plus": "disney", "disney": "disney", "prime video": "prime", "amazon prime": "prime",
    "hbo": "max", "hbo max": "max", "max": "max",
})

CERRABLES = {
    "chrome", "firefox", "edge", "brave", "opera", "notepad", "calculator", "code", "word", "excel",
    "discord", "steam", "telegram", "whatsapp", "paint", "spotify", "outlook", "powerpoint", "wordpad",
    "teams", "zoom", "slack", "vlc", "obs", "onenote", "powershell",
}


def registrar_alias(tabla):
    """Añade equivalencias propias: {'frase hablada': 'clave de app'}."""
    for alias, destino in (tabla or {}).items():
        a = normalizar(alias)
        if a and destino:
            ES_ALIAS[a] = str(destino)

NUMEROS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3,
    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
    "veintiun": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27,
    "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
    "noventa": 90, "cien": 100, "ciento": 100,
}
UNIDADES = {
    "segundo": 1, "segundos": 1, "seg": 1,
    "minuto": 60, "minutos": 60, "min": 60,
    "hora": 3600, "horas": 3600,
}
TECLAS_VOZ = {
    "enter": "enter", "intro": "enter", "aceptar": "enter",
    "escape": "escape", "esc": "escape", "escapar": "escape",
    "tab": "tab", "tabulador": "tab", "espacio": "space",
    "space": "space", "retroceso": "backspace", "backspace": "backspace",
    "suprimir": "delete", "delete": "delete", "inicio": "home",
    "home": "home", "fin": "end", "end": "end",
    "flecha arriba": "up", "arriba": "up",
    "flecha abajo": "down", "abajo": "down",
    "flecha izquierda": "left", "izquierda": "left",
    "flecha derecha": "right", "derecha": "right",
}
ATAJOS = {
    "copiar": "copy", "copia": "copy", "pegar": "paste", "pega": "paste",
    "cortar": "cut", "corta": "cut", "deshacer": "undo", "rehacer": "redo",
    "guardar": "save", "seleccionar todo": "selectall", "selecciona todo": "selectall",
}

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
CHISTES = [
    "¿Qué le dice un jardinero a otro? Disfrutemos mientras podamos.",
    "¿Por qué los pájaros no usan Facebook? Porque ya tienen Twitter.",
    "¿Qué hace una abeja en el gimnasio? ¡Zumba!",
    "¿Cómo se llama el campeón de buceo japonés? Tokofondo. ¿Y el subcampeón? Kasitoko.",
    "Un programador se murió en la ducha. Decía el champú: enjuagar, repetir.",
]

INICIOS_CORTESIA = (
    "hazme el favor de", "me puedes ayudar a", "me podrias ayudar a",
    "podrias ayudarme a", "te importaria", "me gustaria que", "me gustaria",
    "quisiera que", "quiero que", "necesito que", "me ayudas a", "ayudame a",
    "me podria", "me podrias", "me puede", "me puedes",
    "puedes", "podrias", "podria", "quisiera", "necesito", "quiero", "por favor", "porfa",
    "porfis", "oye jarvis", "hola jarvis", "hey jarvis", "jarvis", "oye",
    "hey", "me",
)
FINAL_CORTESIA = (" por favor", " porfa", " porfis", " cuando puedas")


def normalizar(texto):
    texto = "".join(
        c for c in unicodedata.normalize("NFD", str(texto).lower())
        if unicodedata.category(c) != "Mn"
    )
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return " ".join(texto.split())


def _limpiar_orden(texto):
    t = normalizar(texto)
    cambio = True
    while t and cambio:
        cambio = False
        for inicio in sorted(INICIOS_CORTESIA, key=len, reverse=True):
            if t == inicio:
                t = ""
                cambio = True
                break
            if t.startswith(inicio + " "):
                t = t[len(inicio):].strip()
                cambio = True
                break
    cambio = True
    while t and cambio:
        cambio = False
        for final in FINAL_CORTESIA:
            if t.endswith(final):
                t = t[:-len(final)].strip()
                cambio = True
                break
    return t


def _buscar_app(texto, apps):
    disponibles = {normalizar(k): str(k) for k in apps}
    aliases = {
        alias: destino for alias, destino in ES_ALIAS.items()
        if destino in apps
    }
    tabla = {**disponibles, **aliases}
    for alias in sorted(tabla, key=len, reverse=True):
        if re.search(r"\b" + re.escape(alias) + r"\b", texto):
            return tabla[alias]

    # Tolera errores pequeños de transcripción solo en nombres de aplicaciones.
    palabras = [p for p in texto.split() if p not in {"el", "la", "los", "las", "un", "una"}]
    nombres_cortos = {k: v for k, v in tabla.items() if " " not in k and len(k) >= 4}
    for palabra in palabras:
        posibles = get_close_matches(palabra, nombres_cortos, n=2, cutoff=0.84)
        if posibles:
            if len(posibles) == 1 or (
                SequenceMatcher(None, palabra, posibles[0]).ratio()
                - SequenceMatcher(None, palabra, posibles[1]).ratio() >= 0.08
            ):
                return nombres_cortos[posibles[0]]
    return None


def _duracion_segundos(palabras):
    total = 0
    horas_media = set()
    for i, palabra in enumerate(palabras[:-1]):
        if palabra == "media" and palabras[i + 1] in {"hora", "horas"}:
            total += 1800
            horas_media.add(i + 1)

    if palabras and palabras[-1] == "media" and "hora" in palabras:
        total += 1800

    for i, unidad in enumerate(palabras):
        if unidad not in UNIDADES or i in horas_media:
            continue
        cantidad = 0
        j = i - 1
        while j >= 0:
            palabra = palabras[j]
            if palabra.isdigit():
                cantidad += int(palabra)
            elif palabra in NUMEROS:
                cantidad += NUMEROS[palabra]
            elif palabra == "y":
                j -= 1
                continue
            else:
                break
            j -= 1
        total += cantidad * UNIDADES[unidad]
    return total


def _hora_texto():
    ahora = datetime.datetime.now()
    h12 = ahora.hour % 12 or 12
    periodo = (
        "de la madrugada" if ahora.hour < 5 else
        "de la mañana" if ahora.hour < 12 else
        "de la tarde" if ahora.hour < 19 else "de la noche"
    )
    prefijo = "Es la" if h12 == 1 else "Son las"
    minutos = "en punto" if ahora.minute == 0 else f"y {ahora.minute}"
    return f"{prefijo} {h12} {minutos} {periodo}."


def _fecha_texto():
    hoy = datetime.date.today()
    return f"Hoy es {DIAS[hoy.weekday()]}, {hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}."


def es_solo_activacion(texto):
    palabras = normalizar(texto).split()
    return not palabras or all(p in {"jarvis", "hey", "oye", "unk"} for p in palabras)


# ---------- acciones sobre el equipo: archivos, limpieza, procesos, sistema ----------
CARPETAS_VOZ = {
    "descargas": "descargas", "descarga": "descargas", "escritorio": "escritorio",
    "documentos": "documentos", "imagenes": "imagenes", "fotos": "imagenes",
    "videos": "videos", "musica": "musica",
}
TIPOS_VOZ = {
    "zip": "zip", "rar": "zip", "comprimido": "zip", "comprimida": "zip", "pdf": "pdf",
    "imagen": "imagen", "foto": "imagen", "instalador": "instalador", "video": "video",
    "audio": "audio", "cancion": "audio", "texto": "texto",
}
V_BORRAR = {"borra", "borrar", "elimina", "eliminar", "suprime", "suprimir", "tira", "tirar"}
V_LIMPIA = {"limpia", "limpiar", "vacia", "vaciar", "borra", "borrar", "elimina", "eliminar",
            "libera", "liberar", "purga", "purgar", "limpieza", "optimiza", "optimizar"}
V_UNZIP = {"descomprime", "descomprimir", "extrae", "extraer", "unzip", "desempaqueta", "desempaquetar"}
V_ZIP = {"comprime", "comprimir", "zipea", "empaqueta", "empaquetar"}
V_COPIA = {"copia", "copiar"}
V_MUEVE = {"mueve", "mover", "traslada", "trasladar"}
V_RENOM = {"renombra", "renombrar"}
V_KILL = {"mata", "matar", "termina", "terminar", "finaliza", "finalizar", "forzar", "fuerza",
          "forzosamente", "forzado"}
STOP_NOMBRE = {"de", "en", "que", "el", "la", "los", "las", "un", "una", "zip", "temporal", "llamado", "llamada",
               "ultimo", "ultima", "reciente", "descargas", "escritorio", "documentos", "este", "esta", "mi"}
_DISCO_RE = re.compile(r"(?:[a-zA-Z]:\\|%[A-Za-z]+%\\)")
_CONECTORES_FIN = re.compile(r"(?:\s+(?:a|hacia|en|y|al|dentro de|hasta|con|permanentemente|definitivamente|para siempre|siempre|por favor|porfa|ahora))+\s*$", re.I)
_ARCHIVO_RE = re.compile(r"(?<![\w\\/:%.])([\w\-()áéíóúñÁÉÍÓÚÑ]+(?:\.[\w\-()áéíóúñÁÉÍÓÚÑ]+)*\.[A-Za-z0-9]{1,5})(?![\w])")
_COMILLAS_RE = re.compile(r'["“«](.+?)["”»]')


def _rutas_absolutas(original):
    marcas = [m.start() for m in _DISCO_RE.finditer(original)]
    rutas = []
    for i, ini in enumerate(marcas):
        fin = marcas[i + 1] if i + 1 < len(marcas) else len(original)
        seg = original[ini:fin].strip().strip('"“”«»').rstrip(" .,;!?")
        seg = _CONECTORES_FIN.sub("", seg).strip().strip('"“”«»').rstrip("\\")
        if len(seg) > 3:
            rutas.append(seg)
    return rutas


def _carpeta_en(texto):
    for palabra in texto.split():
        if palabra in CARPETAS_VOZ:
            return CARPETAS_VOZ[palabra]
    return None


def _objetivos(original, t, w):
    """Especificaciones de archivo/carpeta mencionadas: ruta=, nombre=, ultimo=."""
    orig = re.sub(r"(\w)\s+punto\s+([A-Za-z0-9]{1,5})\b", r"\1.\2", original, flags=re.I)
    specs = ["ruta=" + r for r in _rutas_absolutas(orig)]
    resto = orig
    for r in _rutas_absolutas(orig):
        resto = resto.replace(r, " ")
    for m in _COMILLAS_RE.finditer(resto):
        specs.append("nombre=" + m.group(1).strip())
    resto_sc = _COMILLAS_RE.sub(" ", resto)
    for m in _ARCHIVO_RE.finditer(resto_sc):
        nombre = m.group(1)
        if not nombre.lower().startswith(("www.", "http")):
            specs.append("nombre=" + nombre)
    if not specs:
        if any(x in w for x in ("ultimo", "ultima", "reciente", "recien")):
            carpeta = _carpeta_en(t) or "descargas"
            tipo = next((TIPOS_VOZ[x] for x in w if x in TIPOS_VOZ), "")
            specs.append("ultimo=" + carpeta + ("/" + tipo if tipo else ""))
        else:
            m = re.search(r"\b(?:archivo|documento|carpeta)\s+(?:llamad[ao]\s+)?([a-z0-9\-]+)", t)
            if m and m.group(1) not in STOP_NOMBRE and m.group(1) not in CARPETAS_VOZ:
                specs.append("nombre=" + m.group(1))
    carpeta = _carpeta_en(t)
    if carpeta:
        specs = [s + "@" + carpeta if s.startswith("nombre=") and "@" not in s else s for s in specs]
    return specs


def _interpretar_pc(sin_prefijo, t, w, apps):
    ws = set(w)
    abrir_v = {"abre", "abrir", "abreme", "muestrame", "muestra", "ensename", "ve", "ir"}

    # Equivalencias propias: "aprende que el chisme es Discord" / "cuando diga X abre Y"
    m = re.match(r"^(?:aprende|recuerda|anota)\s+que\s+(.+?)\s+(?:es|significa|equivale a)\s+(.+)$", sin_prefijo.strip(" .!?"), re.I)
    if not m:
        m = re.match(r"^cuando\s+(?:yo\s+)?(?:diga|digo)\s+(.+?)[,;]?\s+(?:abre|abrir|ejecuta)\s+(.+)$", sin_prefijo.strip(" .!?"), re.I)
    if m:
        return "alias:" + m.group(1).strip(" \"“”«»") + "|" + m.group(2).strip(" \"“”«»")

    # ----- limpieza -----
    if ws & V_LIMPIA or "limpieza" in ws:
        if "papelera" in ws:
            return "clean:recycle"
        if "portapapeles" in ws:
            return "clean:clip"
        if "dns" in ws:
            return "clean:dns"
        if ws & {"cache", "caches"}:
            return "clean:cache"
        if ws & {"temporales", "temporal", "temp"}:
            return "clean:temp"
        objetivo = {"pc", "equipo", "computadora", "ordenador", "sistema", "espacio", "disco", "basura", "computador"}
        if (ws & objetivo or "limpieza" in ws) and not (ws & {"archivo", "archivos", "carpeta", "documento", "foto", "imagen"}):
            return "clean:full" if ws & {"completa", "profunda", "papelera", "total"} else "clean:all"
    if "dns" in ws and "flush" in ws:
        return "clean:dns"

    # ----- procesos -----
    sin_timer = not (ws & {"temporizador", "cronometro", "alarma", "recordatorio"})
    if sin_timer and ws & {"memoria", "ram", "procesos", "programas"} and ws & {"consumiendo", "gastando", "consume", "consumen", "pesados", "pesan", "usando"} and ws & {"que", "cual", "quien", "cuales", "mas"}:
        return "proc:top"
    forzado = ws & {"fuerza", "forzosamente", "forzado", "forzar"}
    if sin_timer and (ws & V_KILL or (forzado and ws & {"cierra", "cerrar"})) and (forzado or ws & {"proceso", "procesos", "programa", "aplicacion", "app", "mata", "matar", "termina", "finaliza", "terminar", "finalizar", "tarea"}):
        stop = V_KILL | {"el", "la", "los", "las", "proceso", "procesos", "programa", "aplicacion", "app", "a", "de", "que", "tarea",
                         "cierra", "cerrar", "fuerza", "forzosamente", "forzado", "por", "favor", "y", "un", "una", "se", "esta",
                         "estan", "trabado", "colgado", "congelado", "mi"}
        objetivo = " ".join(x for x in w if x not in stop)
        app = _buscar_app(objetivo, apps) if objetivo else None
        nombre = app or (objetivo.split()[0] if objetivo else None)
        if nombre and nombre != "browser":
            return "proc:kill|" + nombre
        return "decir:¿Qué proceso quieres terminar?"

    # ----- sistema -----
    if ws & {"apaga", "apagar", "apagues", "suspende", "suspender"} and ws & {"pantalla", "monitor"}:
        return "sys:screenoff"
    if ws & {"suspende", "suspender", "suspension", "duerme", "dormir", "hiberna", "hibernar"} and ws & {"equipo", "computadora", "pc", "ordenador", "laptop"}:
        return "sys:sleep"
    if "sesion" in ws and ws & {"cierra", "cerrar", "termina", "finaliza"}:
        return "sys:logoff"
    if ("espacio" in ws and ws & {"disco", "libre", "libres", "queda", "disponible"}) or ("cuanto" in ws and "disco" in ws) or ("disco" in ws and ws & {"lleno", "capacidad"}):
        return "sys:disk"
    if "ip" in ws and ws & {"mi", "cual", "dime", "direccion", "mia"}:
        return "sys:ip"
    if w[0] in {"hay", "tengo", "tenemos", "funciona", "estoy"} and ws & {"internet", "conexion", "red", "wifi"}:
        return "sys:ping"

    # ----- archivos y carpetas -----
    objs = _objetivos(sin_prefijo, t, w)
    carpeta = _carpeta_en(t)
    sustantivo = bool(ws & {"archivo", "archivos", "carpeta", "documento", "foto", "imagen", "descarga", "zip", "pdf", "video", "ultimo", "ultima"})

    if (ws & V_BORRAR or ("papelera" in ws and ws & {"manda", "mandar", "pasa", "envia", "mete"})) and (objs or sustantivo):
        if not objs:
            return "decir:¿Qué quieres borrar? Dame el nombre del archivo o la ruta completa."
        definitivo = bool(ws & {"permanentemente", "definitivamente", "siempre", "permanente", "definitivo"})
        return ("file:purge|" if definitivo else "file:delete|") + objs[0]

    if ws & V_UNZIP and (objs or ws & {"zip", "archivo", "comprimido", "rar"}):
        return ("file:unzip|" + objs[0]) if objs else "decir:¿Qué archivo quieres descomprimir? Dame el nombre o di «el último zip de descargas»."
    if ws & V_ZIP and (objs or sustantivo):
        return ("file:zip|" + objs[0]) if objs else "decir:¿Qué quieres comprimir? Dame el nombre o la ruta."

    if ws & (V_COPIA | V_MUEVE) and (objs or sustantivo):
        mover = bool(ws & V_MUEVE)
        if not objs:
            return "decir:¿Qué archivo quieres " + ("mover" if mover else "copiar") + "?"
        rutas = [o for o in objs if o.startswith("ruta=")]
        dest = None
        if len(rutas) >= 2:
            origen, dest = rutas[0], rutas[1]
        else:
            m = re.search(r"\b(?:a|hacia|al|en|dentro de)\s+(?:la\s+carpeta\s+(?:de\s+)?|el\s+|la\s+)?(descargas|escritorio|documentos|imagenes|videos|musica)$", t)
            if m:
                dest = "carpeta=" + m.group(1)
                previo = t[:m.start()]
                origen = objs[0]
                if origen.startswith("nombre=") and "@" in origen:
                    nombre = origen.split("=", 1)[1].split("@")[0]
                    q = _carpeta_en(previo)
                    origen = "nombre=" + nombre + ("@" + q if q else "")
        if dest:
            return ("file:move|" if mover else "file:copy|") + origen + "|" + dest
        return "decir:¿A qué carpeta lo " + ("muevo" if mover else "copio") + "? Di por ejemplo «a documentos» o dame la ruta."

    if ws & V_RENOM or ("cambia" in ws and "nombre" in ws):
        nombres = [o for o in objs]
        if len(nombres) >= 2:
            nuevo = nombres[1].split("=", 1)[1].split("@")[0]
            return "file:rename|" + nombres[0] + "|" + nuevo
        return "decir:Dime el archivo y el nombre nuevo, por ejemplo «renombra informe.docx a final.docx»."

    if ws & {"crea", "crear", "haz", "hacer", "nueva", "nuevo", "genera"} and "carpeta" in ws and not (ws & V_BORRAR):
        m = re.search(
            r"carpeta\s+(?:(?:llamad[ao]|nombrad[ao]|con\s+(?:el\s+)?nombre(?:\s+de)?|de\s+nombre)\s+)?[\"“«]?(.+?)[\"”»]?"
            r"(?:\s+(?:en|dentro\s+de)\s+(?:la\s+carpeta\s+(?:de\s+)?|el\s+|la\s+)?(descargas|escritorio|documentos|im[aá]genes|v[ií]deos|m[uú]sica))?\s*[.!?]*$",
            sin_prefijo, re.I)
        if m and m.group(1).strip() and normalizar(m.group(1)) not in CARPETAS_VOZ:
            en = normalizar(m.group(2) or "escritorio")
            return "file:mkdir|" + m.group(1).strip() + "|" + CARPETAS_VOZ.get(en, "escritorio")
        return "decir:¿Cómo quieres llamar la carpeta?"

    if ws & {"organiza", "organizar", "ordena", "ordenar", "acomoda", "acomodar"} and carpeta in {"descargas", "escritorio", "documentos"}:
        return "file:organize|" + carpeta

    if carpeta and (("que" in ws and ws & {"hay", "tengo", "contiene"}) or (ws & {"lista", "listar", "muestra", "muestrame", "enumera"} and ws & {"archivos", "contenido", "descargas"})):
        return "file:list|carpeta=" + carpeta

    if ws & {"busca", "buscar", "encuentra", "encontrar", "localiza", "localizar", "donde"} and ws & {"archivo", "documento", "carpeta", "esta"} and objs:
        nombres = [o for o in objs if o.startswith("nombre=")]
        if nombres:
            return "file:find|" + nombres[0].split("=", 1)[1]

    if "cuanto" in ws and ws & {"pesa", "ocupa", "pesan", "ocupan"} and objs:
        return "file:size|" + objs[0]

    if w[0] in abrir_v and (objs or carpeta):
        if objs and sustantivo or (objs and objs[0].startswith(("ruta=", "nombre=")) and "." in objs[0]):
            return "file:open|" + objs[0]
        if carpeta and (carpeta in {"descargas", "documentos"} or "carpeta" in ws):
            return "file:open|carpeta=" + carpeta
    return None


def interpretar_orden(texto, apps, nombre="Jarvis"):
    """Devuelve una acción del asistente o None si no reconoce la orden."""
    texto_original = str(texto).strip()
    sin_prefijo = re.sub(
        r"^(?:(?:oye|hey)\s+)?jarvis[\s,;:]+",
        "", texto_original, count=1, flags=re.IGNORECASE,
    )
    dictado = re.match(r"^(?:escribe|teclea|dicta)\s+(.+)$", sin_prefijo, re.I | re.S)
    if dictado:
        contenido = dictado.group(1).strip()
        if contenido:
            return "type:" + contenido[:500]

    original = normalizar(texto_original)
    sin_activacion = re.sub(r"\bjarvis\b", "", original).strip()
    saludos = {
        "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
        "hello", "hi",
    }
    if sin_activacion in saludos:
        return f"decir:Hola {nombre}, aquí estoy. ¿En qué puedo ayudarte?"

    t = _limpiar_orden(texto)
    w = t.split()
    if not w:
        return None

    # Escritura y control directo del puntero/teclado.
    if t in {"haz clic", "haz click", "clic", "click", "clic izquierdo", "click izquierdo"}:
        return "mouse:click"
    if t in {"clic derecho", "click derecho", "haz clic derecho", "haz click derecho"}:
        return "mouse:right"
    if t in {"doble clic", "doble click", "haz doble clic", "haz doble click"}:
        return "mouse:double"
    if t in {"mueve el cursor al centro", "mueve el mouse al centro", "centra el cursor"}:
        return "mouse:center"
    m = re.fullmatch(
        r"(?:haz\s+)?(?:clic|click)\s+en\s+(\d{1,4})\s+(\d{1,4})", t
    )
    if m:
        return "mouse:at:" + m.group(1) + ":" + m.group(2)
    m = re.fullmatch(
        r"(?:mueve|mover|desplaza|desplazar)\s+(?:el\s+)?(?:cursor|mouse|raton)\s+"
        r"(?:a|hasta)\s+(?:la\s+)?(?:posicion\s+)?(\d{1,4})\s+(?:y\s+)?(\d{1,4})",
        t,
    )
    if m:
        return "mouse:at:" + m.group(1) + ":" + m.group(2)
    m = re.fullmatch(
        r"(?:mueve|mover|desplaza|desplazar)\s+(?:el\s+)?(?:cursor|mouse|raton)\s+"
        r"(?:a|hacia)\s+(?:la\s+)?(izquierda|derecha|arriba|abajo)(?:\s+(\d+|[a-z]+))?"
        r"(?:\s+(?:px|pixeles|pixels|puntos))?",
        t,
    )
    if m:
        direccion, cantidad = m.groups()
        pasos = int(cantidad) if cantidad and cantidad.isdigit() else NUMEROS.get(cantidad or "", 120)
        pasos = max(10, min(pasos, 800))
        dx = -pasos if direccion == "izquierda" else pasos if direccion == "derecha" else 0
        dy = -pasos if direccion == "arriba" else pasos if direccion == "abajo" else 0
        return f"mouse:move:{dx}:{dy}"
    if t in {"desplazate arriba", "desplazate hacia arriba", "sube la pagina", "scroll arriba", "rueda arriba"}:
        return "mouse:scroll_up"
    if t in {"desplazate abajo", "desplazate hacia abajo", "baja la pagina", "scroll abajo", "rueda abajo"}:
        return "mouse:scroll_down"
    if t in ATAJOS:
        return "key:" + ATAJOS[t]
    m = re.fullmatch(
        r"(?:presiona|pulsa|oprime|aprieta|tecla)\s+(?:la\s+)?(?:tecla\s+)?(.+)",
        t,
    )
    if m and m.group(1) in TECLAS_VOZ:
        return "key:" + TECLAS_VOZ[m.group(1)]

    r = _interpretar_pc(sin_prefijo, t, w, apps)
    if r:
        return r

    if any(x in w for x in ("clima", "clima", "tiempo")) and any(x in w for x in ("que", "como", "consulta", "dime", "pronostico")):
        consulta = " ".join(x for x in w if x not in {"que", "como", "esta", "hace", "el", "la", "dime", "consulta", "clima", "tiempo", "pronostico", "en"})
        consulta_final = "clima" + ((" " + consulta.strip()) if consulta.strip() else "")
        return "buscar:https://www.google.com/search?q=" + quote_plus(consulta_final)

    verbos_busqueda = r"busca|buscame|buscar|googlea|investiga|encuentra|averigua"
    verbos_sitio = r"pon|ponme|reproduce"
    destinos = r"youtube|google|internet"

    m = re.match(rf"^(?:{verbos_sitio}|{verbos_busqueda})\s+(.+?)\s+en\s+({destinos})$", t)
    if m:
        consulta, sitio = m.groups()
        base = "https://www.youtube.com/results?search_query=" if sitio == "youtube" else "https://www.google.com/search?q="
        return "buscar:" + base + quote_plus(consulta)

    m = re.match(rf"^(?:{verbos_busqueda})\s+en\s+({destinos})\s+(.+)$", t)
    if m:
        sitio, consulta = m.groups()
        base = "https://www.youtube.com/results?search_query=" if sitio == "youtube" else "https://www.google.com/search?q="
        return "buscar:" + base + quote_plus(consulta)

    m = re.match(rf"^(?:{verbos_busqueda})\s+(.+)$", t)
    if m:
        consulta = re.sub(r"^(?:en\s+)?(?:google|internet)\s+", "", m.group(1))
        if consulta:
            return "buscar:https://www.google.com/search?q=" + quote_plus(consulta)

    # Recordatorios con texto: se programan localmente en memoria durante la sesión.
    if any(x in w for x in ("recuerdame", "recordatorio")):
        segundos = _duracion_segundos(w)
        if segundos:
            original_limpio = re.sub(r"\b(?:en\s+)?(?:\d+|[a-z]+)\s*(?:segundos?|minutos?|horas?)\b", "", texto_original, flags=re.I)
            original_limpio = re.sub(r"\b(?:jarvis|recuerdame|recuérdame|recordatorio|que|me|debo|tengo|hacer|en)\b", " ", original_limpio, flags=re.I)
            detalle = " ".join(original_limpio.split()).strip(" ,.")
            return f"reminder:{segundos}:{detalle or 'Tienes un recordatorio pendiente'}"


    # Temporizadores y avisos sencillos.
    if any(x in w for x in ("temporizador", "cronometro", "avisame", "recuerdame", "alarma")):
        if any(x in w for x in ("cancela", "cancelar", "apaga", "quita", "deten", "elimina", "borra")):
            return "timer:cancel"
        segundos = _duracion_segundos(w)
        return f"timer:{segundos}" if segundos else "decir:¿De cuánto tiempo quieres el temporizador?"

    # Gestión ampliada de Windows (acciones locales y explícitas).
    if "tareas" in w and any(x in w for x in ("abre", "abrir", "inicia", "ejecuta")):
        return "sys:taskmgr"
    if any(x in w for x in ("reinicia", "reiniciar", "reinicio")):
        return "sys:restart"
    if any(x in w for x in ("apaga", "apagar", "apagues")) and any(x in w for x in ("equipo", "computadora", "pc", "ordenador", "windows")):
        return "sys:shutdown"

    # Pestañas, ventanas y funciones del sistema.
    cerrar = {"cierra", "cerrar", "cierre", "cierras"}
    abrir = {
        "abre", "abres", "abras", "abrir", "abreme", "abrime", "ejecuta",
        "ejecutar", "inicia", "iniciar", "lanza", "lanzar", "arranca",
        "enciende", "pon", "ponme", "reproduce", "habre", "habrir",
        "habreme", "abrime",
    }
    if "pestana" in w or "pestanas" in w:
        if any(x in w for x in cerrar):
            return "key:closetab"
        if "nueva" in w or any(x in w for x in abrir):
            return "key:newtab"
    if any(x in w for x in ("ventana", "ventanas")) and any(
        x in w for x in ("cambia", "cambiar", "alterna", "siguiente", "otra")
    ):
        return "key:switch"
    if any(x in w for x in ("actualiza", "actualizar", "recarga", "recargar", "refresca", "refrescar")):
        return "key:refresh"
    if "pantalla completa" in t:
        return "key:fullscreen"
    if t in {"atras", "volver atras", "pagina anterior"}:
        return "key:back"
    if t in {"adelante", "ir adelante", "pagina siguiente"}:
        return "key:forward"
    if any(x in w for x in ("minimiza", "minimizar")) and any(x in w for x in ("ventana", "ventanas", "actual")):
        return "win:minimize"
    if any(x in w for x in ("escritorio", "minimiza", "minimizar", "captura", "pantallazo", "screenshot")):
        if "escritorio" in w:
            return "key:desktop"
        if "captura" in w or "pantallazo" in w or "screenshot" in w:
            return "key:screenshot"
        return "key:minimize"
    if any(x in w for x in ("bloquea", "bloquear", "bloqueame")):
        return "sys:lock"

    if any(x in w for x in ("maximiza", "maximizar")):
        return "win:maximize"
    if any(x in w for x in ("restaura", "restaurar")) and any(x in w for x in ("ventana", "ventanas")):
        return "win:restore"
    if any(x in w for x in ("minimiza", "minimizar")) and any(x in w for x in ("ventana", "ventanas", "actual")):
        return "win:minimize"
    if any(x in w for x in ("cierra", "cerrar")) and any(x in w for x in ("ventana", "ventana actual", "esta ventana")):
        return "win:close"
    if any(x in w for x in ("cambia", "cambiar", "alterna", "alternar")) and any(x in w for x in ("ventana", "ventanas")):
        return "win:switch"


    # Abrir/cerrar apps; acepta "abre el Chrome", "me puedes abrir Chrome", etc.
    if w[0] in abrir:
        app = _buscar_app(" ".join(w[1:]), apps)
        if app:
            return "musica:play" if app == "spotify" else "open:" + app
    if w[0] in cerrar:
        app = _buscar_app(" ".join(w[1:]), apps)
        cerrables = CERRABLES
        return "close:" + app if app in cerrables else None
    if len(w) <= 4:
        app = _buscar_app(t, apps)
        if app:
            return "musica:play" if app == "spotify" else "open:" + app

    # Respuestas breves.
    if "hora" in w and ("que" in w or "dime" in w or len(w) <= 4):
        return "decir:" + _hora_texto()
    if ("dia" in w and ("hoy" in w or "es" in w)) or "fecha" in w:
        return "decir:" + _fecha_texto()
    if "chiste" in w:
        return "decir:" + random.choice(CHISTES)
    if "gracias" in w:
        return f"decir:De nada, {nombre}."
    if w[0] in ("hola", "buenas", "buenos") and len(w) <= 3:
        return f"decir:Hola {nombre}, ¿en qué puedo ayudarte?"
    if "como" in w and "estas" in w:
        return "decir:Todos mis sistemas funcionan perfectamente."
    if ("quien" in w and "eres" in w) or ("como" in w and "llamas" in w):
        return "decir:Soy Jarvis, tu asistente personal."
    if "ayuda" in w or ("que" in w and "puedes" in w):
        return (
            "decir:Puedes hablar con frases normales: abrir o cerrar aplicaciones, "
            "poner o pausar música, cambiar canciones, ajustar el volumen, buscar "
            "en Google o YouTube, escribir texto, usar el ratón y el teclado, "
            "usar temporizadores y preguntar la hora o la fecha."
        )

    # Música y volumen.
    relativos = {
        "la", "el", "lo", "las", "los", "musica", "cancion", "canciones",
        "tema", "pista", "esto", "por", "favor", "todo", "de", "con", "que",
        "esta", "suena", "sonando", "reproduccion", "reproduciendo",
        "spotify", "sonido", "un", "una", "algo", "otra", "vez", "poco",
        "poquito", "alguna", "mas", "menos", "ahora", "ya", "porfa", "porfis",
    }
    if any(x in t for x in ("silencia", "mutea", "mute", "sin sonido", "quita el sonido", "quita el volumen")):
        return "mute"

    pausa = {
        "pausa", "pausar", "pausala", "pausalo", "deten", "detener", "detenla",
        "detenlo", "para", "parar", "stop", "calla", "callate", "silencio", "suspende",
        "suspender",
    }
    if (w[0] in pausa and all(x in relativos for x in w[1:])) or any(
        t.startswith(prefijo) for prefijo in (
            "deja de reproducir", "deja de poner", "deja de escuchar", "para de reproducir"
        )
    ):
        return "pausa"

    poner_musica = {
        "pon", "ponme", "ponle", "reproduce", "reproducir", "toca", "continua",
        "continuar", "sigue", "reanuda", "reanudar", "play", "dale", "escucha",
        "escuchar", "inicia", "iniciar", "comienza", "empieza", "arranca",
    }
    if w[0] in poner_musica and all(x in relativos for x in w[1:]):
        return "musica:play"

    avanzar = {"siguiente", "salta", "saltar", "pasa", "omite", "adelante", "cambia", "cambiar"}
    retroceder = {"anterior", "atras", "retrocede", "regresa", "vuelve", "previa", "previo"}
    objetos_musica = {"cancion", "canciones", "tema", "pista", "musica"}
    if not any(x in w for x in retroceder) and (
        any(x in w for x in avanzar) or ("otra" in w and any(x in w for x in objetos_musica))
    ):
        if (
            any(x in w for x in objetos_musica) or len(w) <= 3
        ) and all(x in relativos | avanzar | retroceder | poner_musica | {"a", "de", "que", "es"} for x in w):
            return "next"
    if any(x in w for x in retroceder) and (
        any(x in w for x in objetos_musica) or len(w) <= 4
    ) and all(x in relativos | retroceder | avanzar | {"a", "de", "que", "es"} for x in w):
        return "prev"

    subir = {"sube", "subir", "aumenta", "aumentar", "alto", "altos", "mas"}
    bajar = {"baja", "bajar", "disminuye", "reduce", "bajo", "bajos", "menos", "mas"}
    objetos_volumen = {"volumen", "musica", "sonido", "audio"}
    permitidas_volumen = relativos | subir | bajar | objetos_volumen | {"el", "la", "un", "una", "poco", "poquito"}
    if any(x in w for x in subir) and (
        any(x in w for x in objetos_volumen) or any(x in w for x in ("alto", "altos"))
    ) and all(x in permitidas_volumen for x in w):
        return "vol+"
    if any(x in w for x in bajar) and (
        any(x in w for x in objetos_volumen) or any(x in w for x in ("bajo", "bajos"))
    ) and all(x in permitidas_volumen for x in w):
        return "vol-"

    # Abrir rutas locales: "abre la carpeta C:\\..." o "abre el archivo ..."
    ruta_match = re.search(r"((?:[a-z]:\\|\\\\)[^<>|?*]+)", texto_original, re.I)
    if ruta_match and any(x in w for x in ("abre", "abrir", "carpeta", "archivo")):
        ruta = ruta_match.group(1).strip().strip('"')
        return "path:" + ruta[:500]

    # Consultas locales de sistema.
    if ("bateria" in w or "memoria" in w or "procesador" in w or "sistema" in w) and any(x in w for x in ("estado", "informacion", "uso", "como", "dime", "consulta")):
        return "sys:info"

    return None
