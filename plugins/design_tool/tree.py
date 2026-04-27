import os

EXCLUDE_DIRS = {
    ".git", "__pycache__", ".ruff_cache",
    "libs", "i18n", ".vscode", "help", "resources",
    "test", "scripts", "readme.html", "LICENSE", "CHANGELOG.md",
    "CONTRIBUTING.md", ".github", ".gitignore", "docs", "Makefile",
    "Dockerfile", "docker-compose.yml", ".pre-commit-config.yaml",
}

def print_tree(startpath, indent=""):
    try:
        items = os.listdir(startpath)
    except PermissionError:
        print(indent + " [Access Denied]")
        return

    items = [i for i in items if i not in EXCLUDE_DIRS]
    items.sort()

    for index, item in enumerate(items):
        path = os.path.join(startpath, item)
        prefix = "└── " if index == len(items) - 1 else "├── "
        print(indent + prefix + item)
        if os.path.isdir(path):
            extension = "    " if index == len(items) - 1 else "│   "
            print_tree(path, indent + extension)

if __name__ == "__main__":
    project_path = os.getcwd().strip()
    if os.path.exists(project_path):
        print(project_path)
        print_tree(project_path)
    else:
        print("Path does not exist!")
