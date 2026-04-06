# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ExternalMapsTool
                                 A QGIS plugin
 Loads external WFS map layers from Belgian government geodata APIs
                             -------------------
        begin                : 2026-03-06
        copyright            : (C) 2026 by Hamza BOUHALI & Musa HAROUNA / M.designsolutions
        email                : info@mdesignsolutions.be
 ***************************************************************************/
"""


def classFactory(iface):
    from .external_maps_tool import ExternalMapsTool
    return ExternalMapsTool(iface)
