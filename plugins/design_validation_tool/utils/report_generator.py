import csv
import os
from datetime import datetime

from .extract_design_session import extract_design_session_name


def generate_csv_report(path, output_directory, validation_results):
    """
    Generate a CSV validation report

    Args:
        output_directory (str): Directory to save the report
        validation_results (list): List of validation results

    Returns:
        str: Path to the generated report
    """
    report_path = f"validation_report_{extract_design_session_name(path)}.csv"
    output_path = os.path.join(output_directory, report_path)

    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['rule_id', 'Description', 'status', 'violation_count', 'failed_features', 'message']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in validation_results:
            writer.writerow(result)

    #print(f"CSV report generated: {output_path}")
    return output_path

def generate_html_report(path, output_directory, validation_results):
    """
    Generate a structured and styled HTML validation report.

    Args:
        output_directory (str): Directory to save the report
        validation_results (list): List of validation results

    Returns:
        str: Path to the generated report
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_path = f"validation_report_{extract_design_session_name(path)}.html"
    output_path = os.path.join(output_directory, report_path)

    # HTML template with semantic structure and consistent styling
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Design Validation Report</title>
    <style>
        body {{
            font-family: 'Arial', sans-serif;
            margin: 40px;
            background-color: #fafafa;
            color: #333;
        }}
        h1 {{
            text-align: center;
            color: #1F3A52;
        }}
        p.timestamp {{
            text-align: center;
            font-size: 0.9em;
            color: #555;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-top: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 10px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tr:hover {{
            background-color: #f1f1f1;
        }}
        .pass {{ color: green; font-weight: bold; }}
        .fail {{ color: red; font-weight: bold; }}
        .error {{ color: orange; font-weight: bold; }}
        .warning {{ color: yellow; font-weight: bold; }}
        td.failed-features {{
            white-space: pre-wrap;  /* preserves multi-line content */
        }}
    </style>
</head>
<body>
    <header>
        <h1>Design Validation Report</h1>
        <p class="timestamp">Generated on: {timestamp}</p>
    </header>
    <main>
        <table>
            <thead>
                <tr>
                    <th>Rule ID</th>
                    <th>Description</th>
                    <th>Status</th>
                    <th>Violation Count</th>
                    <th>Failed Features</th>
                    <th>Message</th>
                </tr>
            </thead>
            <tbody>
                {"".join([
                    f"<tr>"
                    f"<td>{r['rule_id']}</td>"
                    f"<td>{r.get('Description','')}</td>"
                    f"<td class='{r['status'].lower()}'>{r['status']}</td>"
                    f"<td>{r['violation_count']}</td>"
                    f"<td class='failed-features'>{r['failed_features']}</td>"
                    f"<td>{r['message']}</td>"
                    f"</tr>"
                    for r in validation_results
                ])}
            </tbody>
        </table>
    </main>
    <footer>
        <p style="text-align:center; font-size:0.8em; color:#888;">End of Report</p>
    </footer>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as htmlfile:
        htmlfile.write(html_content)

    #print(f"HTML report generated: {output_path}")
    return output_path
