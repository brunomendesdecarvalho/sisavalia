"""Evita que a roda do mouse mude combos/spins sem o usuário querer."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QComboBox, QAbstractSpinBox, QWidget,
)


class WheelGuard(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Wheel:
            return False
        if not isinstance(obj, (QComboBox, QAbstractSpinBox)):
            return False
        if isinstance(obj, QComboBox) and obj.view().isVisible():
            return False
        scroll = self._scroll_area(obj)
        if scroll is not None:
            delta = event.angleDelta().y()
            if delta:
                bar = scroll.verticalScrollBar()
                bar.setValue(bar.value() - int(delta * 0.5))
        event.accept()
        return True

    @staticmethod
    def _scroll_area(widget: QWidget) -> QAbstractScrollArea | None:
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                return parent
            parent = parent.parentWidget()
        return None


def install_wheel_guard(app: QApplication) -> None:
    if app.property("sisavalia_wheel_guard_installed"):
        return
    guard = WheelGuard()
    guard.setParent(app)
    app.installEventFilter(guard)
    app.setProperty("sisavalia_wheel_guard_installed", True)
