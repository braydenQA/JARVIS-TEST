"""Acciones directas sobre el equipo: archivos, limpieza, procesos y sistema.

Reglas de seguridad:
- Borrar manda a la Papelera de Windows (recuperable); el borrado definitivo es explícito.
- Nunca toca rutas del sistema, raíces de unidad, la carpeta personal ni las carpetas
  conocidas completas (Escritorio, Descargas...), ni la carpeta del propio asistente.
- Las acciones destructivas piden confirmación antes (ver CONFIRMAR / preparar).
- Cada función devuelve (texto_chat, texto_voz).
"""

import ctypes
import glob
import os
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
NOWIN = 0x08000000
PERFIL = os.path.expanduser("~")

CARPETAS = {
    "descargas": "Downloads", "escritorio": "Desktop", "documentos": "Documents",
    "imagenes": "Pictures", "videos": "Videos", "musica": "Music",
}
PARCIALES = (".crdownload", ".part", ".tmp", ".partial", ".download")
TIPOS_ULTIMO = {
    "zip": (".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"), "pdf": (".pdf",),
    "imagen": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"),
    "instalador": (".exe", ".msi"), "texto": (".txt", ".md"),
    "video": (".mp4", ".mkv", ".avi", ".mov"), "audio": (".mp3", ".wav", ".flac", ".m4a"),
}
ORGANIZAR = {
    "Imágenes": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"),
    "Documentos": (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv", ".odt"),
    "Comprimidos": (".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"),
    "Instaladores": (".exe", ".msi", ".msix", ".apk"),
    "Video": (".mp4", ".mkv", ".avi", ".mov", ".webm"),
    "Audio": (".mp3", ".wav", ".flac", ".m4a", ".ogg"),
}

# acciones que exigen confirmación explícita antes de ejecutarse
CONFIRMAR = ("file:purge", "file:delete", "clean:recycle", "clean:full",
             "proc:kill", "file:organize", "sys:logoff")


def fmt_bytes(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%d %s" % (n, u)) if u == "B" else ("%.1f %s" % (n, u))
        n /= 1024


# ---------- carpetas conocidas y resolución de rutas ----------
def carpeta(nombre):
    nombre = str(nombre).lower()
    sub = CARPETAS.get(nombre)
    if not sub:
        return None
    for base in (PERFIL, os.path.join(PERFIL, "OneDrive")):
        p = os.path.join(base, sub)
        if os.path.isdir(p):
            return p
    return os.path.join(PERFIL, sub)


def _raices_protegidas():
    r = {os.path.realpath(PERFIL), os.path.realpath(BASE)}
    for k in CARPETAS:
        c = carpeta(k)
        if c:
            r.add(os.path.realpath(c))
    for var in ("APPDATA", "LOCALAPPDATA"):
        if os.environ.get(var):
            r.add(os.path.realpath(os.environ[var]))
    return r


def _prefijos_sistema():
    p = []
    for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        if os.environ.get(var):
            p.append(os.path.realpath(os.environ[var]))
    if os.name != "nt":
        p += ["/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/sbin", "/sys", "/usr", "/var"]
    return p


def protegida(ruta):
    """True si la ruta no debe borrarse, moverse ni renombrarse."""
    try:
        real = os.path.realpath(ruta)
    except Exception:
        return True
    if os.path.splitdrive(real)[1] in ("", "\\", "/"):
        return True
    if real in _raices_protegidas():
        return True
    for pref in _prefijos_sistema():
        if real == pref or real.startswith(pref + os.sep):
            return True
    if os.path.islink(ruta):
        return True
    esj = getattr(os.path, "isjunction", None)
    return bool(esj and esj(ruta))


def _reciente(rutas):
    return max(rutas, key=lambda p: os.path.getmtime(p))


def _sin_parciales(p):
    return not p.lower().endswith(PARCIALES)


def _buscar_nombre(nombre, en=None, profundidad=3):
    """Busca por nombre (con o sin extensión) en las carpetas conocidas; devuelve lista."""
    n = nombre.lower().strip()
    raices = [carpeta(en)] if en and carpeta(en) else [carpeta(k) for k in CARPETAS]
    hallados = []
    for raiz in filter(None, raices):
        if not os.path.isdir(raiz):
            continue
        base_depth = raiz.rstrip(os.sep).count(os.sep)
        for d, dirs, files in os.walk(raiz):
            if d.count(os.sep) - base_depth >= profundidad:
                dirs[:] = []
            for nom in files + dirs:
                low = nom.lower()
                if low == n or os.path.splitext(low)[0] == n:
                    hallados.append(os.path.join(d, nom))
            if len(hallados) > 20:
                break
    return hallados


def resolver(spec, estricto=False):
    """spec: 'ruta=...' | 'nombre=x[@carpeta]' | 'ultimo=carpeta[/tipo]' | 'carpeta=x'.
    Devuelve (ruta, error)."""
    clave, _, valor = str(spec).partition("=")
    valor = valor.strip().strip('"')
    if clave == "ruta":
        ruta = os.path.expandvars(valor)
        return (ruta, None) if os.path.exists(ruta) else (None, "No existe esa ruta.")
    if clave == "carpeta":
        c = carpeta(valor)
        return (c, None) if c and os.path.isdir(c) else (None, "No encuentro esa carpeta.")
    if clave == "ultimo":
        cnom, _, tipo = valor.partition("/")
        c = carpeta(cnom or "descargas")
        if not c or not os.path.isdir(c):
            return None, "No encuentro esa carpeta."
        exts = TIPOS_ULTIMO.get(tipo)
        cand = [os.path.join(c, f) for f in os.listdir(c)
                if os.path.isfile(os.path.join(c, f)) and _sin_parciales(f)
                and (not exts or f.lower().endswith(exts))]
        return (_reciente(cand), None) if cand else (None, "No hay archivos que coincidan en esa carpeta.")
    if clave == "nombre":
        nombre, _, en = valor.partition("@")
        hallados = _buscar_nombre(nombre, en or None)
        if not hallados:
            return None, "No encuentro «%s» en Escritorio, Descargas, Documentos, Imágenes, Vídeos ni Música." % nombre
        if len(hallados) > 1 and estricto:
            return None, "Hay varios con ese nombre: " + "; ".join(hallados[:3]) + ". Dame la ruta completa."
        return _reciente(hallados), None
    return None, "No entendí qué archivo o carpeta indicas."


def describir(ruta):
    if os.path.isdir(ruta):
        n, tam = 0, 0
        for d, _, files in os.walk(ruta):
            for f in files:
                n += 1
                try:
                    tam += os.path.getsize(os.path.join(d, f))
                except OSError:
                    pass
        return "carpeta con %d archivos, %s" % (n, fmt_bytes(tam))
    try:
        return "archivo, %s" % fmt_bytes(os.path.getsize(ruta))
    except OSError:
        return "archivo"


def _unico(ruta):
    if not os.path.exists(ruta):
        return ruta
    base, ext = os.path.splitext(ruta)
    i = 2
    while os.path.exists("%s (%d)%s" % (base, i, ext)):
        i += 1
    return "%s (%d)%s" % (base, i, ext)


# ---------- papelera ----------
def a_papelera(ruta, destino_prueba=None):
    ruta = os.path.abspath(ruta)
    if os.name != "nt":  # entorno de pruebas: simula la papelera
        d = destino_prueba or os.path.join(tempfile.gettempdir(), "papelera_jarvis")
        os.makedirs(d, exist_ok=True)
        shutil.move(ruta, _unico(os.path.join(d, os.path.basename(ruta))))
        return True

    class SHFILEOPSTRUCT(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort),
                    ("fAnyOperationsAborted", ctypes.c_int), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p)]
    op = SHFILEOPSTRUCT()
    op.wFunc = 3                      # FO_DELETE
    op.pFrom = ruta + "\0\0"
    op.fFlags = 0x40 | 0x10 | 0x4 | 0x400   # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted


def borrar_definitivo(ruta):
    def _perm(fn, p, _):
        os.chmod(p, 0o700)
        fn(p)
    if os.path.isdir(ruta):
        shutil.rmtree(ruta, onerror=_perm)
    else:
        os.chmod(ruta, 0o700)
        os.remove(ruta)


# ---------- archivos ----------
def _ruta_segura(base, miembro):
    destino = os.path.realpath(os.path.join(base, miembro))
    return destino == os.path.realpath(base) or destino.startswith(os.path.realpath(base) + os.sep)


def descomprimir(ruta, abrir=True):
    if not os.path.isfile(ruta):
        return "Eso no es un archivo comprimido.", "Eso no es un archivo comprimido."
    nombre = os.path.basename(ruta)
    stem = re.sub(r"(\.tar)?\.[A-Za-z0-9]+$", "", nombre)
    destino = _unico(os.path.join(os.path.dirname(ruta), stem))
    os.makedirs(destino)
    low = nombre.lower()
    try:
        if zipfile.is_zipfile(ruta):
            with zipfile.ZipFile(ruta) as z:
                total = sum(i.file_size for i in z.infolist())
                if total > shutil.disk_usage(destino).free * 0.9:
                    raise OSError("No hay espacio suficiente en el disco.")
                for i in z.infolist():
                    if not _ruta_segura(destino, i.filename):
                        raise OSError("El archivo contiene rutas peligrosas; no lo extraje.")
                z.extractall(destino)
        elif low.endswith((".tar", ".gz", ".tgz", ".bz2", ".xz")) and tarfile.is_tarfile(ruta):
            with tarfile.open(ruta) as t:
                for m in t.getmembers():
                    if not _ruta_segura(destino, m.name) or m.issym() or m.islnk():
                        raise OSError("El archivo contiene rutas peligrosas; no lo extraje.")
                t.extractall(destino)
        else:  # .7z / .rar: bsdtar de Windows 10+ (mejor esfuerzo)
            r = subprocess.run(["tar", "-xf", ruta, "-C", destino], capture_output=True,
                               creationflags=NOWIN if os.name == "nt" else 0, timeout=600)
            if r.returncode != 0:
                raise OSError("No pude extraer ese formato. Instala 7-Zip o usa .zip.")
    except Exception as e:
        shutil.rmtree(destino, ignore_errors=True)
        msg = "No pude descomprimir: %s" % e
        return msg, msg
    n = sum(len(f) for _, _, f in os.walk(destino))
    if abrir and os.name == "nt":
        try:
            os.startfile(destino)
        except Exception:
            pass
    return ("Descomprimido en %s (%d archivos)." % (destino, n),
            "Listo, descomprimí %d archivos en la carpeta %s." % (n, os.path.basename(destino)))


def comprimir(ruta):
    ruta = os.path.abspath(ruta)
    salida = _unico(ruta.rstrip("\\/") + ".zip")
    try:
        if os.path.isdir(ruta):
            shutil.make_archive(salida[:-4], "zip", os.path.dirname(ruta), os.path.basename(ruta))
        else:
            with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(ruta, os.path.basename(ruta))
    except Exception as e:
        msg = "No pude comprimir: %s" % e
        return msg, msg
    return ("Comprimido en %s (%s)." % (salida, fmt_bytes(os.path.getsize(salida))),
            "Listo, creé el archivo %s." % os.path.basename(salida))


def copiar_mover(ruta, destino, mover):
    if not os.path.isdir(destino):
        return "La carpeta de destino no existe.", "La carpeta de destino no existe."
    if protegida(destino) and any(destino.startswith(p) for p in _prefijos_sistema()):
        return "No escribo en carpetas del sistema.", "No escribo en carpetas del sistema."
    if mover and protegida(ruta):
        return "Esa ubicación está protegida; no la muevo.", "Esa ubicación está protegida."
    final = _unico(os.path.join(destino, os.path.basename(ruta.rstrip("\\/"))))
    try:
        if mover:
            shutil.move(ruta, final)
        elif os.path.isdir(ruta):
            shutil.copytree(ruta, final)
        else:
            shutil.copy2(ruta, final)
    except Exception as e:
        return "No pude completar la operación: %s" % e, "No pude completar la operación."
    v = "movido" if mover else "copiado"
    return "%s a %s" % (v.capitalize(), final), "Listo, archivo %s." % v


def renombrar(ruta, nuevo):
    if protegida(ruta):
        return "Esa ubicación está protegida; no la renombro.", "Esa ubicación está protegida."
    if re.search(r'[\\/:*?"<>|]', nuevo) or not nuevo.strip():
        return "El nombre nuevo no es válido.", "El nombre nuevo no es válido."
    destino = os.path.join(os.path.dirname(ruta), nuevo.strip())
    if os.path.exists(destino):
        return "Ya existe algo con ese nombre.", "Ya existe algo con ese nombre."
    os.rename(ruta, destino)
    return "Renombrado a %s" % nuevo, "Listo, renombrado."


def crear_carpeta(nombre, en="escritorio"):
    base = carpeta(en) or carpeta("escritorio")
    if re.search(r'[\\/:*?"<>|]', nombre) or not nombre.strip():
        return "El nombre de la carpeta no es válido.", "El nombre de la carpeta no es válido."
    destino = _unico(os.path.join(base, nombre.strip()))
    os.makedirs(destino)
    return "Carpeta creada: %s" % destino, "Listo, creé la carpeta %s." % os.path.basename(destino)


def listar(ruta, limite=15):
    items = []
    for f in os.listdir(ruta):
        p = os.path.join(ruta, f)
        try:
            items.append((os.path.getmtime(p), f, os.path.isdir(p), 0 if os.path.isdir(p) else os.path.getsize(p)))
        except OSError:
            pass
    items.sort(reverse=True)
    if not items:
        return "La carpeta está vacía.", "La carpeta está vacía."
    lineas = ["%s %s%s" % ("📁" if d else "📄", f, "" if d else "  (%s)" % fmt_bytes(t)) for _, f, d, t in items[:limite]]
    extra = "\n… y %d más" % (len(items) - limite) if len(items) > limite else ""
    return ("Contenido de %s (más recientes primero):\n" % ruta + "\n".join(lineas) + extra,
            "Hay %d elementos. El más reciente es %s." % (len(items), items[0][1]))


def organizar(ruta):
    movidos = {}
    ahora = time.time()
    for f in os.listdir(ruta):
        p = os.path.join(ruta, f)
        if not os.path.isfile(p) or not _sin_parciales(f) or ahora - os.path.getmtime(p) < 120:
            continue
        ext = os.path.splitext(f)[1].lower()
        cat = next((c for c, e in ORGANIZAR.items() if ext in e), "Otros")
        d = os.path.join(ruta, cat)
        os.makedirs(d, exist_ok=True)
        shutil.move(p, _unico(os.path.join(d, f)))
        movidos[cat] = movidos.get(cat, 0) + 1
    if not movidos:
        return "No había archivos sueltos para ordenar.", "No había archivos sueltos para ordenar."
    det = ", ".join("%s: %d" % kv for kv in sorted(movidos.items()))
    return ("Ordené %d archivos (%s)." % (sum(movidos.values()), det),
            "Listo, ordené %d archivos por tipo." % sum(movidos.values()))


# ---------- limpieza ----------
def _vaciar_dir(d, min_edad=0):
    """Borra el contenido de un directorio sin tocar lo que está en uso. Devuelve bytes liberados."""
    liberado = 0
    if not d or not os.path.isdir(d):
        return 0
    ahora = time.time()
    for nom in os.listdir(d):
        p = os.path.join(d, nom)
        try:
            if os.path.islink(p):
                os.unlink(p)
                continue
            if ahora - os.path.getmtime(p) < min_edad:
                continue
            if os.path.isdir(p):
                for dd, _, files in os.walk(p):
                    for f in files:
                        try:
                            liberado += os.path.getsize(os.path.join(dd, f))
                        except OSError:
                            pass
                shutil.rmtree(p, ignore_errors=True)
            else:
                liberado += os.path.getsize(p)
                os.remove(p)
        except Exception:
            continue
    return liberado


def limpiar_temp():
    dirs = {tempfile.gettempdir(), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp"),
            os.path.join(os.environ.get("SystemRoot", ""), "Temp")}
    return sum(_vaciar_dir(d, 300) for d in dirs if d)


def _dirs_cache():
    L = os.environ.get("LOCALAPPDATA", "")
    A = os.environ.get("APPDATA", "")
    pats = []
    for rel in (r"Google\Chrome", r"Microsoft\Edge", r"BraveSoftware\Brave-Browser", r"Opera Software\Opera Stable"):
        for sub in ("Cache", "Code Cache", "GPUCache", r"Service Worker\CacheStorage"):
            pats.append(os.path.join(L, rel, "User Data", "*", sub))
            pats.append(os.path.join(L, rel, "User Data", sub))
    pats.append(os.path.join(L, "Mozilla", "Firefox", "Profiles", "*", "cache2"))
    pats.append(os.path.join(L, r"Microsoft\Windows\INetCache"))
    for app in ("discord", "Code", "Slack", "Microsoft Teams"):
        for sub in ("Cache", "Code Cache", "GPUCache"):
            pats.append(os.path.join(A, app, sub))
    out = []
    for p in pats:
        out += glob.glob(p)
    return out


def limpiar_cache():
    return sum(_vaciar_dir(d) for d in _dirs_cache())


def limpiar_dns():
    if os.name != "nt":
        return False
    return subprocess.run(["ipconfig", "/flushdns"], capture_output=True, creationflags=NOWIN).returncode == 0


def vaciar_papelera():
    if os.name != "nt":
        return False
    return ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7) in (0, 1)  # S_OK / S_FALSE (ya vacía)


def limpiar_portapapeles():
    if os.name != "nt":
        return False
    subprocess.run("cmd /c echo off | clip", shell=True, creationflags=NOWIN)
    return True


# ---------- procesos y sistema ----------
def top_procesos(n=5):
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                procs.append((p.info["memory_info"].rss, p.info["name"]))
            except Exception:
                pass
        agrupado = {}
        for rss, nom in procs:
            agrupado[nom] = agrupado.get(nom, 0) + rss
        top = sorted(((v, k) for k, v in agrupado.items()), reverse=True)[:n]
        txt = "Procesos con más memoria:\n" + "\n".join("%d. %s — %s" % (i + 1, k, fmt_bytes(v)) for i, (v, k) in enumerate(top))
        return txt, "El que más memoria usa es %s con %s." % (top[0][1], fmt_bytes(top[0][0]))
    except Exception:
        return "Necesito psutil para ver los procesos (pip install psutil).", "Necesito psutil para eso."


def matar_proceso(exes):
    ok = False
    for exe in exes:
        r = subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True, creationflags=NOWIN if os.name == "nt" else 0)
        ok = ok or r.returncode == 0
    return ("Proceso terminado a la fuerza." if ok else "No encontré ese proceso en ejecución."), \
           ("Listo, proceso terminado." if ok else "No encontré ese proceso.")


def espacio_disco():
    base = os.path.splitdrive(PERFIL)[0] + os.sep if os.name == "nt" else "/"
    u = shutil.disk_usage(base)
    pct = u.used / u.total * 100
    return ("Disco %s: %s libres de %s (%.0f%% en uso)." % (base, fmt_bytes(u.free), fmt_bytes(u.total), pct),
            "Tienes %s libres de %s, el disco está al %.0f por ciento." % (fmt_bytes(u.free), fmt_bytes(u.total), pct))


def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return "IP local: %s (equipo: %s)" % (ip, socket.gethostname()), "Tu dirección IP local es %s." % ip.replace(".", " punto ")


def hay_internet():
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        return "Hay conexión a Internet.", "Sí, hay conexión a Internet."
    except OSError:
        return "No hay conexión a Internet.", "No, no hay conexión a Internet."


def sistema(nom):
    if nom == "disk":
        return espacio_disco()
    if nom == "ip":
        return ip_local()
    if nom == "ping":
        return hay_internet()
    if nom == "sleep" and os.name == "nt":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=NOWIN)
        return "Suspendiendo el equipo.", "Suspendiendo el equipo."
    if nom == "logoff" and os.name == "nt":
        subprocess.Popen(["shutdown", "/l"], creationflags=NOWIN)
        return "Cerrando la sesión.", "Cerrando la sesión."
    if nom == "screenoff" and os.name == "nt":
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)   # SC_MONITORPOWER off
        return "Pantalla apagada (mueve el ratón para encenderla).", "Apagando la pantalla."
    return "Esa acción solo funciona en Windows.", "Esa acción solo funciona en Windows."


SYS_PC = {"disk", "ip", "ping", "sleep", "logoff", "screenoff"}


# ---------- despacho ----------
def _spec(nom):
    return nom.split("|")


def preparar(acc, cerrar=None):
    """Resuelve rutas y prepara la confirmación. Devuelve (acc_final, mensaje_confirmacion|None, error|None)."""
    tipo, _, nom = acc.partition(":")
    if acc.startswith(("file:delete", "file:purge")):
        partes = _spec(nom)
        ruta, err = resolver(partes[1], estricto=True)
        if err:
            return acc, None, err
        if protegida(ruta):
            return acc, None, "Esa ubicación está protegida (sistema, carpeta personal o carpeta completa); no la borro."
        definitivo = partes[0] == "purge"
        final = "file:%s|%s" % (partes[0], "ruta=" + ruta)
        if definitivo:
            msg = "⚠ ¿Borrar DEFINITIVAMENTE «%s» (%s)? No se puede deshacer. Responde «sí» o «no»." % (ruta, describir(ruta))
        else:
            msg = "¿Mover a la Papelera «%s» (%s)? Responde «sí» o «no»." % (ruta, describir(ruta))
        return final, msg, None
    if acc == "clean:recycle":
        return acc, "¿Vaciar la Papelera de reciclaje? No se puede deshacer. Responde «sí» o «no».", None
    if acc == "clean:full":
        return acc, "Limpiaré temporales, caché de navegadores, DNS y vaciaré la Papelera. ¿Confirmas? Responde «sí» o «no».", None
    if acc.startswith("proc:kill"):
        return acc, "¿Forzar el cierre de «%s»? Se perderá lo que no esté guardado. ¿Confirmas? Responde «sí» o «no»." % nom.partition("|")[2], None
    if acc.startswith("file:organize"):
        c, err = resolver("carpeta=" + nom.partition("|")[2])
        if err:
            return acc, None, err
        return acc, "¿Ordenar los archivos sueltos de «%s» en subcarpetas por tipo? ¿Confirmas? Responde «sí» o «no»." % c, None
    if acc == "sys:logoff":
        return acc, "Esto cerrará tu sesión de Windows. ¿Confirmas? Responde «sí» o «no».", None
    return acc, None, None


def ejecutar(acc, cerrar=None, apps=None):
    """Ejecuta la acción ya confirmada. Devuelve (texto_chat, texto_voz)."""
    cerrar = cerrar or {}
    tipo, _, nom = acc.partition(":")
    try:
        if tipo == "sys":
            return sistema(nom)
        if tipo == "clean":
            if nom == "dns":
                ok = limpiar_dns()
                return ("Caché DNS limpiada." if ok else "No pude limpiar el DNS."), ("Listo, DNS limpiada." if ok else "No pude limpiar el DNS.")
            if nom == "recycle":
                ok = vaciar_papelera()
                return ("Papelera vaciada." if ok else "No pude vaciar la Papelera."), ("Papelera vaciada." if ok else "No pude vaciar la Papelera.")
            if nom == "clip":
                limpiar_portapapeles()
                return "Portapapeles vaciado.", "Portapapeles vaciado."
            t = c = 0
            if nom in ("temp", "all", "full"):
                t = limpiar_temp()
            if nom in ("cache", "all", "full"):
                c = limpiar_cache()
            extra = ""
            if nom in ("all", "full"):
                limpiar_dns()
                extra += " DNS limpiada."
            if nom == "full":
                vaciar_papelera()
                extra += " Papelera vaciada."
            total = t + c
            partes = []
            if nom in ("temp", "all", "full"):
                partes.append("temporales %s" % fmt_bytes(t))
            if nom in ("cache", "all", "full"):
                partes.append("caché %s" % fmt_bytes(c))
            return ("Limpieza lista: %s. Total liberado: %s.%s" % (", ".join(partes), fmt_bytes(total), extra),
                    "Limpieza lista, liberé %s.%s" % (fmt_bytes(total), extra))
        if tipo == "proc":
            op, _, arg = nom.partition("|")
            if op == "top":
                return top_procesos()
            if op == "kill":
                exes = cerrar.get(arg) or [arg if arg.lower().endswith(".exe") else arg + ".exe"]
                return matar_proceso(exes)
        if tipo == "file":
            op, *args = _spec(nom)
            if op == "organize":
                c, err = resolver("carpeta=" + args[0])
                return (err, err) if err else organizar(c)
            if op == "mkdir":
                return crear_carpeta(args[0], args[1] if len(args) > 1 else "escritorio")
            if op == "list":
                c, err = resolver(args[0])
                return (err, err) if err else listar(c)
            if op == "find":
                res = _buscar_nombre(args[0].partition("@")[0], args[0].partition("@")[2] or None)[:6]
                if not res:
                    return "No encontré «%s»." % args[0], "No encontré ese archivo."
                return ("Encontré:\n" + "\n".join(res), "Encontré %d resultados; te los dejé en el chat." % len(res))
            ruta, err = resolver(args[0], estricto=op in ("delete", "purge", "rename"))
            if err:
                return err, err
            if op == "open":
                if os.name == "nt":
                    os.startfile(ruta)
                return "Abriendo %s" % ruta, "Abriendo."
            if op == "size":
                d = describir(ruta)
                return "%s: %s" % (ruta, d), "Es un %s." % d
            if op == "delete":
                if protegida(ruta):
                    return "Ruta protegida.", "Ruta protegida."
                ok = a_papelera(ruta)
                return (("Enviado a la Papelera: %s" % ruta, "Listo, lo mandé a la Papelera.") if ok
                        else ("No pude borrarlo (¿está en uso?).", "No pude borrarlo."))
            if op == "purge":
                if protegida(ruta):
                    return "Ruta protegida.", "Ruta protegida."
                borrar_definitivo(ruta)
                return "Borrado definitivamente: %s" % ruta, "Listo, borrado definitivamente."
            if op == "unzip":
                return descomprimir(ruta)
            if op == "zip":
                return comprimir(ruta)
            if op in ("copy", "move"):
                dest, err2 = resolver(args[1])
                return (err2, err2) if err2 else copiar_mover(ruta, dest, op == "move")
            if op == "rename":
                return renombrar(ruta, args[1])
    except Exception as e:
        msg = "No pude completar la acción: %s" % e
        return msg, "No pude completar la acción."
    return "Acción no reconocida.", "Acción no reconocida."
