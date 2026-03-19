# Implementación del lenguaje Dartmouth BASIC (1964)
#

import basiclex
import basparse
import basinterp

# Si se especificó un archivo, intentar ejecutarlo.
# Si ocurre un error en tiempo de ejecución, entrar
# al modo interactivo.
if len(sys.argv) == 2:
    with open(sys.argv[1]) as f:
        data = f.read()
    prog = basparse.parse(data)
    if not prog:
        raise SystemExit
    b = basinterp.BasicInterpreter(prog)
    try:
        b.run()
        raise SystemExit
    except RuntimeError:
        pass

else:
    b = basinterp.BasicInterpreter({})

# Modo interactivo. Agrega/elimina sentencias incrementalmente
# del objeto BasicInterpreter. Los comandos especiales 'NEW',
# 'LIST' y 'RUN' están disponibles. Un número de línea sin código
# elimina esa línea del programa.

while True:
    try:
        line = input("[BASIC] ")
    except EOFError:
        raise SystemExit
    if not line:
        continue
    line += "\n"
    prog = basparse.parse(line)
    if not prog:
        continue

    keys = list(prog)
    if keys[0] > 0:
        b.add_statements(prog)
    else:
        stat = prog[keys[0]]
        if stat[0] == 'RUN':
            try:
                b.run()
            except RuntimeError:
                pass
        elif stat[0] == 'LIST':
            b.list()
        elif stat[0] == 'BLANK':
            b.del_line(stat[1])
        elif stat[0] == 'NEW':
            b.new()
