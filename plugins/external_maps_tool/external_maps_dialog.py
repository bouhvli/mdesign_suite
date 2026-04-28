# -*- coding: utf-8 -*-
"""
External Maps dock widget.
Sticks to the side panel (like ImageIdentifyTool) and lets the user
select which WFS layers to load before committing.
"""

from qgis.PyQt.QtWidgets import (  # type: ignore
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QCheckBox, QToolButton, QLabel, QFrame,
    QPushButton, QScrollArea, QSizePolicy
)
from qgis.PyQt.QtCore import Qt, pyqtSignal  # type: ignore
from qgis.PyQt.QtGui import QFont  # type: ignore


# ── Layer catalogue ────────────────────────────────────────────────────────────
LAYER_CATALOGUE = [
    {
        "key": "grb_adp",
        "name": "GRB - ADP - administratief perceel",
        "description": (
            "<b>Source:</b> Geographical Reference Base (GRB), Digital Flanders<br><br>"
            "Shows all official administrative land parcels across Flanders. "
            "Use this layer to check property boundaries along the cable route "
            "and identify parcel owners when planning trench paths."
        ),
    },
    {
        "key": "beschermde_monumenten",
        "name": "Beschermde monumenten",
        "description": (
            "<b>Source:</b> Mercator, Flanders Heritage Agency (Agentschap Onroerend Erfgoed)<br><br>"
            "Protected heritage monuments and archaeological sites. "
            "Construction near these areas may require special permits or must avoid "
            "disturbing the protected zone entirely."
        ),
    },
    {
        "key": "verkavelingen",
        "name": "Omgevingsloket - Verkavelingen - V2",
        "description": (
            "<b>Source:</b> Omgevingsloket, Flanders Environment Agency<br><br>"
            "Land subdivision permits colour-coded by current status:<br>"
            "&nbsp;&nbsp;● <span style='color:#32CD32'>Green</span> — Permit approved<br>"
            "&nbsp;&nbsp;● <span style='color:#FFD700'>Yellow</span> — Under consideration, first instance<br>"
            "&nbsp;&nbsp;● <span style='color:#FFA500'>Orange</span> — Under consideration, after appeal<br>"
            "&nbsp;&nbsp;● <span style='color:#FF0000'>Red</span> — Refused<br>"
            "&nbsp;&nbsp;● <span style='color:#9370DB'>Purple</span> — Discontinued<br>"
            "&nbsp;&nbsp;● <span style='color:#D3D3D3'>Grey</span> — No decision yet"
        ),
    },
    {
        "key": "gipod",
        "name": "GIPOD - inname openbaar domein",
        "description": (
            "<b>Source:</b> GIPOD, Digital Flanders<br><br>"
            "Public domain occupation records, filtered to groundwork (<i>Grondwerk</i>) only. "
            "Colour-coded by recency and status:<br>"
            "&nbsp;&nbsp;● <span style='color:#FF0000'>Red</span> — Completed, closed within last 5 years<br>"
            "&nbsp;&nbsp;● <span style='color:#FFD700'>Yellow</span> — Completed, older than 5 years<br>"
            "&nbsp;&nbsp;● <span style='color:#32CD32'>Green</span> — Ongoing or planned<br><br>"
            "Essential for detecting recent underground works."
        ),
    },
    {
        "key": "grb_wgo",
        "name": "GRB - WGO - wegopdeling",
        "description": (
            "<b>Source:</b> Geographical Reference Base (GRB), Digital Flanders<br><br>"
            "Road segment divisions from the official Flemish reference base. "
            "Shows road type classifications and spatial extents — useful for "
            "understanding which roads your cable route crosses."
        ),
    },
]


# ── Collapsible description ────────────────────────────────────────────────────

class CollapsibleDescription(QWidget):
    """A toggle button that reveals / hides a styled description label."""

    def __init__(self, html_description, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 0, 0, 2)
        layout.setSpacing(0)

        self._toggle = QToolButton()
        self._toggle.setArrowType(Qt.RightArrow)
        self._toggle.setText("  About this layer")
        self._toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.setStyleSheet(
            "QToolButton { border: none; color: #666; font-size: 11px; padding: 1px 0; }"
            "QToolButton:hover { color: #1a6fbf; }"
        )
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle)

        self._panel = QLabel(html_description)
        self._panel.setWordWrap(True)
        self._panel.setTextFormat(Qt.RichText)
        self._panel.setVisible(False)
        self._panel.setStyleSheet(
            "QLabel {"
            "  background-color: #f7f9fc;"
            "  border-left: 3px solid #4a90d9;"
            "  padding: 7px 10px;"
            "  color: #333;"
            "  font-size: 11px;"
            "  margin-top: 2px;"
            "}"
        )
        layout.addWidget(self._panel)

    def _on_toggled(self, checked):
        self._toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self._panel.setVisible(checked)


# ── Dock widget ────────────────────────────────────────────────────────────────

class ExternalMapsDockWidget(QDockWidget):
    """Side-panel dock for selecting and loading external WFS layers."""

    load_requested = pyqtSignal(list)   # emits list[str] of selected keys

    def __init__(self, parent=None):
        super().__init__("External Maps", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._checkboxes = {}   # key → QCheckBox
        self._build_ui()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # Header label
        header = QLabel("Select layers to load:")
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        header.setFont(font)
        header.setStyleSheet("color: #1a1a1a; margin-bottom: 4px;")
        root.addWidget(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 4, 0)
        cl.setSpacing(4)

        for entry in LAYER_CATALOGUE:
            cl.addWidget(self._make_layer_row(entry))

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("margin: 4px 0;")
        root.addWidget(sep)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setCursor(Qt.PointingHandCursor)
        self._select_all_btn.setStyleSheet(self._flat_style())
        self._select_all_btn.clicked.connect(self._toggle_all)
        btn_row.addWidget(self._select_all_btn)

        btn_row.addStretch()

        load_btn = QPushButton("Load Selected")
        load_btn.setCursor(Qt.PointingHandCursor)
        load_btn.setStyleSheet(self._primary_style())
        load_btn.clicked.connect(self._on_load)
        btn_row.addWidget(load_btn)

        root.addLayout(btn_row)
        self.setWidget(container)

    def _make_layer_row(self, entry):
        card = QFrame()
        card.setStyleSheet(
            "QFrame { border: 1px solid #dde3ea; border-radius: 4px;"
            " background: white; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 7, 8, 5)
        layout.setSpacing(2)

        cb = QCheckBox(entry["name"])
        cb.setChecked(True)
        cb_font = QFont()
        cb_font.setPointSize(9)
        cb.setFont(cb_font)
        cb.setStyleSheet("QCheckBox { color: #1a1a1a; }")
        self._checkboxes[entry["key"]] = cb
        layout.addWidget(cb)

        layout.addWidget(CollapsibleDescription(entry["description"]))
        return card

    # ── Slots ──────────────────────────────────────────────────────────────────

    def _toggle_all(self):
        all_on = all(cb.isChecked() for cb in self._checkboxes.values())
        for cb in self._checkboxes.values():
            cb.setChecked(not all_on)
        self._select_all_btn.setText("Deselect All" if not all_on else "Select All")

    def _on_load(self):
        keys = self.get_selected_keys()
        if keys:
            self.load_requested.emit(keys)

    def get_selected_keys(self):
        return [k for k, cb in self._checkboxes.items() if cb.isChecked()]

    # ── Styles ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _primary_style():
        return (
            "QPushButton { background:#1a6fbf; color:white; border:none;"
            " border-radius:4px; padding:5px 12px; font-size:12px; }"
            "QPushButton:hover { background:#1558a0; }"
            "QPushButton:pressed { background:#0e4480; }"
        )

    @staticmethod
    def _flat_style():
        return (
            "QPushButton { background:#f0f0f0; color:#333; border:1px solid #ccc;"
            " border-radius:4px; padding:5px 10px; font-size:12px; }"
            "QPushButton:hover { background:#e0e0e0; }"
        )
