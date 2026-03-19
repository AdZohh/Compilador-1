# -----------------------------------------------------------------------------
# ply: lex.py
#
# Copyright (C) 2001-2022
# David M. Beazley (Dabeaz LLC)
# Todos los derechos reservados.
#
# Última versión: https://github.com/dabeaz/ply
#
# Se permite la redistribución y uso en formas fuente y binaria, con o
# sin modificación, siempre que se cumplan las siguientes condiciones:
#
# * Las redistribuciones del código fuente deben conservar el aviso de
#   copyright, esta lista de condiciones y el siguiente aviso.
# * Las redistribuciones en forma binaria deben reproducir el aviso de
#   copyright, esta lista de condiciones y el siguiente aviso en la
#   documentación y/o materiales distribuidos.
# * No se puede usar el nombre de David Beazley o Dabeaz LLC para
#   endorsar productos derivados sin permiso previo por escrito.
#
# ESTE SOFTWARE SE PROPORCIONA "TAL CUAL" SIN GARANTÍAS DE NINGÚN TIPO.
# -----------------------------------------------------------------------------

import re
import sys
import types
import copy
import os
import inspect

# Esta tupla contiene los tipos de cadena aceptables
StringTypes = (str, bytes)

# Esta expresión regular se usa para validar nombres de tokens
_is_identifier = re.compile(r'^[a-zA-Z0-9_]+$')

# Excepción lanzada cuando se encuentra un token inválido y no hay
# manejador de error definido.
class LexError(Exception):
    def __init__(self, message, s):
        self.args = (message,)
        self.text = s

# Clase Token. Representa cada token producido por el analizador léxico.
class LexToken(object):
    def __repr__(self):
        return f'LexToken({self.type},{self.value!r},{self.lineno},{self.lexpos})'

# Objeto sustituto del logger del módulo logging estándar.
class PlyLogger(object):
    def __init__(self, f):
        self.f = f

    def critical(self, msg, *args, **kwargs):
        self.f.write((msg % args) + '\n')

    def warning(self, msg, *args, **kwargs):
        self.f.write('ADVERTENCIA: ' + (msg % args) + '\n')

    def error(self, msg, *args, **kwargs):
        self.f.write('ERROR: ' + (msg % args) + '\n')

    info = critical
    debug = critical

# -----------------------------------------------------------------------------
#                   === Motor del Analizador Léxico ===
#
# La clase Lexer implementa el motor léxico en tiempo de ejecución.
# Métodos y atributos públicos:
#
#    input()   - Carga una nueva cadena en el analizador
#    token()   - Obtiene el siguiente token
#    clone()   - Clona el analizador léxico
#    lineno    - Número de línea actual
#    lexpos    - Posición actual en la cadena de entrada
# -----------------------------------------------------------------------------

class Lexer:
    def __init__(self):
        self.lexre = None             # Expresión regular maestra
        self.lexretext = None         # Cadenas de la regex actual
        self.lexstatere = {}          # Diccionario estado → regex maestra
        self.lexstateretext = {}      # Diccionario estado → cadenas regex
        self.lexstaterenames = {}     # Diccionario estado → nombres de símbolos
        self.lexstate = 'INITIAL'     # Estado actual del lexer
        self.lexstatestack = []       # Pila de estados
        self.lexstateinfo = None      # Información de estados
        self.lexstateignore = {}      # Caracteres ignorados por estado
        self.lexstateerrorf = {}      # Funciones de error por estado
        self.lexstateeoff = {}        # Funciones EOF por estado
        self.lexreflags = 0           # Indicadores de compilación de regex
        self.lexdata = None           # Datos de entrada (cadena)
        self.lexpos = 0               # Posición actual en la entrada
        self.lexlen = 0               # Longitud del texto de entrada
        self.lexerrorf = None         # Regla de error (si existe)
        self.lexeoff = None           # Regla de EOF (si existe)
        self.lextokens = None         # Lista de tokens válidos
        self.lexignore = ''           # Caracteres ignorados
        self.lexliterals = ''         # Caracteres literales que pasan directamente
        self.lexmodule = None         # Módulo fuente
        self.lineno = 1               # Número de línea actual

    def clone(self, object=None):
        c = copy.copy(self)
        # Si se proporcionó object, reasignar todos los métodos de las tablas
        # lexstatere y lexstateerrorf al nuevo objeto.
        if object:
            newtab = {}
            for key, ritem in self.lexstatere.items():
                newre = []
                for cre, findex in ritem:
                    newfindex = []
                    for f in findex:
                        if not f or not f[0]:
                            newfindex.append(f)
                            continue
                        newfindex.append((getattr(object, f[0].__name__), f[1]))
                    newre.append((cre, newfindex))
                newtab[key] = newre
            c.lexstatere = newtab
            c.lexstateerrorf = {}
            for key, ef in self.lexstateerrorf.items():
                c.lexstateerrorf[key] = getattr(object, ef.__name__)
            c.lexmodule = object
        return c

    # ------------------------------------------------------------
    # input() - Carga una nueva cadena en el analizador léxico
    # ------------------------------------------------------------
    def input(self, s):
        self.lexdata = s
        self.lexpos = 0
        self.lexlen = len(s)

    # ------------------------------------------------------------
    # begin() - Cambia el estado del analizador léxico
    # ------------------------------------------------------------
    def begin(self, state):
        if state not in self.lexstatere:
            raise ValueError(f'Estado no definido {state!r}')
        self.lexre = self.lexstatere[state]
        self.lexretext = self.lexstateretext[state]
        self.lexignore = self.lexstateignore.get(state, '')
        self.lexerrorf = self.lexstateerrorf.get(state, None)
        self.lexeoff = self.lexstateeoff.get(state, None)
        self.lexstate = state

    # ------------------------------------------------------------
    # push_state() - Cambia el estado y guarda el anterior en la pila
    # ------------------------------------------------------------
    def push_state(self, state):
        self.lexstatestack.append(self.lexstate)
        self.begin(state)

    # ------------------------------------------------------------
    # pop_state() - Restaura el estado anterior desde la pila
    # ------------------------------------------------------------
    def pop_state(self):
        self.begin(self.lexstatestack.pop())

    # ------------------------------------------------------------
    # current_state() - Devuelve el estado actual del analizador
    # ------------------------------------------------------------
    def current_state(self):
        return self.lexstate

    # ------------------------------------------------------------
    # skip() - Avanza n caracteres en la entrada
    # ------------------------------------------------------------
    def skip(self, n):
        self.lexpos += n

    # ------------------------------------------------------------
    # token() - Devuelve el siguiente token del analizador léxico
    #
    # Nota: Optimizada al máximo para velocidad. No modificar sin
    # entender completamente su funcionamiento.
    # ------------------------------------------------------------
    def token(self):
        # Copias locales de atributos accedidos frecuentemente
        lexpos    = self.lexpos
        lexlen    = self.lexlen
        lexignore = self.lexignore
        lexdata   = self.lexdata

        while lexpos < lexlen:
            # Cortocircuito para espacios, tabulaciones y caracteres ignorados
            if lexdata[lexpos] in lexignore:
                lexpos += 1
                continue

            # Buscar coincidencia con la expresión regular
            for lexre, lexindexfunc in self.lexre:
                m = lexre.match(lexdata, lexpos)
                if not m:
                    continue

                # Crear el token para devolver
                tok = LexToken()
                tok.value = m.group()
                tok.lineno = self.lineno
                tok.lexpos = lexpos

                i = m.lastindex
                func, tok.type = lexindexfunc[i]

                if not func:
                    # Sin función asignada: token ignorado si no tiene tipo
                    if tok.type:
                        self.lexpos = m.end()
                        return tok
                    else:
                        lexpos = m.end()
                        break

                lexpos = m.end()

                # Llamar a la función de procesamiento del token
                tok.lexer = self
                self.lexmatch = m
                self.lexpos = lexpos
                newtok = func(tok)
                del tok.lexer
                del self.lexmatch

                # Si la función no devuelve token, avanzar al siguiente
                if not newtok:
                    lexpos    = self.lexpos
                    lexignore = self.lexignore
                    break
                return newtok
            else:
                # Sin coincidencia: verificar si es un literal
                if lexdata[lexpos] in self.lexliterals:
                    tok = LexToken()
                    tok.value = lexdata[lexpos]
                    tok.lineno = self.lineno
                    tok.type = tok.value
                    tok.lexpos = lexpos
                    self.lexpos = lexpos + 1
                    return tok

                # Sin coincidencia: llamar a t_error() si existe
                if self.lexerrorf:
                    tok = LexToken()
                    tok.value = self.lexdata[lexpos:]
                    tok.lineno = self.lineno
                    tok.type = 'error'
                    tok.lexer = self
                    tok.lexpos = lexpos
                    self.lexpos = lexpos
                    newtok = self.lexerrorf(tok)
                    if lexpos == self.lexpos:
                        raise LexError(f"Error de escaneo. Carácter ilegal {lexdata[lexpos]!r}",
                                       lexdata[lexpos:])
                    lexpos = self.lexpos
                    if not newtok:
                        continue
                    return newtok

                self.lexpos = lexpos
                raise LexError(f"Carácter ilegal {lexdata[lexpos]!r} en posición {lexpos}",
                               lexdata[lexpos:])

        if self.lexeoff:
            tok = LexToken()
            tok.type = 'eof'
            tok.value = ''
            tok.lineno = self.lineno
            tok.lexpos = lexpos
            tok.lexer = self
            self.lexpos = lexpos
            newtok = self.lexeoff(tok)
            return newtok

        self.lexpos = lexpos + 1
        if self.lexdata is None:
            raise RuntimeError('No se proporcionó cadena de entrada con input()')
        return None

    # Interfaz de iterador
    def __iter__(self):
        return self

    def __next__(self):
        t = self.token()
        if t is None:
            raise StopIteration
        return t

# -----------------------------------------------------------------------------
#                        ==== Constructor del Lexer ====
#
# Las funciones y clases siguientes recolectan información léxica y
# construyen un objeto Lexer a partir de ella.
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# _get_regex(func)
#
# Devuelve la expresión regular de una función, ya sea desde su docstring
# o desde el atributo .regex asignado por el decorador @TOKEN.
# -----------------------------------------------------------------------------
def _get_regex(func):
    return getattr(func, 'regex', func.__doc__)

# -----------------------------------------------------------------------------
# get_caller_module_dict()
#
# Devuelve un diccionario con todos los símbolos definidos en el módulo
# llamante. Se usa para obtener el entorno de la llamada a yacc() o lex().
# -----------------------------------------------------------------------------
def get_caller_module_dict(levels):
    f = sys._getframe(levels)
    return { **f.f_globals, **f.f_locals }

# -----------------------------------------------------------------------------
# _form_master_re()
#
# Toma una lista de componentes regex y forma la expresión regular maestra.
# Si el módulo re de Python tiene limitaciones, la divide en subexpresiones.
# -----------------------------------------------------------------------------
def _form_master_re(relist, reflags, ldict, toknames):
    if not relist:
        return [], [], []
    regex = '|'.join(relist)
    try:
        lexre = re.compile(regex, reflags)
        lexindexfunc = [None] * (max(lexre.groupindex.values()) + 1)
        lexindexnames = lexindexfunc[:]

        for f, i in lexre.groupindex.items():
            handle = ldict.get(f, None)
            if type(handle) in (types.FunctionType, types.MethodType):
                lexindexfunc[i] = (handle, toknames[f])
                lexindexnames[i] = f
            elif handle is not None:
                lexindexnames[i] = f
                if f.find('ignore_') > 0:
                    lexindexfunc[i] = (None, None)
                else:
                    lexindexfunc[i] = (None, toknames[f])

        return [(lexre, lexindexfunc)], [regex], [lexindexnames]
    except Exception:
        m = (len(relist) // 2) + 1
        llist, lre, lnames = _form_master_re(relist[:m], reflags, ldict, toknames)
        rlist, rre, rnames = _form_master_re(relist[m:], reflags, ldict, toknames)
        return (llist+rlist), (lre+rre), (lnames+rnames)

# -----------------------------------------------------------------------------
# _statetoken(s, names)
#
# Dado el nombre "t_foo_bar_SPAM" y un diccionario de estados conocidos,
# devuelve (('foo','bar'), 'SPAM'): la tupla de estados y el nombre del token.
# -----------------------------------------------------------------------------
def _statetoken(s, names):
    parts = s.split('_')
    for i, part in enumerate(parts[1:], 1):
        if part not in names and part != 'ANY':
            break

    if i > 1:
        states = tuple(parts[1:i])
    else:
        states = ('INITIAL',)

    if 'ANY' in states:
        states = tuple(names)

    tokenname = '_'.join(parts[i:])
    return (states, tokenname)


# -----------------------------------------------------------------------------
# LexerReflect()
#
# Clase que extrae la información necesaria para construir el lexer desde
# el archivo de entrada del usuario.
# -----------------------------------------------------------------------------
class LexerReflect(object):
    def __init__(self, ldict, log=None, reflags=0):
        self.ldict      = ldict
        self.error_func = None
        self.tokens     = []
        self.reflags    = reflags
        self.stateinfo  = {'INITIAL': 'inclusive'}
        self.modules    = set()
        self.error      = False
        self.log        = PlyLogger(sys.stderr) if log is None else log

    # Obtener toda la información básica
    def get_all(self):
        self.get_tokens()
        self.get_literals()
        self.get_states()
        self.get_rules()

    # Validar toda la información
    def validate_all(self):
        self.validate_tokens()
        self.validate_literals()
        self.validate_rules()
        return self.error

    # Obtener el mapa de tokens
    def get_tokens(self):
        tokens = self.ldict.get('tokens', None)
        if not tokens:
            self.log.error('No se ha definido la lista de tokens')
            self.error = True
            return

        if not isinstance(tokens, (list, tuple)):
            self.log.error('tokens debe ser una lista o tupla')
            self.error = True
            return

        if not tokens:
            self.log.error('tokens está vacío')
            self.error = True
            return

        self.tokens = tokens

    # Validar los tokens
    def validate_tokens(self):
        terminals = {}
        for n in self.tokens:
            if not _is_identifier.match(n):
                self.log.error(f"Nombre de token inválido {n!r}")
                self.error = True
            if n in terminals:
                self.log.warning(f"Token {n!r} definido múltiples veces")
            terminals[n] = 1

    # Obtener la especificación de literales
    def get_literals(self):
        self.literals = self.ldict.get('literals', '')
        if not self.literals:
            self.literals = ''

    # Validar los literales
    def validate_literals(self):
        try:
            for c in self.literals:
                if not isinstance(c, StringTypes) or len(c) > 1:
                    self.log.error(f'Literal inválido {c!r}. Debe ser un solo carácter')
                    self.error = True
        except TypeError:
            self.log.error('Especificación de literales inválida. literals debe ser una secuencia de caracteres')
            self.error = True

    def get_states(self):
        self.states = self.ldict.get('states', None)
        if self.states:
            if not isinstance(self.states, (tuple, list)):
                self.log.error('states debe definirse como tupla o lista')
                self.error = True
            else:
                for s in self.states:
                    if not isinstance(s, tuple) or len(s) != 2:
                        self.log.error("Especificador de estado inválido %r. Debe ser (nombre,'exclusive|inclusive')", s)
                        self.error = True
                        continue
                    name, statetype = s
                    if not isinstance(name, StringTypes):
                        self.log.error('El nombre de estado %r debe ser una cadena', name)
                        self.error = True
                        continue
                    if not (statetype == 'inclusive' or statetype == 'exclusive'):
                        self.log.error("El tipo de estado %r debe ser 'inclusive' o 'exclusive'", name)
                        self.error = True
                        continue
                    if name in self.stateinfo:
                        self.log.error("El estado %r ya está definido", name)
                        self.error = True
                        continue
                    self.stateinfo[name] = statetype

    # Obtener todos los símbolos con prefijo t_ y clasificarlos
    def get_rules(self):
        tsymbols = [f for f in self.ldict if f[:2] == 't_']

        self.toknames = {}
        self.funcsym  = {}
        self.strsym   = {}
        self.ignore   = {}
        self.errorf   = {}
        self.eoff     = {}

        for s in self.stateinfo:
            self.funcsym[s] = []
            self.strsym[s] = []

        if len(tsymbols) == 0:
            self.log.error('No se han definido reglas de la forma t_nombre_regla')
            self.error = True
            return

        for f in tsymbols:
            t = self.ldict[f]
            states, tokname = _statetoken(f, self.stateinfo)
            self.toknames[f] = tokname

            if hasattr(t, '__call__'):
                if tokname == 'error':
                    for s in states:
                        self.errorf[s] = t
                elif tokname == 'eof':
                    for s in states:
                        self.eoff[s] = t
                elif tokname == 'ignore':
                    line = t.__code__.co_firstlineno
                    file = t.__code__.co_filename
                    self.log.error("%s:%d: La regla %r debe definirse como cadena", file, line, t.__name__)
                    self.error = True
                else:
                    for s in states:
                        self.funcsym[s].append((f, t))
            elif isinstance(t, StringTypes):
                if tokname == 'ignore':
                    for s in states:
                        self.ignore[s] = t
                    if '\\' in t:
                        self.log.warning("%s contiene una barra invertida literal '\\'", f)
                elif tokname == 'error':
                    self.log.error("La regla %r debe definirse como función", f)
                    self.error = True
                else:
                    for s in states:
                        self.strsym[s].append((f, t))
            else:
                self.log.error('%s no está definido como función ni como cadena', f)
                self.error = True

        # Ordenar funciones por número de línea
        for f in self.funcsym.values():
            f.sort(key=lambda x: x[1].__code__.co_firstlineno)

        # Ordenar cadenas por longitud de expresión regular (descendente)
        for s in self.strsym.values():
            s.sort(key=lambda x: len(x[1]), reverse=True)

    # Validar todas las reglas t_ recolectadas
    def validate_rules(self):
        for state in self.stateinfo:
            for fname, f in self.funcsym[state]:
                line = f.__code__.co_firstlineno
                file = f.__code__.co_filename
                module = inspect.getmodule(f)
                self.modules.add(module)

                tokname = self.toknames[fname]
                if isinstance(f, types.MethodType):
                    reqargs = 2
                else:
                    reqargs = 1
                nargs = f.__code__.co_argcount
                if nargs > reqargs:
                    self.log.error("%s:%d: La regla %r tiene demasiados argumentos", file, line, f.__name__)
                    self.error = True
                    continue

                if nargs < reqargs:
                    self.log.error("%s:%d: La regla %r requiere un argumento", file, line, f.__name__)
                    self.error = True
                    continue

                if not _get_regex(f):
                    self.log.error("%s:%d: No hay expresión regular para la regla %r", file, line, f.__name__)
                    self.error = True
                    continue

                try:
                    c = re.compile('(?P<%s>%s)' % (fname, _get_regex(f)), self.reflags)
                    if c.match(''):
                        self.log.error("%s:%d: La regex de %r coincide con cadena vacía", file, line, f.__name__)
                        self.error = True
                except re.error as e:
                    self.log.error("%s:%d: Regex inválida para '%s'. %s", file, line, f.__name__, e)
                    if '#' in _get_regex(f):
                        self.log.error("%s:%d. Escapa '#' en la regla %r con '\\#'", file, line, f.__name__)
                    self.error = True

            for name, r in self.strsym[state]:
                tokname = self.toknames[name]
                if tokname == 'error':
                    self.log.error("La regla %r debe definirse como función", name)
                    self.error = True
                    continue

                if tokname not in self.tokens and tokname.find('ignore_') < 0:
                    self.log.error("La regla %r está definida para un token no especificado %s", name, tokname)
                    self.error = True
                    continue

                try:
                    c = re.compile('(?P<%s>%s)' % (name, r), self.reflags)
                    if (c.match('')):
                        self.log.error("La regex de la regla %r coincide con cadena vacía", name)
                        self.error = True
                except re.error as e:
                    self.log.error("Regex inválida para la regla %r. %s", name, e)
                    if '#' in r:
                        self.log.error("Escapa '#' en la regla %r con '\\#'", name)
                    self.error = True

            if not self.funcsym[state] and not self.strsym[state]:
                self.log.error("No se han definido reglas para el estado %r", state)
                self.error = True

            efunc = self.errorf.get(state, None)
            if efunc:
                f = efunc
                line = f.__code__.co_firstlineno
                file = f.__code__.co_filename
                module = inspect.getmodule(f)
                self.modules.add(module)

                if isinstance(f, types.MethodType):
                    reqargs = 2
                else:
                    reqargs = 1
                nargs = f.__code__.co_argcount
                if nargs > reqargs:
                    self.log.error("%s:%d: La regla %r tiene demasiados argumentos", file, line, f.__name__)
                    self.error = True
                if nargs < reqargs:
                    self.log.error("%s:%d: La regla %r requiere un argumento", file, line, f.__name__)
                    self.error = True

        for module in self.modules:
            self.validate_module(module)

    # -----------------------------------------------------------------------------
    # validate_module()
    #
    # Verifica si hay funciones o cadenas t_nombre() duplicadas en el archivo
    # de entrada. Usa búsqueda por expresión regular en el código fuente.
    # -----------------------------------------------------------------------------
    def validate_module(self, module):
        try:
            lines, linen = inspect.getsourcelines(module)
        except IOError:
            return

        fre = re.compile(r'\s*def\s+(t_[a-zA-Z_0-9]*)\(')
        sre = re.compile(r'\s*(t_[a-zA-Z_0-9]*)\s*=')

        counthash = {}
        linen += 1
        for line in lines:
            m = fre.match(line)
            if not m:
                m = sre.match(line)
            if m:
                name = m.group(1)
                prev = counthash.get(name)
                if not prev:
                    counthash[name] = linen
                else:
                    filename = inspect.getsourcefile(module)
                    self.log.error('%s:%d: La regla %s está redefinida. Definida antes en línea %d', filename, linen, name, prev)
                    self.error = True
            linen += 1

# -----------------------------------------------------------------------------
# lex(module)
#
# Construye todas las reglas de expresiones regulares desde las definiciones
# del módulo suministrado.
# -----------------------------------------------------------------------------
def lex(*, module=None, object=None, debug=False,
        reflags=int(re.VERBOSE), debuglog=None, errorlog=None):

    global lexer

    ldict = None
    stateinfo  = {'INITIAL': 'inclusive'}
    lexobj = Lexer()
    global token, input

    if errorlog is None:
        errorlog = PlyLogger(sys.stderr)

    if debug:
        if debuglog is None:
            debuglog = PlyLogger(sys.stderr)

    if object:
        module = object

    if module:
        _items = [(k, getattr(module, k)) for k in dir(module)]
        ldict = dict(_items)
        if '__file__' not in ldict:
            ldict['__file__'] = sys.modules[ldict['__module__']].__file__
    else:
        ldict = get_caller_module_dict(2)

    linfo = LexerReflect(ldict, log=errorlog, reflags=reflags)
    linfo.get_all()
    if linfo.validate_all():
        raise SyntaxError("No se puede construir el analizador léxico")

    if debug:
        debuglog.info('lex: tokens   = %r', linfo.tokens)
        debuglog.info('lex: literals = %r', linfo.literals)
        debuglog.info('lex: states   = %r', linfo.stateinfo)

    lexobj.lextokens = set()
    for n in linfo.tokens:
        lexobj.lextokens.add(n)

    if isinstance(linfo.literals, (list, tuple)):
        lexobj.lexliterals = type(linfo.literals[0])().join(linfo.literals)
    else:
        lexobj.lexliterals = linfo.literals

    lexobj.lextokens_all = lexobj.lextokens | set(lexobj.lexliterals)
    stateinfo = linfo.stateinfo
    regexs = {}

    for state in stateinfo:
        regex_list = []
        for fname, f in linfo.funcsym[state]:
            regex_list.append('(?P<%s>%s)' % (fname, _get_regex(f)))
            if debug:
                debuglog.info("lex: Agregando regla %s -> '%s' (estado '%s')", fname, _get_regex(f), state)
        for name, r in linfo.strsym[state]:
            regex_list.append('(?P<%s>%s)' % (name, r))
            if debug:
                debuglog.info("lex: Agregando regla %s -> '%s' (estado '%s')", name, r, state)
        regexs[state] = regex_list

    if debug:
        debuglog.info('lex: ==== EXPRESIONES REGULARES MAESTRAS ====')

    for state in regexs:
        lexre, re_text, re_names = _form_master_re(regexs[state], reflags, ldict, linfo.toknames)
        lexobj.lexstatere[state] = lexre
        lexobj.lexstateretext[state] = re_text
        lexobj.lexstaterenames[state] = re_names
        if debug:
            for i, text in enumerate(re_text):
                debuglog.info("lex: estado '%s' : regex[%d] = '%s'", state, i, text)

    # Para estados inclusivos, agregar las regex del estado INITIAL
    for state, stype in stateinfo.items():
        if state != 'INITIAL' and stype == 'inclusive':
            lexobj.lexstatere[state].extend(lexobj.lexstatere['INITIAL'])
            lexobj.lexstateretext[state].extend(lexobj.lexstateretext['INITIAL'])
            lexobj.lexstaterenames[state].extend(lexobj.lexstaterenames['INITIAL'])

    lexobj.lexstateinfo = stateinfo
    lexobj.lexre = lexobj.lexstatere['INITIAL']
    lexobj.lexretext = lexobj.lexstateretext['INITIAL']
    lexobj.lexreflags = reflags

    lexobj.lexstateignore = linfo.ignore
    lexobj.lexignore = lexobj.lexstateignore.get('INITIAL', '')

    lexobj.lexstateerrorf = linfo.errorf
    lexobj.lexerrorf = linfo.errorf.get('INITIAL', None)
    if not lexobj.lexerrorf:
        errorlog.warning('No se ha definido la regla t_error')

    lexobj.lexstateeoff = linfo.eoff
    lexobj.lexeoff = linfo.eoff.get('INITIAL', None)

    for s, stype in stateinfo.items():
        if stype == 'exclusive':
            if s not in linfo.errorf:
                errorlog.warning("No hay regla de error para el estado exclusivo %r", s)
            if s not in linfo.ignore and lexobj.lexignore:
                errorlog.warning("No hay regla de ignorado para el estado exclusivo %r", s)
        elif stype == 'inclusive':
            if s not in linfo.errorf:
                linfo.errorf[s] = linfo.errorf.get('INITIAL', None)
            if s not in linfo.ignore:
                linfo.ignore[s] = linfo.ignore.get('INITIAL', '')

    token = lexobj.token
    input = lexobj.input
    lexer = lexobj

    return lexobj

# -----------------------------------------------------------------------------
# runmain()
#
# Ejecuta el lexer como programa principal desde la línea de comandos.
# -----------------------------------------------------------------------------
def runmain(lexer=None, data=None):
    if not data:
        try:
            filename = sys.argv[1]
            with open(filename) as f:
                data = f.read()
        except IndexError:
            sys.stdout.write('Leyendo desde entrada estándar (escribe EOF para terminar):\n')
            data = sys.stdin.read()

    if lexer:
        _input = lexer.input
    else:
        _input = input
    _input(data)
    if lexer:
        _token = lexer.token
    else:
        _token = token

    while True:
        tok = _token()
        if not tok:
            break
        sys.stdout.write(f'({tok.type},{tok.value!r},{tok.lineno},{tok.lexpos})\n')

# -----------------------------------------------------------------------------
# @TOKEN(regex)
#
# Decorador para asignar la expresión regular a una función cuando su
# docstring necesita configurarse de otra manera.
# -----------------------------------------------------------------------------
def TOKEN(r):
    def set_regex(f):
        if hasattr(r, '__call__'):
            f.regex = _get_regex(r)
        else:
            f.regex = r
        return f
    return set_regex
