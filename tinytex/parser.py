# Copyright (C) 2025 Diedrich Vorberg
#
# Contact: diedrich@tux4web.de
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

import sys, re, dataclasses, copy
from functools import cached_property
from io import StringIO

import ply.lex

from tinymarkup.exceptions import (InternalError, ParseError, UnknownMacro,
                                   Location, UnsuitableMacro)
from tinymarkup.parser import Parser
#from tinymarkup.res import paragraph_break_re

from .compiler import TexCompiler
from . import lextokens

tex_base_lexer = ply.lex.lex(module=lextokens,
                             reflags=re.MULTILINE|re.IGNORECASE|re.DOTALL,
                             optimize=False,
                             lextab=None)

class UserCommandParseError(ParseError):
    pass

class UserCommand(object):
    pass

class OldStyleNewCommand(UserCommand):
    """
    \newcommand and \renewcommand

    \(re)newcommand{\cmd}{defn}
    \(re)newcommand{\cmd}[nargs]{defn}
    \(re)newcommand{\cmd}[nargs][optargdefault]{defn}

    There are *-versions of this available which do not support multiple

    nargs and optargdefault — The handling of which is complicated
    and explained below. This is implemented in call().

    nargs

    Optional; an integer from 0 to 9, specifying the number of
    arguments that the command takes, including any optional
    argument. Omitting this argument is the same as specifying 0,
    meaning that the command has no arguments. If you redefine a
    command, the new version can have a different number of arguments
    than the old version.

    optargdefault

    Optional; if this argument is present then the first argument of
    \cmd is optional, with default value optargdefault (which may be
    the empty string). If optargdefault is not present then \cmd does
    not take an optional argument.

    That is, if \cmd is called with a following argument in square
    brackets, as in \cmd[optval]{...}..., then within defn the
    parameter #1 is set to optval. On the other hand, if \cmd is
    called without following square brackets then within defn the
    parameter #1 is set to optargdefault. In either case, the required
    arguments start with #2.

    Omitting [optargdefault] from the definition is entirely different
    from giving the square brackets with empty contents, as in []. The
    former says the command being defined takes no optional argument,
    so #1 is the first required argument (if nargs ≥ 1); the latter
    sets the optional argument #1 to the empty string as the default,
    if no optional argument was given in the call.

    Similarly, omitting [optval] from a call is also entirely
    different from giving the square brackets with empty contents. The
    former sets #1 to the value of optval (assuming the command was
    defined to take an optional argument); the latter sets #1 to the
    empty string, just as with any other value.

    If a command is not defined to take an optional argument, but is
    called with an optional argument, the results are unpredictable:
    there may be a LaTeX error, there may be incorrect typeset output,
    or both.

    https://latexref.xyz/_005cnewcommand-_0026-_005crenewcommand.html
    """
    def __init__(self, command):
        self.command = command
        optparams = command.optional_parameters
        self.rparams = command.required_parameters

        if len(optparams) == 0:
            self.nargs = 0
            self.optargdefault = None
        elif len(optparams) > 0:
            nargs = str(optparams[0])
            try:
                self.nargs = int(nargs)
            except ValueError:
                raise UserCommandParseError(
                    f"Can’t parse number of arguments “{nargs}”",
                    location=self.command.parser_location)

        if len(optparams) > 1:
            self.optargdefault = str(optparams[-1])
            self.wants_optional_parameter = True
        else:
            self.wants_optional_parameter = False

        if len(self.rparams) != 2:
            raise UserCommandParseError(
                f"\(re)newcommand requires two parameters.",
                location=self.command.parser_location)


    @cached_property
    def name(self):
        command = self.rparams[0].first(Command)
        if command is None:
            raise UserCommandParseError(
                "\(re)newcommand’s first param "
                "must be a command to (re-)define.",
                location=self.command.parser_location)
        return command.command

    @property
    def definition(self):
        yield from self.rparams[-1].children

    def call(self, command):
        """
        Return a recursive copy of our definition with the placeholders
        replaced by the call’s parameters.
        """
        parameters = []

        if self.wants_optional_parameter:
            optional = command.optional_parameters
            required = command.required_parameters

            if len(optional) == 0:
                parameters.append(self.optargdefault)
            elif len(optional) == 1:
                parameters.append(optional[0])
            else:
                r = repr(optional)
                raise UserCommandParseError(
                    f"Calling {self.name}: "
                    f"There can only be one optional parameter with "
                    f"old-style user commands, not: {r}",
                    location=self.command.parser_location)

            parameters += list(required)
        else:
            # If the command is called with bracket-parameters for parameters
            # considered required here, they will still work. It all depends
            # on their order, anyway.
            parameters = command.parameters

        if len(parameters) != self.nargs:
            raise UserCommandParseError(
                f"User defined {self.name} "
                f"required {self.nargs} arguments, not {repr(parameters)}.",
                location=self.command.parser_location)

        def walk(nodes):
            for node in nodes:
                if isinstance(node, Placeholder):
                    yield Text(str(parameters[node.no-1]))
                else:
                    ret = node.empty_copy()
                    ret._children = list(walk(node._children))
                    yield ret

        yield from walk(self.definition)


    def __repr__(self):
        me = self.__class__.__name__
        return f"<{me}({self.nargs}, {repr(self.optargdefault)})>"

class XParseDocumentCommand(UserCommand):
    pass

class RootReached(Exception):
    pass

class Node(object):
    def __init__(self):
        self._children = []

    def append(self, child):
        self._children.append(child)
        child.parent = self
        return child

    @property
    def children(self):
        for child in self._children:
            yield child

    def walk(self, node_classes):
        """
        Perform an in-order pass of this Node and yield all instances of
        “node_classes”.
        """
        for child in self._children:
            if isinstance(child, node_classes):
                yield child
            for grandchild in child.walk(node_classes):
                yield grandchild

    def first(self, node_classes):
        for child in self._children:
            if isinstance(child, node_classes):
                return child
            else:
                ret = child.first(node_classes)
                if ret is not None:
                    return ret

        return None

    def walk_up_to(self, NodeClass):
        here = self
        while True:
            if isinstance(here, NodeClass):
                return here
            elif isinstance(here, Root):
                raise RootReached()
            else:
                here = here.parent

    def print(self, level=0):
        print(level*"  ", repr(self))
        for child in self.children:
            child.print(level+1)

    def _repr_info(self):
        return ""

    def __repr__(self):
        info = self._repr_info()
        if info:
            info = f" “{info}” "
        return f"{self.__class__.__name__}{info}({len(self._children)})"

    @property
    def text(self):
        ret = StringIO()
        for node in self.walk(FlatNode):
            ret.write(str(node))

        return ret.getvalue()

    def __str__(self):
        return self.text

    def find_user_commands(self):
        r"""
        Recursively search for user command definitions (\newcommand,
        \renewcommand and \NewDocumentCommand) and yield UserCommand
        objects.
        """
        children = iter(self._children)
        for child in children:
            if isinstance(child, Command):
                if child.command in { "newcommand", "renewcommand", }:
                    yield OldStyleNewCommand(child)
                elif child.command == "NewDocumentCommand":
                    yield XParseDocumentCommand(child, next(children))
            else:
                for cmd in child.find_user_commands():
                    yield cmd

    def resolve_user_commands(self, user_commands:dict):
        """
        Return a recursive copy of this node with the user
        commands resolved.
        """
        def children():
            for child in self._children:
                if isinstance(child, Command):
                    if child.command in { "newcommand", "renewcommand",
                                          "NewDocumentCommand",}:
                        pass
                    elif child.command in user_commands:
                        usercmd = user_commands[child.command]
                        yield from usercmd.call(child)
                else:
                    yield child

        ret = self.empty_copy()
        ret._children = list(children())
        return ret

    def empty_copy(self):
        return self.__class__()

class Root(Node):
    pass

class Environment(Node):
    def __init__(self, environment):
        super().__init__()
        self.environment = environment

    def empty_copy(self):
        return self.__class__(self.environment)

    def _repr_info(self):
        return self.environment

class Command(Node):
    def __init__(self, command, parser_location=None):
        super().__init__()
        self.command = command
        self.parser_location = parser_location

    def empty_copy(self):
        return self.__class__(self.command, self.parser_location)

    def _repr_info(self):
        return self.command

    def append(self, child):
        assert isinstance(child, (OptionalParameter,
                                  RequiredParameter)), TypeError
        return super().append(child)

    @property
    def parameters(self):
        """
        Return a list of command parameters.
        """
        return tuple(self._children)

    @property
    def optional_parameters(self):
        return tuple([p for p in self._children
                      if isinstance(p, OptionalParameter)])

    @property
    def required_parameters(self):
        return tuple([p for p in self._children
                      if isinstance(p, RequiredParameter)])

class OptionalParameter(Node):
    pass

class RequiredParameter(Node):
    pass

class LineBreak(Node):
    pass

class ParagraphBreak(Node):
    pass

class FlatNode(Node):
    def append(self, child):
        raise NotImplemented()

    def __str__(self):
        raise NotImplemented()

class BeginScope(FlatNode):
    # This is an open curly brace that’s not a paramter.
    pass

class EndScope(FlatNode):
    # This is an closing curly brace that’s not a paramter.
    pass

class Whitespace(FlatNode):
    def __str__(self):
        return " "

class Text(FlatNode):
    def __init__(self, text):
        super().__init__()
        self._text = text

    @property
    def text(self):
        return self._text

    def __str__(self):
        return self._text

    def __repr__(self):
        return f"Text(“{self.text}”)"

class Placeholder(Text):
    def __init__(self, text):
        super().__init__(text)
        self.no = int(text[1:])

class TexParser(Parser):
    def __init__(self):
        super().__init__(tex_base_lexer)

    def parse(self, source:str, compiler:TexCompiler):
        root = here = Root()
        for token in self.lexer.tokenize(source):
            def require_context(NodeClass):
                if not isinstance(here, NodeClass):
                    raise ParseError("Context required: %s" % (
                        NodeClass.__name__), location=self.location)

            match token.type:
                case "begin_environment":
                    here = here.append(Environment(token.value))

                case "end_environment":
                    try:
                        here = here.walk_up_to(Environment)
                    except RootReached:
                        raise ParseError("Not in an environment.",
                                         location=self.location)
                    if here.environment != token.value:
                        raise ParseError(f"Not in a “{tokebn.value}” "
                                         "environment.",
                                         location=self.location)
                    here = here.parent

                case "command":
                    if isinstance(here, Command):
                        here = here.parent

                    # Locations are (rather) expensive. Let’s not create
                    # one for each command.
                    if token.value in { "newcommand", "renewcommand",
                                        "NewDocumentCommand",}:
                        location = self.location
                    else:
                        location = None

                    here = here.append(Command(
                        token.value, parser_location=location))

                case "open_oparam":
                    require_context(Command)
                    here = here.append(OptionalParameter())

                case "close_oparam":
                    if isinstance(here, Command):
                        here = here.parent

                    require_context(OptionalParameter)
                    here = here.parent

                case "open_curly":
                    if isinstance(here, Command):
                        here = here.append(RequiredParameter())
                    else:
                        here.append(BeginScope())

                case "close_curly":
                    if isinstance(here, Command):
                        # There was a command without parameters.
                        try:
                            here = here.parent.walk_up_to(Command)
                        except RootReached:
                            pass
                    elif isinstance(here, RequiredParameter):
                        # This is the end of a RequiredParameter
                        here = here.walk_up_to(Command)
                    else:
                        here.append(EndScope())

                case "linebreak":
                    here.append(LineBreak())

                case "eols":
                    if isinstance(here, Command):
                        here = here.parent
                    here.append(ParagraphBreak())

                case "comment":
                    pass

                case "whitespace":
                    if isinstance(here, Command):
                        here = here.parent

                    here.append(Whitespace())

                case "placeholder":
                    here.append(Placeholder(token.value))

                case "word"|"text":
                    here.append(Text(token.value))

        root.print()
        print("*"*60)
        user_commands = root.find_user_commands()
        user_commands_by_name = dict([(c.name, c) for c in user_commands])
        root = root.resolve_user_commands(user_commands_by_name)

        root.print()
