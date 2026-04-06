from qgis.core import (
    QgsProject, QgsSpatialIndex, QgsVectorLayer,
    QgsFeature, QgsField, QgsMarkerSymbol, QgsSingleSymbolRenderer
)
from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtTest import QTest


class FlagDesign:
    def __init__(self):
        self.changes = []
    
    def run_flag_operations(self):
        """Run all flagging operations"""
        self.changes = []
        print("Running flag operations...")
        return [self.flag_distribution_points()]

    def flag_distribution_points(
        self,
        dp_name='Distribution Points',
        ducts_name='Distribution Ducts',
        buffer=1.0,
        threshold=8
    ):
        """Flag DPs with too many intersecting ducts and create a flagged layer"""
        try:
            proj = QgsProject.instance()
            dp_layers = proj.mapLayersByName(dp_name)
            duct_layers = proj.mapLayersByName(ducts_name)

            if not dp_layers or not duct_layers:
                msg = f"Layers '{dp_name}' or '{ducts_name}' not found"
                print("ERROR:", msg)
                return {
                    'operation': 'flag_distribution_points',
                    'status': 'failed',
                    'error': msg
                }

            dp_layer, ducts_layer = dp_layers[0], duct_layers[0]

            # Create memory layer for flagged points
            flagged_layer = QgsVectorLayer(
                f"Point?crs={dp_layer.crs().authid()}",
                "Flagged Distribution Points",
                "memory"
            )
            provider = flagged_layer.dataProvider()

            fields = dp_layer.fields()
            fields.append(QgsField('duct_count', QVariant.Int))
            provider.addAttributes(fields)
            flagged_layer.updateFields()

            # spatial index 
            idx = QgsSpatialIndex()
            duct_geoms = {}
            for f in ducts_layer.getFeatures():
                g = f.geometry()
                if g and not g.isEmpty():
                    idx.insertFeature(f)
                    duct_geoms[f.id()] = g

            flagged_features = []
            for dp in dp_layer.getFeatures():
                g = dp.geometry()
                if not g or g.isEmpty():
                    continue

                buf = g.buffer(buffer, 5)
                cands = idx.intersects(buf.boundingBox())
                cnt = sum(
                    1 for fid in cands
                    if fid in duct_geoms and duct_geoms[fid].intersects(buf)
                )

                if cnt > threshold:
                    f_new = QgsFeature(flagged_layer.fields())
                    f_new.setGeometry(g)
                    f_new.setAttributes(dp.attributes() + [cnt])
                    flagged_features.append(f_new)
                    msg = f"Flagged DP {dp.id()} with {cnt} ducts"
                    print(msg)
                    self.changes.append(msg)

            if not flagged_features:
                print("No Distribution Points exceeded the threshold")
                return {
                    'operation': 'flag_distribution_points',
                    'status': 'completed',
                    'flagged_count': 0,
                    'flag_layer_id': None,
                    'flagged_ids': []
                }

            provider.addFeatures(flagged_features)
            flagged_layer.updateExtents()

            # Style
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'star',
                'color': '255,0,0',
                'size': '6',
                'outline_color': '0,0,0',
                'outline_width': '0.5'
            })
            flagged_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            proj.addMapLayer(flagged_layer)

            print(f"SUCCESS: Created layer with {len(flagged_features)} features")

            return {
                'operation': 'flag_distribution_points',
                'status': 'completed',
                'flagged_count': len(flagged_features),
                'flag_layer_id': flagged_layer.id(),
                'flagged_ids': [f.id() for f in flagged_features]
            }

        except Exception as e:
            print(f"Error in flag_distribution_points: {e}")
            return {
                'operation': 'flag_distribution_points',
                'status': 'failed',
                'error': str(e)
            }
