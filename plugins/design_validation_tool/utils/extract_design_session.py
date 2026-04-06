import os


def extract_design_session_name(path):
    """
    Extracts the design session name from a given path.
    The design session name is always the folder before 'output'.
    
    Args:
        path (str): Full path string
    
    Returns:
        str: Design session name, or None if not found
    """
    # Normalize path for safety
    normalized_path = os.path.normpath(path)
    
    # Split into parts
    parts = normalized_path.split(os.sep)
    
    # Find 'output' folder
    if "output" in parts:
        output_index = parts.index("output")
        if output_index > 0:
            return parts[output_index - 1]
    
    return "Unknown_Design_Session"
