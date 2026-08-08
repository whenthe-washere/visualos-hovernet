import json
from PySide6.QtCore import Qt, QPoint, QTimer, QUrl, QEvent
from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

class AutocompleteDropdown(QListWidget):
    """Floating suggestion list that appears below the URL bar."""
    def __init__(self, url_bar, parent_window):
        self.url_bar = url_bar
        self.parent_window = parent_window
        super().__init__(parent_window)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.itemClicked.connect(self._on_item_clicked)
        self.update_style()

    def update_style(self):
        win = self.parent_window
        r, g, b = (85, 142, 255)
        if win and hasattr(win, 'get_accent_rgb'):
            r, g, b = win.get_accent_rgb()
        is_dark = getattr(win, 'is_dark_mode', True) if win else True
        bg = f"rgba({max(r//5,10)},{max(g//5,10)},{max(b//5,10)},240)" if is_dark else "rgba(255,255,255,250)"
        border = f"rgba({r//2},{g//2},{b//2},180)"
        text = "#DEE9FF" if is_dark else "#111122"
        sel = f"rgba({r},{g},{b},80)" if is_dark else f"rgba({r},{g},{b},40)"
        hover = f"rgba({r//3},{g//3},{b//3},180)" if is_dark else f"rgba({r},{g},{b},20)"
        self.setStyleSheet(f"""
            QListWidget {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 6px;
                color: {text};
                font-size: 12px;
                outline: none;
            }}
            QListWidget::item {{ padding: 5px 10px; border: none; }}
            QListWidget::item:selected {{ background: {sel}; color: {"#ffffff" if is_dark else "#000000"}; }}
            QListWidget::item:hover {{ background: {hover}; }}
        """)

        self._nam = QNetworkAccessManager(self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._fetch)
        self._current_reply = None

        self.url_bar.textEdited.connect(self._on_text_edited)
        self.url_bar.installEventFilter(self)

    def _on_text_edited(self, text):
        text = text.strip()
        if not text or text.startswith(("http://", "https://", "about:", "file://", "hovernet:")):
            self.hide()
            return
        self._debounce.start()

    def _fetch(self):
        query = self.url_bar.text().strip()
        if not query:
            self.hide()
            return
        url = QUrl(f"https://suggestqueries.google.com/complete/search?client=firefox&q={QUrl.toPercentEncoding(query).data().decode()}")
        req = QNetworkRequest(url)
        req.setRawHeader(b"User-Agent", b"Mozilla/5.0")
        if self._current_reply:
            try: self._current_reply.abort()
            except: pass
        self._current_reply = self._nam.get(req)
        self._current_reply.finished.connect(self._on_reply)

    def _on_reply(self):
        reply = self.sender()
        if not reply or reply.error() != QNetworkReply.NetworkError.NoError:
            if reply: reply.deleteLater()
            return

        try:
            raw = bytes(reply.readAll())
            data = json.loads(raw.decode("utf-8"))
            suggestions = data[1] if len(data) > 1 else []
        except: suggestions = []
        finally:
            reply.deleteLater()
            if self._current_reply == reply: self._current_reply = None

        self.clear()
        for s in suggestions[:8]: self.addItem(QListWidgetItem(s))
        if self.count() == 0:
            self.hide()
            return

        self._reposition()
        self.show()
        self.raise_()

    def _reposition(self):
        bar = self.url_bar
        pos = bar.mapToGlobal(QPoint(0, bar.height()))
        self.move(pos)
        self.setFixedWidth(bar.width())
        row_h = self.sizeHintForRow(0) if self.count() > 0 else 28
        self.setFixedHeight(min(self.count(), 8) * (row_h + 2) + 6)

    def _on_item_clicked(self, item):
        self.url_bar.setText(item.text())
        self.hide()
        self.parent_window.load_url()

    def eventFilter(self, obj, event):
        if obj is self.url_bar:
            if event.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(150, self._maybe_hide)
            elif event.type() == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Down and self.count():
                    cur = self.currentRow()
                    self.setCurrentRow(min(cur + 1, self.count() - 1))
                    return True
                elif key == Qt.Key.Key_Up and self.count():
                    cur = self.currentRow()
                    self.setCurrentRow(max(cur - 1, 0))
                    return True
                elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                    if self.isVisible() and self.currentItem():
                        self._on_item_clicked(self.currentItem())
                        return True
                elif key == Qt.Key.Key_Escape:
                    self.hide()
                    return True
        return super().eventFilter(obj, event)

    def _maybe_hide(self):
        if not self.underMouse(): self.hide()
