import os


def print_tree(startpath, prefix=""):
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, "").count(os.sep)
        indent = "    " * level
        print(f"{indent}{os.path.basename(root)}/")
        sub_indent = "    " * (level + 1)
        for f in files:
            print(f"{sub_indent}{f}")
        # Don’t walk deeper
        dirs[:1] = []


if __name__ == "__main__":
    project_root = os.path.dirname(os.path.abspath(__file__))
    print(f"📂 Project Root: {project_root}\n")
    print_tree(project_root)
