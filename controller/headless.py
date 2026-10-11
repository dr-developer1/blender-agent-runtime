"""Local headless script runner: python -m controller.headless SCRIPT."""
import argparse
import sys
from .lifecycle import BlenderProcessError, run_headless


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script')
    parser.add_argument('--blender', default='blender')
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    try:
        result = run_headless(args.script, executable=args.blender, timeout=args.timeout)
    except (BlenderProcessError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(result.stdout, end='')
    return result.returncode if result.returncode >= 0 else 1


if __name__ == '__main__':
    sys.exit(main())
