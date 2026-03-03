from ..features.flag.flag import FlagDesign
from ..features.update import UpdateDesign
from qgis.PyQt.QtGui import QColor # type: ignore

class DesignEngine:
    def __init__(
        self, 
        run_output_directory=None, 
        project_file_path=None,
        update_addresses=False,
        point_layer=None,
        surveyed_addresses_file=None,
        analyze_intersections=False,
        trenches_layer_name=None,
        assign_clusters_by_distribution=False
    ):
        self.results = []
        
        print(f"\n=== DesignEngine.__init__ ===")
        print(f"trenches_layer_name: {trenches_layer_name}")
        print(f"assign_clusters_by_distribution: {assign_clusters_by_distribution}")
        
        if trenches_layer_name:
            print(f"DesignEngine: Storing trenches layer name: '{trenches_layer_name}'")
        
        if assign_clusters_by_distribution:
            print(f"DesignEngine: Cluster assignment by distribution cables: ENABLED")
        
        self.update_design = UpdateDesign(
            update_addresses=update_addresses,
            point_layer=point_layer,
            surveyed_addresses_file=surveyed_addresses_file,
            analyze_intersections=analyze_intersections,
            trenches_layer_name=trenches_layer_name,
            assign_clusters_by_distribution=assign_clusters_by_distribution
        )
        
        print(f"UpdateDesign.assign_clusters_by_distribution: {self.update_design.assign_clusters_by_distribution}")
        print("=== DesignEngine.__init__ complete ===\n")
        
        self.flag_design = FlagDesign()
        self.run_output_directory = run_output_directory
        self.project_file_path = project_file_path

    def run_design(self):
        """Run all selected validation design rule"""
        print("\n=== DesignEngine.run_design() ===")
        self.results.clear()
        self.results = self.update_design.updatedesign()
        flag_results = self.flag_design.run_flag_operations()
        self.results.extend(flag_results)
        print("=== DesignEngine.run_design() complete ===\n")
        return self.results