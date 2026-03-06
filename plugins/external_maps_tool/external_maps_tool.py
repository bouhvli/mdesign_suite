# -*- coding: utf-8 -*-
"""
External Maps Tool - QGIS plugin
Opens a side-panel dock (like ImageIdentifyTool) for selecting and loading
external WFS layers from Belgian government geodata APIs.
"""

import os
from qgis.PyQt.QtCore import QCoreApplication, Qt  # type: ignore
from qgis.PyQt.QtGui import QIcon  # type: ignore
from qgis.PyQt.QtWidgets import QAction, QMessageBox  # type: ignore
from qgis.core import Qgis  # type: ignore

from .utils.external_map_loader import add_external_wfs_layers
from .external_maps_dialog import ExternalMapsDockWidget


class ExternalMapsTool:
    """QGIS Plugin Implementation for loading external WFS map layers."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr(u'&External Maps Tool')

        self.dock_widget = None
        self.action = None

    def tr(self, message):
        return QCoreApplication.translate('ExternalMapsTool', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, status_tip=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        if status_tip is not None:
            action.setStatusTip(status_tip)
        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = self.add_action(
            icon_path,
            text=self.tr(u'External Maps'),
            callback=self.run,
            status_tip=self.tr(u'Open the External Maps panel'),
            parent=self.iface.mainWindow()
        )
        self.action.setCheckable(True)

        # Create the dock widget
        self.dock_widget = ExternalMapsDockWidget()
        self.dock_widget.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        # Connect signals
        self.dock_widget.load_requested.connect(self._do_load)
        self.dock_widget.visibilityChanged.connect(self._on_dock_visibility_changed)

    def get_actions(self):
        return self.actions

    def unload(self):
        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None

        for action in self.actions:
            self.iface.removePluginMenu(self.tr(u'&External Maps Tool'), action)

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _on_dock_visibility_changed(self, visible):
        if not visible and self.action:
            self.action.setChecked(False)

    def _do_load(self, selected_keys):
        self.log_message(f"Loading {len(selected_keys)} layer(s)...", "INFO")
        loaded, failed = add_external_wfs_layers(self.log_message, selected_keys=selected_keys)

        # Build confirmation message
        lines = []
        if loaded:
            lines.append(f"<b>{len(loaded)} layer(s) added to the project:</b>")
            lines += [f"&nbsp;&nbsp;✔ {name}" for name in loaded]
        if failed:
            if lines:
                lines.append("")
            lines.append(f"<b>{len(failed)} layer(s) failed to load:</b>")
            lines += [f"&nbsp;&nbsp;✘ {name}" for name in failed]

        msg = QMessageBox(self.iface.mainWindow())
        msg.setWindowTitle("External Maps — Load Complete")
        msg.setTextFormat(1)   # Qt.RichText
        msg.setText("<br>".join(lines))

        if failed and not loaded:
            msg.setIcon(QMessageBox.Critical)
        elif failed:
            msg.setIcon(QMessageBox.Warning)
        else:
            msg.setIcon(QMessageBox.Information)

        msg.exec_()

    def log_message(self, message, level="INFO"):
        level_map = {
            "INFO":    Qgis.Info,
            "SUCCESS": Qgis.Success,
            "WARNING": Qgis.Warning,
            "ERROR":   Qgis.Critical,
        }
        self.iface.messageBar().pushMessage(
            "External Maps", message,
            level=level_map.get(level, Qgis.Info),
            duration=4
        )

    def run(self):
        """Toggle the External Maps side panel."""
        if self.action.isChecked():
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
            self.dock_widget.show()
        else:
            self.dock_widget.hide()
