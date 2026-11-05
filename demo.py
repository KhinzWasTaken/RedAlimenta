"""Levanta RedAlimenta para la demostración con un solo comando.

    python demo.py              compila el frontend si hace falta, siembra la base y arranca en :8000
    python demo.py --reiniciar  igual, pero borra la base y vuelve a sembrar (demo desde cero)
    python demo.py --compilar   fuerza recompilar el frontend

El backend FastAPI sirve el frontend ya compilado: abre http://localhost:8000
(desde el celular en la misma red: http://IP-DEL-PC:8000).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BACKEND = RAIZ / "backend"
FRONTEND = RAIZ / "frontend"


def npm(*args: str) -> None:
    ejecutable = shutil.which("npm")
    if ejecutable is None:
        sys.exit("No se encontró npm. Instala Node.js 18+ para compilar el frontend.")
    subprocess.run([ejecutable, *args], cwd=FRONTEND, check=True)


def compilar_frontend(forzar: bool) -> None:
    if (FRONTEND / "dist" / "index.html").exists() and not forzar:
        return
    if not (FRONTEND / "node_modules").exists():
        print("» Instalando dependencias del frontend…")
        npm("install")
    print("» Compilando el frontend…")
    npm("run", "build")


def main() -> None:
    args = sys.argv[1:]
    compilar_frontend("--compilar" in args)
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    from app import seed

    seed.main(["--reiniciar"] if "--reiniciar" in args else [])

    import uvicorn

    puerto = int(os.environ.get("PORT", 8000))
    print(f"\n» RedAlimenta en http://localhost:{puerto}  (Ctrl+C para detener)\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=puerto)


if __name__ == "__main__":
    main()
