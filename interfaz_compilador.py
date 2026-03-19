# =============================================================================
# interfaz_compilador.py
#
# Compilador PLY — Análisis Léxico y Semántico
# - Resaltado de sintaxis en tiempo real
# - Análisis léxico con tabla de tokens y colores por categoría
# - Análisis semántico con tabla de símbolos
# - Árbol semántico visual (canvas tkinter, sin necesitar graphviz instalado)
# - Buffer de entrada visible
# - Consola de salida con fases diferenciadas
#
# Requiere: Python 3.x, tkinter (incluido), graphviz (opcional)
#   pip install graphviz
# =============================================================================

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import sys, io, os, re, time
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
import ply.lex as lex
import ply.yacc as yacc

try:
    import graphviz
    GRAPHVIZ_OK = True
except ImportError:
    GRAPHVIZ_OK = False

# =============================================================================
#  NODO DEL ÁRBOL
# =============================================================================
class Nodo:
    _c = 0
    def __init__(self, tipo, valor=None, hijos=None):
        Nodo._c += 1
        self.id     = f"n{Nodo._c}"
        self.tipo   = tipo
        self.valor  = valor
        self.hijos  = hijos or []
    def __repr__(self):
        return f"Nodo({self.tipo},{self.valor})"

# =============================================================================
#  LEXER
# =============================================================================
reserved = {
    'if':'IF','else':'ELSE','while':'WHILE','for':'FOR',
    'def':'DEF','return':'RETURN','print':'PRINT',
    'true':'TRUE','false':'FALSE',
    'and':'AND','or':'OR','not':'NOT',
    'int':'TINT','float':'TFLOAT','string':'TSTRING','bool':'TBOOL',
}

tokens = (
    'NOMBRE','NUMERO','FLOTANTE','CADENA',
    'MASMAS','MENOSMENOS',
    'IGUAL_IGUAL','DIFERENTE','MENOR_IGUAL','MAYOR_IGUAL',
    'FLECHA',
) + tuple(reserved.values())

literals = ['=','+','-','*','/','(',')','<','>','{','}',',',';']

t_MASMAS      = r'\+\+'
t_MENOSMENOS  = r'--'
t_IGUAL_IGUAL = r'=='
t_DIFERENTE   = r'!='
t_MENOR_IGUAL = r'<='
t_MAYOR_IGUAL = r'>='
t_FLECHA      = r'->'
t_ignore      = ' \t'

def t_FLOTANTE(t):
    r'\d+\.\d+'
    t.value = float(t.value)
    return t

def t_NUMERO(t):
    r'\d+'
    t.value = int(t.value)
    return t

def t_CADENA(t):
    r'"[^"]*"'
    t.value = t.value[1:-1]
    return t

def t_NOMBRE(t):
    r'[a-zA-Z_][a-zA-Z0-9_]*'
    t.type = reserved.get(t.value, 'NOMBRE')
    return t

def t_nuevalinea(t):
    r'\n+'
    t.lexer.lineno += t.value.count('\n')

def t_COMENTARIO(t):
    r'\#[^\n]*'
    pass

def t_error(t):
    # Solo reportar si NO es un literal declarado
    if t.value[0] not in '=+-*/<>(){}[],;' and t.value[0] not in literals:
        if hasattr(t.lexer, 'errores_lex'):
            t.lexer.errores_lex.append(
                f"Carácter ilegal '{t.value[0]}' en línea {t.lexer.lineno}")
    t.lexer.skip(1)

_devnull     = open(os.devnull, 'w')
_lexer_base  = lex.lex(errorlog=lex.PlyLogger(_devnull))

# =============================================================================
#  PARSER / GRAMÁTICA
# =============================================================================
tabla_simbolos = {}   # nombre → {tipo, valor, linea}
errores_sem    = []

precedence = (
    ('left',  'OR'),
    ('left',  'AND'),
    ('right', 'NOT'),
    ('left',  'IGUAL_IGUAL', 'DIFERENTE'),
    ('left',  '<', '>', 'MENOR_IGUAL', 'MAYOR_IGUAL'),
    ('left',  '+', '-'),
    ('left',  '*', '/'),
    ('right', 'UMINUS'),
)

# ── Programa ─────────────────────────────────────────────────────────────────
def p_programa(p):
    '''programa : lista_stmt'''
    p[0] = Nodo('PROGRAMA', hijos=p[1] if p[1] else [])

def p_lista_stmt_multi(p):
    '''lista_stmt : lista_stmt stmt'''
    p[0] = (p[1] or []) + ([p[2]] if p[2] else [])

def p_lista_stmt_uno(p):
    '''lista_stmt : stmt'''
    p[0] = [p[1]] if p[1] else []

# ── Sentencias ────────────────────────────────────────────────────────────────
def p_stmt_asignar(p):
    '''stmt : NOMBRE "=" expr'''
    tipo_val = ('float' if isinstance(p[3].valor, float) else
                'int'   if isinstance(p[3].valor, int)   else
                'str'   if isinstance(p[3].valor, str)   else
                'bool'  if isinstance(p[3].valor, bool)  else 'expr')
    tabla_simbolos[p[1]] = {'tipo': tipo_val, 'valor': p[3].valor, 'linea': p.lineno(1)}
    p[0] = Nodo('ASIGNAR', p[1], [p[3]])

def p_stmt_expr(p):
    '''stmt : expr'''
    p[0] = Nodo('EXPR', hijos=[p[1]])

def p_stmt_print(p):
    '''stmt : PRINT "(" expr ")"'''
    p[0] = Nodo('PRINT', hijos=[p[3]])

def p_stmt_return(p):
    '''stmt : RETURN expr'''
    p[0] = Nodo('RETURN', hijos=[p[2]])

def p_stmt_if_simple(p):
    '''stmt : IF "(" expr ")" "{" lista_stmt "}"'''
    p[0] = Nodo('IF', hijos=[p[3]] + (p[6] or []))

def p_stmt_if_else(p):
    '''stmt : IF "(" expr ")" "{" lista_stmt "}" ELSE "{" lista_stmt "}"'''
    p[0] = Nodo('IF_ELSE', hijos=[p[3]] + (p[6] or []) + (p[10] or []))

def p_stmt_while(p):
    '''stmt : WHILE "(" expr ")" "{" lista_stmt "}"'''
    p[0] = Nodo('WHILE', hijos=[p[3]] + (p[6] or []))

# ── Expresiones ───────────────────────────────────────────────────────────────
def p_expr_suma(p):
    '''expr : expr '+' expr'''
    v = (p[1].valor + p[3].valor) if isinstance(p[1].valor,(int,float)) and isinstance(p[3].valor,(int,float)) else None
    p[0] = Nodo('BINOP', '+', [p[1], p[3]]); p[0].valor = v

def p_expr_resta(p):
    '''expr : expr '-' expr'''
    v = (p[1].valor - p[3].valor) if isinstance(p[1].valor,(int,float)) and isinstance(p[3].valor,(int,float)) else None
    p[0] = Nodo('BINOP', '-', [p[1], p[3]]); p[0].valor = v

def p_expr_mult(p):
    '''expr : expr '*' expr'''
    v = (p[1].valor * p[3].valor) if isinstance(p[1].valor,(int,float)) and isinstance(p[3].valor,(int,float)) else None
    p[0] = Nodo('BINOP', '*', [p[1], p[3]]); p[0].valor = v

def p_expr_div(p):
    '''expr : expr '/' expr'''
    v = (p[1].valor / p[3].valor) if isinstance(p[1].valor,(int,float)) and isinstance(p[3].valor,(int,float)) and p[3].valor!=0 else None
    p[0] = Nodo('BINOP', '/', [p[1], p[3]]); p[0].valor = v

def p_expr_lt(p):
    '''expr : expr '<' expr'''
    p[0] = Nodo('BINOP', '<', [p[1], p[3]]); p[0].valor = None

def p_expr_gt(p):
    '''expr : expr '>' expr'''
    p[0] = Nodo('BINOP', '>', [p[1], p[3]]); p[0].valor = None

def p_expr_eq(p):
    '''expr : expr IGUAL_IGUAL expr'''
    p[0] = Nodo('BINOP', '==', [p[1], p[3]]); p[0].valor = None

def p_expr_neq(p):
    '''expr : expr DIFERENTE expr'''
    p[0] = Nodo('BINOP', '!=', [p[1], p[3]]); p[0].valor = None

def p_expr_leq(p):
    '''expr : expr MENOR_IGUAL expr'''
    p[0] = Nodo('BINOP', '<=', [p[1], p[3]]); p[0].valor = None

def p_expr_geq(p):
    '''expr : expr MAYOR_IGUAL expr'''
    p[0] = Nodo('BINOP', '>=', [p[1], p[3]]); p[0].valor = None

def p_expr_and(p):
    '''expr : expr AND expr'''
    p[0] = Nodo('BINOP', 'and', [p[1], p[3]]); p[0].valor = None

def p_expr_or(p):
    '''expr : expr OR expr'''
    p[0] = Nodo('BINOP', 'or', [p[1], p[3]]); p[0].valor = None

def p_expr_not(p):
    '''expr : NOT expr'''
    p[0] = Nodo('NOT', hijos=[p[2]]); p[0].valor = None

def p_expr_uminus(p):
    '''expr : '-' expr %prec UMINUS'''
    v = -p[2].valor if isinstance(p[2].valor,(int,float)) else None
    p[0] = Nodo('NEG', hijos=[p[2]]); p[0].valor = v

def p_expr_grupo(p):
    '''expr : '(' expr ')' '''
    p[0] = p[2]

def p_expr_numero(p):
    '''expr : NUMERO'''
    p[0] = Nodo('NUM', p[1]); p[0].valor = p[1]

def p_expr_flotante(p):
    '''expr : FLOTANTE'''
    p[0] = Nodo('FLOAT', p[1]); p[0].valor = p[1]

def p_expr_cadena(p):
    '''expr : CADENA'''
    p[0] = Nodo('STR', p[1]); p[0].valor = p[1]

def p_expr_true(p):
    '''expr : TRUE'''
    p[0] = Nodo('BOOL', True); p[0].valor = True

def p_expr_false(p):
    '''expr : FALSE'''
    p[0] = Nodo('BOOL', False); p[0].valor = False

def p_expr_nombre(p):
    '''expr : NOMBRE'''
    # Solo reportar error si la variable nunca fue asignada en el código
    val = tabla_simbolos.get(p[1], {}).get('valor')
    if p[1] not in tabla_simbolos:
        errores_sem.append(f"Variable '{p[1]}' usada pero no definida (línea {p.lineno(1)})")
    p[0] = Nodo('VAR', p[1]); p[0].valor = val

def p_expr_llamada(p):
    '''expr : NOMBRE '(' lista_args ')' '''
    p[0] = Nodo('LLAMADA', p[1], p[3]); p[0].valor = None

def p_expr_incr(p):
    '''expr : NOMBRE MASMAS'''
    val = tabla_simbolos.get(p[1], {}).get('valor', 0)
    nueva = val + 1 if isinstance(val,(int,float)) else val
    if p[1] in tabla_simbolos: tabla_simbolos[p[1]]['valor'] = nueva
    p[0] = Nodo('INCR', p[1]); p[0].valor = nueva

def p_expr_decr(p):
    '''expr : NOMBRE MENOSMENOS'''
    val = tabla_simbolos.get(p[1], {}).get('valor', 0)
    nueva = val - 1 if isinstance(val,(int,float)) else val
    if p[1] in tabla_simbolos: tabla_simbolos[p[1]]['valor'] = nueva
    p[0] = Nodo('DECR', p[1]); p[0].valor = nueva

def p_lista_args_multi(p):
    '''lista_args : lista_args ',' expr'''
    p[0] = p[1] + [p[3]]

def p_lista_args_uno(p):
    '''lista_args : expr'''
    p[0] = [p[1]]

def p_lista_args_vacio(p):
    '''lista_args : '''
    p[0] = []

def p_error(p):
    pass

_parser = yacc.yacc(debug=False, errorlog=yacc.PlyLogger(_devnull))

# =============================================================================
#  COLORES POR TIPO DE TOKEN
# =============================================================================
COLORES_TOKEN = {
    'NUMERO':       '#f9e2af',
    'FLOTANTE':     '#fab387',
    'CADENA':       '#a6e3a1',
    'NOMBRE':       '#cdd6f4',
    'IF':           '#cba6f7',
    'ELSE':         '#cba6f7',
    'WHILE':        '#cba6f7',
    'FOR':          '#cba6f7',
    'DEF':          '#cba6f7',
    'RETURN':       '#cba6f7',
    'PRINT':        '#cba6f7',
    'TINT':         '#89dceb',
    'TFLOAT':       '#89dceb',
    'TSTRING':      '#89dceb',
    'TBOOL':        '#89dceb',
    'TRUE':         '#89dceb',
    'FALSE':        '#89dceb',
    'AND':          '#89b4fa',
    'OR':           '#89b4fa',
    'NOT':          '#89b4fa',
    'IGUAL_IGUAL':  '#f38ba8',
    'DIFERENTE':    '#f38ba8',
    'MENOR_IGUAL':  '#f38ba8',
    'MAYOR_IGUAL':  '#f38ba8',
    'MASMAS':       '#94e2d5',
    'MENOSMENOS':   '#94e2d5',
    'FLECHA':       '#94e2d5',
    '__default__':  '#6c7086',
}

CATEGORIAS = {
    'NUMERO':'Numérico','FLOTANTE':'Numérico','CADENA':'Cadena',
    'NOMBRE':'Identificador',
    'IF':'Reservada','ELSE':'Reservada','WHILE':'Reservada','FOR':'Reservada',
    'DEF':'Reservada','RETURN':'Reservada','PRINT':'Reservada',
    'TINT':'Tipo','TFLOAT':'Tipo','TSTRING':'Tipo','TBOOL':'Tipo',
    'TRUE':'Booleano','FALSE':'Booleano',
    'AND':'Lógico','OR':'Lógico','NOT':'Lógico',
    'IGUAL_IGUAL':'Comparación','DIFERENTE':'Comparación',
    'MENOR_IGUAL':'Comparación','MAYOR_IGUAL':'Comparación',
    'MASMAS':'Operador','MENOSMENOS':'Operador','FLECHA':'Operador',
}

NCOLORES = {
    'PROGRAMA':  ('#89b4fa','#042c53'),
    'ASIGNAR':   ('#a6e3a1','#173404'),
    'BINOP':     ('#fab387','#412402'),
    'IF':        ('#cba6f7','#26215c'),
    'IF_ELSE':   ('#cba6f7','#26215c'),
    'WHILE':     ('#f38ba8','#501313'),
    'FOR':       ('#f38ba8','#501313'),
    'RETURN':    ('#94e2d5','#04342c'),
    'PRINT':     ('#f9e2af','#412402'),
    'LLAMADA':   ('#f9e2af','#412402'),
    'NUM':       ('#45475a','#cdd6f4'),
    'FLOAT':     ('#45475a','#cdd6f4'),
    'STR':       ('#a6e3a1','#173404'),
    'BOOL':      ('#89dceb','#04342c'),
    'VAR':       ('#313244','#cdd6f4'),
    'EXPR':      ('#313244','#6c7086'),
    'NEG':       ('#fab387','#412402'),
    'NOT':       ('#89b4fa','#042c53'),
    'INCR':      ('#94e2d5','#04342c'),
    'DECR':      ('#94e2d5','#04342c'),
    'ERROR':     ('#f38ba8','#501313'),
}

# =============================================================================
#  INTERFAZ
# =============================================================================
class InterfazCompilador:
    BG     = "#1e1e2e"
    PANEL  = "#181825"
    BORDE  = "#313244"
    TEXTO  = "#cdd6f4"
    SEC    = "#6c7086"
    ACENTO = "#89b4fa"
    EXITO  = "#a6e3a1"
    ERROR  = "#f38ba8"
    WARN   = "#fab387"
    NLINEA = "#2a2a3e"
    BTN_BG = "#89b4fa"
    BTN_FG = "#1e1e2e"
    RESALT = "#45475a"

    def __init__(self, raiz):
        self.raiz             = raiz
        self.raiz.title("Compilador PLY — Léxico & Semántico")
        self.raiz.geometry("1400x820")
        self.raiz.configure(bg=self.BG)
        self.raiz.minsize(1000, 640)
        self._buffer_entrada  = []
        self._ultimo_texto    = ""
        self._timer_live      = None
        self._arbol_resultado = None
        self._build_ui()
        self._insertar_ejemplo()

    # =========================================================================
    #  UI
    # =========================================================================
    def _build_ui(self):
        self._barra_superior()
        self._panel_principal()
        self._barra_estado()

    def _barra_superior(self):
        b = tk.Frame(self.raiz, bg=self.PANEL, pady=6)
        b.pack(side=tk.TOP, fill=tk.X)
        tk.Label(b, text="⚙  PLY Compiler",
                 bg=self.PANEL, fg=self.ACENTO,
                 font=("Consolas",13,"bold")).pack(side=tk.LEFT, padx=16)
        tk.Frame(b, bg=self.BORDE, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)
        for txt, cmd, bg, fg in [
            ("▶  Compilar",  self.compilar,       self.BTN_BG, self.BTN_FG),
            ("🌳  Árbol",    self.mostrar_arbol,   self.RESALT, self.TEXTO),
            ("⟳  Limpiar",  self.limpiar_todo,    self.RESALT, self.TEXTO),
            ("📂  Abrir",    self.abrir_archivo,   self.RESALT, self.TEXTO),
            ("💾  Guardar",  self.guardar_archivo, self.RESALT, self.TEXTO),
        ]:
            tk.Button(b, text=txt, command=cmd, bg=bg, fg=fg,
                      activebackground=self.ACENTO, activeforeground=self.BTN_FG,
                      font=("Consolas",10,"bold"), relief=tk.FLAT,
                      padx=12, pady=3, cursor="hand2", bd=0
                      ).pack(side=tk.LEFT, padx=3)
        self._var_live = tk.BooleanVar(value=True)
        tk.Checkbutton(b, text="🔴 En vivo", variable=self._var_live,
                       bg=self.PANEL, fg=self.WARN, selectcolor=self.PANEL,
                       activebackground=self.PANEL, font=("Consolas",9),
                       cursor="hand2").pack(side=tk.LEFT, padx=8)
        tk.Label(b, text="MODO: Léxico + Semántico",
                 bg=self.PANEL, fg=self.SEC,
                 font=("Consolas",9)).pack(side=tk.RIGHT, padx=16)

    def _panel_principal(self):
        cont = tk.Frame(self.raiz, bg=self.BG)
        cont.pack(fill=tk.BOTH, expand=True, padx=6, pady=(3,0))
        pw = tk.PanedWindow(cont, orient=tk.HORIZONTAL,
                            bg=self.BORDE, sashwidth=4, sashrelief=tk.FLAT)
        pw.pack(fill=tk.BOTH, expand=True)
        fe = tk.Frame(pw, bg=self.BG)
        pw.add(fe, minsize=360, stretch="always")
        self._panel_editor(fe)
        fd = tk.Frame(pw, bg=self.BG)
        pw.add(fd, minsize=420, stretch="always")
        self._panel_derecho(fd)

    def _panel_editor(self, padre):
        tk.Label(padre, text="  📝 Código fuente",
                 bg=self.PANEL, fg=self.ACENTO,
                 font=("Consolas",10,"bold"), anchor="w").pack(fill=tk.X)
        marco = tk.Frame(padre, bg=self.PANEL,
                         highlightbackground=self.BORDE, highlightthickness=1)
        marco.pack(fill=tk.BOTH, expand=True, pady=(2,4))
        self.numeros = tk.Text(marco, width=4, padx=4, state=tk.DISABLED,
                               bg=self.NLINEA, fg=self.SEC,
                               font=("Consolas",12), relief=tk.FLAT, bd=0,
                               cursor="arrow", selectbackground=self.NLINEA)
        self.numeros.pack(side=tk.LEFT, fill=tk.Y)
        self.editor = tk.Text(marco, wrap=tk.NONE,
                              bg=self.PANEL, fg=self.TEXTO,
                              insertbackground=self.ACENTO,
                              selectbackground=self.ACENTO,
                              selectforeground=self.BTN_FG,
                              font=("Consolas",12), relief=tk.FLAT, bd=0,
                              undo=True, padx=8, pady=4)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sv = tk.Scrollbar(marco, orient=tk.VERTICAL, command=self._scroll_editor)
        sv.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.configure(yscrollcommand=sv.set)
        sh = tk.Scrollbar(padre, orient=tk.HORIZONTAL, command=self.editor.xview)
        sh.pack(side=tk.BOTTOM, fill=tk.X)
        self.editor.configure(xscrollcommand=sh.set)
        for tipo, color in COLORES_TOKEN.items():
            self.editor.tag_config(f"tok_{tipo}", foreground=color)
        self.editor.tag_config("tok_comentario", foreground="#585b70")
        self.editor.bind('<KeyRelease>',    self._on_key)
        self.editor.bind('<MouseWheel>',    self._sync_numeros)
        self.editor.bind('<Control-Return>',lambda e: self.compilar())
        self.editor.bind('<ButtonRelease>', self._actualizar_estado)

    def _panel_derecho(self, padre):
        st = ttk.Style()
        st.theme_use('clam')
        st.configure("C.TNotebook", background=self.BG, borderwidth=0)
        st.configure("C.TNotebook.Tab", background=self.RESALT, foreground=self.SEC,
                     padding=[10,4], font=("Consolas",9,"bold"))
        st.map("C.TNotebook.Tab",
               background=[("selected",self.PANEL)],
               foreground=[("selected",self.ACENTO)])
        self.nb = ttk.Notebook(padre, style="C.TNotebook")
        self.nb.pack(fill=tk.BOTH, expand=True)
        for titulo, fn in [
            ("🔍 Tokens",   self._tab_tokens),
            ("🧠 Semántico",self._tab_semantico),
            ("📦 Buffer",   self._tab_buffer),
            ("💬 Consola",  self._tab_consola),
        ]:
            f = tk.Frame(self.nb, bg=self.BG)
            self.nb.add(f, text=titulo)
            fn(f)

    def _make_tree(self, padre):
        st = ttk.Style()
        st.configure("CT.Treeview",
                     background=self.PANEL, foreground=self.TEXTO,
                     fieldbackground=self.PANEL, font=("Consolas",10), rowheight=22)
        st.configure("CT.Treeview.Heading",
                     background=self.RESALT, foreground=self.ACENTO,
                     font=("Consolas",10,"bold"), relief=tk.FLAT)
        st.map("CT.Treeview",
               background=[('selected',self.ACENTO)],
               foreground=[('selected',self.BTN_FG)])
        return ttk.Treeview(padre, style="CT.Treeview")

    def _tab_tokens(self, padre):
        tk.Label(padre, text="  Tokens reconocidos",
                 bg=self.PANEL, fg=self.ACENTO,
                 font=("Consolas",10,"bold"), anchor="w").pack(fill=tk.X)
        marco = tk.Frame(padre, bg=self.PANEL,
                         highlightbackground=self.BORDE, highlightthickness=1)
        marco.pack(fill=tk.BOTH, expand=True, pady=2)
        cols = ('tipo','valor','linea','pos','categoria')
        self.tbl_tokens = ttk.Treeview(marco, columns=cols,
                                       show='headings', style="CT.Treeview")
        for c,h,w in [('tipo','Tipo',100),('valor','Valor',130),
                      ('linea','Línea',55),('pos','Pos',55),
                      ('categoria','Categoría',100)]:
            self.tbl_tokens.heading(c, text=h)
            self.tbl_tokens.column(c, width=w, anchor='center')
        sv = ttk.Scrollbar(marco, orient=tk.VERTICAL, command=self.tbl_tokens.yview)
        self.tbl_tokens.configure(yscrollcommand=sv.set)
        self.tbl_tokens.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sv.pack(side=tk.RIGHT, fill=tk.Y)
        for tipo, color in COLORES_TOKEN.items():
            self.tbl_tokens.tag_configure(tipo, foreground=color)
        self._lbl_ntokens = tk.Label(padre, text="0 tokens",
                                     bg=self.BG, fg=self.SEC,
                                     font=("Consolas",9), anchor="e")
        self._lbl_ntokens.pack(fill=tk.X, padx=4)

    def _tab_semantico(self, padre):
        tk.Label(padre, text="  Tabla de símbolos",
                 bg=self.PANEL, fg=self.ACENTO,
                 font=("Consolas",10,"bold"), anchor="w").pack(fill=tk.X)
        marco = tk.Frame(padre, bg=self.PANEL,
                         highlightbackground=self.BORDE, highlightthickness=1)
        marco.pack(fill=tk.BOTH, expand=True, pady=(2,2))
        cols2 = ('nombre','tipo','valor','linea')
        self.tbl_sim = ttk.Treeview(marco, columns=cols2,
                                    show='headings', style="CT.Treeview")
        for c,h,w in [('nombre','Nombre',110),('tipo','Tipo',80),
                      ('valor','Valor',120),('linea','Línea',60)]:
            self.tbl_sim.heading(c, text=h)
            self.tbl_sim.column(c, width=w, anchor='center')
        sv2 = ttk.Scrollbar(marco, orient=tk.VERTICAL, command=self.tbl_sim.yview)
        self.tbl_sim.configure(yscrollcommand=sv2.set)
        self.tbl_sim.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sv2.pack(side=tk.RIGHT, fill=tk.Y)
        tk.Label(padre, text="  Errores semánticos",
                 bg=self.PANEL, fg=self.ERROR,
                 font=("Consolas",10,"bold"), anchor="w").pack(fill=tk.X, pady=(4,0))
        self.txt_err_sem = scrolledtext.ScrolledText(
            padre, height=6, bg=self.PANEL, fg=self.ERROR,
            font=("Consolas",10), relief=tk.FLAT, bd=0,
            state=tk.DISABLED, padx=6, pady=4)
        self.txt_err_sem.pack(fill=tk.X)

    def _tab_buffer(self, padre):
        tk.Label(padre, text="  Buffer de entrada — historial de edición",
                 bg=self.PANEL, fg=self.ACENTO,
                 font=("Consolas",10,"bold"), anchor="w").pack(fill=tk.X)
        self.txt_buffer = scrolledtext.ScrolledText(
            padre, bg=self.PANEL, fg=self.WARN,
            font=("Consolas",10), relief=tk.FLAT, bd=0,
            state=tk.DISABLED, padx=8, pady=4)
        self.txt_buffer.pack(fill=tk.BOTH, expand=True)
        self.txt_buffer.tag_config('ts',    foreground=self.SEC)
        self.txt_buffer.tag_config('nueva', foreground=self.EXITO)

    def _tab_consola(self, padre):
        tk.Label(padre, text="  Salida del compilador",
                 bg=self.PANEL, fg=self.ACENTO,
                 font=("Consolas",10,"bold"), anchor="w").pack(fill=tk.X)
        self.consola = scrolledtext.ScrolledText(
            padre, bg=self.PANEL, fg=self.TEXTO,
            font=("Consolas",11), relief=tk.FLAT, bd=0,
            state=tk.DISABLED, padx=8, pady=4)
        self.consola.pack(fill=tk.BOTH, expand=True)
        for t,c in [('res',self.EXITO),('err',self.ERROR),('warn',self.WARN),
                    ('info',self.ACENTO),('sec',self.SEC)]:
            self.consola.tag_config(t, foreground=c)

    def _barra_estado(self):
        b = tk.Frame(self.raiz, bg=self.PANEL, pady=3)
        b.pack(side=tk.BOTTOM, fill=tk.X)
        self._lbl_estado = tk.Label(
            b, text="Listo — Ctrl+Enter para compilar | 🔴 En vivo activado",
            bg=self.PANEL, fg=self.SEC, font=("Consolas",9), anchor="w")
        self._lbl_estado.pack(side=tk.LEFT, padx=12)
        self._lbl_cursor = tk.Label(b, text="L1 C1",
                                    bg=self.PANEL, fg=self.SEC,
                                    font=("Consolas",9))
        self._lbl_cursor.pack(side=tk.RIGHT, padx=12)

    # =========================================================================
    #  EVENTOS
    # =========================================================================
    def _on_key(self, _=None):
        self._sync_numeros()
        self._actualizar_estado()
        self._registrar_buffer()
        if self._var_live.get():
            if self._timer_live:
                self.raiz.after_cancel(self._timer_live)
            self._timer_live = self.raiz.after(350, self._analisis_vivo)

    def _analisis_vivo(self):
        codigo = self.editor.get("1.0", tk.END)
        if codigo == self._ultimo_texto:
            return
        self._ultimo_texto = codigo
        self._resaltar_sintaxis(codigo)
        self._llenar_tokens(codigo)

    def _registrar_buffer(self):
        nuevo = self.editor.get("1.0", tk.END)
        if nuevo == self._ultimo_texto:
            return
        ts = time.strftime('%H:%M:%S')
        self._buffer_entrada.append({'ts': ts, 'texto': nuevo})
        if len(self._buffer_entrada) > 200:
            self._buffer_entrada.pop(0)
        self.txt_buffer.configure(state=tk.NORMAL)
        self.txt_buffer.delete("1.0", tk.END)
        for e in self._buffer_entrada[-30:]:
            self.txt_buffer.insert(tk.END, f"[{e['ts']}]  ", 'ts')
            self.txt_buffer.insert(tk.END,
                e['texto'].replace('\n','↵ ')[:80] + "\n", 'nueva')
        self.txt_buffer.see(tk.END)
        self.txt_buffer.configure(state=tk.DISABLED)

    # =========================================================================
    #  RESALTADO DE SINTAXIS
    # =========================================================================
    def _offset_a_pos(self, texto, offset):
        antes = texto[:offset]
        linea = antes.count('\n') + 1
        col   = offset - antes.rfind('\n') - 1
        return linea, col

    def _resaltar_sintaxis(self, codigo):
        for tipo in COLORES_TOKEN:
            self.editor.tag_remove(f"tok_{tipo}", "1.0", tk.END)
        self.editor.tag_remove("tok_comentario", "1.0", tk.END)
        # Comentarios
        for m in re.finditer(r'#[^\n]*', codigo):
            li, ci = self._offset_a_pos(codigo, m.start())
            lf, cf = self._offset_a_pos(codigo, m.end())
            try:
                self.editor.tag_add("tok_comentario", f"{li}.{ci}", f"{lf}.{cf}")
            except:
                pass
        # Tokens
        lx = _lexer_base.clone()
        lx.errores_lex = []
        lx.lineno = 1
        lx.input(codigo)
        for tok in lx:
            if tok.type == 'CADENA':
                raw_len = len(tok.value) + 2
            else:
                raw_len = len(str(tok.value))
            li, ci = self._offset_a_pos(codigo, tok.lexpos)
            lf, cf = self._offset_a_pos(codigo, tok.lexpos + raw_len)
            tag = f"tok_{tok.type}" if tok.type in COLORES_TOKEN else "tok___default__"
            try:
                self.editor.tag_add(tag, f"{li}.{ci}", f"{lf}.{cf}")
            except:
                pass

    # =========================================================================
    #  TABLA DE TOKENS
    # =========================================================================
    def _llenar_tokens(self, codigo):
        for i in self.tbl_tokens.get_children():
            self.tbl_tokens.delete(i)
        lx = _lexer_base.clone()
        lx.errores_lex = []
        lx.lineno = 1
        lx.input(codigo)
        total = 0
        for tok in lx:
            cat = CATEGORIAS.get(tok.type, 'Operador/Símbolo')
            tag = tok.type if tok.type in COLORES_TOKEN else '__default__'
            val = f'"{tok.value}"' if tok.type == 'CADENA' else str(tok.value)
            self.tbl_tokens.insert('', tk.END,
                values=(tok.type, val, tok.lineno, tok.lexpos, cat),
                tags=(tag,))
            total += 1
        self._lbl_ntokens.config(text=f"{total} token{'s' if total!=1 else ''}")
        return total

    # =========================================================================
    #  COMPILACIÓN
    # =========================================================================
    def compilar(self, _=None):
        codigo = self.editor.get("1.0", tk.END).strip()
        if not codigo:
            self._log("⚠  Sin código para compilar.\n", 'warn')
            return
        self._limpiar_analisis()
        global tabla_simbolos, errores_sem
        tabla_simbolos = {}
        errores_sem    = []
        Nodo._c        = 0
        self.nb.select(3)  # consola

        # FASE 1: LÉXICO
        self._log("━"*46+"\n",'sec')
        self._log("  📖 FASE 1 — ANÁLISIS LÉXICO\n",'info')
        self._log("━"*46+"\n",'sec')
        total = self._llenar_tokens(codigo)
        self._resaltar_sintaxis(codigo)
        lx2 = _lexer_base.clone(); lx2.errores_lex=[]; lx2.lineno=1
        lx2.input(codigo); list(lx2)
        errs_lex = lx2.errores_lex
        if errs_lex:
            for e in errs_lex: self._log(f"  ✗ {e}\n",'err')
        else:
            self._log(f"  ✓ {total} token(s) sin errores léxicos\n",'res')

        # FASE 2: SEMÁNTICO
        self._log("\n"+"━"*46+"\n",'sec')
        self._log("  🧠 FASE 2 — ANÁLISIS SEMÁNTICO\n",'info')
        self._log("━"*46+"\n",'sec')
        old_err = sys.stderr; sys.stderr = io.StringIO()
        try:
            resultado = _parser.parse(codigo, lexer=_lexer_base.clone())
            self._arbol_resultado = resultado
        except Exception as ex:
            self._arbol_resultado = None
            self._log(f"  ✗ Error: {ex}\n",'err')
        sys.stderr = old_err

        # Si el parser devolvió None pero hay símbolos, construir árbol básico
        if self._arbol_resultado is None and tabla_simbolos:
            hijos = []
            for nombre, info in tabla_simbolos.items():
                n = Nodo('ASIGNAR', nombre)
                n.valor = info['valor']
                hijos.append(n)
            self._arbol_resultado = Nodo('PROGRAMA', hijos=hijos)

        # Llenar tabla símbolos
        for nombre, info in tabla_simbolos.items():
            self.tbl_sim.insert('', tk.END,
                values=(nombre, info['tipo'], str(info['valor']), info['linea']))

        # Errores semánticos
        self.txt_err_sem.configure(state=tk.NORMAL)
        self.txt_err_sem.delete("1.0", tk.END)
        if errores_sem:
            for e in errores_sem:
                self.txt_err_sem.insert(tk.END, f"✗ {e}\n")
                self._log(f"  ✗ {e}\n",'err')
        else:
            self.txt_err_sem.insert(tk.END, "✓ Sin errores semánticos")
            if tabla_simbolos:
                self._log(f"  ✓ {len(tabla_simbolos)} símbolo(s) definido(s)\n",'res')
        self.txt_err_sem.configure(state=tk.DISABLED)

        # Resumen
        hay_err = bool(errs_lex or errores_sem)
        self._log("\n"+"━"*46+"\n",'sec')
        if not hay_err:
            self._log("  ✅ Compilación exitosa\n",'res')
            self._lbl_estado.config(
                text=f"✓ {total} tokens | {len(tabla_simbolos)} símbolos | Sin errores",
                fg=self.EXITO)
        else:
            n = len(errs_lex)+len(errores_sem)
            self._log(f"  ❌ {n} error(es)\n",'err')
            self._lbl_estado.config(text=f"✗ {n} error(es)", fg=self.ERROR)

        if tabla_simbolos:
            self.nb.select(1)

    # =========================================================================
    #  ÁRBOL — ventana con canvas tkinter
    # =========================================================================
    def mostrar_arbol(self):
        codigo = self.editor.get("1.0", tk.END).strip()
        if not codigo:
            messagebox.showwarning("Sin código", "Escribe código primero.")
            return
        # Compilar si aún no hay árbol
        if self._arbol_resultado is None:
            self.compilar()
        arbol = self._arbol_resultado
        if arbol is None:
            messagebox.showwarning("Sin árbol",
                "No se pudo generar el árbol.\nRevisa que el código sea válido.")
            return

        # Intentar exportar con graphviz si está disponible
        if GRAPHVIZ_OK:
            try:
                self._exportar_graphviz(arbol)
                return
            except Exception:
                pass  # fallback a canvas

        # Mostrar árbol en ventana tkinter (siempre funciona)
        self._abrir_ventana_arbol(arbol)

    def _exportar_graphviz(self, arbol):
        dot = graphviz.Digraph(
            comment='Árbol Semántico',
            graph_attr={'bgcolor':'#1e1e2e','rankdir':'TB','splines':'curved'},
            node_attr={'style':'filled','fontname':'Consolas','fontsize':'11',
                       'fontcolor':'#1e1e2e','shape':'box'},
            edge_attr={'color':'#6c7086','arrowsize':'0.7'})

        def ag(nodo):
            if not nodo: return
            bg, fg = NCOLORES.get(nodo.tipo, ('#45475a','#cdd6f4'))
            label = nodo.tipo
            if nodo.valor is not None:
                v = str(nodo.valor)
                if len(v)>15: v=v[:12]+"..."
                label += f"\n{v}"
            dot.node(nodo.id, label=label, fillcolor=bg, fontcolor=fg)
            for h in nodo.hijos:
                if h: ag(h); dot.edge(nodo.id, h.id)

        ag(arbol)
        ruta = os.path.join(os.path.expanduser("~"), "arbol_semantico")
        dot.render(ruta, format='pdf', cleanup=True, view=True)
        self._log(f"\n  🌳 Árbol PDF: {ruta}.pdf\n", 'info')

    def _abrir_ventana_arbol(self, raiz_nodo):
        win = tk.Toplevel(self.raiz)
        win.title("Árbol Semántico — PLY Compiler")
        win.geometry("1000x660")
        win.configure(bg=self.BG)

        # Barra
        bar = tk.Frame(win, bg=self.PANEL, pady=6)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="🌳  Árbol Semántico",
                 bg=self.PANEL, fg=self.ACENTO,
                 font=("Consolas",12,"bold")).pack(side=tk.LEFT, padx=12)
        tk.Label(bar, text="Usa la rueda del mouse para hacer scroll",
                 bg=self.PANEL, fg=self.SEC,
                 font=("Consolas",9)).pack(side=tk.LEFT, padx=12)

        # Canvas con scroll
        fc = tk.Frame(win, bg=self.BG)
        fc.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(fc, bg="#11111b", highlightthickness=0)
        sv = tk.Scrollbar(fc,  orient=tk.VERTICAL,   command=canvas.yview)
        sh = tk.Scrollbar(win, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=sv.set, xscrollcommand=sh.set)
        sh.pack(side=tk.BOTTOM, fill=tk.X)
        sv.pack(side=tk.RIGHT,  fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── Layout BFS ────────────────────────────────────────────────────────
        NW, NH, PX, PY = 130, 48, 18, 70

        def calcular_posiciones(raiz):
            # 1. BFS para asignar nivel y orden
            cola = deque([(raiz, 0)])
            niveles = {}
            visitados = set()
            orden = []
            while cola:
                nodo, nivel = cola.popleft()
                if nodo is None or nodo.id in visitados:
                    continue
                visitados.add(nodo.id)
                niveles.setdefault(nivel, []).append(nodo)
                orden.append((nodo, nivel))
                for hijo in nodo.hijos:
                    if hijo and hijo.id not in visitados:
                        cola.append((hijo, nivel+1))

            # 2. Asignar x,y iniciales
            pos = {}
            for nivel, nodos in niveles.items():
                y = 40 + nivel * (NH + PY)
                for i, n in enumerate(nodos):
                    x = 40 + i * (NW + PX)
                    pos[n.id] = [x, y]

            # 3. Centrar padres sobre sus hijos (3 pasadas)
            for _ in range(4):
                for nodo, nivel in reversed(orden):
                    hijos_v = [h for h in nodo.hijos if h and h.id in pos]
                    if hijos_v:
                        cx = sum(pos[h.id][0] for h in hijos_v) / len(hijos_v)
                        pos[nodo.id][0] = cx

            # 4. Resolver solapamientos en cada nivel
            for nivel, nodos in niveles.items():
                nodos_s = sorted(nodos, key=lambda n: pos[n.id][0])
                for i in range(1, len(nodos_s)):
                    prev_x = pos[nodos_s[i-1].id][0]
                    curr_x = pos[nodos_s[i].id][0]
                    if curr_x < prev_x + NW + PX:
                        pos[nodos_s[i].id][0] = prev_x + NW + PX

            return pos

        pos = calcular_posiciones(raiz_nodo)

        # Tamaño canvas
        max_x = max(p[0] for p in pos.values()) + NW + 60
        max_y = max(p[1] for p in pos.values()) + NH + 60
        canvas.configure(scrollregion=(0, 0, max(max_x,1000), max(max_y,600)))

        # ── Dibujar aristas ───────────────────────────────────────────────────
        def dibujar_aristas(nodo):
            if nodo is None or nodo.id not in pos:
                return
            px, py = pos[nodo.id]
            for hijo in nodo.hijos:
                if hijo and hijo.id in pos:
                    hx, hy = pos[hijo.id]
                    # Línea curva bezier
                    x1 = px + NW//2; y1 = py + NH
                    x2 = hx + NW//2; y2 = hy
                    cx = (x1+x2)/2;  cy = (y1+y2)/2
                    canvas.create_line(
                        x1, y1, cx, y1, x2, y2,
                        smooth=True, fill="#45475a",
                        width=1.5, arrow=tk.LAST,
                        arrowshape=(8,10,4))
                    dibujar_aristas(hijo)

        # ── Dibujar nodos ─────────────────────────────────────────────────────
        def rect_redondeado(c, x, y, w, h, r, fill, outline=""):
            c.create_arc(x,   y,   x+2*r, y+2*r, start=90,  extent=90,  fill=fill, outline=fill)
            c.create_arc(x+w-2*r, y,   x+w, y+2*r, start=0,   extent=90,  fill=fill, outline=fill)
            c.create_arc(x,   y+h-2*r, x+2*r, y+h, start=180, extent=90,  fill=fill, outline=fill)
            c.create_arc(x+w-2*r, y+h-2*r, x+w, y+h, start=270, extent=90,  fill=fill, outline=fill)
            c.create_rectangle(x+r, y,   x+w-r, y+h,   fill=fill, outline="")
            c.create_rectangle(x,   y+r, x+w,   y+h-r, fill=fill, outline="")

        def dibujar_nodos(nodo):
            if nodo is None or nodo.id not in pos:
                return
            x, y = pos[nodo.id]
            bg, fg = NCOLORES.get(nodo.tipo, ('#45475a','#cdd6f4'))
            rect_redondeado(canvas, x, y, NW, NH, 8, bg)

            label = nodo.tipo
            if nodo.valor is not None:
                v = str(nodo.valor)
                if len(v) > 13: v = v[:10]+"..."
                # Tipo arriba, valor abajo
                canvas.create_text(x+NW//2, y+14, text=label,
                                   fill=fg, font=("Consolas",9,"bold"), anchor="center")
                canvas.create_text(x+NW//2, y+32, text=v,
                                   fill=fg, font=("Consolas",8), anchor="center")
            else:
                canvas.create_text(x+NW//2, y+NH//2, text=label,
                                   fill=fg, font=("Consolas",9,"bold"), anchor="center")
            for hijo in nodo.hijos:
                dibujar_nodos(hijo)

        dibujar_aristas(raiz_nodo)
        dibujar_nodos(raiz_nodo)

        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        canvas.bind("<Shift-MouseWheel>",
                    lambda e: canvas.xview_scroll(int(-1*(e.delta/120)), "units"))

    # =========================================================================
    #  UTILIDADES
    # =========================================================================
    def _log(self, texto, tag=''):
        self.consola.configure(state=tk.NORMAL)
        self.consola.insert(tk.END, texto, tag)
        self.consola.see(tk.END)
        self.consola.configure(state=tk.DISABLED)

    def _limpiar_analisis(self):
        for i in self.tbl_tokens.get_children(): self.tbl_tokens.delete(i)
        self._lbl_ntokens.config(text="0 tokens")
        for i in self.tbl_sim.get_children(): self.tbl_sim.delete(i)
        self.consola.configure(state=tk.NORMAL)
        self.consola.delete("1.0", tk.END)
        self.consola.configure(state=tk.DISABLED)

    def limpiar_todo(self):
        self.editor.delete("1.0", tk.END)
        self._limpiar_analisis()
        self._buffer_entrada.clear()
        self.txt_buffer.configure(state=tk.NORMAL)
        self.txt_buffer.delete("1.0", tk.END)
        self.txt_buffer.configure(state=tk.DISABLED)
        self.txt_err_sem.configure(state=tk.NORMAL)
        self.txt_err_sem.delete("1.0", tk.END)
        self.txt_err_sem.configure(state=tk.DISABLED)
        self._sync_numeros()
        self._arbol_resultado = None
        self._lbl_estado.config(text="Listo — Ctrl+Enter para compilar", fg=self.SEC)

    def _scroll_editor(self, *args):
        self.editor.yview(*args)
        self.numeros.yview(*args)

    def _sync_numeros(self, _=None):
        self.numeros.configure(state=tk.NORMAL)
        self.numeros.delete("1.0", tk.END)
        n = int(self.editor.index('end-1c').split('.')[0])
        self.numeros.insert("1.0", "\n".join(str(i) for i in range(1, n+1)))
        self.numeros.configure(state=tk.DISABLED)
        self.numeros.yview_moveto(self.editor.yview()[0])

    def _actualizar_estado(self, _=None):
        pos = self.editor.index(tk.INSERT)
        l, c = pos.split('.')
        self._lbl_cursor.config(text=f"L{l} C{int(c)+1}")
        self._sync_numeros()

    def abrir_archivo(self):
        r = filedialog.askopenfilename(
            filetypes=[("Todos","*.*"),("Texto","*.txt"),("Python","*.py")])
        if r:
            try:
                with open(r, encoding='utf-8') as f:
                    self.editor.delete("1.0", tk.END)
                    self.editor.insert("1.0", f.read())
                self._sync_numeros()
                self.raiz.title(f"PLY Compiler — {os.path.basename(r)}")
            except Exception as ex:
                messagebox.showerror("Error", str(ex))

    def guardar_archivo(self):
        r = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Texto","*.txt"),("Python","*.py"),("Todos","*.*")])
        if r:
            try:
                with open(r, 'w', encoding='utf-8') as f:
                    f.write(self.editor.get("1.0", tk.END))
                self.raiz.title(f"PLY Compiler — {os.path.basename(r)}")
            except Exception as ex:
                messagebox.showerror("Error", str(ex))

    def _insertar_ejemplo(self):
        self.editor.insert("1.0", """\
# Compilador PLY — Análisis Léxico y Semántico
# Ctrl+Enter para compilar | Botón 🌳 para ver el árbol

x = 10
y = 3.14
nombre = "hola mundo"
z = x + y * 2

if (z > 20) {
    resultado = z - x
}

while (x > 0) {
    x = x - 1
}

suma = x + y + z
print(suma)
""")
        self._sync_numeros()

# =============================================================================
#  PUNTO DE ENTRADA
# =============================================================================
if __name__ == '__main__':
    raiz = tk.Tk()
    app  = InterfazCompilador(raiz)
    raiz.mainloop()
