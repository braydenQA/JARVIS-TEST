import unittest

from command_parser import es_solo_activacion, interpretar_orden


APPS = {
    "chrome": "chrome",
    "firefox": "firefox",
    "browser": "https://www.google.com",
    "spotify": "spotify:",
    "youtube": "https://www.youtube.com",
    "calculator": "calc",
    "notepad": "notepad",
    "discord": "discord:",
    "gmail": "https://mail.google.com",
}


class InterpretarOrdenTests(unittest.TestCase):
    def test_frases_naturales_para_apps(self):
        casos = {
            "Jarvis, ¿puedes abrir Google Chrome, por favor?": "open:chrome",
            "Me puedes abrir la calculadora": "open:calculator",
            "Me podría abrir Firefox": "open:firefox",
            "abre el crome": "open:chrome",
            "habre el crome": "open:chrome",
            "cierra el bloc de notas": "close:notepad",
            "abre el navegador": "open:browser",
            "abre spoty": "musica:play",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(interpretar_orden(texto, APPS), esperado)

    def test_busquedas_en_google_y_youtube(self):
        casos = {
            "busca gatos en YouTube": "buscar:https://www.youtube.com/results?search_query=gatos",
            "busca en YouTube gatos": "buscar:https://www.youtube.com/results?search_query=gatos",
            "pon rock en YouTube": "buscar:https://www.youtube.com/results?search_query=rock",
            "quiero buscar playas de Costa Rica": "buscar:https://www.google.com/search?q=playas+de+costa+rica",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(interpretar_orden(texto, APPS), esperado)

    def test_musica_y_volumen(self):
        casos = {
            "pon música, por favor": "musica:play",
            "quiero escuchar música": "musica:play",
            "inicia la música": "musica:play",
            "¿puedes pausar la música?": "pausa",
            "detén la reproducción": "pausa",
            "detén la música": "pausa",
            "pon la siguiente canción": "next",
            "quiero otra canción": "next",
            "cambia a la canción anterior": "prev",
            "sube un poco el volumen": "vol+",
            "más alto": "vol+",
            "baja el sonido por favor": "vol-",
            "más bajo": "vol-",
            "silencia el sonido": "mute",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(interpretar_orden(texto, APPS), esperado)

    def test_temporizadores_con_varias_unidades(self):
        casos = {
            "avísame en cinco minutos": "timer:300",
            "temporizador de una hora y veinte minutos": "timer:4800",
            "temporizador de 1 hora 20 minutos": "timer:4800",
            "temporizador de media hora": "timer:1800",
            "cancela el temporizador": "timer:cancel",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(interpretar_orden(texto, APPS), esperado)

    def test_sistema_y_ayuda(self):
        self.assertEqual(interpretar_orden("abre una nueva pestaña", APPS), "key:newtab")
        self.assertEqual(interpretar_orden("cierra la pestaña", APPS), "key:closetab")
        self.assertEqual(interpretar_orden("pantalla completa", APPS), "key:fullscreen")
        self.assertTrue(interpretar_orden("¿qué puedes hacer?", APPS).startswith("decir:Puedes hablar"))
        self.assertIsNone(interpretar_orden("haz una cosa desconocida", APPS))


    def test_comandos_ampliados_windows_y_recordatorios(self):
        casos = {
            "reinicia el equipo": "sys:restart",
            "apaga la computadora": "sys:shutdown",
            "abre el administrador de tareas": "sys:taskmgr",
            "maximiza la ventana": "win:maximize",
            "minimiza la ventana actual": "win:minimize",
            "restaura la ventana": "win:restore",
            "cierra la ventana actual": "win:close",
            "recuérdame en cinco minutos comprar leche": "reminder:300:comprar leche",
            "qué clima hace": "buscar:https://www.google.com/search?q=clima",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(interpretar_orden(texto, APPS), esperado)

    def test_detecta_activacion_sola(self):
        self.assertTrue(es_solo_activacion("Hey, Jarvis"))
        self.assertFalse(es_solo_activacion("Jarvis abre Chrome"))

    def test_saluda_solo_con_un_saludo_explicito(self):
        for texto in ("hola", "hola Jarvis", "Jarvis, hola", "buenas Jarvis"):
            with self.subTest(texto=texto):
                self.assertTrue(
                    interpretar_orden(texto, APPS).startswith("decir:Hola")
                )

    def test_control_manos_libres(self):
        casos = {
            "escribe Hola, ¿cómo estás?": "type:Hola, ¿cómo estás?",
            "Jarvis, escribe Reunión a las 3": "type:Reunión a las 3",
            "presiona Enter": "key:enter",
            "pulsa la tecla Escape": "key:escape",
            "copiar": "key:copy",
            "pegar": "key:paste",
            "haz clic": "mouse:click",
            "haz clic derecho": "mouse:right",
            "doble clic": "mouse:double",
            "mueve el cursor a la derecha 100": "mouse:move:100:0",
            "mueve el cursor a 500 y 300": "mouse:at:500:300",
            "desplázate hacia abajo": "mouse:scroll_down",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(interpretar_orden(texto, APPS), esperado)

    def test_archivos_limpieza_procesos_y_sistema(self):
        apps = {**APPS, "powershell": "powershell", "devmgmt": "devmgmt.msc", "claude": "https://claude.ai", "whatsappweb": "x"}
        casos = {
            "borra el archivo informe.docx": "file:delete|nombre=informe.docx",
            "borra el archivo informe punto docx": "file:delete|nombre=informe.docx",
            "elimina el último zip de descargas": "file:delete|ultimo=descargas/zip",
            "borra C:\\Users\\Bray\\Desktop\\viejo.txt permanentemente": "file:purge|ruta=C:\\Users\\Bray\\Desktop\\viejo.txt",
            "descomprime el último zip de descargas": "file:unzip|ultimo=descargas/zip",
            "comprime la carpeta proyecto": "file:zip|nombre=proyecto",
            "mueve informe.docx de descargas a documentos": "file:move|nombre=informe.docx@descargas|carpeta=documentos",
            "copia foto.png a escritorio": "file:copy|nombre=foto.png|carpeta=escritorio",
            "renombra informe.docx a final.docx": "file:rename|nombre=informe.docx|final.docx",
            "crea una carpeta llamada Proyectos en el escritorio": "file:mkdir|Proyectos|escritorio",
            "organiza descargas": "file:organize|descargas",
            "qué hay en descargas": "file:list|carpeta=descargas",
            "busca el archivo tesis.pdf": "file:find|tesis.pdf",
            "abre la carpeta de descargas": "file:open|carpeta=descargas",
            "limpia los archivos temporales": "clean:temp",
            "limpia la caché": "clean:cache",
            "vacía la papelera": "clean:recycle",
            "limpia mi pc": "clean:all",
            "limpieza completa del equipo": "clean:full",
            "mata el proceso chrome": "proc:kill|chrome",
            "qué procesos consumen más memoria": "proc:top",
            "cuánto espacio libre queda en el disco": "sys:disk",
            "suspende el equipo": "sys:sleep",
            "cierra sesión": "sys:logoff",
            "aprende que el chisme es discord": "alias:el chisme|discord",
            "abre el administrador de dispositivos": "open:devmgmt",
            "abre claude": "open:claude",
            "abre whatsapp web": "open:whatsappweb",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(interpretar_orden(texto, apps), esperado)

    def test_borrar_no_confunde_otras_ordenes(self):
        self.assertEqual(interpretar_orden("cancela el temporizador", APPS), "timer:cancel")
        self.assertEqual(interpretar_orden("borra el temporizador", APPS), "timer:cancel")
        self.assertEqual(interpretar_orden("abre el escritorio", APPS), "key:desktop")
        self.assertNotIn("clean:", interpretar_orden("borra el archivo del disco informe.docx", APPS))


if __name__ == "__main__":
    unittest.main()
