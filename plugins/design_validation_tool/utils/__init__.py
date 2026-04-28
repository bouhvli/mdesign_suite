"""
Utility modules for the Design Validation Tool plugin
"""

from .project_handler import load_project as load_project
from .report_generator import (
    generate_csv_report as generate_csv_report,
    generate_html_report as generate_html_report,
)
from .extract_design_session import (
    extract_design_session_name as extract_design_session_name,
)
from .layout_generator import run_report as run_report
from .violation_details import get_violation_details as get_violation_details
from .styling_methods import (
    apply_style_from_qml as apply_style_from_qml,
    setup_labels as setup_labels,
)
from .layer_loader import (
    get_layer_by_name as get_layer_by_name,
    get_layer_from_API as get_layer_from_API,
)
from .external_map_loader import (
    add_external_wfs_layers as add_external_wfs_layers,
    import_external_maps as import_external_maps,
)
from .geometry_fixer import (
    fix_selected_layers as fix_selected_layers,
    check_layer_for_invalid_geometries as check_layer_for_invalid_geometries,
)
