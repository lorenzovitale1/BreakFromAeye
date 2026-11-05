"""Punto d'ingresso dell'eseguibile (PyInstaller)."""
import sys

from eyegaze.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
