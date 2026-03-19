# =============================================================================
# convertir_a_escritorio.py
#
# Script para convertir el compilador PLY en un programa de escritorio
# ejecutable (.exe en Windows, binario en Mac/Linux) usando PyInstaller.
#
# USO:
#   1. Instala PyInstaller:       pip install pyinstaller
#   2. Ejecuta este script:       python convertir_a_escritorio.py
#   3. El ejecutable quedará en:  dist/CompiladorPLY.exe  (Windows)
#                                 dist/CompiladorPLY      (Mac/Linux)
#
# OPCIONES DISPONIBLES (modifica las variables de configuración abajo):
#   - Un solo archivo ejecutable vs carpeta con dependencias
#   - Mostrar u ocultar la consola de fondo
#   - Icono personalizado
#   - Nombre del ejecutable
# =============================================================================

import subprocess
import sys
import os
import shutil

# =============================================================================
#  CONFIGURACIÓN — Modifica estas variables según tus necesidades
# =============================================================================

# Archivo principal de la interfaz gráfica
ARCHIVO_PRINCIPAL = "interfaz_compilador.py"

# Nombre del ejecutable resultante
NOMBRE_EJECUTABLE = "CompiladorPLY"

# True = genera un solo archivo .exe (más fácil de distribuir pero más lento al iniciar)
# False = genera una carpeta con todos los archivos (más rápido al iniciar)
UN_SOLO_ARCHIVO = True

# True = oculta la consola negra de fondo (recomendado para aplicaciones con GUI)
# False = muestra la consola (útil para depuración)
OCULTAR_CONSOLA = True

# Ruta al archivo de icono (.ico en Windows, .icns en Mac)
# Deja en None si no tienes icono personalizado
RUTA_ICONO = None  # Ejemplo: "icono.ico"

# Directorio donde se generará el ejecutable
DIRECTORIO_SALIDA = "dist"

# =============================================================================
#  FUNCIONES AUXILIARES
# =============================================================================

def verificar_pyinstaller():
    """Verifica que PyInstaller esté instalado, si no lo instala."""
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} encontrado")
        return True
    except ImportError:
        print("✗ PyInstaller no está instalado.")
        respuesta = input("  ¿Deseas instalarlo ahora? (s/n): ").strip().lower()
        if respuesta == 's':
            print("  Instalando PyInstaller...")
            resultado = subprocess.run(
                [sys.executable, "-m", "pip", "install", "pyinstaller"],
                capture_output=True, text=True
            )
            if resultado.returncode == 0:
                print("  ✓ PyInstaller instalado correctamente")
                return True
            else:
                print(f"  ✗ Error al instalar: {resultado.stderr}")
                return False
        return False


def construir_comando():
    """Construye el comando de PyInstaller con las opciones configuradas."""
    cmd = [sys.executable, "-m", "PyInstaller"]

    # Modo: un archivo o carpeta
    if UN_SOLO_ARCHIVO:
        cmd.append("--onefile")
        print("  Modo: Un solo archivo ejecutable")
    else:
        cmd.append("--onedir")
        print("  Modo: Carpeta con dependencias")

    # Modo de ventana (ocultar consola)
    if OCULTAR_CONSOLA:
        cmd.append("--windowed")
        print("  Consola: Oculta (modo GUI)")
    else:
        print("  Consola: Visible (modo depuración)")

    # Nombre del ejecutable
    cmd.extend(["--name", NOMBRE_EJECUTABLE])
    print(f"  Nombre: {NOMBRE_EJECUTABLE}")

    # Icono personalizado
    if RUTA_ICONO and os.path.exists(RUTA_ICONO):
        cmd.extend(["--icon", RUTA_ICONO])
        print(f"  Icono: {RUTA_ICONO}")
    elif RUTA_ICONO:
        print(f"  ⚠ Icono no encontrado en: {RUTA_ICONO} (se omitirá)")

    # Directorio de salida
    cmd.extend(["--distpath", DIRECTORIO_SALIDA])

    # Incluir el directorio src/ply como datos
    ply_src = os.path.join("src", "ply")
    if os.path.exists(ply_src):
        separador = ";" if sys.platform == "win32" else ":"
        cmd.extend(["--add-data", f"{ply_src}{separador}ply"])
        print(f"  Incluyendo: {ply_src}")

    # Limpiar builds anteriores automáticamente
    cmd.append("--clean")

    # No confirmar cada pregunta
    cmd.append("--noconfirm")

    # Archivo principal
    cmd.append(ARCHIVO_PRINCIPAL)

    return cmd


def limpiar_archivos_temporales():
    """Elimina archivos temporales de construcciones anteriores."""
    carpetas_temp = ["build", "__pycache__", f"{NOMBRE_EJECUTABLE}.spec"]
    for carpeta in carpetas_temp:
        if os.path.exists(carpeta):
            if os.path.isdir(carpeta):
                shutil.rmtree(carpeta)
            else:
                os.remove(carpeta)
    print("  ✓ Archivos temporales eliminados")


def mostrar_resumen(exitoso):
    """Muestra el resumen final del proceso."""
    print("\n" + "=" * 60)
    if exitoso:
        ext = ".exe" if sys.platform == "win32" else ""
        ruta_exe = os.path.join(DIRECTORIO_SALIDA, f"{NOMBRE_EJECUTABLE}{ext}")
        print("  ✓ CONVERSIÓN EXITOSA")
        print(f"\n  El ejecutable se encuentra en:")
        print(f"    {os.path.abspath(ruta_exe)}")
        print(f"\n  Tamaño aproximado:")
        if os.path.exists(ruta_exe):
            tam = os.path.getsize(ruta_exe)
            if tam > 1_000_000:
                print(f"    {tam / 1_000_000:.1f} MB")
            else:
                print(f"    {tam / 1_000:.1f} KB")
        print(f"\n  Para distribuir el programa:")
        if UN_SOLO_ARCHIVO:
            print(f"    Comparte únicamente el archivo: {NOMBRE_EJECUTABLE}{ext}")
        else:
            print(f"    Comparte toda la carpeta: {DIRECTORIO_SALIDA}/{NOMBRE_EJECUTABLE}/")
    else:
        print("  ✗ LA CONVERSIÓN FALLÓ")
        print("\n  Posibles soluciones:")
        print("    1. Verifica que PyInstaller esté instalado: pip install pyinstaller")
        print("    2. Verifica que el archivo principal exista:", ARCHIVO_PRINCIPAL)
        print("    3. Revisa los mensajes de error arriba")
    print("=" * 60)


# =============================================================================
#  PROCESO PRINCIPAL
# =============================================================================

def main():
    print("=" * 60)
    print("  CONVERTIDOR A PROGRAMA DE ESCRITORIO")
    print("  PLY Compiler → Ejecutable nativo")
    print("=" * 60)
    print()

    # 1. Verificar que el archivo principal existe
    if not os.path.exists(ARCHIVO_PRINCIPAL):
        print(f"✗ No se encontró el archivo principal: {ARCHIVO_PRINCIPAL}")
        print(f"  Asegúrate de ejecutar este script desde la raíz del proyecto PLY.")
        sys.exit(1)
    print(f"✓ Archivo principal encontrado: {ARCHIVO_PRINCIPAL}")

    # 2. Verificar PyInstaller
    print()
    print("Verificando dependencias...")
    if not verificar_pyinstaller():
        print("✗ No se puede continuar sin PyInstaller.")
        sys.exit(1)

    # 3. Construir el comando
    print()
    print("Configuración de la build:")
    cmd = construir_comando()

    # 4. Confirmar antes de ejecutar
    print()
    print("Comando que se ejecutará:")
    print(" ", " ".join(cmd))
    print()
    respuesta = input("¿Continuar con la conversión? (s/n): ").strip().lower()
    if respuesta != 's':
        print("Operación cancelada.")
        sys.exit(0)

    # 5. Ejecutar PyInstaller
    print()
    print("Iniciando conversión (esto puede tardar 1-3 minutos)...")
    print("-" * 60)

    resultado = subprocess.run(cmd)
    exitoso = resultado.returncode == 0

    # 6. Limpiar temporales si fue exitoso
    if exitoso:
        print()
        print("Limpiando archivos temporales...")
        limpiar_archivos_temporales()

    # 7. Mostrar resumen
    mostrar_resumen(exitoso)

    # 8. Ofrecer ejecutar inmediatamente (solo en éxito)
    if exitoso and sys.platform != "win32":
        print()
        ejecutar = input("¿Quieres ejecutar el programa ahora? (s/n): ").strip().lower()
        if ejecutar == 's':
            ruta_exe = os.path.join(DIRECTORIO_SALIDA, NOMBRE_EJECUTABLE)
            os.chmod(ruta_exe, 0o755)
            subprocess.Popen([ruta_exe])
            print(f"  Ejecutando: {ruta_exe}")


if __name__ == '__main__':
    main()
