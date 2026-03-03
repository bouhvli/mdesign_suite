# coding=utf-8
"""Unit tests for DistributionValidator behaviors (validate_max_cables_leaving_dp)."""

import unittest
from unittest import mock

from features.distribution.distribution_validator import DistributionValidator


class TestDistributionValidator(unittest.TestCase):
    """Tests for DistributionValidator rules using mocks to isolate QGIS dependencies."""

    def setUp(self):
        self.validator = DistributionValidator()

    # Simple fakes mirroring behavior used by the validator
    class FakeFeature:
        def __init__(self, fid, attrs=None, geom=None):
            self._id = fid
            self._attrs = attrs or {}
            self._geom = geom

        def id(self):
            return self._id

        def __getitem__(self, key):
            return self._attrs.get(key)

        def fields(self):
            class F:  # minimal fields().names() interface
                def __init__(self, names):
                    self._names = names

                def names(self):
                    return self._names
            return F(list(self._attrs.keys()))

        def geometry(self):
            return self._geom

    class FakeGeometry:
        def __init__(self, empty=False, bbox=None, intersects=False, length=1.0, within=False):
            self._empty = empty
            self._bbox = bbox or object()
            self._intersects = intersects
            self._length = length
            self._within = within

        def isEmpty(self):
            return self._empty

        def buffer(self, *_args, **_kwargs):
            # return self for chaining; in tests we only check identity and intersects
            return self

        def boundingBox(self):
            return self._bbox

        def intersects(self, _other):
            return self._intersects

        def within(self, _other):
            return self._within

        def length(self):
            return self._length

        # Additional stubs used by other validations
        def intersection(self, _other):
            return self

        def centroid(self):
            return self

        def asPoint(self):
            return object()

        def lineLocatePoint(self, _pt):
            return 0.5

        def combine(self, _other):
            return self

    # Behavior 1: Error when Distribution Points layer missing
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_max_cables_leaving_dp_missing_dp_layer(self, m_get_layer):
        # Return None for DP layer
        m_get_layer.side_effect = [None, mock.Mock()]

        result = self.validator.validate_max_cables_leaving_dp(max_cables=5)

        self.assertEqual(result['rule_id'], 'DISTRIBUTION_001')
        self.assertEqual(result['status'], 'ERROR')
        self.assertIn('Distribution Points layer not found', result['message'])

    # Behavior 2: Error when Distribution Cables layer missing
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_max_cables_leaving_dp_missing_cables_layer(self, m_get_layer):
        m_get_layer.side_effect = [mock.Mock(), None]
        # Mock DP layer has AGG_ID
        m_get_layer.side_effect[0].fields().names.return_value = ['AGG_ID']

        result = self.validator.validate_max_cables_leaving_dp(max_cables=5)
        self.assertEqual(result['status'], 'ERROR')
        self.assertIn('Distribution Cables layer not found', result['message'])

    # Behavior 3: Flags too many related cables leaving a DP
    @mock.patch('features.distribution.distribution_validator.QgsSpatialIndex')
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_max_cables_leaving_dp_exceeds_limit(self, m_get_layer, m_index):
        # Prepare layers
        dp_layer = mock.Mock()
        cab_layer = mock.Mock()
        m_get_layer.side_effect = [dp_layer, cab_layer]

        # Fields
        dp_layer.fields().names.return_value = ['AGG_ID', 'DP_ID']
        cab_layer.fields().names.return_value = ['TOP_AGG_ID', 'CABLE_ID']

        # One DP with AGG_ID 'DP-A'
        dp_geom = self.FakeGeometry(empty=False)
        dp_feat = self.FakeFeature(1, {'AGG_ID': 'DP-A', 'DP_ID': 'D1'}, dp_geom)
        dp_layer.getFeatures.return_value = [dp_feat]

        # Spatial index returns 6 candidate cable ids
        m_index_instance = mock.Mock()
        m_index.return_value = m_index_instance
        m_index_instance.intersects.return_value = [10, 11, 12, 13, 14, 15]

        # Each candidate is a related cable with CABLE_IDs
        def get_feature_side_effect(fid):
            geom = self.FakeGeometry(empty=False, intersects=True)
            return self.FakeFeature(fid, {'TOP_AGG_ID': 'DP-A', 'CABLE_ID': f'C{fid}'}, geom)
        cab_layer.getFeature.side_effect = get_feature_side_effect

        result = self.validator.validate_max_cables_leaving_dp(max_cables=5)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['violation_count'], 1)
        self.assertIn('related distribution cables (max 5)', result['message'])
        # Ensure violation recorded in self.violations as well
        self.assertTrue(any(v.get('violation_type') == 'max_cables_leaving_dp' for v in self.validator.violations))

    # Behavior 4: Flags unrelated cables intersecting the DP buffer
    @mock.patch('features.distribution.distribution_validator.QgsSpatialIndex')
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_max_cables_leaving_dp_unrelated_cables(self, m_get_layer, m_index):
        dp_layer = mock.Mock()
        cab_layer = mock.Mock()
        m_get_layer.side_effect = [dp_layer, cab_layer]

        dp_layer.fields().names.return_value = ['AGG_ID', 'DP_ID']
        cab_layer.fields().names.return_value = ['TOP_AGG_ID', 'CABLE_ID']

        dp_geom = self.FakeGeometry(empty=False)
        dp_feat = self.FakeFeature(1, {'AGG_ID': 'DP-1', 'DP_ID': 'DPX'}, dp_geom)
        dp_layer.getFeatures.return_value = [dp_feat]

        m_index_instance = mock.Mock()
        m_index.return_value = m_index_instance
        m_index_instance.intersects.return_value = [21, 22, 23]

        # Two cables unrelated, one related
        def get_feature_side_effect(fid):
            if fid == 21:
                return self.FakeFeature(fid, {'TOP_AGG_ID': 'OTHER', 'CABLE_ID': 'CU1'}, self.FakeGeometry(empty=False, intersects=True))
            if fid == 22:
                return self.FakeFeature(fid, {'TOP_AGG_ID': 'OTHER', 'CABLE_ID': 'CU2'}, self.FakeGeometry(empty=False, intersects=True))
            return self.FakeFeature(fid, {'TOP_AGG_ID': 'DP-1', 'CABLE_ID': 'CR'}, self.FakeGeometry(empty=False, intersects=True))
        cab_layer.getFeature.side_effect = get_feature_side_effect

        # Merge helper: let as-is, FakeGeometry.combine not used because we don't call _merge_line_geometries directly
        result = self.validator.validate_max_cables_leaving_dp(max_cables=5)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['violation_count'], 1)
        self.assertIn('unrelated cables intersecting it', result['message'])
        self.assertTrue(any(v.get('violation_type') == 'unrelated_cables_at_dp' for v in self.validator.violations))

    # Behavior 5: PASS when no violations and fields present
    @mock.patch('features.distribution.distribution_validator.QgsSpatialIndex')
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_max_cables_leaving_dp_no_violations(self, m_get_layer, m_index):
        dp_layer = mock.Mock()
        cab_layer = mock.Mock()
        m_get_layer.side_effect = [dp_layer, cab_layer]

        dp_layer.fields().names.return_value = ['AGG_ID', 'DP_ID']
        cab_layer.fields().names.return_value = ['TOP_AGG_ID', 'CABLE_ID']

        dp_geom = self.FakeGeometry(empty=False)
        dp_feat = self.FakeFeature(1, {'AGG_ID': 'DP-2', 'DP_ID': 'D2'}, dp_geom)
        dp_layer.getFeatures.return_value = [dp_feat]

        m_index_instance = mock.Mock()
        m_index.return_value = m_index_instance
        m_index_instance.intersects.return_value = [31, 32, 33]

        # Only related cables and count <= max
        def get_feature_side_effect(fid):
            return self.FakeFeature(fid, {'TOP_AGG_ID': 'DP-2', 'CABLE_ID': f'C{fid}'}, self.FakeGeometry(empty=False, intersects=True))
        cab_layer.getFeature.side_effect = get_feature_side_effect

        result = self.validator.validate_max_cables_leaving_dp(max_cables=4)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['violation_count'], 0)
        self.assertIn('No violations', result['message'])


# New behaviors/tests
    # 1) DISTRIBUTION_002: facade cable length error when TYPE field missing
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_facade_cable_max_length_missing_type_field(self, m_get_layer):
        cab_layer = mock.Mock()
        m_get_layer.side_effect = [cab_layer]
        cab_layer.fields().names.return_value = []
        result = self.validator.validate_facade_cable_max_length(max_length=100.0)
        self.assertEqual(result['rule_id'], 'DISTRIBUTION_002')
        self.assertEqual(result['status'], 'ERROR')
        self.assertIn('missing TYPE field', result['message'])

    # 2) DISTRIBUTION_002: flags cable exceeding length when type contains facade
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_facade_cable_max_length_flags_excess(self, m_get_layer):
        cab_layer = mock.Mock()
        m_get_layer.side_effect = [cab_layer]
        cab_layer.fields().names.return_value = ['TYPE', 'CABLE_ID']
        long_geom = self.FakeGeometry(empty=False, length=600.0)
        feat = self.FakeFeature(7, {'TYPE': 'Façade', 'CABLE_ID': 'CF1'}, long_geom)
        cab_layer.getFeatures.return_value = [feat]
        result = self.validator.validate_facade_cable_max_length(max_length=500.0)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['violation_count'], 1)
        self.assertIn('Façade cable CF1 has length', result['message'])

    # 3) DISTRIBUTION_006: parallel aerial limit creates violation for >2
    @mock.patch('features.distribution.distribution_validator.QgsSpatialIndex')
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_parallel_aerial_cable_limit_group_violation(self, m_get_layer, _m_index):
        cab_layer = mock.Mock()
        m_get_layer.side_effect = [cab_layer]
        # Three aerial cables that completely overlap (our FakeGeometry.intersection returns self, with length equal to cable length)
        cab_layer.getFeatures.return_value = [
            self.FakeFeature(1, {'TYPE': 'aerial', 'CABLE_ID': 'A1'}, self.FakeGeometry(empty=False, intersects=True, length=100.0)),
            self.FakeFeature(2, {'TYPE': 'AERIAL', 'CABLE_ID': 'A2'}, self.FakeGeometry(empty=False, intersects=True, length=100.0)),
            self.FakeFeature(3, {'TYPE': 'aeriAl', 'CABLE_ID': 'A3'}, self.FakeGeometry(empty=False, intersects=True, length=100.0)),
        ]
        result = self.validator.validate_parallel_aerial_cable_limit(max_parallel=2)
        self.assertEqual(result['rule_id'], 'DISTRIBUTION_006')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['violation_count'], 1)
        self.assertIn('parallel aerial cables', result['message'])

    # 4) DISTRIBUTION_007: underground drop consistency flags mismatch
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_underground_drop_consistency_mismatch(self, m_get_layer):
        dist_layer = mock.Mock()
        drop_layer = mock.Mock()
        poc_layer = mock.Mock()
        m_get_layer.side_effect = [dist_layer, drop_layer, poc_layer]
        # Underground dist cable with group G1
        dist_layer.getFeatures.return_value = [self.FakeFeature(1, {'TYPE': 'underground', 'CAB_GROUP': 'G1'}, self.FakeGeometry())]
        # POC in same subcluster -> AGG_ID maps to TOP_AGG_ID on drop
        poc_layer.getFeatures.return_value = [self.FakeFeature(11, {'SUBCLUSTER': 'G1', 'AGG_ID': 'P1'}, self.FakeGeometry())]
        # A drop cable connected to P1 but not underground
        drop_layer.getFeatures.return_value = [self.FakeFeature(21, {'TOP_AGG_ID': 'P1', 'TYPE': 'aerial', 'CABLE_ID': 'D1'}, self.FakeGeometry())]
        result = self.validator.validate_underground_drop_consistency()
        self.assertEqual(result['rule_id'], 'DISTRIBUTION_007')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['violation_count'], 1)
        self.assertIn('not underground', result['message'])

    # 5) DISTRIBUTION_008: facade start/end underground segments violation
    @mock.patch('features.distribution.distribution_validator.QgsGeometry')
    @mock.patch('features.distribution.distribution_validator.QgsSpatialIndex')
    @mock.patch('features.distribution.distribution_validator.get_layer_by_name')
    def test_validate_facade_total_underground_length_violation(self, m_get_layer, m_index, m_qgsgeom):
        dist_layer = mock.Mock()
        routes_layer = mock.Mock()
        m_get_layer.side_effect = [dist_layer, routes_layer]
        # One facade cable
        dist_layer.getFeatures.return_value = [self.FakeFeature(1, {'TYPE': 'facade', 'CABLE_ID': 'F1'}, self.FakeGeometry(empty=False))]
        # Spatial index returns routes within bbox
        m_index_instance = mock.Mock()
        m_index.return_value = m_index_instance
        m_index_instance.intersects.return_value = [101, 102, 103]
        # Mock QgsGeometry.fromPointXY to return a dummy point acceptable to lineLocatePoint
        m_qgsgeom.fromPointXY.return_value = object()
        # Build routes with TYPE and LENGTH fields
        def get_route(fid):
            if fid == 101:
                return self.FakeFeature(fid, {'TYPE': 'BURIED', 'LENGTH': 40.0, 'AERIALTYPE': 'FACADE'}, self.FakeGeometry(empty=False, intersects=True))
            if fid == 102:
                return self.FakeFeature(fid, {'TYPE': 'TRANSITION', 'LENGTH': 30.0, 'AERIALTYPE': ''}, self.FakeGeometry(empty=False, intersects=True))
            # Mark an aerial facade to stop segment accumulation
            return self.FakeFeature(fid, {'TYPE': 'AERIAL', 'LENGTH': 0.0, 'AERIALTYPE': 'FACADE'}, self.FakeGeometry(empty=False, intersects=True))
        routes_layer.getFeature.side_effect = get_route
        routes_layer.fields().names.return_value = ['TYPE', 'AERIALTYPE', 'LENGTH']
        result = self.validator.validate_facade_total_underground_length(max_length=60.0)
        self.assertEqual(result['rule_id'], 'DISTRIBUTION_008')
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['violation_count'], 1)
        self.assertIn('underground segments over 60.0m', result['message'])


if __name__ == '__main__':
    unittest.main()
