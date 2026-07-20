r"""Quick test runner for DialogMesh v6.

Usage:
  .venv-test\Scripts\python tests\run_tests.py              # all tests
  .venv-test\Scripts\python tests\run_tests.py --smoke      # smoke only (fast)
  .venv-test\Scripts\python tests\run_tests.py --api        # API tests
  .venv-test\Scripts\python tests\run_tests.py --gateway    # gateway tests
  .venv-test\Scripts\python tests\run_tests.py --quick      # smoke + health check
"""
import os, sys, time, subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)


def run_pytest(args: str):
    cmd = [sys.executable, "-m", "pytest"] + args.split()
    return subprocess.run(cmd).returncode


def check_services():
    """Quick health check before running tests."""
    import urllib.request, urllib.error
    
    print("═══ Service health ═══")
    try:
        r = urllib.request.Request("http://127.0.0.1:8000/v4/health")
        r.add_header("Authorization", "Bearer dev-token")
        urllib.request.urlopen(r, timeout=2)
        print("  API :8000       ✅ UP")
    except Exception:
        print("  API :8000       ❌ DOWN (start with .venv-test\\Scripts\\python scripts\\start_server.py --no-gateway)")

    try:
        urllib.request.urlopen("http://127.0.0.1:8080/v1/health", timeout=2)
        print("  Gateway :8080   ✅ UP")
    except Exception:
        print("  Gateway :8080   ❌ DOWN (start with gateway\\gateway.exe)")


if __name__ == "__main__":
    argv = sys.argv[1:]

    if "--quick" in argv or not argv:
        check_services()
        print("\n═══ Smoke tests ═══")
        run_pytest("tests/test_api.py -v -m smoke --tb=line")
    
    elif "--smoke" in argv:
        check_services()
        run_pytest("tests/test_api.py -v -m smoke --tb=line")

    elif "--api" in argv:
        run_pytest("tests/test_api.py -v -m api --tb=short")

    elif "--gateway" in argv:
        run_pytest("tests/test_api.py -v -m gateway --tb=short")

    elif "--all" in argv:
        check_services()
        run_pytest("tests/test_api.py -v --tb=short")

    else:
        print("Usage: python tests/run_tests.py [--quick|--smoke|--api|--gateway|--all]")
