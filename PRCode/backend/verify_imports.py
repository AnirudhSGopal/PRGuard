import sys
try:
    import app.main
    print("SUCCESS: app.main imported correctly")
    sys.exit(0)
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)
except Exception as e:
    print(f"OTHER ERROR: {e}")
    sys.exit(2)
