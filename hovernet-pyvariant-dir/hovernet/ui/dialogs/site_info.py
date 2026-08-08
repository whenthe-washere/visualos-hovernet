from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QStackedWidget, QWidget
from PySide6.QtGui import QDesktopServices, QFont
from ..widgets.buttons import SettingsToggle

class SiteInfoDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._main_window = main_window
        self.setWindowTitle("Site info")
        self.setFixedWidth(420)

        cur = main_window.browser_area.currentWidget()
        self._url_str = main_window.url_bar.text()
        self._is_secure = self._url_str.startswith("https://")

        r, g, b = main_window.get_accent_rgb()
        self._accent_rgb = (r, g, b)
        is_dark = getattr(main_window, 'is_dark_mode', True)
        self._is_dark = is_dark

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self._build_main_page()
        self._build_security_page()
        self._build_cookies_page()

        self._stack.setCurrentIndex(0)
        self._apply_style()

    def _build_main_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel(f"Site info for <b>{self._url_str[:50]}</b>")
        title.setObjectName("headerTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        btn_sec = self._make_category_btn(
            "Security status",
            "Connection security, certificate, and privacy",
            lambda: self._stack.setCurrentIndex(1)
        )
        layout.addWidget(btn_sec)

        btn_cookie = self._make_category_btn(
            "Cookies and website data",
            "Third-party cookie blocking and site data",
            lambda: self._stack.setCurrentIndex(2)
        )
        layout.addWidget(btn_cookie)

        layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        self._style_button(close_btn, accent=True)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._stack.addWidget(page)

    def _make_category_btn(self, title, desc, callback):
        btn = QPushButton()
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        muted = "#888E99" if self._is_dark else "#676D78"
        btn.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                padding: 10px 12px; text-align: left;
            }
        """)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(12)
        t = QLabel(f"<b>{title}</b><br><span style='color:{muted};font-size:11px;'>{desc}</span>")
        t.setTextFormat(Qt.TextFormat.RichText)
        t.setWordWrap(True)
        btn_layout.addWidget(t, 1)
        arrow = QLabel("\u276F")
        arrow.setStyleSheet(f"color: {muted}; font-size: 15px; background: transparent;")
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        btn_layout.addWidget(arrow, 0)
        btn.setLayout(btn_layout)
        return btn

    def _build_security_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        back_btn = QPushButton("\u2190  Security status")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        back_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 13px; font-weight: 600; text-align: left; padding: 0; }")
        layout.addWidget(back_btn)

        card = QFrame()
        card.setObjectName("infoCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)

        status_text = "Secure connection" if self._is_secure else "Not secure"
        color = "#22C55E" if self._is_secure else "#EF4444"
        status_lbl = QLabel(f"<b style='color:{color}'>\u2713 {status_text}</b>")
        status_lbl.setTextFormat(Qt.TextFormat.RichText)
        cl.addWidget(status_lbl)

        detail = ("This website has a valid SSL/TLS certificate and "
                  "encrypts traffic between your browser and the server."
                  if self._is_secure else
                  "This website does not use a secure connection. "
                  "Information sent over this connection could be intercepted.")
        detail_lbl = QLabel(detail)
        detail_lbl.setWordWrap(True)
        detail_lbl.setObjectName("detailText")
        cl.addWidget(detail_lbl)

        more_info = QLabel('<a href="https://support.google.com/chrome/answer/95617" style="color: #558EFF;">More info</a>')
        more_info.setOpenExternalLinks(True)
        more_info.setObjectName("linkText")
        cl.addWidget(more_info)

        cert_btn = QPushButton("Certificate")
        cert_btn.clicked.connect(self._show_certificate)
        self._style_button(cert_btn)
        cl.addWidget(cert_btn, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(card)
        layout.addStretch()

        self._stack.addWidget(page)

    def _build_cookies_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        back_btn = QPushButton("\u2190  Cookies and website data")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        back_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 13px; font-weight: 600; text-align: left; padding: 0; }")
        layout.addWidget(back_btn)

        card = QFrame()
        card.setObjectName("infoCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)

        desc = QLabel("Control how cookies and site data are handled for "
                      "this website. Blocking may break some site features.")
        desc.setWordWrap(True)
        desc.setObjectName("detailText")
        cl.addWidget(desc)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(8)
        toggle_label = QLabel("Block third-party cookies")
        toggle_label.setObjectName("rowTitle")
        self._toggle = SettingsToggle()
        self._toggle.setChecked(getattr(self._main_window, '_block_third_party_cookies', False))
        self._toggle.toggled.connect(self._on_toggle_cookies)
        toggle_row.addWidget(toggle_label, 1)
        toggle_row.addWidget(self._toggle, 0)
        cl.addLayout(toggle_row)

        layout.addWidget(card)
        layout.addStretch()

        self._stack.addWidget(page)

    def _on_toggle_cookies(self, checked):
        self._main_window._block_third_party_cookies = checked
        cs = self._main_window._get_cookie_store()
        if checked:
            cs.setCookieFilter(self._main_window._cookie_filter)
        else:
            cs.setCookieFilter(lambda req: True)

    def _show_certificate(self):
        from PySide6.QtWidgets import QMessageBox
        if self._is_secure:
            QMessageBox.information(self, "Certificate",
                "HoverNet uses Chromium's lightweight certificate handling.\n\n"
                "Full certificate viewer is not available in this build.\n"
                f"Connection: {self._url_str}")
        else:
            QMessageBox.information(self, "Certificate",
                "No certificate available \u2014 the connection is not secure.")

    def _style_button(self, btn, accent=False):
        r, g, b = self._accent_rgb
        is_dark = self._is_dark
        if accent:
            bg = f"rgba({r},{g},{b},180)"
            hover = f"rgba({r},{g},{b},220)"
        else:
            mr, mg, mb = max(r//4, 14), max(g//4, 14), max(b//4, 14)
            bg = f"rgba({mr+10},{mg+10},{mb+10},160)" if is_dark else "#e8e8f0"
            hover = f"rgba({r},{g},{b},30)" if is_dark else f"rgba({r},{g},{b},15)"
        text = "#ffffff" if is_dark else "#000000"
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {text}; border: none;
                border-radius: 6px; padding: 6px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {hover}; }}
        """)

    def _apply_style(self):
        r, g, b = self._accent_rgb
        is_dark = self._is_dark
        dr, dg, db = max(r//6, 8), max(g//6, 8), max(b//6, 8)
        mr, mg, mb = max(r//4, 14), max(g//4, 14), max(b//4, 14)
        bg = f"rgb({dr},{dg},{db})" if is_dark else "#f0f0f5"
        card_bg = f"rgba({mr+5},{mg+5},{mb+5},255)" if is_dark else "#ffffff"
        text = "#ffffff" if is_dark else "#000000"
        muted = "#888E99" if is_dark else "#676D78"
        border = f"rgba({r//3},{g//3},{b//3},120)" if is_dark else "#d0d0d8"
        self.setStyleSheet(f"""
            SiteInfoDialog {{
                background-color: {bg};
            }}
            QLabel#headerTitle {{
                color: {text}; font-size: 14px; background: transparent; font-weight: 400;
            }}
            QLabel#detailText {{
                color: {muted}; font-size: 11px; background: transparent; line-height: 1.4;
            }}
            QLabel#linkText {{
                font-size: 11px; background: transparent;
            }}
            QLabel#rowTitle {{
                color: {text}; font-size: 12px; font-weight: 600; background: transparent;
            }}
            QFrame#infoCard {{
                background: {card_bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
        """)
