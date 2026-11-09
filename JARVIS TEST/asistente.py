import asyncio, csv, hashlib, io, json, os, random, re, socket, subprocess, sys, threading, time, warnings, webbrowser, ctypes, platform
import numpy as np
import sounddevice as sd
import webview
from command_parser import interpretar_orden, es_solo_activacion, registrar_alias, normalizar, _buscar_app
import acciones_pc as pc

warnings.filterwarnings("ignore")
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ.get("APPDATA", BASE), "AsistenteAplausos")
os.makedirs(DATA, exist_ok=True)
DEFAULTS = {
    "frase": "Hola Brayden, bienvenido a casa", "voz": "es-MX-JorgeNeural", "velocidad": "+0%", "tono": "+0Hz",
    "robot": False, "reproductor": "winsound", "cancion_url": "https://open.spotify.com/track/2zYzyRzz6pRmhPzyfMEC8s",
    "factor": 4, "umbral_min": 0.04, "iniciar_minimizado": False, "microfono": None,
    "palabra": "hey jarvis", "musica_segundos": 30, "saludar": False, "mantener_spotify": False, "sonidos": True, "volumen_voz": 0.008, "ganancia_mic": 6, "conf_min": 0.35, "comando_espera": 4, "comandos_es": True, "pausar_audio_al_escuchar": True,
    "nombre": "Brayden", "silencio_previo": 1.5, "silencio_final": 1.0,
}
try:
    CFG = {**DEFAULTS, **json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))}
except Exception:
    CFG = dict(DEFAULTS)
NOWIN = 0x08000000

def _matar_viejo():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-NetTCPConnection -LocalPort 47653 -ErrorAction SilentlyContinue | "
                    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"],
                   stdin=subprocess.DEVNULL, capture_output=True, creationflags=NOWIN)


_lock = socket.socket()
for _i in range(0 if "--diag" in sys.argv else 2):
    try:
        _lock.bind(("127.0.0.1", 47653))
        break
    except OSError:
        if _i:
            sys.exit(0)
        _matar_viejo()
        time.sleep(1.5)
        _lock = socket.socket()

voz_activa = False   # mientras habla: se libera CPU para que el audio no tartamudee
bloqueado = False
estado = "escuchando"
SALIR = False
ventana = None
listo = False
spec_mic = np.zeros(48, dtype=np.float32)
spec_loop = np.zeros(48, dtype=np.float32)
t_loop = 0.0
nivel = 0.0
umbral_act = 0.05
ultimo_sonido = time.time()
mic_name = ""
mic_enviado = False
mutex = threading.Lock()


# ---------- análisis de espectro ----------
def bandas(x, n=48):
    if len(x) < 256:
        return np.zeros(n, dtype=np.float32)
    m = np.abs(np.fft.rfft(x * np.hanning(len(x)))) / (len(x) / 4)
    edges = np.unique(np.geomspace(2, len(m) * 0.55, n + 1).astype(int))
    out = np.zeros(n, dtype=np.float32)
    for i in range(min(n, len(edges) - 1)):
        out[i] = m[edges[i]:max(edges[i] + 1, edges[i + 1])].mean()
    db = 20 * np.log10(out + 1e-9)
    return np.clip((db + 70) / 60, 0, 1).astype(np.float32)


def loopback():
    """Audio del sistema (lo que suena en bocinas/audífonos)."""
    global spec_loop, t_loop
    try:
        import soundcard as sc
        sp = sc.default_speaker()
        mic = sc.get_microphone(id=str(sp.name), include_loopback=True)
        with mic.recorder(samplerate=44100, channels=2, blocksize=2048) as rec:
            while not SALIR:
                d = rec.record(numframes=1024)
                if voz_activa:
                    t_loop = time.time()
                    continue
                spec_loop = bandas(d.mean(axis=1).astype(np.float32))
                t_loop = time.time()
    except Exception as e:
        log(f"loopback (audio del sistema) fallo: {e}")


# ---------- palabra de activación (offline, Vosk) ----------
import queue, urllib.request, zipfile

MODELO_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODELO_DIR = os.path.join(DATA, "vosk-model-small-en-us-0.15")
mic_dev = None
cola_voz = queue.Queue(maxsize=200)


MODELO_ES_URL = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
MODELO_ES_DIR = os.path.join(DATA, "vosk-model-small-es-0.42")
MODELO_ES = None


def _bajar(url, carpeta):
    if os.path.isdir(carpeta):
        return True
    try:
        log("descargando modelo de voz: " + os.path.basename(carpeta))
        z = os.path.join(DATA, "modelo.zip")
        urllib.request.urlretrieve(url, z)
        zipfile.ZipFile(z).extractall(DATA)
        os.remove(z)
        return os.path.isdir(carpeta)
    except Exception as e:
        log(f"modelo fallo: {e}")
        return False


def asegurar_modelo():
    return _bajar(MODELO_URL, MODELO_DIR)


def cargar_es(vosk):
    """Modelo en español para las órdenes (se descarga una sola vez, ~40 MB)."""
    global MODELO_ES
    if not CFG.get("comandos_es", True):
        return
    if _bajar(MODELO_ES_URL, MODELO_ES_DIR):
        try:
            MODELO_ES = vosk.Model(MODELO_ES_DIR)
            log("modelo español listo")
        except Exception as e:
            log(f"modelo español fallo: {e}")


def oir(msg):
    if "--diag" in sys.argv:
        print("   [HUD]", msg)
    try:
        if listo:
            ventana.evaluate_js("window.setOye(%s)" % json.dumps(str(msg)[:38]))
    except Exception:
        pass


def cb_voz(indata, frames, t, status):
    try:
        cola_voz.put_nowait(bytes(indata))
    except queue.Full:
        pass


VK = {"play": 0xB3, "next": 0xB0, "prev": 0xB1, "volup": 0xAF, "voldown": 0xAE, "mute": 0xAD}
sp_play = False       # estimación: ¿Spotify está sonando por orden nuestra?
cancelar_auto = False  # un comando de voz cancela la pausa automática
ACCIONES = {
    "pause": "pausa", "paws": "pausa", "stop": "pausa", "silence": "pausa",
    "play": "play", "resume": "play", "continue": "play",
    "next": "next", "skip": "next", "forward": "next",
    "previous": "prev", "back": "prev", "before": "prev",
    "up": "vol+", "louder": "vol+", "increase": "vol+",
    "down": "vol-", "lower": "vol-", "softer": "vol-", "decrease": "vol-",
    "mute": "mute",
}


def tecla(vk, n=1):
    u = ctypes.windll.user32
    for _ in range(n):
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, 2, 0)
        time.sleep(0.12)


# ---------- comandos extra: apps, navegadores, web, ventanas, sistema ----------
APPS = {  # palabra -> destino (exe/URI de Windows, o URL)
    "chrome": "chrome", "firefox": "firefox", "edge": "msedge", "brave": "brave", "opera": "opera",
    "browser": "https://www.google.com", "internet": "https://www.google.com",
    "spotify": "spotify:", "whatsapp": "whatsapp:", "discord": "discord:", "telegram": "tg:", "steam": "steam:",
    "notepad": "notepad", "calculator": "calc", "explorer": "explorer", "files": "explorer",
    "settings": "ms-settings:", "terminal": "cmd", "console": "cmd", "code": "code", "paint": "mspaint",
    "word": "winword", "excel": "excel", "camera": "microsoft.windows.camera:", "maps": "https://maps.google.com",
    "youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com",
    "netflix": "https://www.netflix.com", "github": "https://github.com",
    "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com",
}
APPS.update({str(k).lower(): v for k, v in (CFG.get("apps_extra") or {}).items()})  # tus propias apps en config.json

def detectar_apps_inicio():
    """Registra accesos directos del menú Inicio para poder abrir aplicaciones instaladas."""
    if os.name != "nt":
        return
    roots = [
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for carpeta, dirs, archivos in os.walk(root):
            profundidad = carpeta[len(root):].count(os.sep)
            if profundidad >= 4:
                dirs[:] = []
            for archivo in archivos:
                if not archivo.lower().endswith(".lnk"):
                    continue
                nombre = os.path.splitext(archivo)[0].strip().lower()
                clave = re.sub(r"[^a-z0-9áéíóúñ _-]", "", nombre).strip()
                if len(clave) >= 2 and clave not in APPS and clave not in {"uninstall", "readme"}:
                    APPS[clave] = os.path.join(carpeta, archivo)


APPS.update({  # equivalencias de Windows y sitios web (las apps instaladas se detectan solas)
    "powershell": "powershell", "wt": "wt", "control": "control", "devmgmt": "devmgmt.msc",
    "diskmgmt": "diskmgmt.msc", "services": "services.msc", "eventvwr": "eventvwr.msc",
    "resmon": "resmon", "msinfo": "msinfo32", "cleanmgr": "cleanmgr", "regedit": "regedit",
    "snip": "ms-screenclip:", "clock": "ms-clock:", "calendar": "outlookcal:", "store": "ms-windows-store:",
    "photos": "ms-photos:", "xbox": "xbox:", "onenote": "onenote:", "teams": "msteams:",
    "recorder": "shell:AppsFolder\\Microsoft.WindowsSoundRecorder_8wekyb3d8bbwe!App",
    "wordpad": "write", "outlook": "outlook", "powerpoint": "powerpnt",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "twitter": "https://x.com",
    "tiktok": "https://www.tiktok.com", "linkedin": "https://www.linkedin.com", "reddit": "https://www.reddit.com",
    "twitch": "https://www.twitch.tv", "whatsappweb": "https://web.whatsapp.com", "drive": "https://drive.google.com",
    "docs": "https://docs.google.com", "translate": "https://translate.google.com", "wikipedia": "https://es.wikipedia.org",
    "amazon": "https://www.amazon.com", "mercadolibre": "https://www.mercadolibre.com", "disney": "https://www.disneyplus.com",
    "prime": "https://www.primevideo.com", "max": "https://www.max.com",
})
APPS.update({str(k).lower(): v for k, v in (CFG.get("apps_extra") or {}).items()})
registrar_alias(CFG.get("alias_apps") or {})  # tus equivalencias aprendidas ("aprende que X es Y")


def completar_apps():
    """Apps sin destino fijo (zoom, slack, vlc, obs): se enlazan al acceso directo instalado que las contenga."""
    for clave in ("zoom", "slack", "vlc", "obs"):
        if clave in APPS:
            continue
        for k, v in list(APPS.items()):
            if k.startswith(clave) or (" " + clave) in (" " + k):
                APPS[clave] = v
                break


detectar_apps_inicio()
completar_apps()
CERRAR = {  # palabra -> proceso(s) que se cierran con "jarvis close X"
    "chrome": ["chrome.exe"], "firefox": ["firefox.exe"], "edge": ["msedge.exe"], "brave": ["brave.exe"],
    "opera": ["opera.exe"], "notepad": ["notepad.exe"], "calculator": ["CalculatorApp.exe", "calc.exe"],
    "code": ["Code.exe"], "word": ["WINWORD.EXE"], "excel": ["EXCEL.EXE"], "discord": ["Discord.exe"],
    "steam": ["steam.exe"], "telegram": ["Telegram.exe"], "whatsapp": ["WhatsApp.exe", "WhatsApp.Root.exe"],
    "paint": ["mspaint.exe"], "powershell": ["powershell.exe"], "wordpad": ["wordpad.exe"],
    "outlook": ["OUTLOOK.EXE", "olk.exe"], "powerpoint": ["POWERPNT.EXE"], "onenote": ["ONENOTE.EXE"],
    "teams": ["ms-teams.exe", "Teams.exe"], "zoom": ["Zoom.exe"], "slack": ["slack.exe"],
    "vlc": ["vlc.exe"], "obs": ["obs64.exe", "obs32.exe"], "spotify": ["Spotify.exe"],
}
ABRIR_V = {"open", "launch", "start", "run"}
FRASES = {  # frases cortas -> acción de teclado / sistema
    ("new", "tab"): "key:newtab", ("close", "tab"): "key:closetab", ("refresh",): "key:refresh",
    ("reload",): "key:refresh", ("fullscreen",): "key:fullscreen", ("desktop",): "key:desktop",
    ("minimize",): "key:minimize", ("screenshot",): "key:screenshot", ("switch",): "key:switch",
    ("enter",): "key:enter", ("return",): "key:enter", ("escape",): "key:escape",
    ("tab",): "key:tab", ("space",): "key:space", ("backspace",): "key:backspace",
    ("delete",): "key:delete", ("copy",): "key:copy", ("paste",): "key:paste",
    ("cut",): "key:cut", ("undo",): "key:undo", ("redo",): "key:redo",
    ("save",): "key:save", ("select", "all"): "key:selectall",
    ("click",): "mouse:click", ("right", "click"): "mouse:right",
    ("double", "click"): "mouse:double", ("scroll", "up"): "mouse:scroll_up",
    ("scroll", "down"): "mouse:scroll_down", ("back",): "key:back",
    ("forward",): "key:forward",
    ("lock",): "sys:lock",
}
PALABRAS_EXTRA = (
    {w for f in FRASES for w in f} | set(APPS) | ABRIR_V |
    {"close", "write", "type", "click", "right", "double", "press", "enter",
     "return", "escape", "tab", "space", "copy", "paste", "cut", "undo",
     "redo", "save", "select", "all", "scroll", "up", "down"}
)


def parse_extra(rest):
    """rest: palabras tras 'jarvis'. Devuelve 'open:X' | 'close:X' | 'key:X' | 'sys:X' | None."""
    if not rest:
        return None
    if tuple(rest[:2]) in FRASES:
        return FRASES[tuple(rest[:2])]
    if tuple(rest[:1]) in FRASES and len(rest) == 1:
        return FRASES[tuple(rest[:1])]
    if rest[0] in ABRIR_V and len(rest) > 1 and rest[1] in APPS:
        return "open:" + rest[1]
    if rest[0] == "close" and len(rest) > 1 and rest[1] in CERRAR:
        return "close:" + rest[1]
    if len(rest) == 2 and rest[0] in {"press", "hit"} and rest[1] in {
        "enter", "return", "escape", "tab", "space", "backspace", "delete",
    }:
        return "key:" + ("enter" if rest[1] == "return" else rest[1])
    if len(rest) == 1 and rest[0] in APPS and rest[0] != "spotify":
        return "open:" + rest[0]
    return None


def combo(*vks):
    u = ctypes.windll.user32
    for v in vks:
        u.keybd_event(v, 0, 0, 0)
    for v in reversed(vks):
        u.keybd_event(v, 0, 2, 0)
    time.sleep(0.1)


TECLAS = {  # 0x11 Ctrl, 0x10 Shift, 0x5B Win, 0x12 Alt
    "newtab": (0x11, 0x54), "closetab": (0x11, 0x57), "refresh": (0x74,), "fullscreen": (0x7A,),
    "desktop": (0x5B, 0x44), "minimize": (0x5B, 0x4D), "screenshot": (0x5B, 0x10, 0x53), "switch": (0x12, 0x09),
    "enter": (0x0D,), "escape": (0x1B,), "tab": (0x09,), "space": (0x20,),
    "backspace": (0x08,), "delete": (0x2E,), "home": (0x24,), "end": (0x23,),
    "up": (0x26,), "down": (0x28,), "left": (0x25,), "right": (0x27,),
    "copy": (0x11, 0x43), "paste": (0x11, 0x56), "cut": (0x11, 0x58),
    "undo": (0x11, 0x5A), "redo": (0x11, 0x59), "save": (0x11, 0x53),
    "selectall": (0x11, 0x41), "back": (0x12, 0x25), "forward": (0x12, 0x27),
}


def enviar_texto(texto):
    """Escribe texto Unicode en la ventana activa, sin usar el portapapeles."""
    if os.name != "nt":
        raise RuntimeError("La escritura por voz requiere Windows.")
    user32 = ctypes.windll.user32
    unidades = texto[:500].encode("utf-16-le")
    ulong_ptr = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
            ("dwExtraInfo", ulong_ptr),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long), ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong), ("dwExtraInfo", ulong_ptr),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("union", INPUTUNION)]

    events = []
    for i in range(0, len(unidades), 2):
        code = unidades[i] | (unidades[i + 1] << 8)
        for flags in (0x0004, 0x0006):  # KEYEVENTF_UNICODE, luego KEYUP
            event = INPUT()
            event.type = 1  # INPUT_KEYBOARD
            event.union.ki = KEYBDINPUT(0, code, flags, 0, 0)
            events.append(event)
    if events:
        batch = (INPUT * len(events))(*events)
        send_input = user32.SendInput
        send_input.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        send_input.restype = ctypes.c_uint
        send_input(len(events), batch, ctypes.sizeof(INPUT))


def ejecutar_mouse(accion, argumentos):
    if os.name != "nt":
        raise RuntimeError("El control del ratón por voz requiere Windows.")
    user32 = ctypes.windll.user32
    ancho, alto = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    if accion == "center":
        user32.SetCursorPos(ancho // 2, alto // 2)
    elif accion == "at":
        x, y = (int(v) for v in argumentos[:2])
        user32.SetCursorPos(max(0, min(x, ancho - 1)), max(0, min(y, alto - 1)))
    elif accion == "move":
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        p = POINT()
        user32.GetCursorPos(ctypes.byref(p))
        dx, dy = (int(v) for v in argumentos[:2])
        user32.SetCursorPos(
            max(0, min(p.x + dx, ancho - 1)),
            max(0, min(p.y + dy, alto - 1)),
        )
    elif accion in {"click", "right", "double"}:
        down, up = (0x0002, 0x0004) if accion != "right" else (0x0008, 0x0010)
        veces = 2 if accion == "double" else 1
        for i in range(veces):
            user32.mouse_event(down, 0, 0, 0, 0)
            user32.mouse_event(up, 0, 0, 0, 0)
            if i + 1 < veces:
                time.sleep(0.12)
    elif accion in {"scroll_up", "scroll_down"}:
        delta = 480 if accion == "scroll_up" else -480
        user32.mouse_event(0x0800, 0, 0, ctypes.c_uint32(delta).value, 0)


def guardar_alias(frase, clave):
    ruta = os.path.join(BASE, "config.json")
    try:
        datos = json.load(open(ruta, encoding="utf-8"))
    except Exception:
        datos = {}
    datos.setdefault("alias_apps", {})[frase] = clave
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def ejecutar_extra(acc):
    tipo, _, nom = acc.partition(":")
    if tipo in ("file", "clean", "proc") or (tipo == "sys" and nom in pc.SYS_PC):
        chat, voz = pc.ejecutar(acc, CERRAR, APPS)
        ui_chat("assistant", chat)
        decir(voz)
        return
    if tipo == "alias":
        frase, _, destino = nom.partition("|")
        clave = _buscar_app(normalizar(destino), APPS)
        if len(normalizar(frase)) < 3 or not clave:
            msg = "No conozco la aplicación «%s»; no pude crear la equivalencia." % destino
        else:
            registrar_alias({frase: clave})
            try:
                guardar_alias(normalizar(frase), clave)
            except Exception as e:
                log("alias no guardado: %s" % e)
            msg = "Entendido: cuando digas «%s» abriré %s." % (frase, clave)
        ui_chat("assistant", msg)
        decir(msg)
        return
    if tipo == "open":
        d = APPS[nom]
        if d.startswith("http"):
            webbrowser.open(d)
        elif d.endswith(":"):
            os.startfile(d)
        elif d.lower().endswith(".lnk") and os.path.exists(d):
            os.startfile(d)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", d], stdin=subprocess.DEVNULL, creationflags=NOWIN)
    elif tipo == "close":
        for exe in CERRAR[nom]:
            subprocess.run(["taskkill", "/IM", exe], stdin=subprocess.DEVNULL, capture_output=True, creationflags=NOWIN)
    elif tipo == "key":
        combo(*TECLAS[nom])
    elif tipo == "type":
        enviar_texto(nom)
    elif tipo == "mouse":
        partes = nom.split(":")
        ejecutar_mouse(partes[0], partes[1:])
    elif tipo == "sys" and nom == "lock":
        ctypes.windll.user32.LockWorkStation()
    elif tipo == "sys" and nom == "taskmgr":
        subprocess.Popen(["taskmgr.exe"], creationflags=NOWIN)
    elif tipo == "sys" and nom == "info":
        try:
            import psutil
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.3)
            decir(f"El procesador está usando {cpu:.0f} por ciento. La memoria RAM está usando {mem.percent:.0f} por ciento.")
        except Exception:
            decir(f"Estás usando {platform.system()} {platform.release()}.")
    elif tipo == "sys" and nom in {"shutdown", "restart"}:
        args = [ "shutdown", "/s" if nom == "shutdown" else "/r", "/t", "0" ]
        subprocess.Popen(args, creationflags=NOWIN)
    elif tipo == "win":
        acciones = {
            "minimize": (0x5B, 0x4D), "maximize": (0x5B, 0x26),
            "restore": (0x5B, 0x27), "switch": (0x12, 0x09),
            "close": (0x12, 0x73),
        }
        if nom in acciones:
            combo(*acciones[nom])
    elif tipo == "path":
        ruta = os.path.expandvars(nom)
        if os.path.exists(ruta):
            os.startfile(ruta)
        else:
            decir("No encuentro esa ruta en este equipo.")
    elif tipo == "reminder":
        partes = nom.split(":", 1)
        segundos = max(1, int(partes[0]))
        detalle = partes[1] if len(partes) > 1 else "Tienes un recordatorio pendiente"
        ev = threading.Event()
        recordatorios.append(ev)
        def avisar():
            if not ev.wait(segundos):
                decir(detalle)
            if ev in recordatorios:
                recordatorios.remove(ev)
        threading.Thread(target=avisar, daemon=True).start()
        decir(f"Recordatorio programado para dentro de {dur_txt(segundos)}.")
    elif tipo == "buscar":
        webbrowser.open(nom)
    elif tipo == "decir":
        decir(nom)
    elif tipo == "musica":
        poner_musica()
    elif tipo == "timer":
        if nom == "cancel":
            for ev in list(timers) + list(recordatorios):
                ev.set()
            timers.clear()
            recordatorios.clear()
            decir("Listo, temporizadores y recordatorios cancelados.")
        else:
            poner_timer(int(nom))


APPCMD = {"play": 14, "next": 11, "prev": 12, "play!": 46, "pause!": 47}  # 14 alterna; 46/47 explícitos


def enviar_cmd(nombre):
    """Orden directa a la ventana de Spotify (aunque esté oculta); sin ventana, tecla multimedia."""
    h = spotify_hwnd()
    if h:
        ctypes.windll.user32.SendMessageW(h, 0x319, h, APPCMD[nombre] << 16)
        return True
    tecla(VK[nombre.rstrip("!").replace("pause", "play")])
    return False


def audio_vivo():
    return time.time() - t_loop < 1.0  # la captura del audio del sistema funciona


def audio_sonando():
    return float(np.mean(spec_loop)) > 0.08


def esta_sonando():
    return audio_sonando() if audio_vivo() else sp_play


def poner(deseado):
    """Deja Spotify sonando (True) o en pausa (False), verificando con el audio real del sistema."""
    if not audio_vivo():  # sin medición: órdenes explícitas (no alternan)
        enviar_cmd("play!" if deseado else "pause!")
        return
    for i in range(3):
        time.sleep(0.4)
        if audio_sonando() == deseado:
            return
        if i == 0:
            enviar_cmd("play!" if deseado else "pause!")
        elif i == 1:
            enviar_cmd("play")  # alterna
        else:
            tecla(VK["play"])
        time.sleep(2.0)


def titulos_visibles():
    return tuple(t for t in titulos_spotify() if t not in BASURA and "IME" not in t)


def media(nombre, n=1, verificar=True):
    for _ in range(n):
        antes = titulos_visibles()
        enviar_cmd(nombre)
        if verificar and any(" - " in t for t in antes):
            time.sleep(2.0)
            if titulos_visibles() == antes:
                tecla(VK[nombre])
        time.sleep(0.3)


cmd_hasta = 0.0
silencio_hasta = 0.0


def sonido(tipo):
    """Tono corto para distinguir que ya escucha o va a ejecutar."""
    if not CFG.get("sonidos", True):
        return
    try:
        import winsound
        tonos = {
            "escucha": ((760, 75), (1040, 95)),
            "ejecutar": ((1180, 65), (1480, 85)),
        }
        for hz, ms in tonos.get(tipo, ((900, 80),)):
            winsound.Beep(hz, ms)
            time.sleep(0.035)
    except Exception:
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass


def comando(acc):
    try:
        _comando_impl(acc)
    finally:
        restaurar_audio_orden(acc)


def _comando_impl(acc):
    global sp_play, cancelar_auto, cmd_hasta
    cancelar_auto = True
    cmd_hasta = time.time() + 15
    sonido("ejecutar")
    if ":" in acc:
        oir("CMD: " + acc.upper())
        try:
            ejecutar_extra(acc)
            log("comando extra: " + acc)
        except Exception as e:
            log(f"comando extra fallo {acc}: {e}")
        return
    if acc == "vol+":
        tecla(VK["volup"], 5)
        return
    if acc == "vol-":
        tecla(VK["voldown"], 5)
        return
    if acc == "mute":
        tecla(VK["mute"])
        return
    if not spotify_abierto():
        if acc == "pausa":
            if not audio_pausado_espera:
                tecla(VK["play"])
            sp_play = False
        elif acc == "play":
            tecla(VK["play"])
            sp_play = True
        elif acc == "next":
            tecla(VK["next"])
            sp_play = True
        elif acc == "prev":
            tecla(VK["prev"], 2)
            sp_play = True
        return
    if acc == "pausa":
        poner(False)
        sp_play = False
    elif acc == "play":
        poner(True)
        sp_play = True
    elif acc == "next":
        media("next")
        sp_play = True
    elif acc == "prev":
        media("prev", 2, verificar=False)  # 2 pulsaciones = pista anterior
        sp_play = True
    elif acc == "vol+":
        tecla(VK["volup"], 5)
    elif acc == "vol-":
        tecla(VK["voldown"], 5)
    elif acc == "mute":
        tecla(VK["mute"])
    log("comando: " + acc)


RELLENO = {"hey", "hi", "hola", "buenas", "buenos", "dias", "tardes", "noches", "ok", "okay", "a", "oye"}
SENUELOS = {"travis", "jervis", "garvis", "gervais", "harvest", "harvey", "service", "davis", "nervous", "carvers",
            "jarvik", "jarvie", "jarvic", "starve", "marvis", "gravis", "jarred", "javier", "jargon", "jars"}
WAKE = {"jarvis", "jervis", "garvis", "harvis", "marvis", "darvis", "tarvis", "jarvas", "jarves", "jarvik", "jarvie", "jarvic", "jarvin"}
GRAMATICA = []


def variantes_jarvis():
    """Todas las palabras a UNA letra de distancia de 'jarvis' (cambiar, quitar o añadir una letra)."""
    base, letras = "jarvis", "abcdefghijklmnopqrstuvwxyz"
    v = {base}
    for i in range(len(base) + 1):
        v |= {base[:i] + c + base[i:] for c in letras}
    for i in range(len(base)):
        v.add(base[:i] + base[i + 1:])
        v |= {base[:i] + c + base[i + 1:] for c in letras}
    return v


def preparar_wake():
    """Acepta como 'jarvis' las variantes de una letra que existan en el vocabulario del modelo."""
    global WAKE, GRAMATICA
    try:
        with open(os.path.join(MODELO_DIR, "graph", "words.txt"), encoding="utf-8", errors="ignore") as f:
            vocab = {ln.split()[0] for ln in f if ln.strip()}
        WAKE = {"jarvis"} | (variantes_jarvis() & vocab) | (WAKE & vocab)
    except Exception as e:
        log(f"vocabulario no leído, uso lista fija: {e}")
    GRAMATICA = sorted(WAKE | {"hey", "hi", "hola", "buenas", "buenos", "dias", "tardes", "noches", "hello", "[unk]"} | set(ACCIONES) | PALABRAS_EXTRA | (SENUELOS - WAKE))
    log("equivalentes de jarvis: " + ", ".join(sorted(WAKE)))


def interpretar(r, abierta):
    """'jarvis' [orden], o un comando suelto si la ventana de comandos está abierta.
    Devuelve (activa, accion, suelto, duracion_palabra, fin_jarvis_si_hay_habla_despues)."""
    toks = r.get("text", "").split()
    res = r.get("result", [])
    NO = (False, None, False, 0, None)

    def dur(i):
        return (res[i]["end"] - res[i]["start"]) if i < len(res) else 0
    for i, w in enumerate(toks):
        if w in WAKE:
            if [x for x in toks[:i] if x not in RELLENO] or any(x in SENUELOS and x not in WAKE for x in toks):
                return NO  # nada antes de "jarvis" y sin palabras parecidas
            if i < len(res) and res[i].get("conf", 1) < float(CFG.get("conf_min", 0.5)):
                return NO
            despues = toks[i + 1:]
            rest = [x for x in despues if x != "[unk]"]
            acc = next((ACCIONES[x] for x in rest if x in ACCIONES), None) or parse_extra(rest)
            saludo = {"hola", "buenas", "buenos", "hello", "hi"}
            if not acc and any(x in saludo for x in toks):
                if all(x in RELLENO or x in WAKE or x == "[unk]" for x in toks):
                    acc = intencion(" ".join(toks))
            habla = "[unk]" in despues and not acc
            if habla and i + 1 < len(res) and res[-1]["end"] - res[i + 1]["start"] < 0.35:
                habla = False  # ruido corto tras la palabra, no una orden
            return True, acc, False, dur(i), (res[i]["end"] if habla and i < len(res) else (0.0 if habla else None))
    idx = [w for w in toks if w not in RELLENO]
    if abierta and idx and len(idx) <= 2 and all(w in ACCIONES for w in idx):
        return True, ACCIONES[idx[0]], True, dur(toks.index(idx[0])), None
    return NO


# ---------- órdenes en español (estilo Alexa) ----------
esp_hasta = 0.0   # hasta cuándo se espera una orden hablada tras "jarvis"
esp_token = 0
timers = []
recordatorios = []
confirmacion_pendiente = None
audio_pausado_espera = False
audio_orden_lock = threading.Lock()


def pausar_audio_al_escuchar():
    """Silencia música de salida durante la ventana de orden, si estaba sonando."""
    global audio_pausado_espera
    if not CFG.get("pausar_audio_al_escuchar", True):
        return
    with audio_orden_lock:
        if audio_pausado_espera:
            return
        sonando = audio_sonando() if audio_vivo() else sp_play
        if not sonando:
            return
        tecla(VK["play"])
        audio_pausado_espera = True
        log("audio pausado para escuchar la orden")


def restaurar_audio_orden(acc=None):
    """Reanuda el audio que se pausó temporalmente para oír al usuario."""
    global audio_pausado_espera, sp_play
    with audio_orden_lock:
        if not audio_pausado_espera:
            return
        audio_pausado_espera = False
    if acc in {"pausa", "mute"}:
        sp_play = False
        return
    if acc in {"play", "musica:play"}:
        sp_play = True
        return
    tecla(VK["play"])
    sp_play = True


def dur_txt(seg):
    h, m, s_ = seg // 3600, seg % 3600 // 60, seg % 60
    p = []
    if h: p.append(f"{h} hora{'s' if h > 1 else ''}")
    if m: p.append(f"{m} minuto{'s' if m > 1 else ''}")
    if s_: p.append(f"{s_} segundo{'s' if s_ > 1 else ''}")
    return " y ".join(p) or "0 segundos"


def intencion(texto):
    return interpretar_orden(texto, APPS, CFG.get("nombre", "Brayden"))


def transcribir_es(audio):
    import vosk
    rec = vosk.KaldiRecognizer(MODELO_ES, 16000)
    rec.AcceptWaveform(audio + bytes(16000))
    return json.loads(rec.FinalResult()).get("text", "")


def decir(frase):
    """Respuesta hablada (voz Edge con caché, o voz de Windows si no hay internet)."""
    global voz_activa
    voz_activa = True
    try:
        r = generar_voz(frase, guardar=False)
        if r:
            x, sr = r
            x = np.concatenate([np.zeros(int(sr * 0.6), dtype=np.float32), suavizar(x, sr)])
            if not reproducir(x, sr):
                voz_windows(frase)
        else:
            voz_windows(frase)
    except Exception as e:
        log(f"decir fallo: {e}")
    finally:
        voz_activa = False


def poner_musica():
    global sp_play
    if not filas_spotify():
        try:
            lanzar_spotify()
        except OSError:
            webbrowser.open(CFG["cancion_url"])
            return
        esperar(spotify_ventana, 30)
    if not esta_sonando():
        enviar_cmd("play!")
    sp_play = True


def poner_timer(seg):
    ev = threading.Event()
    timers.append(ev)

    def run():
        if not ev.wait(seg):
            try:
                import winsound
                for _ in range(3):
                    winsound.Beep(1200, 150)
                    time.sleep(0.1)
            except Exception:
                pass
            decir(f"{CFG.get('nombre', 'Brayden')}, tu temporizador de {dur_txt(seg)} ha terminado.")
        if ev in timers:
            timers.remove(ev)
    threading.Thread(target=run, daemon=True).start()
    decir(f"Temporizador de {dur_txt(seg)}, empezando ahora.")


def orden_es(audio, con_wake):
    """Transcribe la orden en español y la ejecuta. con_wake: el audio incluye la palabra 'jarvis'."""
    global esp_token, esp_hasta, estado
    try:
        txt = transcribir_es(audio)
        log(f"orden es='{txt}' con_wake={con_wake}")
        if not txt.strip():
            if con_wake:
                esperar_orden()
            else:
                restaurar_audio_orden()
            return
        if con_wake and es_solo_activacion(txt):
            esperar_orden()
            return
        procesar_solicitud(txt, hablar_respuesta=True)
        restaurar_audio_orden()
    except Exception as e:
        log(f"orden_es fallo: {e}")
        restaurar_audio_orden()


def esperar_orden():
    """Tras 'jarvis', avisa con un tono y espera una orden; el silencio no inicia acciones."""
    global esp_token, esp_hasta, estado
    espera = float(CFG.get("comando_espera", 5))
    if MODELO_ES is None or espera <= 0:
        if not bloqueado:
            estado = "escuchando"
        return
    esp_token += 1
    mi = esp_token
    esp_hasta = time.time() + espera
    if not bloqueado:
        estado = "orden"
    pausar_audio_al_escuchar()
    sonido("escucha")
    oir("DIME...")
    time.sleep(espera + 0.8)
    if esp_token == mi:        # sin orden, vuelve a esperar sin saludar ni abrir música
        esp_hasta = 0.0
        if not bloqueado:
            estado = "escuchando"
        oir("ESCUCHANDO · DI JARVIS")
        restaurar_audio_orden()
    elif not bloqueado and estado == "orden":
        estado = "escuchando"


def escuchar_palabra():
    vol_min = float(CFG.get("volumen_voz", 0.02))
    while not SALIR:
        try:
            if not asegurar_modelo():
                time.sleep(30)
                continue
            log("cargando vosk...")
            import vosk
            vosk.SetLogLevel(-1)
            preparar_wake()
            gram = vosk.KaldiRecognizer(vosk.Model(MODELO_DIR), 16000, json.dumps(GRAMATICA))
            gram.SetWords(True)
            try:  # respuesta más rápida al terminar de decir la palabra
                gram.SetEndpointerMode(vosk.EndpointerMode.SHORT)
            except Exception:
                pass
            threading.Thread(target=cargar_es, args=(vosk,), daemon=True).start()
            utt = []
            st = None
            for dev in (mic_dev, None):
                try:
                    st = sd.RawInputStream(device=dev, samplerate=16000, channels=1, dtype="int16",
                                           blocksize=1600, callback=cb_voz)
                    st.start()
                    break
                except Exception as e:
                    log(f"voz mic {dev} fallo: {e}")
            if st is None:
                time.sleep(10)
                continue
            log("escuchando: jarvis")
            if "--diag" in sys.argv:
                print(">>> Di 'jarvis' (o 'jarvis pause'). Ctrl+C para salir.")
            pico = 0.0
            while not SALIR:
                if esp_hasta and time.time() > esp_hasta:
                    globals()["esp_hasta"] = 0.0
                    if not bloqueado and estado == "orden":
                        globals()["estado"] = "escuchando"
                    restaurar_audio_orden()
                try:
                    d = cola_voz.get(timeout=1)
                except queue.Empty:
                    continue
                if voz_activa:
                    pico = 0.0
                    utt.clear()
                    gram.Reset()
                    continue
                a16 = np.frombuffer(d, dtype=np.int16).astype(np.float32)
                pico = max(pico, float(np.max(np.abs(a16))) / 32768.0)
                d = np.clip(a16 * float(CFG.get("ganancia_mic", 4)), -32768, 32767).astype(np.int16).tobytes()
                utt.append(d)
                if len(utt) > 150:
                    del utt[:50]
                if not gram.AcceptWaveform(d):
                    if (
                        not audio_pausado_espera
                        and CFG.get("pausar_audio_al_escuchar", True)
                        and audio_vivo()
                        and audio_sonando()
                    ):
                        try:
                            parcial = json.loads(gram.PartialResult()).get("partial", "").split()
                            if any(w in WAKE for w in parcial):
                                pausar_audio_al_escuchar()
                        except Exception:
                            pass
                    continue
                r = json.loads(gram.Result())
                audio, utt = b"".join(utt), []
                p, pico = pico, 0.0
                tg = r.get("text", "")
                en_ventana = MODELO_ES is not None and time.time() < esp_hasta + 0.6
                if not en_ventana and not tg.replace("[unk]", "").strip():
                    restaurar_audio_orden()
                    continue
                activa, acc, suelto, dur, fin = interpretar(r, time.time() < cmd_hasta)
                if en_ventana and not activa:  # no es "jarvis": es la orden hablada
                    if len(audio) > 12000:
                        threading.Thread(target=orden_es, args=(audio, False), daemon=True).start()
                    continue
                if not activa and audio_pausado_espera and not en_ventana:
                    restaurar_audio_orden()
                confs = [round(w.get("conf", 0), 2) for w in r.get("result", [])]
                log(f"oyo='{tg}' pico={p:.2f} dur={dur:.2f} conf={confs} activa={activa} cmd={acc}")
                oir("OYE: " + tg.replace("[unk]", "?"))
                if not activa:
                    continue
                if not (0.2 <= dur <= 1.6):
                    oir("IGNORADO: NO ES PALABRA")
                    log("ignorado: duración fuera de rango")
                    restaurar_audio_orden()
                    continue
                if p < vol_min:
                    oir(f"VOZ BAJA {p:.2f}<{vol_min}")
                    log(f"ignorado: voz baja {p:.2f} < {vol_min}")
                    restaurar_audio_orden()
                    continue
                if acc:
                    threading.Thread(target=comando, args=(acc,), daemon=True).start()
                elif not bloqueado and (time.time() > silencio_hasta or en_ventana):
                    if fin is not None and MODELO_ES is not None:   # "jarvis, pon música" en una sola frase
                        threading.Thread(target=orden_es, args=(audio, True), daemon=True).start()
                    else:
                        threading.Thread(target=esperar_orden, daemon=True).start()
                elif not en_ventana:
                    restaurar_audio_orden()
        except Exception as e:
            log(f"wake: {e}")
            time.sleep(5)


# ---------- voz robótica ----------
def robotizar(x, sr):
    t = np.arange(len(x)) / sr
    y = 0.62 * x + 0.38 * x * np.sin(2 * np.pi * 70 * t)
    d = int(sr * 0.012)
    out = y.copy()
    out[d:] += 0.38 * y[:-d]
    return (out / (np.max(np.abs(out)) * 1.05 + 1e-9)).astype(np.float32)


def periodo():
    h = time.localtime().tm_hour
    return "Buenos días" if 5 <= h < 12 else "Buenas tardes" if 12 <= h < 19 else "Buenas noches"


def frases():
    n, sal = CFG.get("nombre", "Brayden"), periodo()
    return [
        f"{sal}, {n}. Todos los sistemas están en línea. Bienvenido a casa.",
        f"{sal}, {n}. Te estaba esperando. Todo está listo y funcionando con normalidad. Preparando tu música.",
        f"A sus órdenes, {n}. Los sistemas están operativos y la conexión es estable. Disfruta de la música.",
        f"{sal}, señor {n}. Es un placer tenerte de vuelta. Iniciando reproducción.",
        f"Protocolo de bienvenida activado. {sal}, {n}. Todo bajo control.",
    ]


def pregenerar():
    for f in frases():
        generar_voz(f)


def generar_voz(frase, guardar=True):
    import traceback
    clave = f"v3{frase}{CFG['voz']}{CFG['velocidad']}{CFG['tono']}{CFG['robot']}"
    p = os.path.join(DATA, "v_" + hashlib.md5(clave.encode()).hexdigest()[:10] + ".npz")
    if os.path.exists(p):
        try:
            d = np.load(p)
            return d["x"], int(d["sr"])
        except Exception as e:
            log(f"cache de voz dañado, se regenera: {e}")
            try:
                os.remove(p)
            except OSError:
                pass
    try:
        import edge_tts, miniaudio
        mp3 = os.path.join(DATA, "tmp_" + os.path.basename(p)[2:-4] + ".mp3")
        asyncio.run(edge_tts.Communicate(frase, CFG["voz"], rate=CFG["velocidad"], pitch=CFG["tono"]).save(mp3))
        dec = miniaudio.decode_file(mp3, output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1, sample_rate=48000)
        x = np.array(dec.samples, dtype=np.float32)
        if CFG.get("robot", True):
            x = robotizar(x, 48000)
        if guardar:
            np.savez(p, x=x, sr=48000)
        try:
            os.remove(mp3)
        except OSError:
            pass
        return x, 48000
    except Exception:
        log("generar_voz fallo: " + traceback.format_exc())
        return None


def suavizar(x, sr):
    """Normaliza y aplica fundidos de 25 ms (evita clics que suenan a corte)."""
    x = x.astype(np.float32)
    x = x / (float(np.max(np.abs(x))) + 1e-9) * 0.9
    f = min(int(sr * 0.025), len(x) // 2)
    x[:f] *= np.linspace(0, 1, f, dtype=np.float32)
    x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    return x


def reproducir(x, sr):
    cola = np.zeros(int(sr * float(CFG.get("silencio_final", 1.0))), dtype=np.float32)
    x = np.concatenate([x, cola])
    if CFG.get("reproductor", "winsound") != "sd":  # reproducción nativa: no depende de Python mientras suena
        try:
            import wave, winsound
            y = np.repeat((np.clip(x, -1, 1) * 32767).astype(np.int16)[:, None], 2, axis=1)
            p = os.path.join(DATA, "saludo.wav")
            with wave.open(p, "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(y.tobytes())
            winsound.PlaySound(p, winsound.SND_FILENAME)
            return True
        except Exception as e:
            log(f"winsound fallo: {e}")
    try:
        sd.play(x, sr, latency="high")
        sd.wait()
        return True
    except Exception as e:
        log(f"sd.play fallo: {e}")
    return False


def voz_windows(frase):
    frase = frase.replace("'", "''")
    ps = ("Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          "try{$s.SelectVoiceByHints('NotSet','NotSet',0,[Globalization.CultureInfo]'es-ES')}catch{};"
          f"$s.Rate=-2;$s.Volume=100;$s.Speak('{frase}')")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="ignore",
                       creationflags=NOWIN)
    log(f"voz windows rc={r.returncode} {r.stderr.strip()[:300]}")
    return r.returncode == 0


def hablar():
    global voz_activa
    voz_activa = True
    try:
        _hablar()
    finally:
        voz_activa = False


def _hablar():
    frase = random.choice(frases())
    pre = float(CFG.get("silencio_previo", 1.5))
    oir("SALUDANDO...")
    r = generar_voz(frase)
    if r:
        x, sr = r
        x = suavizar(x, sr)
        x = np.concatenate([np.zeros(int(sr * pre), dtype=np.float32), x])  # silencio: deja llegar la señal a los parlantes
        log("saludo: '%s' %d muestras" % (frase, len(x)))
        if reproducir(x, sr):
            return
        oir("SALUDO: FALLO AUDIO")
    else:
        oir("SALUDO: SIN VOZ EDGE")
    log("saludo: voz windows")
    time.sleep(pre)
    if not voz_windows(frase):
        try:
            import winsound
            winsound.Beep(800, 300)
        except Exception:
            pass


# ---------- música ----------
NAV = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def abrir_musica():
    url = CFG["cancion_url"]
    nav = next((p for p in NAV if os.path.exists(p)), None)
    if nav:
        return subprocess.Popen([
            nav, "--user-data-dir=" + os.path.join(DATA, "perfil"),
            "--autoplay-policy=no-user-gesture-required",
            "--no-first-run", "--no-default-browser-check",
            "--window-size=900,600", "--app=" + url,
        ])
    os.startfile(url)
    return None


def log(msg):
    if "--diag" in sys.argv:
        print(msg)
    try:
        with open(os.path.join(DATA, "log.txt"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def abrir_mic():
    """Prueba el micrófono configurado, el predeterminado y luego todos los de entrada."""
    global mic_name
    cand = []
    if CFG.get("microfono") not in (None, ""):
        cand.append(CFG["microfono"])
    cand.append(None)
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                cand.append(i)
                log(f"dispositivo {i}: {d['name']}")
    except Exception as e:
        log(f"query_devices: {e}")
    for dev in cand:
        try:
            info = sd.query_devices(dev, "input")
            sr = int(info["default_samplerate"])
            st = sd.InputStream(device=dev, channels=1, samplerate=sr, blocksize=int(sr * 0.023), callback=det)
            st.start()
            mic_name = info["name"]
            globals()["mic_dev"] = dev
            log(f"mic en uso: {mic_name} {sr}Hz")
            return st
        except Exception as e:
            log(f"mic {dev} fallo: {e}")
    return None


# ---------- Spotify (app de escritorio) ----------
def es_spotify():
    return "open.spotify.com" in CFG["cancion_url"]


def spotify_uri():
    m = re.search(r"open\.spotify\.com/(?:intl-[a-z]+/)?(playlist|album|track|artist|show|episode)/([A-Za-z0-9]+)", CFG["cancion_url"])
    # el sufijo :play inicia la reproducción desde el principio de la lista
    return f"spotify:{m.group(1)}:{m.group(2)}:play"


def filas_spotify():
    """[(pid, título)] de cada proceso Spotify.exe ([] si está cerrado)."""
    try:
        out = subprocess.run(["tasklist", "/v", "/fi", "imagename eq Spotify.exe", "/fo", "csv", "/nh"],
                             stdin=subprocess.DEVNULL, capture_output=True, text=True,
                             creationflags=NOWIN, errors="ignore").stdout
        return [(int(row[1]), row[-1].strip()) for row in csv.reader(io.StringIO(out))
                if len(row) > 5 and row[0].lower() == "spotify.exe"]
    except Exception:
        return None  # error al consultar: estado desconocido


def titulos_spotify():
    return [t for _, t in (filas_spotify() or [])]


def spotify_hwnd():
    """Ventana principal de Spotify (aunque esté oculta en la bandeja)."""
    import ctypes.wintypes as wt
    pids = {p for p, _ in (filas_spotify() or [])}
    if not pids:
        return None
    u = ctypes.windll.user32
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(h, _):
        pid = wt.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids:
            cls = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(h, cls, 256)
            if cls.value == "Chrome_WidgetWin_0":
                found.append((u.GetWindowTextLengthW(h), h))
        return True

    u.EnumWindows(WNDENUMPROC(cb), 0)
    found.sort(reverse=True)
    return found[0][1] if found else None


def spotify_abierto():
    f = filas_spotify()
    return f is None or bool(f)  # si no se pudo consultar, se asume abierto


BASURA = ("N/D", "N/A", "", "Default IME", "MSCTFIME UI", "Chrome Legacy Window")


def spotify_ventana():
    return any(t not in BASURA and "IME" not in t for t in titulos_spotify())


def spotify_sonando():
    return any(" - " in t and t not in BASURA for t in titulos_spotify())


def spotify_activo():
    """Spotify abierto y sonando."""
    if not filas_spotify():
        return False
    if spotify_ventana():
        return spotify_sonando()
    return audio_sonando() if audio_vivo() else sp_play


def tecla_play():
    media("play")


ultimo_lanzamiento = 0.0
spotify_launch_lock = threading.Lock()


def lanzar_spotify():
    global ultimo_lanzamiento
    with spotify_launch_lock:
        ahora = time.time()
        if filas_spotify():
            return False
        if ahora - ultimo_lanzamiento < 12:
            return False
        os.startfile(spotify_uri())  # :play => pista desde el principio
        ultimo_lanzamiento = ahora
        return True


def esperar(cond, seg):
    t = time.time()
    while time.time() - t < seg and not cond():
        time.sleep(0.3)
    return cond()


def musica_spotify(t0, abierto):
    global sp_play, cancelar_auto
    cancelar_auto = False
    dur = CFG.get("musica_segundos", 30)
    poner_musica()                 # reutiliza Spotify; no vuelve a abrir la pista en bucle
    sp_play = True
    while time.time() - t0 < dur and not cancelar_auto:
        time.sleep(0.5)
    if not cancelar_auto:
        poner(False)  # pausa (no cierra Spotify)
        sp_play = False


def vigilar_spotify():
    """Mantiene Spotify abierto: si lo cierras del todo, lo vuelve a abrir."""
    if not (es_spotify() and CFG.get("mantener_spotify", True)):
        return
    fallos = 0
    while not SALIR:
        time.sleep(8)
        if time.time() - ultimo_lanzamiento < 60:
            fallos = 0
            continue
        f = filas_spotify()
        if f is None or f:
            fallos = 0
            continue
        fallos += 1
        if fallos >= 3:  # cerrado durante ~24 s seguidos
            fallos = 0
            try:
                os.startfile("spotify:")
                log("spotify reabierto")
            except OSError:
                return
            globals()["ultimo_lanzamiento"] = time.time()


def musica_navegador(t0):
    dur = CFG.get("musica_segundos", 30)
    proc = abrir_musica()
    time.sleep(max(0, dur - (time.time() - t0)))
    if proc:
        proc.terminate()


# ---------- flujo principal ----------
def saludo_seguro():
    try:
        hablar()
    except Exception as e:
        log(f"saludo fallo: {e}")


def accion():
    global bloqueado, estado
    with mutex:
        if bloqueado:
            return
        bloqueado = True
    try:
        t0 = time.time()
        log("prueba manual de música")
        sp = es_spotify()
        abierto = sp and bool(filas_spotify())
        if abierto and spotify_activo():
            oir("SPOTIFY YA ACTIVO")
            log("spotify ya activo: sin saludo ni relanzar")
            return
        estado = "reproduciendo"
        globals()["cmd_hasta"] = time.time() + CFG.get("musica_segundos", 30) + 15
        try:
            if es_spotify():
                musica_spotify(t0, abierto)
            else:
                musica_navegador(t0)
        except Exception as e:
            log(f"musica fallo: {e}")
        time.sleep(1)
    finally:
        det.reset()
        globals()["silencio_hasta"] = time.time() + 4  # ignora el eco de la propia música
        estado = "escuchando"
        bloqueado = False


class Detector:
    def __init__(self):
        self.reset()

    def reset(self):
        self.floor, self.prev, self.last, self.cool = 0.01, 0.0, 0.0, time.monotonic() + 1.5

    def __call__(self, indata, frames, t, status):
        global spec_mic, nivel, umbral_act, ultimo_sonido
        if voz_activa:
            return
        x = indata[:, 0]
        spec_mic = bandas(x)
        pico = float(np.max(np.abs(x)))
        nivel = max(nivel, pico)
        if pico > 2e-4:
            ultimo_sonido = time.time()
        now = time.monotonic()
        thr = max(self.floor * CFG["factor"], CFG["umbral_min"])
        umbral_act = thr
        if now >= self.cool and pico <= thr:
            self.floor = 0.98 * self.floor + 0.02 * pico
        self.prev = pico


det = Detector()


def empujar():
    global nivel, mic_enviado
    while not SALIR:
        time.sleep(0.2 if voz_activa else 1 / 20)
        if not listo:
            continue
        est = estado
        if est == "escuchando" and time.time() - ultimo_sonido > 6:
            est = "sinmic"
        if time.time() - t_loop < 0.5 and estado != "escuchando":
            s = np.maximum(spec_mic * 0.6, spec_loop)
        else:
            s = spec_mic
        try:
            if not mic_enviado:
                ventana.evaluate_js("window.setMic(%s)" % json.dumps(mic_name or "SIN MICROFONO"))
                mic_enviado = True
                ventana.evaluate_js("window.setExtra(%s)" % json.dumps(sorted(str(k) for k in (CFG.get("apps_extra") or {}))))
            ventana.evaluate_js("window.setSpec(%s,'%s',%.3f,%.3f)" % (
                json.dumps([round(float(v), 2) for v in s]), est, nivel, umbral_act))
        except Exception:
            pass
        nivel *= 0.8



# ---------- conversación unificada: voz + texto ----------
def ui_chat(rol, mensaje):
    """Añade un mensaje al panel de conversación sin bloquear el asistente."""
    try:
        if ventana:
            ventana.evaluate_js(
                "window.addChatMessage(%s,%s)" %
                (json.dumps(str(rol)), json.dumps(str(mensaje)[:1200]))
            )
    except Exception:
        pass


def texto_respuesta(acc):
    if acc.startswith("decir:"):
        return acc.partition(":")[2]
    if acc.startswith("open:"):
        return "Abriendo " + acc.partition(":")[2] + "."
    if acc.startswith("close:"):
        return "Cerrando " + acc.partition(":")[2] + "."
    if acc.startswith("buscar:"):
        return "Abriendo la búsqueda en tu navegador."
    if acc.startswith("musica:"):
        return "Reproduciendo música."
    if acc == "pausa":
        return "Pausando la reproducción."
    if acc == "play":
        return "Reanudando la reproducción."
    if acc == "next":
        return "Pasando a la siguiente canción."
    if acc == "prev":
        return "Volviendo a la canción anterior."
    if acc.startswith("timer:"):
        return "Temporizador actualizado."
    if acc.startswith("reminder:"):
        return "Voy a avisarte cuando llegue el momento."
    if acc.startswith("sys:lock"):
        return "Bloqueando el equipo."
    if acc.startswith("sys:taskmgr"):
        return "Abriendo el administrador de tareas."
    if acc.startswith("sys:shutdown"):
        return "Voy a apagar el equipo."
    if acc.startswith("sys:restart"):
        return "Voy a reiniciar el equipo."
    if acc.startswith("sys:info"):
        return "Consultando el estado del sistema."
    if acc.startswith("file:"):
        op = acc[5:].split("|")[0]
        return {"delete": "Enviando a la Papelera…", "purge": "Borrando definitivamente…",
                "unzip": "Descomprimiendo el archivo…", "zip": "Comprimiendo…", "copy": "Copiando…",
                "move": "Moviendo…", "rename": "Renombrando…", "mkdir": "Creando la carpeta…",
                "organize": "Ordenando los archivos por tipo…", "list": "Revisando la carpeta…",
                "find": "Buscando el archivo…", "size": "Calculando el tamaño…",
                "open": "Abriendo…"}.get(op, "Procesando el archivo…")
    if acc.startswith("clean:"):
        return "Limpiando, esto puede tardar unos segundos…"
    if acc.startswith("proc:"):
        return "Revisando los procesos…" if acc == "proc:top" else "Terminando el proceso…"
    if acc.startswith("alias:"):
        return "Creando la equivalencia…"
    if acc.startswith("sys:") and acc[4:] in pc.SYS_PC:
        return "Consultando el sistema…"
    if acc.startswith("win:"):
        return "Hecho."
    if acc.startswith("path:"):
        return "Abriendo la ubicación solicitada."
    if acc.startswith("type:"):
        return "Escribiendo el texto en la ventana activa."
    if acc.startswith("key:"):
        return "Ejecutando el atajo de teclado."
    if acc.startswith("mouse:"):
        return "Controlando el puntero."
    if acc.startswith("vol"):
        return "Ajustando el volumen."
    if acc == "mute":
        return "Alternando el sonido."
    return "Solicitud recibida."


def procesar_solicitud(texto, hablar_respuesta=False):
    """Entrada común para texto y voz; usa el mismo parser y exige confirmación en acciones críticas."""
    global confirmacion_pendiente
    limpio = str(texto).strip()
    if not limpio:
        return {"ok": False, "message": "Escribe o di una solicitud."}
    ui_chat("user", limpio)
    normal = limpio.lower().strip(" .!?¿¡")
    if confirmacion_pendiente:
        pendiente = confirmacion_pendiente
        if normal in {"si", "sí", "confirmo", "confirmar", "adelante", "hazlo"}:
            confirmacion_pendiente = None
            respuesta = "Confirmado. Ejecutando la acción."
            ui_chat("assistant", respuesta)
            if hablar_respuesta:
                threading.Thread(target=decir, args=(respuesta,), daemon=True).start()
            threading.Thread(target=comando, args=(pendiente,), daemon=True).start()
            return {"ok": True, "message": respuesta}
        if normal in {"no", "cancelar", "cancela", "mejor no"}:
            confirmacion_pendiente = None
            respuesta = "Acción cancelada."
            ui_chat("assistant", respuesta)
            if hablar_respuesta:
                threading.Thread(target=decir, args=(respuesta,), daemon=True).start()
            return {"ok": True, "message": respuesta}
        confirmacion_pendiente = None
    acc = intencion(limpio)
    if not acc:
        respuesta = "No entendí la solicitud. Puedes pedirme que abra aplicaciones, controle la música, busque en Internet o gestione Windows."
        ui_chat("assistant", respuesta)
        if hablar_respuesta:
            threading.Thread(target=decir, args=(respuesta,), daemon=True).start()
        return {"ok": False, "message": respuesta}
    acc, aviso, error = pc.preparar(acc, CERRAR)
    if error:
        ui_chat("assistant", error)
        if hablar_respuesta:
            threading.Thread(target=decir, args=(error,), daemon=True).start()
        return {"ok": False, "message": error}
    if acc in {"sys:shutdown", "sys:restart"} or aviso:
        confirmacion_pendiente = acc
        respuesta = aviso or "Esta acción cerrará tu sesión de Windows. ¿Confirmas? Responde «sí» o «no»."
        ui_chat("assistant", respuesta)
        if hablar_respuesta:
            threading.Thread(target=decir, args=(respuesta,), daemon=True).start()
        return {"ok": True, "message": respuesta, "confirmation": True}
    respuesta = texto_respuesta(acc)
    ui_chat("assistant", respuesta)
    if not (acc.startswith("decir:") and not hablar_respuesta):
        threading.Thread(target=comando, args=(acc,), daemon=True).start()
    if hablar_respuesta and not acc.startswith(("decir:", "timer:", "reminder:", "file:", "clean:", "proc:", "alias:")) and acc[4:] not in pc.SYS_PC:
        threading.Thread(target=decir, args=(respuesta,), daemon=True).start()
    if hablar_respuesta:
        global esp_hasta, estado
        esp_hasta = time.time() + max(3.0, float(CFG.get("comando_espera", 4)))
        if not bloqueado:
            estado = "orden"
    return {"ok": True, "message": respuesta}


class Api:
    def orden(self, texto):
        return procesar_solicitud(texto, hablar_respuesta=False)

    def escuchar(self):
        global estado
        if not bloqueado:
            estado = "orden"
        threading.Thread(target=esperar_orden, daemon=True).start()
        return True

    def probar(self):
        threading.Thread(target=accion, daemon=True).start()

    def guardar_chat(self, texto):
        try:
            carpeta = os.path.join(BASE, "conversaciones")
            os.makedirs(carpeta, exist_ok=True)
            ruta = os.path.join(carpeta, "jarvis_chat_%s.txt" % time.strftime("%Y%m%d_%H%M%S"))
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(str(texto))
            try:
                os.startfile(carpeta)
            except Exception:
                pass
            return {"ok": True, "path": ruta}
        except Exception as e:
            log("guardar_chat: %s" % e)
            return {"ok": False}

    def salir(self):
        global SALIR
        SALIR = True
        ventana.destroy()


def al_cerrar():
    if SALIR:
        return True
    ventana.minimize()  # cerrar = minimizar; para salir usa el botón SALIR
    return False


def main():
    global ventana, listo
    log("inicio asistente")
    try:  # prioridad alta: el audio no se corta por carga de CPU
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x00008000)
    except Exception:
        pass
    threading.Thread(target=pregenerar, daemon=True).start()
    stream = abrir_mic()
    threading.Thread(target=loopback, daemon=True).start()
    threading.Thread(target=escuchar_palabra, daemon=True).start()
    threading.Thread(target=vigilar_spotify, daemon=True).start()
    ventana = webview.create_window(
        "J.A.R.V.I.S", os.path.join(BASE, "hud.html"), js_api=Api(),
        width=1180, height=760, min_size=(940, 600), background_color="#02070c",
        minimized=bool(CFG.get("iniciar_minimizado", False)),
    )
    ventana.events.closing += al_cerrar
    ventana.events.loaded += lambda: globals().__setitem__("listo", True)
    threading.Thread(target=empujar, daemon=True).start()
    webview.start()


def diag():
    print("=== DIAGNOSTICO ===")
    print("Spotify:", filas_spotify())
    threading.Thread(target=loopback, daemon=True).start()
    abrir_mic()
    print("Microfono:", mic_name or "NINGUNO")
    time.sleep(1.5)
    print("Audio del sistema medible:", audio_vivo())
    print("Probando saludo (debe sonar ahora)...")
    hablar()
    print("Saludo terminado. Si no lo oiste, mira los mensajes de arriba.")
    escuchar_palabra()


if __name__ == "__main__":
    if "--diag" in sys.argv:
        try:
            diag()
        except KeyboardInterrupt:
            pass
        input("Enter para cerrar...")
    else:
        main()
