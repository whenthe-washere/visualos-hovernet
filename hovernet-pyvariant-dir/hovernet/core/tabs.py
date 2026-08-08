import math
import os
from PySide6.QtCore import Qt, QSize, QPoint, QRect, QEvent, QTimer

from PySide6.QtWidgets import (
    QTabBar, QScrollArea, QFrame, QProxyStyle, QStyle, QApplication,
    QWidget, QAbstractButton
)
from PySide6.QtGui import QIcon, QPainter, QColor, QPen, QBrush, QLinearGradient, QCursor, QPainterPath

from ..utils.easing import linear_out, linear_in


def tab_bar_path(x, y, w, h, tl, tr, bl, br):
    """Rounded-rect path with independent corner radii (for adaptive tab bars)."""
    path = QPainterPath()
    path.moveTo(x + tl, y)
    path.lineTo(x + w - tr, y)
    path.arcTo(x + w - 2 * tr, y, 2 * tr, 2 * tr, 90.0, -90.0)
    path.lineTo(x + w, y + h - br)
    path.arcTo(x + w - 2 * br, y + h - 2 * br, 2 * br, 2 * br, 0.0, -90.0)
    path.lineTo(x + bl, y + h)
    path.arcTo(x, y + h - 2 * bl, 2 * bl, 2 * bl, -90.0, -90.0)
    path.lineTo(x, y + tl)
    path.arcTo(x, y, 2 * tl, 2 * tl, 180.0, -90.0)
    path.closeSubpath()
    return path


class ShiftedRightButtonStyle(QProxyStyle):
    """Shifts the standard-mode close button left so it visually aligns with
    the tab's rounded outline (matching the adaptive bar's inner corner)."""

    def subElementRect(self, element, option, widget=None):
        rect = super().subElementRect(element, option, widget)
        if element == QStyle.SubElement.SE_TabBarTabRightButton and isinstance(widget, CustomTabBar):
            rect.translate(-8, 0)
        return rect


class CustomTabBar(QTabBar):
    def __init__(self, main_window=None):
        super().__init__(main_window)
        self.main_window = main_window
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setAutoFillBackground(False)
        self.setStyle(ShiftedRightButtonStyle())
        self.setStyleSheet("QTabBar { background: transparent; qproperty-drawBase: 0; }")
        self.tabCloseRequested.connect(self.close_tab)
        self.tabMoved.connect(self._on_tab_moved)
        
        self._compact_mode = False
        self._hovered_index = -1
        # Compact expansion is delay-gated: hovering a tab first shows only its
        # close button; the width animation + title start once the delay
        # elapses, and a new tab cannot start expanding until the previously
        # hovered tab's shrink delay has ended (fast hover would otherwise
        # animate the contents before the tab bar finishes expanding).
        self._compact_hover_delay = 50
        self._expand_pending_index = -1
        self._expanded_index = -1
        self._shrink_pending = False
        self._expand_timer = QTimer(self)
        self._expand_timer.setSingleShot(True)
        self._expand_timer.timeout.connect(self._on_expand_delay_elapsed)
        self._shrink_timer = QTimer(self)
        self._shrink_timer.setSingleShot(True)
        self._shrink_timer.timeout.connect(self._on_shrink_delay_elapsed)
        self._dragging = False
        self._drag_from_text = None
        self._drag_offset = QPoint()
        self._drag_base_rect = QRect()
        self._press_pos = QPoint()
        self._press_index = -1
        # Title/icon changes while a drag is in progress would relayout the
        # native slot rects under the moving-tab pixmap, making its stale
        # snapshot overlap the relaid-out neighbor labels. Buffer them and
        # apply once the drag ends.
        self._pending_text_updates = {}
        self._pending_icon_updates = {}
        self.setMouseTracking(True)
        
        self._current_widths = {}
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_animations)
        self._anim_timer.setInterval(16)

        # Enter/exit tab animations (per-tab linear time 0..1). Any tab that is
        # created animates in (linear + ease-out); closing tabs animate out
        # (linear + ease-in) before the underlying widget is removed.
        self._enter_progress = {}
        self._exit_progress = {}
        self._anim_step = 1.0 / 14.0

        # Tab index -> download completion percentage (0..100). Drawn as a
        # progress outline around the tab while a minimized download is active.
        self._download_progress = {}

    def addTab(self, *args, **kwargs):
        idx = super().addTab(*args, **kwargs)
        self._enter_progress[idx] = 0.0
        self._exit_progress.pop(idx, None)
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        return idx

    def removeTab(self, index):
        super().removeTab(index)
        self._enter_progress.pop(index, None)
        self._exit_progress.pop(index, None)
        self._remap_animation_progress(index)
        self._expanded_index = self._shift_down_index(self._expanded_index, index)
        self._expand_pending_index = self._shift_down_index(self._expand_pending_index, index)
        self._pending_text_updates.pop(index, None)
        self._pending_icon_updates.pop(index, None)
        self._pending_text_updates = {
            (i - 1 if i > index else i): t
            for i, t in self._pending_text_updates.items()
        }
        self._pending_icon_updates = {
            (i - 1 if i > index else i): t
            for i, t in self._pending_icon_updates.items()
        }
        self._download_progress = {
            (i - 1 if i > index else i): p
            for i, p in self._download_progress.items() if i != index
        }

    @staticmethod
    def _shift_down_index(idx, removed_index):
        if idx < 0:
            return idx
        if idx == removed_index:
            return -1
        return idx - 1 if idx > removed_index else idx

    def setTabText(self, index, text):
        if self._dragging:
            self._pending_text_updates[index] = text
            return
        super().setTabText(index, text)

    def setTabIcon(self, index, icon):
        if self._dragging:
            self._pending_icon_updates[index] = icon
            return
        super().setTabIcon(index, icon)

    def _remap_animation_progress(self, removed_index):
        shifted = {}
        for i, t in self._enter_progress.items():
            shifted[i - 1 if i > removed_index else i] = t
        self._enter_progress = shifted
        shifted = {}
        for i, t in self._exit_progress.items():
            shifted[i - 1 if i > removed_index else i] = t
        self._exit_progress = shifted

    def _refresh_hover(self):
        """Re-derive the hovered tab from the actual cursor position. During
        width animation the tab layout lags the mouse (relayout is deferred),
        so a mousemove can land in a stale-layout window and pin the wrong
        tab. Re-checking here, once the geometry has settled, keeps the hover
        under the cursor correct even when the mouse is no longer moving."""
        if not self.compact_mode or not self.underMouse():
            return False
        pos = self.mapFromGlobal(QCursor.pos())
        idx = self.tabAt(pos)
        if idx != self._hovered_index:
            self._hovered_index = idx
            self._update_compact_expansion()
            self._notify_tab_hovered(idx)
            return True
        return False

    def _notify_tab_hovered(self, index):
        if self.main_window and hasattr(self.main_window, '_on_tab_hovered'):
            self.main_window._on_tab_hovered(index)

    def _update_compact_expansion(self):
        """Apply the compact hover delay whenever the hovered tab changes. The
        pending expansion is held back while a shrink delay is in progress, so
        tabs only ever start expanding once the previous tab's shrinking delay
        has ended."""
        if not self.compact_mode:
            return
        self._expand_timer.stop()
        idx = self._hovered_index
        if idx == -1 or idx >= self.count():
            self._expand_pending_index = -1
            if self._expanded_index != -1 and not self._shrink_timer.isActive():
                self._shrink_pending = True
                self._shrink_timer.start(self._compact_hover_delay)
            return
        self._expand_pending_index = idx
        if self._expanded_index != -1 and self._expanded_index != idx:
            # cursor moved onto another tab: shrink the current one first and
            # hold this expansion until that shrink delay has ended
            if not self._shrink_timer.isActive():
                self._shrink_pending = True
                self._shrink_timer.start(self._compact_hover_delay)
            return
        if self._shrink_pending or self._expanded_index == idx:
            return
        self._expand_timer.start(self._compact_hover_delay)

    def _on_expand_delay_elapsed(self):
        if not self.compact_mode:
            return
        idx = self._expand_pending_index
        if idx == -1 or idx >= self.count() or idx != self._hovered_index or self._shrink_pending:
            self._expand_pending_index = -1
            return
        self._expanded_index = idx
        self._expand_pending_index = -1
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        self.update()

    def _on_shrink_delay_elapsed(self):
        self._shrink_pending = False
        if self._expanded_index != -1 and self._expanded_index != self._hovered_index:
            self._expanded_index = -1
            if not self._anim_timer.isActive():
                self._anim_timer.start()
            self.update()
        # the lock is released: a held-back expansion may proceed now
        idx = self._expand_pending_index
        if idx != -1 and idx == self._hovered_index and idx != self._expanded_index:
            self._expand_timer.start(self._compact_hover_delay)

    def _update_animations(self):
        anim_active = False

        for i, t in list(self._enter_progress.items()):
            if i >= self.count():
                self._enter_progress.pop(i, None)
                continue
            t += self._anim_step
            if t >= 1.0:
                self._enter_progress.pop(i, None)
            else:
                self._enter_progress[i] = t
                anim_active = True

        for i, t in list(self._exit_progress.items()):
            t += self._anim_step
            if t >= 1.0:
                self._exit_progress.pop(i, None)
                self._finish_exit(i)
            else:
                self._exit_progress[i] = t
                anim_active = True

        compact_changed = False
        if self.compact_mode:
            self._refresh_hover()
            for i in range(self.count()):
                target = 36
                if i == self._expanded_index:
                    text = self.tabText(i)[:20]
                    tw = self.fontMetrics().horizontalAdvance(text)
                    target = 46 + tw

                cur = self._current_widths.get(i, 36)
                if abs(cur - target) > 0.5:
                    self._current_widths[i] = cur + (target - cur) * 0.3
                    compact_changed = True
                else:
                    self._current_widths[i] = target

        if anim_active or compact_changed:
            self.updateGeometry()
            self.update()
            p = self.parent()
            while p:
                if isinstance(p, CompactTabScrollArea):
                    p.updateGeometry()
                    break
                p = p.parent()
        elif self.compact_mode and self._refresh_hover():
            self.updateGeometry()
            self.update()
            return
        else:
            self._anim_timer.stop()

    @property
    def compact_mode(self):
        return getattr(self, '_compact_mode', False)

    @compact_mode.setter
    def compact_mode(self, value):
        self._compact_mode = value
        if value:
            self.setMouseTracking(True)
            self.setExpanding(False)
            self.setTabsClosable(False)
        else:
            self.setExpanding(True)
            self.setTabsClosable(True)
        if not value:
            self._expand_timer.stop()
            self._shrink_timer.stop()
            self._expand_pending_index = -1
            self._expanded_index = -1
            self._shrink_pending = False
        self.updateGeometry()
        self.update()

    def new_tab_requested(self):
        if self.main_window:
            self.main_window.add_tab()

    def close_tab(self, index):
        if index < 0 or index >= self.count():
            return
        if self._exit_progress:
            return  # only one exit animation at a time
        self._exit_progress[index] = 0.0
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _finish_exit(self, index):
        self._exit_progress.pop(index, None)
        if self.main_window:
            self.main_window.close_tab(index)

    def _has_active_tab_animation(self):
        return bool(self._enter_progress or self._exit_progress)

    def _tab_opacity(self, index):
        op = 1.0
        t = self._enter_progress.get(index, 1.0)
        op *= linear_out(t)
        t = self._exit_progress.get(index, 0.0)
        op *= 1.0 - linear_in(t)
        return max(0.0, min(1.0, op))

    def tab_width(self, index):
        return self.tabSizeHint(index).width()

    def tabSizeHint(self, index):
        if not self.compact_mode:
            return super().tabSizeHint(index)
            
        w = self._current_widths.get(index, 36)
        return QSize(int(w), 28)

    def mouseMoveEvent(self, event):
        # Support both Qt 5 (pos()) and Qt 6 (position())
        pos = event.pos() if hasattr(event, 'pos') else event.position().toPoint()
        if self._press_index != -1 and event.buttons() & Qt.MouseButton.LeftButton:
            # The dragged tab keeps a fixed offset from the cursor (matching the
            # native QTabBar), so the custom background bar follows it.
            self._drag_offset = pos - self._press_pos
            if not self._dragging and self._drag_offset.manhattanLength() >= QApplication.startDragDistance():
                self._dragging = True
                self._drag_index = self._press_index
                self._drag_base_rect = self.tabRect(self._drag_index)
                self.update()
        idx = self.tabAt(pos)
        if idx != self._hovered_index:
            self._hovered_index = idx
            self._notify_tab_hovered(idx)
            if self.compact_mode:
                self._update_compact_expansion()
                self.update()
                if not self._anim_timer.isActive():
                    self._anim_timer.start()
            else:
                self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hovered_index != -1:
            self._hovered_index = -1
            self._notify_tab_hovered(-1)
            if self.compact_mode:
                self._update_compact_expansion()
                self.update()
                if not self._anim_timer.isActive():
                    self._anim_timer.start()
            else:
                self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.compact_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos() if hasattr(event, 'pos') else event.position().toPoint()
            idx = self.tabAt(pos)
            if idx != -1 and idx == self._hovered_index:
                rect = self.tabRect(idx)
                close_rect = QRect(rect.x() + 10, rect.y() + (rect.height() - 16) // 2, 16, 16)
                if close_rect.contains(pos):
                    self.tabCloseRequested.emit(idx)
                    return
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos() if hasattr(event, 'pos') else event.position().toPoint()
            self._press_pos = pos
            self._press_index = self.tabAt(pos)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._dragging or self._press_index != -1:
            self._dragging = False
            self._drag_index = -1
            self._drag_offset = QPoint()
            self._drag_base_rect = QRect()
            self._press_index = -1
            self._press_pos = QPoint()
            self._flush_pending_updates()
            self.update()

    def _flush_pending_updates(self):
        """Apply title/icon changes that arrived mid-drag, now that the tab
        layout is settling. Indices were kept in sync through live reorders."""
        for idx, text in self._pending_text_updates.items():
            super().setTabText(idx, text)
        self._pending_text_updates.clear()
        for idx, icon in self._pending_icon_updates.items():
            super().setTabIcon(idx, icon)
        self._pending_icon_updates.clear()

    @staticmethod
    def _reordered_index(index, from_idx, to_idx):
        """Qt's calculateNewPosition: where a tab index ends up after the tab
        at from_idx is moved to to_idx (used to track the dragged tab and any
        buffered title/icon updates through live drag reorders)."""
        if index == from_idx:
            return to_idx
        start, end = min(from_idx, to_idx), max(from_idx, to_idx)
        if start <= index <= end:
            return index + (-1 if from_idx < to_idx else 1)
        return index

    def _on_tab_moved(self, from_idx, to_idx):
        """Track the dragged tab's index through the live reorders the native
        QTabBar performs during a drag, so its background keeps following the
        cursor instead of whatever tab happens to occupy the original slot."""
        if not self._dragging or self._drag_index == -1:
            return
        self._drag_index = self._reordered_index(self._drag_index, from_idx, to_idx)
        self._pending_text_updates = {
            self._reordered_index(i, from_idx, to_idx): t
            for i, t in self._pending_text_updates.items()
        }
        self._pending_icon_updates = {
            self._reordered_index(i, from_idx, to_idx): t
            for i, t in self._pending_icon_updates.items()
        }
        self._download_progress = {
            self._reordered_index(i, from_idx, to_idx): p
            for i, p in self._download_progress.items()
        }

    def set_download_progress_map(self, progress_map):
        self._download_progress = {
            int(k): max(0.0, min(100.0, float(v)))
            for k, v in progress_map.items()
        }
        self.update()

    def download_progress_map(self):
        return dict(self._download_progress)

    def _tab_paint_rect(self, index):
        """Rect to draw a tab's background/content at. The dragged tab is
        painted following the cursor (its original slot + horizontal drag
        offset) so the custom background stays glued to the moving tab
        content; tabs only slide horizontally like the native contents."""
        if self._dragging and index == self._drag_index:
            return QRect(self._drag_base_rect).translated(self._drag_offset.x(), 0)
        return self.tabRect(index)

    def _bar_radii(self, index, height):
        """Adaptive roundness: fully rounded on free sides, less rounded on any
        side that has a neighboring tab next to it. Direction-aware: compact
        mode lists tabs right-to-left, so the first tab sits on the right."""
        count = self.count()
        full = height / 2.0
        small = min(6.0, height / 2.0)
        if self._dragging and index == self._drag_index:
            # A dragged tab keeps full roundness on every corner while it is in
            # motion; adaptive radii are re-derived from its slot on drop.
            return full, full, full, full
        tl = tr = bl = br = small
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        if (index == count - 1) if rtl else (index == 0):
            tl = bl = full
        if (index == 0) if rtl else (index == count - 1):
            tr = br = full
        return tl, tr, bl, br

    def _draw_download_outlines(self, painter, accent_color):
        """Draw each tab's download progress as a partial border around the tab:
        a dim full border as the track plus an accent border whose dash pattern
        covers the completed fraction of the perimeter."""
        if not self._download_progress:
            return
        for i, pct in list(self._download_progress.items()):
            if i < 0 or i >= self.count():
                continue
            rect = self._tab_paint_rect(i)
            if not rect.isValid() or rect.width() <= 2 or rect.height() <= 2:
                continue
            bar = rect.adjusted(1, 1, -1, -1)
            tl, tr, bl, br = self._bar_radii(i, bar.height())
            path = tab_bar_path(bar.x(), bar.y(), bar.width(), bar.height(), tl, tr, bl, br)
            w, h = bar.width(), bar.height()
            total = 2 * (w + h) + (math.pi / 2 - 2) * (tl + tr + bl + br)
            if total <= 0:
                continue
            painter.save()
            painter.setOpacity(self._tab_opacity(i))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            track = QColor(accent_color)
            track.setAlpha(55)
            painter.setPen(QPen(track, 2))
            painter.drawPath(path)
            filled = total * (max(0.0, min(100.0, pct)) / 100.0)
            prog = QColor(accent_color)
            prog.setAlpha(235)
            pw = 2.5
            pen = QPen(prog, pw)
            if filled >= total - 0.5:
                painter.setPen(pen)
            else:
                # Qt dash values are multiplied by pen width internally, so
                # divide by pw to convert path-length → dash-pattern units.
                pen.setDashPattern([max(filled / pw, 0.01), max((total - filled) / pw, 0.01)])
                painter.setPen(pen)
            painter.drawPath(path)
            painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent_rgb = (85, 142, 255)
        if self.main_window and hasattr(self.main_window, 'get_accent_rgb'):
            accent_rgb = self.main_window.get_accent_rgb()
        accent_color = QColor(*accent_rgb)
        is_dark = getattr(self.main_window, 'is_dark_mode', True) if self.main_window else True

        # 1. Bar backgrounds for every tab (adaptive roundness). The dragged
        # tab is painted last so its background sits on top of neighbors.
        drag_i = self._drag_index if self._dragging else -1
        order = [i for i in range(self.count()) if i != drag_i]
        if drag_i != -1:
            order.append(drag_i)
        for i in order:
            rect = self._tab_paint_rect(i)
            if not rect.isValid() or rect.width() <= 0:
                continue
            bar = rect.adjusted(1, 1, -1, -1)
            if bar.width() <= 0 or bar.height() <= 0:
                continue
            if self._dragging:
                is_selected = (i == self._drag_index)
            else:
                is_selected = (i == self.currentIndex())
            is_hovered = (i == self._hovered_index)

            tl, tr, bl, br = self._bar_radii(i, bar.height())

            painter.save()
            painter.setOpacity(self._tab_opacity(i))
            has_dl = i in self._download_progress
            if is_selected and not has_dl:
                bg = QColor(accent_color)
                bg.setAlpha(45)
                painter.setBrush(bg)
                border = QColor(100, 100, 140, 70) if is_dark else QColor(100, 100, 140, 40)
                painter.setPen(QPen(border, 1.5))
            elif is_selected:
                # Active tab with a download: use inactive colours so the
                # accent download outline is clearly visible on top.
                bg = QColor(255, 255, 255, 13) if is_dark else QColor(0, 0, 0, 7)
                border = QColor(100, 100, 140, 70) if is_dark else QColor(100, 100, 140, 40)
                painter.setBrush(bg)
                painter.setPen(QPen(border, 1))
            elif is_hovered:
                bg = QColor(255, 255, 255, 24) if is_dark else QColor(0, 0, 0, 12)
                border = QColor(100, 100, 140, 110) if is_dark else QColor(100, 100, 140, 60)
                painter.setBrush(bg)
                painter.setPen(QPen(border, 1))
            else:
                bg = QColor(255, 255, 255, 13) if is_dark else QColor(0, 0, 0, 7)
                border = QColor(100, 100, 140, 70) if is_dark else QColor(100, 100, 140, 40)
                painter.setBrush(bg)
                painter.setPen(QPen(border, 1))
            painter.drawPath(tab_bar_path(bar.x(), bar.y(), bar.width(), bar.height(),
                                          tl, tr, bl, br))
            painter.restore()

        if self.compact_mode or self._has_active_tab_animation():
            # 2. Download progress outlines (compact/animation draw their own
            # content on top, so outlines must go here).
            self._draw_download_outlines(painter, accent_color)

            # Compact draws its own content always; standard draws it too while
            # a tab enter/exit animation is running so the text fades with the
            # bar instead of popping in at full opacity.
            for i in range(self.count()):
                rect = self._tab_paint_rect(i)
                if not rect.isValid() or rect.width() <= 0:
                    continue
                if self._dragging:
                    is_selected = (i == self._drag_index)
                else:
                    is_selected = (i == self.currentIndex())
                is_hovered = (i == self._hovered_index)
                painter.save()
                painter.setOpacity(self._tab_opacity(i))
                self._draw_tab_content(painter, i, rect, is_selected, is_hovered, is_dark)
                painter.restore()
            painter.end()
            return

        painter.end()
        super().paintEvent(event)

        # Standard mode: draw outlines AFTER the native painting so they sit
        # on top.  Also overlay an inactive border on selected tabs that have
        # a download so the accent progress outline is distinct.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        has_downloads = bool(self._download_progress)
        if has_downloads:
            cur = self._drag_index if self._dragging else self.currentIndex()
            if cur in self._download_progress:
                rect = self._tab_paint_rect(cur)
                if rect.isValid() and rect.width() > 2 and rect.height() > 2:
                    bar = rect.adjusted(1, 1, -1, -1)
                    tl, tr, bl, br = self._bar_radii(cur, bar.height())
                    path = tab_bar_path(bar.x(), bar.y(), bar.width(),
                                        bar.height(), tl, tr, bl, br)
                    painter.save()
                    painter.setOpacity(self._tab_opacity(cur))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    border = QColor(100, 100, 140, 70) if is_dark else QColor(100, 100, 140, 40)
                    painter.setPen(QPen(border, 2))
                    painter.drawPath(path)
                    painter.restore()
            self._draw_download_outlines(painter, accent_color)
        painter.end()

    def _draw_tab_content(self, painter, i, rect, is_selected, is_hovered, is_dark):
        font_metrics = painter.fontMetrics()

        if self.compact_mode:
            # Favicon / Close Button (compact shows the X in place of the icon
            # on hover)
            icon_rect = QRect(rect.x() + 10, rect.y() + (rect.height() - 16) // 2, 16, 16)
            if is_hovered:
                painter.save()
                mouse_pos = self.mapFromGlobal(QCursor.pos())
                is_over_close = icon_rect.contains(mouse_pos)

                if is_over_close:
                    painter.setPen(QPen(QColor(239, 68, 68), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                else:
                    close_col = QColor(255, 255, 255, 180) if is_dark else QColor(0, 0, 0, 150)
                    painter.setPen(QPen(close_col, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

                cx, cy = icon_rect.center().toTuple()
                painter.translate(cx, cy + 2)
                s = 4
                painter.drawLine(-s, -s, s, s)
                painter.drawLine(s, -s, -s, s)
                painter.restore()
            else:
                icon = self.tabIcon(i)
                if not icon.isNull():
                    icon.paint(painter, icon_rect)
                else:
                    painter.save()
                    painter.setBrush(QColor(135, 145, 170))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(icon_rect.center(), 3, 3)
                    painter.restore()

            # Compact title only appears once the tab is actually expanding
            # (after the hover delay); while merely hovered, only the close
            # button shows.
            if i != self._expanded_index:
                return
            text_x = rect.x() + 32
        else:
            # Standard content is only drawn by us while a tab animation runs;
            # otherwise the native QTabBar paints text/icons after our bars.
            icon_rect = QRect(rect.x() + 12, rect.y() + (rect.height() - 16) // 2, 16, 16)
            icon = self.tabIcon(i)
            if not icon.isNull():
                icon.paint(painter, icon_rect)
            else:
                painter.save()
                painter.setBrush(QColor(135, 145, 170))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(icon_rect.center(), 3, 3)
                painter.restore()
            text_x = rect.x() + 36

        painter.save()
        if is_dark:
            text_color = Qt.GlobalColor.white if is_selected else QColor("#A9B5CC")
        else:
            text_color = QColor(0, 0, 0) if is_selected else QColor("#434954")
        painter.setPen(text_color)

        text_y = rect.y() + (rect.height() + font_metrics.ascent() - font_metrics.descent()) // 2

        title = self.tabText(i)
        max_chars = 20
        if len(title) <= max_chars:
            painter.drawText(text_x, text_y, title)
        else:
            title_20 = title[:max_chars]
            prefix = title_20[:-3]
            suffix = title_20[-3:]

            painter.drawText(text_x, text_y, prefix)
            w_pref = font_metrics.horizontalAdvance(prefix)

            opacities = [0.7, 0.4, 0.1]
            for char, opacity in zip(suffix, opacities):
                painter.save()
                painter.setOpacity(painter.opacity() * opacity)
                painter.drawText(text_x + w_pref, text_y, char)
                painter.restore()
                w_pref += font_metrics.horizontalAdvance(char)
        painter.restore()


class CompactTabScrollArea(QScrollArea):
    def __init__(self, tab_bar, parent=None):
        super().__init__(parent)
        self.tab_bar = tab_bar
        self.setWidget(tab_bar)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")
        
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        
        self.horizontalScrollBar().valueChanged.connect(self.update_overlays)
        self.tab_bar.installEventFilter(self)

    def update_overlays(self):
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.tab_bar and (event.type() == QEvent.Type.LayoutRequest or event.type() == QEvent.Type.Resize):
            self.updateGeometry()
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.angleDelta().x()
        sb = self.horizontalScrollBar()
        scroll_amount = 30 if delta > 0 else -30
        sb.setValue(sb.value() - scroll_amount)
        event.accept()

    def sizeHint(self):
        if not self.tab_bar.compact_mode:
            return super().sizeHint()
            
        scroll_val = self.horizontalScrollBar().value()
        accum = 0
        start_idx = 0
        for i in range(self.tab_bar.count()):
            w = self.tab_bar.tab_width(i)
            if accum + w > scroll_val:
                start_idx = i
                break
            accum += w
            
        total_w = 0
        count = 0
        for i in range(start_idx, self.tab_bar.count()):
            total_w += self.tab_bar.tab_width(i)
            count += 1
            if count == 4:
                break
                
        if count < 4:
            total_w += (4 - count) * 36
            
        return QSize(total_w + 12, 28)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        super().paintEvent(event)
        
        if not self.tab_bar.compact_mode:
            return
            
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        sb = self.horizontalScrollBar()
        val = sb.value()
        max_val = sb.maximum()
        
        h = self.viewport().height()
        w = self.viewport().width()
        
        fade_color = QColor(30, 40, 60, 255)
        # Match current accent color if possible
        if self.tab_bar.main_window and hasattr(self.tab_bar.main_window, 'get_accent_rgb'):
            accent_rgb = self.tab_bar.main_window.get_accent_rgb()
            # Fade into the unified URL bar bg which is dark blue (30, 40, 60)
            fade_color = QColor(30, 40, 60, 255)
            
        transparent_color = QColor(fade_color.red(), fade_color.green(), fade_color.blue(), 0)
        
        fade_w = 16
        
        if val > 0:
            left_grad = QLinearGradient(0, 0, fade_w, 0)
            left_grad.setColorAt(0, fade_color)
            left_grad.setColorAt(1, transparent_color)
            painter.fillRect(0, 0, fade_w, h, left_grad)
            
        if val < max_val:
            right_grad = QLinearGradient(w - fade_w, 0, w, 0)
            right_grad.setColorAt(0, transparent_color)
            right_grad.setColorAt(1, fade_color)
            painter.fillRect(w - fade_w, 0, fade_w, h, right_grad)
