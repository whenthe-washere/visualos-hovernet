from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea,
    QListWidget, QListWidgetItem
)
from ..core.browser import BrowserView

class HistoryView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setObjectName("historyPage")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar to switch between browsing history and download history.
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("historySidebar")
        self.sidebar.setFixedWidth(170)
        self.sidebar.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.sidebar.setSpacing(4)
        self.sidebar.setUniformItemSizes(True)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._item_browsing = QListWidgetItem("Browsing History")
        self._item_browsing.setToolTip("Browsing history")
        self.sidebar.addItem(self._item_browsing)
        self._item_downloads = QListWidgetItem("Download History")
        self._item_downloads.setToolTip("Download history")
        self.sidebar.addItem(self._item_downloads)
        self.sidebar.currentRowChanged.connect(self._switch_view)
        layout.addWidget(self.sidebar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setObjectName("historyScroll")

        container = QWidget()
        container.setObjectName("historyContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setSpacing(20)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.title_label = QLabel("Browsing History")
        self.title_label.setObjectName("historyTitle")
        self.title_label.setWordWrap(True)
        container_layout.addWidget(self.title_label)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.history_list.setUniformItemSizes(True)
        self.history_list.setSpacing(6)
        self.history_list.setWordWrap(True)
        container_layout.addWidget(self.history_list)

        self.download_list = QListWidget()
        self.download_list.setObjectName("downloadList")
        self.download_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.download_list.setUniformItemSizes(True)
        self.download_list.setSpacing(6)
        self.download_list.setWordWrap(True)
        self.download_list.setVisible(False)
        container_layout.addWidget(self.download_list)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        self.apply_styles()
        self.refresh()
        self.sidebar.setCurrentRow(0)

    def apply_styles(self):
        is_dark = getattr(self.main_window, 'is_dark_mode', True) if self.main_window else True
        r, g, b = (85, 142, 255)
        if self.main_window and hasattr(self.main_window, 'get_accent_rgb'):
            r, g, b = self.main_window.get_accent_rgb()

        # Accent-derived dark shades
        dr, dg, db = max(r//6, 8), max(g//6, 8), max(b//6, 8)
        mr, mg, mb = max(r//4, 14), max(g//4, 14), max(b//4, 14)

        bg_page = f"rgb({dr},{dg},{db})" if is_dark else "#f0f0f5"
        bg_container_start = f"rgb({dr},{dg},{db})" if is_dark else "#f0f0f5"
        bg_container_end = f"rgba({mr},{mg},{mb},180)" if is_dark else f"rgba({r}, {g}, {b}, 15)"
        text_title = "#ffffff" if is_dark else "#000000"
        text_list = "#DEE9FF" if is_dark else "#343945"
        bg_item = f"rgba({mr+5},{mg+5},{mb+5},255)" if is_dark else "rgba(255, 255, 255, 255)"

        sidebar_bg = f"rgba({mr},{mg},{mb},90)" if is_dark else "rgba(255,255,255,200)"
        sidebar_item = f"rgba({mr+4},{mg+4},{mb+4},200)" if is_dark else "rgba(255,255,255,220)"
        sidebar_item_hover = f"rgba({r},{g},{b},45)" if is_dark else f"rgba({r},{g},{b},25)"
        sidebar_item_sel = f"rgba({r},{g},{b},70)" if is_dark else f"rgba({r},{g},{b},45)"
        sidebar_text = "#DEE9FF" if is_dark else "#343945"
        sidebar_text_sel = "#ffffff" if is_dark else "#000000"

        self.setStyleSheet(f"""
            QWidget#historyPage {{ background-color: {bg_page}; }}
            QWidget#historyContainer {{ background: qlineargradient(x1:0, y1:0, x0:0, y1:1, stop:0 {bg_container_start}, stop:1 {bg_container_end}); }}
            QLabel#historyTitle {{ color: {text_title}; font-size: 30px; font-weight: 800; background: transparent; }}
            QListWidget#historyList, QListWidget#downloadList {{ border: none; background: transparent; color: {text_list}; }}
            QListWidget#historyList::item, QListWidget#downloadList::item {{ padding: 16px; margin: 0; border-radius: 12px; background: {bg_item}; border: 1px solid rgba({r}, {g}, {b}, 30); }}
            QListWidget#historyList::item:selected, QListWidget#downloadList::item:selected {{ background: rgba({r}, {g}, {b}, 30); color: {text_title}; }}
            QListWidget#historySidebar {{
                background: {sidebar_bg}; border: none; color: {sidebar_text};
                padding: 12px 8px; outline: none;
            }}
            QListWidget#historySidebar::item {{
                padding: 10px 12px; margin: 2px 0; border-radius: 8px;
                background: {sidebar_item}; font-size: 12px; font-weight: 600;
            }}
            QListWidget#historySidebar::item:hover {{ background: {sidebar_item_hover}; }}
            QListWidget#historySidebar::item:selected {{
                background: {sidebar_item_sel}; color: {sidebar_text_sel};
                border: 1px solid rgba({r}, {g}, {b}, 90);
            }}
        """)

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        for child in self.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
            child.update()

    def _switch_view(self, row):
        show_downloads = row == 1
        self.history_list.setVisible(not show_downloads)
        self.download_list.setVisible(show_downloads)
        self.title_label.setText("Download History" if show_downloads else "Browsing History")

    def refresh(self):
        self._refresh_browsing()
        self._refresh_downloads()

    def _refresh_browsing(self):
        self.history_list.clear()
        items = self._collect_history_items()
        if not items:
            empty = QListWidgetItem("No browsing history is available.")
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.history_list.addItem(empty)
            return

        for title, url in items:
            label = f"{title}\n{url}"
            item = QListWidgetItem(label)
            item.setToolTip(url)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.history_list.addItem(item)

    def _refresh_downloads(self):
        self.download_list.clear()
        downloads = getattr(self.main_window, '_downloads', [])
        if not downloads:
            empty = QListWidgetItem("No download history is available.")
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.download_list.addItem(empty)
            return

        for entry in downloads:
            filename = entry.get("filename", "Unknown file")
            status = entry.get("status", "")
            path = entry.get("path", "")
            label = f"{filename}\n{status}\n{path}"
            item = QListWidgetItem(label)
            item.setToolTip(path or filename)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.download_list.addItem(item)

    def _collect_history_items(self):
        seen_urls = set()
        entries = []
        for idx in range(self.main_window.browser_area.count()):
            widget = self.main_window.browser_area.widget(idx)
            if isinstance(widget, BrowserView):
                history = widget.history()
                for item in history.items():
                    url = item.url().toString()
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        entries.append((item.title() or url, url))
        return entries
