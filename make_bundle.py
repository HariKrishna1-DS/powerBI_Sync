import os
import zipfile

output_filename = "DataTrace_Workspace.zip"
exclude_dirs = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".streamlit"}

print("Packaging DataTrace Workspace...")
with zipfile.ZipFile(output_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk("."):
        # Filter excluded directories in-place
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file == output_filename:
                continue
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, ".")
            zipf.write(file_path, arcname)

size_mb = os.path.getsize(output_filename) / (1024 * 1024)
print(f"Successfully created '{output_filename}' ({size_mb:.2f} MB)")
