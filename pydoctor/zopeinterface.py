"""Support for Zope interfaces."""

from __future__ import print_function

import ast
import re

import astor
from pydoctor import astbuilder, model
from six import text_type


class ZopeInterfaceModule(model.Module):
    def setup(self):
        super(ZopeInterfaceModule, self).setup()
        self.implements_directly = [] # [name of interface]

    @property
    def allImplementedInterfaces(self):
        """Return all the interfaces provided by this module
        """
        return list(self.implements_directly)


class ZopeInterfaceClass(model.Class):
    isinterface = False
    isschemafield = False
    isinterfaceclass = False
    implementsOnly = False
    implementedby_directly = None # [objects], when isinterface == True
    def setup(self):
        super(ZopeInterfaceClass, self).setup()
        self.implements_directly = [] # [name of interface]

    @property
    def allImplementedInterfaces(self):
        """Return all the interfaces implemented by this class.

        This returns them in something like the classic class MRO.
        """
        r = list(self.implements_directly)
        if self.implementsOnly:
            return r
        for b in self.baseobjects:
            if b is None:
                continue
            for interface in b.allImplementedInterfaces:
                if interface not in r:
                    r.append(interface)
        return r

    @property
    def allImplementations(self):
        r = list(self.implementedby_directly)
        stack = list(r)
        while stack:
            c = stack.pop(0)
            for sc in c.subclasses:
                if sc.implementsOnly:
                    continue
                stack.append(sc)
                if sc not in r:
                    r.append(sc)
        return r


class ZopeInterfaceFunction(model.Function):
    def docsources(self):
        for source in super(ZopeInterfaceFunction, self).docsources():
            yield source
        if not isinstance(self.parent, (model.Class, model.Module)):
            return
        for interface in self.parent.allImplementedInterfaces:
            io = self.system.objForFullName(interface)
            if io is not None:
                for io2 in io.allbases(include_self=True):
                    if self.name in io2.contents:
                        yield io2.contents[self.name]

def addInterfaceInfoToScope(scope, interfaceargs):
    for arg in interfaceargs:
        if not isinstance(arg, tuple):
            fullName = scope.expandName(astor.to_source(arg).strip())
        else:
            fullName = arg[1]
        obj = scope.system.objForFullName(fullName)
        if isinstance(obj, ZopeInterfaceClass):
            scope.implements_directly.append(fullName)
            if not obj.isinterface:
                obj.system.msg(
                    'zopeinterface',
                    'probable interface %r not marked as such'%obj,
                    thresh=1)
                obj.isinterface = True
                obj.kind = "Interface"
                obj.implementedby_directly = []
            obj.implementedby_directly.append(scope)
        elif obj is not None:
            obj.system.msg(
                'zopeinterface',
                'probable interface %r not detected as class'%obj)

def addInterfaceInfoToModule(module, interfaceargs):
    addInterfaceInfoToScope(module, interfaceargs)

def addInterfaceInfoToClass(cls, interfaceargs, implementsOnly):
    cls.implementsOnly = implementsOnly
    if implementsOnly:
        cls.implements_directly = []
    addInterfaceInfoToScope(cls, interfaceargs)


schema_prog = re.compile(r'zope\.schema\.([a-zA-Z_][a-zA-Z0-9_]*)')
interface_prog = re.compile(
    r'zope\.schema\.interfaces\.([a-zA-Z_][a-zA-Z0-9_]*)'
    r'|zope\.interface\.Interface')

def namesInterface(system, name):
    if interface_prog.match(name):
        return True
    obj = system.objForFullName(name)
    if not obj or not isinstance(obj, model.Class):
        return False
    return obj.isinterface

def extractAttributeDescription(node):
    pass

def extractSchemaDescription(node):
    pass

def extractStringLiteral(node):
    if isinstance(node, ast.Str):
        return node.s
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Call):
        return node.args[0].s
    else:
        raise TypeError("cannot extract string from %r" % (node,))

class ZopeInterfaceModuleVisitor(astbuilder.ModuleVistor):

    schema_like_patterns = [
        (r'zope\.interface\.Attribute', extractAttributeDescription),
        ]

    def funcNameFromCall(self, node):
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = astor.to_source(node).strip().split("(")[0]
        elif isinstance(node.func, ast.Call):
            return self.funcNameFromCall(node.func)
        else:
            return None
        return self.builder.current.expandName(name)

    def _handleAssignmentInModule(self, target, annotation, expr, lineno):
        super(ZopeInterfaceModuleVisitor, self)._handleAssignmentInModule(
                target, annotation, expr, lineno)

        if not isinstance(expr, ast.Call):
            return
        funcName = self.funcNameFromCall(expr)
        if funcName is None:
            return
        ob = self.system.objForFullName(funcName)
        if isinstance(ob, model.Class) and ob.isinterfaceclass:
            interface = self.builder.pushClass(target, "...")
            self.builder.system.msg('parsing', 'new interface')
            interface.isinterface = True
            interface.implementedby_directly = []
            interface.linenumber = lineno
            self.builder.popClass()

    def _handleAssignmentInClass(self, target, annotation, expr, lineno):
        super(ZopeInterfaceModuleVisitor, self)._handleAssignmentInClass(
                target, annotation, expr, lineno)

        def handleSchemaField():
            descriptions = [arg.value for arg in expr.keywords if arg.arg == 'description']
            if len(descriptions) > 1:
                self.builder.system.msg('parsing', 'xxx')
            elif len(descriptions) == 1:
                attr.docstring = extractStringLiteral(descriptions[0])

        if not isinstance(expr, ast.Call):
            return
        attr = self.builder.current.contents[target]
        funcName = self.funcNameFromCall(expr)
        if funcName is None:
            return
        if funcName == 'zope.interface.Attribute':
            args = expr.args
            if args is not None and len(args) == 1:
                attr.kind = 'Attribute'
                attr.docstring = extractStringLiteral(expr.args[0])
        elif schema_prog.match(funcName):
            attr.kind = schema_prog.match(funcName).group(1)
            handleSchemaField()
        else:
            cls = self.builder.system.objForFullName(funcName)
            if isinstance(cls, ZopeInterfaceClass) and cls.isschemafield:
                attr.kind = cls.name
                handleSchemaField()

    def visit_Call(self, node):
        base = self.funcNameFromCall(node)
        if base is None:
            return
        meth = getattr(self, "visit_Call_" + base.replace('.', '_'), None)
        if meth is not None:
            meth(base, node)

    def visit_Call_zope_interface_moduleProvides(self, funcName, node):
        if not isinstance(self.builder.current, model.Module):
            self.default(node)
            return

        addInterfaceInfoToModule(self.builder.current, node.args)

    def visit_Call_zope_interface_implements(self, funcName, node):
        if not isinstance(self.builder.current, model.Class):
            self.default(node)
            return
        addInterfaceInfoToClass(self.builder.current, node.args,
                                funcName == 'zope.interface.implementsOnly')
    visit_Call_zope_interface_implementsOnly = visit_Call_zope_interface_implements

    def visit_Call_zope_interface_classImplements(self, funcName, node):
        clsname = self.builder.current.expandName(
            astor.to_source(node.args[0]).strip())
        if clsname not in self.system.allobjects:
            self.builder.system.msg(
                "parsing",
                "classImplements on unknown class %r"%clsname)
            return
        cls = self.system.allobjects[clsname]
        addInterfaceInfoToClass(cls, node.args[1:],
                                funcName == 'zope.interface.classImplementsOnly')
    visit_Call_zope_interface_classImplementsOnly = visit_Call_zope_interface_classImplements

    def visit_ClassDef(self, node):
        super(ZopeInterfaceModuleVisitor, self).visit_ClassDef(node)
        cls = self.builder.current.contents[node.name]

        bases = []

        for base in cls.bases:
            if isinstance(base, ast.Name):
                bases.append(self.builder.current.expandName(base.id))
            elif isinstance(base, text_type):
                bases.append(self.builder.current.expandName(base))
            else:
                raise Exception(base)

        if 'zope.interface.interface.InterfaceClass' in bases:
            cls.isinterfaceclass = True
            
        if len([b for b in cls.bases
                if namesInterface(self.system, b)]) > 0:
            cls.isinterface = True
            cls.kind = "Interface"
            cls.implementedby_directly = []

        for n, o in zip(cls.bases, cls.baseobjects):
            if schema_prog.match(n) or (o and o.isschemafield):
                cls.isschemafield = True

        for ((dn, fn, o), args) in cls.decorators:
            if fn == 'zope.interface.implementer':
                addInterfaceInfoToClass(cls, args, False)


class ZopeInterfaceASTBuilder(astbuilder.ASTBuilder):
    ModuleVistor = ZopeInterfaceModuleVisitor


class ZopeInterfaceSystem(model.System):
    Module = ZopeInterfaceModule
    Class = ZopeInterfaceClass
    Function = ZopeInterfaceFunction
    defaultBuilder = ZopeInterfaceASTBuilder
