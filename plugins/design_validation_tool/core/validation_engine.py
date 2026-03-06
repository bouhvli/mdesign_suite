from ..features.data_quality.data_quality_validator import DataQualityValidator
from ..features.poc_clustering.poc_validator import POCValidator
from ..features.overlapping.overlapping_validator import OverlappingValidator
from ..features.primary_distribution.primary_distribution_validator import PrimaryDistributionValidator
from ..features.feeder.feeder_validator import FeederValidator
from ..features.distribution.distribution_validator import DistributionValidator
from ..features.trenches.trenshes import Trenches
from ..features.crossings.crossings_validator import CrossingsValidator
from ..utils.shape_file_creation import create_violation_shapefile
from ..features.feature_lock.feature_lock_validator import FeatureLockValidator
from qgis.PyQt.QtGui import QColor # type: ignore

class ValidationEngine:
    def __init__(self, run_output_directory=None, project_file_path=None, iface=None):
        self.results = []
        self.poc_validator = POCValidator()
        self.overlap_validator = OverlappingValidator()
        self.primary_distribution_validator = PrimaryDistributionValidator()
        self.feeder_validator = FeederValidator()
        self.distribution_validator = DistributionValidator()
        self.trenches_validator = Trenches()
        self.feature_lock_validator = FeatureLockValidator()
        self.data_quality_validator = DataQualityValidator()
        self.crossings_validator = CrossingsValidator()
        self.all_violations = []
        self.run_output_directory = run_output_directory
        self.project_file_path = project_file_path
        self.iface = iface

    def validate_poc_clustering(self, selected_checks):
        """Validate all POC clustering rules"""
        # CRITICAL: Clear violations from previous runs
        self.poc_validator.violations.clear()
        
        poc_results = []

        if selected_checks.get("poc_clustering", False):
            # Rule 1: Maximum POCs in line
            poc_results.append(
                self.poc_validator.validate_max_pocs_in_line(max_pocs=11)
            )

            # Rule 2: Max connections per POC
            poc_results.append(
                self.poc_validator.validate_max_connections_per_poc(max_connections=8)
            )
            # Rule 3: UG/Facade connections
            poc_results.append(
                self.poc_validator.validate_ug_facade_connections(
                    max_left=4, max_right=4
                )
            )
            # Rule 4: POCs in single cluster
            poc_results.append(self.poc_validator.validate_pocs_in_single_cluster())

            # Rule 5: Proximity, home count, and drop cable length
            poc_results.append(self.poc_validator.validate_proximity_checks())

            # Rule 6: Aerial drop cable length
            poc_results.append(self.poc_validator.validate_aerial_drop_cable_length(max_length=40.0))

            # Rule 7: Façade drop cables crossing gaps
            poc_results.append(self.poc_validator.validate_facade_drop_cables_no_gap())

            # Rule 8: Stacked POCs (POCs at the same location)
            poc_results.append(self.poc_validator.validate_stacked_pocs())

            # Rule 9: POC placement between served buildings
            poc_results.append(self.poc_validator.validate_poc_placement_between_buildings(max_offset=0.5))

            # Collect all violations
            self.all_violations.extend(self.poc_validator.violations)
            output_path = create_violation_shapefile(
                        self.run_output_directory,
                        self.poc_validator.violations,  
                        feature="POC_Clustering",
                        project_path=self.project_file_path,
                        iface=self.iface if hasattr(self, 'iface') else None,
                        color=QColor(0, 0, 255)
                    )

        return poc_results

    def validate_overlap(self, selected_checks):
        """Validate overlapping and inefficiency rules"""
        # CRITICAL: Clear violations from previous runs
        if hasattr(self.overlap_validator, 'violations'):
            self.overlap_validator.violations.clear()
        
        overlap_results = []
        
        if selected_checks.get('overlap', False):
            
            # Rule 1: Parallel duct overlap
            parallel_result = self.overlap_validator.validate_parallel_overlap()
            overlap_results.append(parallel_result)
            
            # Rule 2: Oversized ducts
            # oversized_result = self.overlap_validator.validate_oversized_ducts()
            # overlap_results.append(oversized_result)

            # Rule 3: Cluster Overlap
            cluster_result = self.overlap_validator.validate_cluster_overlaps()
            if cluster_result:  # Only append if there are violations
                if isinstance(cluster_result, list):
                    overlap_results.extend(cluster_result)
                else:
                    overlap_results.append(cluster_result)
            if hasattr(self.overlap_validator, 'violations'):
                # Collect all violations
                self.all_violations.extend(self.overlap_validator.violations)

        output_path = create_violation_shapefile(
                        self.run_output_directory,
                        self.overlap_validator.violations,  
                        feature="OVERLAPPING",
                        project_path=self.project_file_path,
                        iface=self.iface if hasattr(self, 'iface') else None,
                        color=QColor(255, 0, 0)
                    )
        return overlap_results
    
    def validate_feeder(self, selected_checks):
        """Validate Feeder rules"""
        # CRITICAL: Clear violations from previous runs
        if hasattr(self.feeder_validator, 'violations'):
            self.feeder_validator.violations.clear()
        
        feeder_results = []
        
        if selected_checks.get("feeder", False):
            feeder_results = self.feeder_validator.validate_feeder_rules()

            if hasattr(self.feeder_validator, 'violations'):
                self.all_violations.extend(self.feeder_validator.violations)
                
                output_path = create_violation_shapefile(
                    self.run_output_directory,
                    self.feeder_validator.violations,
                    feature="FEEDER",
                    project_path=self.project_file_path,
                    iface=self.iface if hasattr(self, 'iface') else None,
                    color=QColor(255, 0, 255)
                )
        
        return feeder_results

    def validate_primary_distribution(self, selected_checks):
        """Validate primary distribution rules"""
        # CRITICAL: Clear violations from previous runs
        if hasattr(self.primary_distribution_validator, 'violations'):
            self.primary_distribution_validator.violations.clear()
        
        primary_results = []
        
        if selected_checks.get("primary_distribution", False):
            primary_results = self.primary_distribution_validator.validate_primary_distribution_rules()

            if hasattr(self.primary_distribution_validator, 'violations'):
                self.all_violations.extend(self.primary_distribution_validator.violations)

                output_path = create_violation_shapefile(
                    self.run_output_directory,
                    self.primary_distribution_validator.violations,
                    feature="PRIMARY_DISTRIBUTION",
                    project_path=self.project_file_path,
                    iface=self.iface if hasattr(self, 'iface') else None,
                    color=QColor(0, 255, 0)
                )

        return primary_results

    def validate_distribution(self, selected_checks):
        """Validate distribution rules"""
        # CRITICAL: Clear violations from previous runs
        if hasattr(self.distribution_validator, 'violations'):
            self.distribution_validator.violations.clear()
        
        distribution_results = []

        if selected_checks.get("distribution", False):
            distribution_results = self.distribution_validator.validate_distribution_rules()

            if hasattr(self.distribution_validator, 'violations'):
                self.all_violations.extend(self.distribution_validator.violations)

                output_path = create_violation_shapefile(
                    self.run_output_directory,
                    self.distribution_validator.violations,
                    feature="DISTRIBUTION",
                    project_path=self.project_file_path,
                    iface=self.iface if hasattr(self, 'iface') else None,
                    color=QColor(255, 165, 0)  # Orange 
                )

        return distribution_results

    def validate_trenches(self):
        """Validate possible trenches rules"""
        # CRITICAL: Clear violations from previous runs
        if hasattr(self.trenches_validator, 'trenches_violations'):
            self.trenches_validator.trenches_violations.clear()

        trenches_results = self.trenches_validator.validate_trenches_rules()

        if hasattr(self.trenches_validator, 'trenches_violations'):
            self.all_violations.extend(self.trenches_validator.trenches_violations)

            if self.trenches_validator.trenches_violations:
                output_path = create_violation_shapefile(
                    self.run_output_directory,
                    self.trenches_validator.trenches_violations,
                    feature="TRENCHES",
                    project_path=self.project_file_path,
                    iface=self.iface if hasattr(self, 'iface') else None,
                    color=QColor(8, 12, 128)
                )

        return trenches_results

    def validate_feature_lock(self):
        """Validate feature lock status across all layers"""
        if hasattr(self.feature_lock_validator, 'violations'):
            self.feature_lock_validator.violations.clear()

        lock_results = []

        lock_result = self.feature_lock_validator.validate_feature_lock_status()
        lock_results.append(lock_result)

        return lock_results
    
    def data_quality_check(self):
        """Validate data quality"""
        if hasattr(self.data_quality_validator, 'violations'):
            self.data_quality_validator.violations.clear()

        data_quality_results = []

        # Run all data quality rules
        data_quality_results = self.data_quality_validator.data_quality_rules()
        
        # Collect all violations from data quality validator
        if hasattr(self.data_quality_validator, 'violations'):
            self.all_violations.extend(self.data_quality_validator.violations)
            
            # Create violation shapefile if there are violations with geometry
            violations_with_geometry = [
                v for v in self.data_quality_validator.violations 
                if v.get("geometry") is not None
            ]
            if violations_with_geometry:
                output_path = create_violation_shapefile(
                    self.run_output_directory,
                    violations_with_geometry,
                    feature="DATA_QUALITY",
                    project_path=self.project_file_path,
                    iface=self.iface if hasattr(self, 'iface') else None,
                    color=QColor(128, 0, 128)  # Purple for data quality
                )

        return data_quality_results

    def validate_crossings(self, selected_checks):
        """Validate all crossing rules"""
        # Clear violations from previous runs
        if hasattr(self.crossings_validator, 'violations'):
            self.crossings_validator.violations.clear()
        
        crossings_results = []
        
        if selected_checks.get("crossings", False):
            # Get configuration parameters (could come from dialog)
            min_crossing_distance = 50.0  # Default, could be configurable
            max_road_width = 15.0  # Default, could be configurable
            
            # Run all crossing validations
            crossings_results = self.crossings_validator.validate_crossing_rules(
                min_crossing_distance=min_crossing_distance,
                max_road_width_for_crossing=max_road_width
            )
            
            # Collect all violations
            if hasattr(self.crossings_validator, 'violations'):
                self.all_violations.extend(self.crossings_validator.violations)
                
                # Create violation shapefile
                output_path = create_violation_shapefile(
                    self.run_output_directory,
                    self.crossings_validator.violations,
                    feature="CROSSINGS",
                    project_path=self.project_file_path,
                    iface=self.iface if hasattr(self, 'iface') else None,
                    color=QColor(255, 20, 147)  # Pink
                )
        
        return crossings_results

    def run_validation(self, selected_checks):
        """Run all selected validation checks"""
        # CRITICAL: Clear all state from previous runs
        self.results.clear()
        self.all_violations.clear()

        # Run POC clustering validation
        if selected_checks.get("poc_clustering", False):
            self.results.extend(self.validate_poc_clustering(selected_checks))

        # Run other validations
        if selected_checks.get("overlap", False):
            self.results.extend(self.validate_overlap(selected_checks))

        if selected_checks.get("primary_distribution", False):
            self.results.extend(self.validate_primary_distribution(selected_checks))

        if selected_checks.get("feeder", False):
            self.results.extend(self.validate_feeder(selected_checks))

        if selected_checks.get("distribution", False):
            self.results.extend(self.validate_distribution(selected_checks))
        
        if selected_checks.get("data_quality", False):
            data_quality_results = self.data_quality_check()
            if data_quality_results:
                self.results.extend(data_quality_results)
        
        if selected_checks.get("trenches", False):
            trenches_results = self.validate_trenches()
            if trenches_results:
                self.results.extend(trenches_results)

            lock_results = self.validate_feature_lock()
            if lock_results:
                self.results.extend(lock_results)


        if selected_checks.get("crossings", False):
            crossings_results = self.validate_crossings(selected_checks)
            if crossings_results:
                self.results.extend(crossings_results)

        return self.results

    def get_violation_geometries(self):
        """Get geometries of all violations for shapefile creation"""
        return [
            v["geometry"]
            for v in self.all_violations
            if "geometry" in v and v["geometry"] is not None
        ]

    def get_all_violations(self):
        """Get all violation dictionaries with complete information"""
        return self.all_violations