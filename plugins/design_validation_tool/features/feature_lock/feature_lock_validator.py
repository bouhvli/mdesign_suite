from qgis.core import QgsVectorLayer, QgsFeatureRequest, QgsProject  # type: ignore
from ...utils.layer_loader import get_layer_by_name


class FeatureLockValidator:
    def __init__(self):
        self.violations = []

    def validate_feature_lock_status(self):
        """
        Validate that all features in layers are locked (LOCKED != 'Unlocked').
        
        Rule: All features must have LOCKED status set to something other than 'Unlocked'
        """
        print("Validating feature lock status...")
        description = "Features must be Locked"

        project = QgsProject.instance()
        layers = list(project.mapLayers().values())

        violations = []
        layers_with_unlocked = {}  # Track which layers have unlocked features
        total_unlocked = 0

        for layer in layers:
            # Check if layer is a vector layer
            if not isinstance(layer, QgsVectorLayer):
                continue

            # Check if layer has 'LOCKED' column (case-insensitive check)
            field_names = [field.name().upper() for field in layer.fields()]

            if 'LOCKED' not in field_names:
                continue

            # Find the actual field name (preserving original case)
            actual_field_name = None
            for field in layer.fields():
                if field.name().upper() == 'LOCKED':
                    actual_field_name = field.name()
                    break

            # Count features where LOCKED = 'Unlocked'
            expression = f'"{actual_field_name}" = \'Unlocked\''
            features = layer.getFeatures(QgsFeatureRequest().setFilterExpression(expression))

            # Collect violations for each unlocked feature
            unlocked_in_layer = 0
            for feature in features:
                unlocked_in_layer += 1
                total_unlocked += 1

                violation_info = {
                    'rule_id': 'FEATURE_LOCK_001',
                    'Description': description,
                    'layer': layer.name(),
                    'feature_id': feature.id(),
                    'feature_name': (
                        feature['NAME']
                        if 'NAME' in [f.name() for f in layer.fields()]
                        else str(feature.id())
                    ),
                    'locked_status': feature[actual_field_name],
                    'geometry': feature.geometry(),
                    'violation_type': 'feature_unlocked',
                    'violation_reason': f"Feature {feature.id()} in layer '{layer.name()}' is unlocked"
                }
                violations.append(violation_info)

            if unlocked_in_layer > 0:
                layers_with_unlocked[layer.name()] = unlocked_in_layer

        # Build failed features string with layer names
        failed_features_list = [
            f"{layer}({count})"
            for layer, count in layers_with_unlocked.items()
        ]

        result = {
            'rule_id': 'FEATURE_LOCK_001',
            'Description': description,
            'status': 'PASS' if not violations else 'FAIL',
            'violation_count': len(violations),
            'failed_features': ', '.join(failed_features_list) if failed_features_list else 'None',
            'message': f'Found {total_unlocked} unlocked features across {len(layers_with_unlocked)} layers' if total_unlocked > 0 else 'All features are locked',
        }

        self.violations.extend(violations)
        print(f"Feature Lock validation result: {result}")
        return result