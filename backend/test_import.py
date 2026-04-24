import sys
print("starting import")
try:
    from app.main import app
    print("imported app")
except Exception as e:
    print(f"Error: {e}")
print("done")
