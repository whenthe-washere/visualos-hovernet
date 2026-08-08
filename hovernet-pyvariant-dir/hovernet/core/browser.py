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

        # Match the app's dark background so blank/loading pages aren't a white void.
        # Use neutral dark; will be updated when the window's theme is applied.
        self.page().setBackgroundColor(QColor(10, 10, 16))
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

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            angle_delta = event.angleDelta().y()
            if angle_delta != 0:
                factor = 1.1 if angle_delta > 0 else (1 / 1.1)
                main_win = self.window()
                if main_win and hasattr(main_win, '_zoom'):
                    main_win._zoom(factor)
                return
        super().wheelEvent(event)

    def event(self, e):
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.Type.NativeGesture:
            if e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                val = e.value()
                # value() is the magnification delta, e.g. 0.01 for small zoom in
                factor = 1.0 + val
                main_win = self.window()
                if main_win and hasattr(main_win, '_zoom'):
                    main_win._zoom(factor)
                return True
        return super().event(e)

