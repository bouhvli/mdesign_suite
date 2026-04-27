# This script should be run in the QGIS Python Console.
# It assumes the layer "Address Points" exists in the current project.
# Adjust output paths as needed.

import os
from qgis.core import QgsProject, QgsVectorFileWriter, QgsFeature, QgsVectorLayer, QgsWkbTypes

# Get the layer
layer_name = 'Address Points'
layer = QgsProject.instance().mapLayersByName(layer_name)[0]

if not layer:
    print(f"Layer '{layer_name}' not found.")
else:
    # Define output paths (adjust as needed)
    shapefile_path = 'C:\\Users\\HamzaBouhali\\OneDrive - M.Design\\Bureau\\MRO_AALST_02_POP_001\\output_features.shp'  # Change this to your desired output shapefile path
    html_path = 'C:\\Users\\HamzaBouhali\\OneDrive - M.Design\\Bureau\\MRO_AALST_02_POP_001\\output_comments.html'      # Change this to your desired output HTML path

    # Collect filtered features
    filtered_features = []
    html_content = '''
<html>
<head>
    <title>Features with Comments</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f4f4f4;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #4CAF50;
            color: white;
        }
        tr:nth-child(even) {
            background-color: #f2f2f2;
        }
        tr:hover {
            background-color: #ddd;
        }
    </style>
</head>
<body>
    <h1>Features with Comments</h1>
    <table>
        <tr><th>DEMAND</th><th>COMMENT</th></tr>
'''

    for feature in layer.getFeatures():
        comment = feature.attribute('Comment')  # Assuming field name is 'Comment'
        if comment and str(comment).strip():  # Check if comment is not None and not empty
            filtered_features.append(feature)
            
            demand = feature.attribute('Demand')  # Assuming field name is 'Demand'
            demand_str = str(demand) if demand is not None else ''
            comment_str = str(comment)
            
            html_content += f'<tr><td>{demand_str}</td><td>{comment_str}</td></tr>'

    html_content += '''
    </table>
</body>
</html>
'''

    # Write HTML file
    with open(html_path, 'w') as html_file:
        html_file.write(html_content)
    print(f"HTML file generated at: {html_path}")

    # Get geometry type as string
    geom_type = QgsWkbTypes.displayString(layer.wkbType())

    # Create a temporary memory layer for filtered features
    temp_layer = QgsVectorLayer(f"{geom_type}?crs={layer.crs().authid()}", 'temp', 'memory')
    temp_layer.dataProvider().addAttributes(layer.fields())
    temp_layer.updateFields()
    temp_layer.dataProvider().addFeatures(filtered_features)

    # Export to Shapefile
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = 'ESRI Shapefile'
    error = QgsVectorFileWriter.writeAsVectorFormatV3(temp_layer, shapefile_path, QgsProject.instance().transformContext(), options)
    
    if error[0] == QgsVectorFileWriter.NoError:
        print(f"Shapefile generated at: {shapefile_path}")
    else:
        print(f"Error generating shapefile: {error[1]}")