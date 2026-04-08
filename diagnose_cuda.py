import torch
import sys
import os

print(f"Python version: {sys.version}")
print(f"Torch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA version (torch): {torch.version.cuda}")
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")
    print(f"Device Count: {torch.cuda.device_count()}")
else:
    print("CUDA NOT AVAILABLE to PyTorch")

print("\n--- Environment ---")
print(f"LD_LIBRARY_PATH: {os.environ.get('LD_LIBRARY_PATH', 'Not set')}")
print(f"PATH: {os.environ.get('PATH', 'Not set')}")

print("\n--- System ---")
os.system("nvidia-smi")
os.system("nvcc --version")
