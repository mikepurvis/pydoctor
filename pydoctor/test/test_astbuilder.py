from __future__ import print_function

import textwrap

import astor

from pydoctor import astbuilder, model
from pydoctor.epydoc2stan import get_parsed_type



from . import py2only, py3only

def fromText(text, modname='<test>', system=None,
             buildercls=None,
             systemcls=model.System):
    if system is None:
        _system = systemcls()
    else:
        _system = system
    if buildercls is None:
        buildercls = _system.defaultBuilder
    builder = buildercls(_system)
    mod = builder.pushModule(modname, None)
    builder.popModule()
    ast = astbuilder.parse(textwrap.dedent(text))
    builder.processModuleAST(ast, mod)
    mod = _system.allobjects[modname]
    mod.ast = ast
    mod.state = model.ProcessingState.PROCESSED
    return mod

def unwrap(parsed_docstring):
    epytext = parsed_docstring._tree
    assert epytext.tag == 'epytext'
    assert len(epytext.children) == 1
    para = epytext.children[0]
    assert para.tag == 'para'
    assert len(para.children) == 1
    return para.children[0]

def type2str(type_expr):
    if type_expr is None:
        return None
    else:
        return astor.to_source(type_expr).strip()

def test_no_docstring():
    # Inheritance of the docstring of an overridden method depends on
    # methods with no docstring having None in their 'docstring' field.
    mod = fromText('''
    def f():
        pass
    class C:
        def m(self):
            pass
    ''', modname='test')
    f = mod.contents['f']
    assert f.docstring is None
    m = mod.contents['C'].contents['m']
    assert m.docstring is None

def test_simple():
    src = '''
    """ MOD DOC """
    def f():
        """This is a docstring."""
    '''
    mod = fromText(src)
    assert len(mod.contents) == 1
    func, = mod.contents.values()
    assert func.fullName() == '<test>.f'
    assert func.docstring == """This is a docstring."""


def test_function_argspec():
    src = textwrap.dedent('''
    def f(a, b=3, *c, **kw):
        pass
    ''')
    mod = fromText(src)
    docfunc, = mod.contents.values()
    assert docfunc.argspec == (['a', 'b'], 'c', 'kw', ('3',))


@py2only
def test_function_argspec_with_tuple():
    src = textwrap.dedent('''
    def f((a,z), b=3, *c, **kw):
        pass
    ''')
    mod = fromText(src)
    docfunc, = mod.contents.values()
    assert docfunc.argspec ==  ([['a', 'z'], 'b'], 'c', 'kw', ('3',))

def test_class():
    src = '''
    class C:
        def f():
            """This is a docstring."""
    '''
    mod = fromText(src)
    assert len(mod.contents) == 1
    cls, = mod.contents.values()
    assert cls.fullName() == '<test>.C'
    assert cls.docstring == None
    assert len(cls.contents) == 1
    func, = cls.contents.values()
    assert func.fullName() == '<test>.C.f'
    assert func.docstring == """This is a docstring."""


def test_class_with_base():
    src = '''
    class C:
        def f():
            """This is a docstring."""
    class D(C):
        def f():
            """This is a docstring."""
    '''
    mod = fromText(src)
    assert len(mod.contents) == 2
    clsC, clsD = mod.orderedcontents
    assert clsC.fullName() == '<test>.C'
    assert clsC.docstring == None
    assert len(clsC.contents) == 1

    assert clsD.fullName() == '<test>.D'
    assert clsD.docstring == None
    assert len(clsD.contents) == 1

    assert len(clsD.bases) == 1
    base, = clsD.bases
    assert base == '<test>.C'

def test_follow_renaming():
    src = '''
    class C: pass
    D = C
    class E(D): pass
    '''
    mod = fromText(src)
    C = mod.contents['C']
    E = mod.contents['E']
    assert E.baseobjects == [C], E.baseobjects

def test_class_with_base_from_module():
    src = '''
    from X.Y import A
    from Z import B as C
    class D(A, C):
        def f():
            """This is a docstring."""
    '''
    mod = fromText(src)
    assert len(mod.contents) == 1
    clsD, = mod.contents.values()

    assert clsD.fullName() == '<test>.D'
    assert clsD.docstring == None
    assert len(clsD.contents) == 1

    assert len(clsD.bases) == 2
    base1, base2 = clsD.bases
    assert base1 == 'X.Y.A'
    assert base2 == 'Z.B'

    src = '''
    import X
    import Y.Z as M
    class D(X.A, X.B.C, M.C):
        def f():
            """This is a docstring."""
    '''
    mod = fromText(src)
    assert len(mod.contents) == 1
    clsD, = mod.contents.values()

    assert clsD.fullName() == '<test>.D'
    assert clsD.docstring == None
    assert len(clsD.contents) == 1

    assert len(clsD.bases) == 3
    base1, base2, base3 = clsD.bases
    assert base1 == 'X.A', base1
    assert base2 == 'X.B.C', base2
    assert base3 == 'Y.Z.C', base3

def test_aliasing():
    def addsrc(system):
        src_a = '''
        class A:
            pass
        '''
        src_b = '''
        from a import A as B
        '''
        src_c = '''
        from b import B
        class C(B):
            pass
        '''
        fromText(src_a, 'a', system)
        fromText(src_b, 'b', system)
        fromText(src_c, 'c', system)

    system = model.System()
    addsrc(system)
    assert system.allobjects['c.C'].bases == ['a.A']

def test_more_aliasing():
    def addsrc(system):
        src_a = '''
        class A:
            pass
        '''
        src_b = '''
        from a import A as B
        '''
        src_c = '''
        from b import B as C
        '''
        src_d = '''
        from c import C
        class D(C):
            pass
        '''
        fromText(src_a, 'a', system)
        fromText(src_b, 'b', system)
        fromText(src_c, 'c', system)
        fromText(src_d, 'd', system)

    system = model.System()
    addsrc(system)
    assert system.allobjects['d.D'].bases == ['a.A']

def test_aliasing_recursion():
    system = model.System()
    src = '''
    class C:
        pass
    from mod import C
    class D(C):
        pass
    '''
    mod = fromText(src, 'mod', system)
    assert mod.contents['D'].bases == ['mod.C'], mod.contents['D'].bases

def test_subclasses():
    src = '''
    class A:
        pass
    class B(A):
        pass
    '''
    system = fromText(src).system
    assert (system.allobjects['<test>.A'].subclasses ==
            [system.allobjects['<test>.B']])

def test_inherit_names():
    src = '''
    class A:
        pass
    class A(A):
        pass
    '''
    mod = fromText(src)
    assert [b.name for b in mod.contents['A'].allbases()] == ['A 0']

def test_nested_class_inheriting_from_same_module():
    src = '''
    class A:
        pass
    class B:
        class C(A):
            pass
    '''
    fromText(src)

def test_all_recognition():
    mod = fromText('''
    def f():
        pass
    __all__ = ['f']
    ''')
    astbuilder.findAll(mod.ast, mod)
    assert mod.all == ['f']

def test_all_in_class_non_recognition():
    mod = fromText('''
    class C:
        __all__ = ['f']
    ''')
    astbuilder.findAll(mod.ast, mod)
    assert mod.all is None

def test_classmethod():
    mod = fromText('''
    class C:
        @classmethod
        def f(klass):
            pass
    ''')
    assert mod.contents['C'].contents['f'].kind == 'Class Method'
    mod = fromText('''
    class C:
        def f(klass):
            pass
        f = classmethod(f)
    ''')
    assert mod.contents['C'].contents['f'].kind == 'Class Method'

def test_classdecorator():
    mod = fromText('''
    def cd(cls):
        pass
    @cd
    class C:
        pass
    ''', modname='mod')
    C = mod.contents['C']
    assert C.decorators == [(('cd', 'mod.cd', mod.contents['cd']), None)], \
      C.decorators


def test_classdecorator_with_args():
    mod = fromText('''
    def cd(): pass
    class A: pass
    @cd(A)
    class C:
        pass
    ''', modname='test')
    cd = mod.contents['cd']
    A = mod.contents['A']
    C = mod.contents['C']
    assert C.decorators == [(('cd', 'test.cd', cd), [('A', 'test.A', A)])], \
      C.decorators


def test_import_star():
    mod_a = fromText('''
    def f(): pass
    ''', modname='a')
    mod_b = fromText('''
    from a import *
    ''', modname='b', system=mod_a.system)
    assert mod_b.resolveName('f') == mod_a.contents['f']


def test_inline_docstring_modulevar():
    mod = fromText('''
    """regular module docstring

    @var b: doc for b
    """

    """not a docstring"""

    a = 1
    """inline doc for a"""

    b = 2

    def f():
        pass
    """not a docstring"""
    ''', modname='test')
    assert sorted(mod.contents.keys()) == ['a', 'b', 'f']
    a = mod.contents['a']
    assert a.docstring == """inline doc for a"""
    b = mod.contents['b']
    assert unwrap(b.parsed_docstring) == """doc for b"""
    f = mod.contents['f']
    assert not f.docstring

def test_inline_docstring_classvar():
    mod = fromText('''
    class C:
        """regular class docstring"""

        def f(self):
            pass
        """not a docstring"""

        a = 1
        """inline doc for a"""

        """not a docstring"""

        _b = 2
        """inline doc for _b"""

        None
        """not a docstring"""
    ''', modname='test')
    C = mod.contents['C']
    assert sorted(C.contents.keys()) == ['_b', 'a', 'f']
    f = C.contents['f']
    assert not f.docstring
    a = C.contents['a']
    assert a.docstring == """inline doc for a"""
    assert a.privacyClass is model.PrivacyClass.VISIBLE
    b = C.contents['_b']
    assert b.docstring == """inline doc for _b"""
    assert b.privacyClass is model.PrivacyClass.PRIVATE

@py3only
def test_inline_docstring_annotated_classvar():
    mod = fromText('''
    class C:
        """regular class docstring"""

        a: int
        """inline doc for a"""

        _b: int = 4
        """inline doc for _b"""
    ''', modname='test')
    C = mod.contents['C']
    assert sorted(C.contents.keys()) == ['_b', 'a']
    a = C.contents['a']
    assert a.docstring == """inline doc for a"""
    assert a.privacyClass is model.PrivacyClass.VISIBLE
    b = C.contents['_b']
    assert b.docstring == """inline doc for _b"""
    assert b.privacyClass is model.PrivacyClass.PRIVATE

def test_inline_docstring_instancevar():
    mod = fromText('''
    class C:
        """regular class docstring"""

        d = None
        """inline doc for d"""

        f = None
        """inline doc for f"""

        def __init__(self):
            self.a = 1
            """inline doc for a"""

            """not a docstring"""

            self._b = 2
            """inline doc for _b"""

            x = -1
            """not a docstring"""

            self.c = 3
            """inline doc for c"""

            self.d = 4

            self.e = 5
        """not a docstring"""

        def set_f(self, value):
            self.f = value
    ''', modname='test')
    C = mod.contents['C']
    assert sorted(C.contents.keys()) == [
        '__init__', '_b', 'a', 'c', 'd', 'e', 'f', 'set_f'
        ]
    a = C.contents['a']
    assert a.docstring == """inline doc for a"""
    assert a.privacyClass is model.PrivacyClass.VISIBLE
    assert a.kind == 'Instance Variable'
    b = C.contents['_b']
    assert b.docstring == """inline doc for _b"""
    assert b.privacyClass is model.PrivacyClass.PRIVATE
    assert b.kind == 'Instance Variable'
    c = C.contents['c']
    assert c.docstring == """inline doc for c"""
    assert c.privacyClass is model.PrivacyClass.VISIBLE
    assert c.kind == 'Instance Variable'
    d = C.contents['d']
    assert d.docstring == """inline doc for d"""
    assert d.privacyClass is model.PrivacyClass.VISIBLE
    assert d.kind == 'Instance Variable'
    e = C.contents['e']
    assert not e.docstring
    f = C.contents['f']
    assert f.docstring == """inline doc for f"""
    assert f.privacyClass is model.PrivacyClass.VISIBLE
    assert f.kind == 'Instance Variable'

@py3only
def test_inline_docstring_annotated_instancevar():
    mod = fromText('''
    class C:
        """regular class docstring"""

        a: int

        def __init__(self):
            self.a = 1
            """inline doc for a"""

            self.b: int = 2
            """inline doc for b"""
    ''', modname='test')
    C = mod.contents['C']
    assert sorted(C.contents.keys()) == ['__init__', 'a', 'b']
    a = C.contents['a']
    assert a.docstring == """inline doc for a"""
    b = C.contents['b']
    assert b.docstring == """inline doc for b"""

def test_variable_scopes():
    mod = fromText('''
    l = 1
    """module-level l"""

    m = 1
    """module-level m"""

    class C:
        """class docstring

        @ivar k: class level doc for k
        """

        a = None

        k = 640

        m = 2
        """class-level m"""

        def __init__(self):
            self.a = 1
            """inline doc for a"""
            self.l = 2
            """instance l"""
    ''', modname='test')
    l1 = mod.contents['l']
    assert l1.kind == 'Variable'
    assert l1.docstring == """module-level l"""
    m1 = mod.contents['m']
    assert m1.kind == 'Variable'
    assert m1.docstring == """module-level m"""
    C = mod.contents['C']
    assert sorted(C.contents.keys()) == ['__init__', 'a', 'k', 'l', 'm']
    a = C.contents['a']
    assert a.kind == 'Instance Variable'
    assert a.docstring == """inline doc for a"""
    k = C.contents['k']
    assert k.kind == 'Instance Variable'
    assert unwrap(k.parsed_docstring) == """class level doc for k"""
    l2 = C.contents['l']
    assert l2.kind == 'Instance Variable'
    assert l2.docstring == """instance l"""
    m2 = C.contents['m']
    assert m2.kind == 'Class Variable'
    assert m2.docstring == """class-level m"""

def test_variable_types():
    mod = fromText('''
    class C:
        """class docstring

        @cvar a: first
        @type a: C{str}

        @type b: C{str}
        @cvar b: second

        @type c: C{str}

        @ivar d: fourth
        @type d: C{str}

        @type e: C{str}
        @ivar e: fifth

        @type f: C{str}
        """

        a = "A"

        b = "B"

        c = "C"
        """third"""

        def __init__(self):

            self.d = "D"

            self.e = "E"

            self.f = "F"
            """sixth"""
    ''', modname='test')
    C = mod.contents['C']
    assert sorted(C.contents.keys()) == [
        '__init__', 'a', 'b', 'c', 'd', 'e', 'f'
        ]
    a = C.contents['a']
    assert unwrap(a.parsed_docstring) == """first"""
    assert str(unwrap(a.parsed_type)) == '<code>str</code>'
    assert a.kind == 'Class Variable'
    b = C.contents['b']
    assert unwrap(b.parsed_docstring) == """second"""
    assert str(unwrap(b.parsed_type)) == '<code>str</code>'
    assert b.kind == 'Class Variable'
    c = C.contents['c']
    assert c.docstring == """third"""
    assert str(unwrap(c.parsed_type)) == '<code>str</code>'
    assert c.kind == 'Class Variable'
    d = C.contents['d']
    assert unwrap(d.parsed_docstring) == """fourth"""
    assert str(unwrap(d.parsed_type)) == '<code>str</code>'
    assert d.kind == 'Instance Variable'
    e = C.contents['e']
    assert unwrap(e.parsed_docstring) == """fifth"""
    assert str(unwrap(e.parsed_type)) == '<code>str</code>'
    assert e.kind == 'Instance Variable'
    f = C.contents['f']
    assert f.docstring == """sixth"""
    assert str(unwrap(f.parsed_type)) == '<code>str</code>'
    assert f.kind == 'Instance Variable'

@py3only
def test_annotated_variables():
    mod = fromText('''
    class C:
        """class docstring

        @cvar a: first
        @type a: string

        @type b: string
        @cvar b: second
        """

        a: str = "A"

        b: str

        c: str = "C"
        """third"""

        d: str
        """fourth"""

        e: List['C']
        """fifth"""

        f: 'List[C]'
        """sixth"""

        g: 'List["C"]'
        """seventh"""

        def __init__(self):
            self.s: List[str] = []
            """instance"""

    m: bytes = b"M"
    """module-level"""
    ''', modname='test')
    C = mod.contents['C']
    a = C.contents['a']
    assert unwrap(a.parsed_docstring) == """first"""
    assert str(unwrap(get_parsed_type(a))) == 'string'
    b = C.contents['b']
    assert unwrap(b.parsed_docstring) == """second"""
    assert str(unwrap(get_parsed_type(b))) == 'string'
    c = C.contents['c']
    assert c.docstring == """third"""
    assert str(unwrap(get_parsed_type(c))) == '<code>str</code>'
    d = C.contents['d']
    assert d.docstring == """fourth"""
    assert str(unwrap(get_parsed_type(d))) == '<code>str</code>'
    e = C.contents['e']
    assert e.docstring == """fifth"""
    assert str(unwrap(get_parsed_type(e))) == '<code>List[C]</code>'
    f = C.contents['f']
    assert f.docstring == """sixth"""
    assert str(unwrap(get_parsed_type(f))) == '<code>List[C]</code>'
    g = C.contents['g']
    assert g.docstring == """seventh"""
    assert str(unwrap(get_parsed_type(g))) == '<code>List[C]</code>'
    s = C.contents['s']
    assert s.docstring == """instance"""
    assert str(unwrap(get_parsed_type(s))) == '<code>List[str]</code>'
    m = mod.contents['m']
    assert m.docstring == """module-level"""
    assert str(unwrap(get_parsed_type(m))) == '<code>bytes</code>'

def test_inferred_variable_types():
    mod = fromText('''
    class C:
        a = "A"
        b = 2
        c = ['a', 'b', 'c']
        d = {'a': 1, 'b': 2}
        e = (True, False, True)
        f = 1.618
        g = {2, 7, 1, 8}
        h = []
        i = ['r', 2, 'd', 2]
        j = ((), ((), ()))
        n = None
        x = list(range(10))
        y = [n for n in range(10) if n % 2]
        def __init__(self):
            self.s = ['S']
    m = b'octets'
    ''', modname='test')
    C = mod.contents['C']
    assert type2str(C.contents['a'].annotation) == 'str'
    assert type2str(C.contents['b'].annotation) == 'int'
    assert type2str(C.contents['c'].annotation) == 'List[str]'
    assert type2str(C.contents['d'].annotation) == 'Dict[str, int]'
    assert type2str(C.contents['e'].annotation) == 'Tuple[bool, ...]'
    assert type2str(C.contents['f'].annotation) == 'float'
    # The Python 2.7 implementation of literal_eval() does not support
    # set literals.
    assert type2str(C.contents['g'].annotation) in ('Set[int]', None)
    # Element type is unknown, not uniform or too complex.
    assert type2str(C.contents['h'].annotation) == 'List'
    assert type2str(C.contents['i'].annotation) == 'List'
    assert type2str(C.contents['j'].annotation) == 'Tuple'
    # It is unlikely that a variable actually will contain only None,
    # so we should treat this as not be able to infer the type.
    assert C.contents['n'].annotation is None
    # These expressions are considered too complex for pydoctor.
    # Maybe we can use an external type inferrer at some point.
    assert C.contents['x'].annotation is None
    assert C.contents['y'].annotation is None
    # Type inference isn't different for module and instance variables,
    # so we don't need to re-test everything.
    assert type2str(C.contents['s'].annotation) == 'List[str]'
    # On Python 2.7, bytes literals are parsed into ast.Str objects,
    # so there is no way to tell them apart from ASCII strings.
    assert type2str(mod.contents['m'].annotation) in ('bytes', 'str')

def test_type_from_attrib():
    mod = fromText('''
    import attr
    from attr import attrib
    class C:
        a = attr.ib(type=int)
        b = attrib(type=int)
        c = attr.ib(type='C')
        d = attr.ib(default=True)
    ''', modname='test')
    C = mod.contents['C']
    assert type2str(C.contents['a'].annotation) == 'int'
    assert type2str(C.contents['b'].annotation) == 'int'
    assert type2str(C.contents['c'].annotation) == 'C'
    assert type2str(C.contents['d'].annotation) == 'bool'
