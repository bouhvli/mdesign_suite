# coding=utf-8
import unittest

from .utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from qgis.core import QgsVectorLayer, QgsWkbTypes, QgsField
from qgis.PyQt.QtCore import QVariant

from survey_app.survey_app import SurveyApp


class ApplySurveyedSymbologyTest(unittest.TestCase):
    """Tests for apply_surveyed_symbology method."""

    def setUp(self):
        self.iface = IFACE
        self.app = SurveyApp(self.iface)

    def _make_memory_layer(self, geom_type: str, name: str):
        vl = QgsVectorLayer(f"{geom_type}?crs=EPSG:4326", name, "memory")
        prov = vl.dataProvider()
        prov.addAttributes([QgsField("SURVEYED", QVariant.Bool)])
        vl.updateFields()
        return vl

    def test_returns_when_layer_invalid(self):
        # Create an invalid layer by passing None
        self.app.apply_surveyed_symbology(None)
        # Nothing to assert; just ensure no exception occurs
        self.assertTrue(True)

    def test_applies_rule_based_renderer_for_polygon(self):
        layer = self._make_memory_layer("Polygon", "poly")
        self.app.apply_surveyed_symbology(layer)
        renderer = layer.renderer()
        self.assertEqual(renderer.type(), "rule-based")
        # Expect two rules: surveyed and not surveyed
        root = renderer.rootRule()
        children = root.children()
        self.assertEqual(len(children), 2)
        labels = sorted([r.label() for r in children])
        self.assertEqual(labels, ["Not Surveyed", "Surveyed"])

    def test_applies_rule_based_renderer_for_line(self):
        layer = self._make_memory_layer("LineString", "line")
        self.app.apply_surveyed_symbology(layer)
        renderer = layer.renderer()
        self.assertEqual(renderer.type(), "rule-based")
        root = renderer.rootRule()
        children = root.children()
        self.assertEqual(len(children), 2)

    def test_applies_rule_based_renderer_for_point(self):
        layer = self._make_memory_layer("Point", "pt")
        self.app.apply_surveyed_symbology(layer)
        renderer = layer.renderer()
        self.assertEqual(renderer.type(), "rule-based")
        root = renderer.rootRule()
        children = root.children()
        self.assertEqual(len(children), 2)

    def test_rule_filters_match_surveyed_logic(self):
        layer = self._make_memory_layer("Point", "pt2")
        self.app.apply_surveyed_symbology(layer)
        renderer = layer.renderer()
        root = renderer.rootRule()
        children = root.children()
        # Map labels to filter expressions
        label_to_expr = {r.label(): r.filterExpression() for r in children}
        self.assertIn('"SURVEYED" = 1', label_to_expr.values())
        self.assertIn('"SURVEYED" = 0 OR "SURVEYED" IS NULL', label_to_expr.values())


if __name__ == "__main__":
    suite = unittest.makeSuite(ApplySurveyedSymbologyTest)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
