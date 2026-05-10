from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineScript

class BrowserView(QWebEngineView):
    """QWebEngineView subclass that tracks load progress for the URL bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # store current load progress for the URL-bar background when switching tabs
        self._load_progress = -1

        # Match the app's dark background so blank/loading pages aren't a white void
        self.page().setBackgroundColor(QColor("#1E1E3C"))
        # Inject lightweight polyfills
        try:
            profile = self.page().profile()
            poly_js = r"""
                (function(){
                if(!window.structuredClone){
                    window.structuredClone = function(obj){
                    try{ return JSON.parse(JSON.stringify(obj)); }catch(e){ return null; }
                    };
                }
                if(!String.prototype.replaceAll){
                    String.prototype.replaceAll = function(search, replace){
                    if(search instanceof RegExp) return this.replace(search, replace);
                    return this.split(String(search)).join(replace);
                    };
                }
                })();
                """
            script = QWebEngineScript()
            script.setName("ie12_polyfills")
            script.setSourceCode(poly_js)
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setRunsOnSubFrames(True)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            self.page().scripts().add(script)
        except Exception:
            pass

    def createWindow(self, type):
        """Handle requests to open links in a new window/tab."""
        main_win = self.window()
        if main_win and hasattr(main_win, 'add_tab'):
            return main_win.add_tab(None)
        return super().createWindow(type)
