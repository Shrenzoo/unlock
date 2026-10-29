"""Loopback-only development entry point."""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="Start the local UNLOCK engineering coordinator"
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("unlock_engine.api.app:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
