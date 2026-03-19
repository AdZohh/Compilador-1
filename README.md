# PLY (Python Lex-Yacc) — Versión en Español

PLY es una implementación en Python puro de las herramientas clásicas `lex` y `yacc` para la construcción de compiladores e intérpretes.

**Repositorio original:** https://github.com/dabeaz/ply  
**Autor:** David M. Beazley (Dabeaz LLC)  
**Versión traducida:** Comentarios y documentación en español

---

## ¿Qué incluye esta versión?

```
ply-master/
├── src/ply/
│   ├── lex.py                   ← Analizador léxico (comentarios en español)
│   └── yacc.py                  ← Analizador sintáctico (comentarios en español)
├── example/
│   ├── calc/         calc.py    ← Calculadora simple con variables
│   ├── calcdebug/    calc.py    ← Calculadora con modo depuración
│   ├── calceof/      calc.py    ← Calculadora con regla t_eof()
│   ├── BASIC/                   ← Intérprete completo de BASIC (1964)
│   ├── ansic/                   ← Parser del lenguaje C estándar
│   └── GardenSnake/             ← Subconjunto de Python con indentación
├── tests/                       ← 60+ pruebas unitarias
├── doc/
│   ├── ply.md                   ← Documentación completa de PLY
│   └── internals.md             ← Detalles internos del motor
│
├── interfaz_compilador.py       ← ★ INTERFAZ GRÁFICA (nuevo)
└── convertir_a_escritorio.py    ← ★ CONVERSOR A EJECUTABLE (nuevo)
```

---

## Instalación rápida

```bash
# Clonar o descomprimir el proyecto
cd ply-master

# Instalar PLY en tu entorno Python
pip install -e .

# O usarlo directamente sin instalar:
# Agrega src/ al PYTHONPATH
export PYTHONPATH=src   # Linux/Mac
set PYTHONPATH=src      # Windows
```

---

## Ejecutar la interfaz gráfica

```bash
python interfaz_compilador.py
```

La interfaz incluye:
- **Editor de código** con numeración de líneas
- **Tabla de tokens** reconocidos (tipo, valor, línea, posición)
- **Consola de salida** con colores para resultados y errores
- **Abrir/guardar** archivos de código fuente
- Atajos: `Ctrl+Enter` para compilar

---

## Convertir a programa de escritorio

```bash
# Paso 1: Instalar PyInstaller (solo la primera vez)
pip install pyinstaller

# Paso 2: Ejecutar el conversor
python convertir_a_escritorio.py
```

El ejecutable se genera en la carpeta `dist/`:
- **Windows:** `dist/CompiladorPLY.exe`
- **Mac/Linux:** `dist/CompiladorPLY`

---

## Uso básico de PLY

### 1. Definir tokens (analizador léxico)

```python
import ply.lex as lex

tokens = ('NUMERO', 'NOMBRE')
t_NOMBRE = r'[a-zA-Z_][a-zA-Z0-9_]*'

def t_NUMERO(t):
    r'\d+'
    t.value = int(t.value)
    return t

t_ignore = ' \t'

def t_error(t):
    print(f"Carácter ilegal: {t.value[0]}")
    t.lexer.skip(1)

lexer = lex.lex()
```

### 2. Definir gramática (analizador sintáctico)

```python
import ply.yacc as yacc

def p_expresion_suma(p):
    'expresion : expresion "+" expresion'
    p[0] = p[1] + p[3]

def p_expresion_numero(p):
    'expresion : NUMERO'
    p[0] = p[1]

def p_error(p):
    print("Error de sintaxis")

parser = yacc.yacc()
resultado = parser.parse("3 + 4")
print(resultado)  # 7
```

---

## Documentación

- **`doc/ply.md`** — Guía completa de uso de PLY
- **`doc/internals.md`** — Detalles del motor interno (LALR, tablas LR)

---

## Ejemplos incluidos

| Ejemplo | Descripción |
|---------|-------------|
| `example/calc/` | Calculadora con variables. El más simple para aprender |
| `example/BASIC/` | Intérprete completo de Dartmouth BASIC 1964 |
| `example/ansic/` | Lexer y parser para el lenguaje C completo |
| `example/GardenSnake/` | Subconjunto de Python con indentación significativa |
| `example/cpp/` | Preprocesador de C |

---

## Licencia

Copyright (C) 2001-2022 David M. Beazley (Dabeaz LLC)  
Distribuido bajo licencia BSD. Ver el encabezado de `src/ply/lex.py` para los detalles completos.
