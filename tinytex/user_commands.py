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

from functools import cached_property
from collections import deque

from tinymarkup.exceptions import ParseError
from .nodes import (RootReached, Node, Root, Environment, Command,
                    OptionalParameter, RequiredParameter,
                    LineBreak, ParagraphBreak, BeginScope, EndScope,
                    Whitespace, Text, Placeholder)

class UserCommandParseError(ParseError):
    pass

def find_user_commands(root):
    r"""
    Recursively search for user command definitions (\newcommand,
    \renewcommand and \NewDocumentCommand) and yield UserCommand
    objects.
    """
    children = iter(root.children)
    for child in children:
        if isinstance(child, Command):
            if child.name in { "newcommand", "renewcommand", }:
                yield OldStyleNewCommand(child)
            elif child.name == "NewDocumentCommand":
                yield XParseDocumentCommand(child, next(children))
        else:
            for cmd in find_user_commands(child):
                yield cmd

def resolve_user_commands(root, extra_user_commands={}):
    """
    Return a recursive copy of this node with the user
    commands resolved.
    """
    user_commands = dict([(cmd.name, cmd,)
                          for cmd in find_user_commands(root)])
    user_commands.update(extra_user_commands)

    def process(node):
        def newchildren(children):
            scopes = []
            for child in children:
                if isinstance(child, Command):
                    if child.name in { "newcommand", "renewcommand" }:
                        pass
                    elif child.name == "NewDocumentCommand":
                        # Skip the next command node so the
                        # command definition does not get called.
                        next(children)
                    elif child.name in user_commands:
                        usercmd = user_commands[child.name]
                        for newnode in usercmd.call(child):
                            yield process(newnode)
                    else:
                        yield process(child)
                elif isinstance(child, BeginScope):
                    newbegin = child.copy() # No need to process().
                    scopes.append(newbegin)
                    yield newbegin
                elif isinstance(child, EndScope):
                    newend = child.copy()
                    newbegin = scopes.pop()
                    newbegin.end = newend
                    newend.begin = newbegin
                    yield newend
                else:
                    yield process(child)

        return node.copy(newchildren(node.children))

    return process(root)

class Argument(object):
    pass

class Mandetory(Argument):
    pass

class Optional(Argument):
    def __init__(self, default=None):
        self.default = default

    @classmethod
    def from_nodes(Optional, letter, nodes):
        begin = next(nodes)
        if not isinstance(begin, BeginScope):
            raise UserCommandParseError(
                "“O” argument must be "
                "followed by {}-Scope.",
                location=self.parser_location)

        end = begin.end
        scope = begin.assemble()

        here = next(nodes)
        while not here is end:
            here = next(nodes)

        return Optional(scope)


    def __repr__(self):
        return f"<{self.__class__.__name__} {{{repr(self.default)}}}"


class UserCommand(object):
    def call(self, command):
        """
        Return a recursive copy of our definition with the placeholders
        replaced by the call’s parameters.
        """
        rparams = deque(command.required_parameters)
        oparams = deque(command.optional_parameters)

        def argument_values():
            for spec in self.argspecs:
                if isinstance(spec, Mandetory):
                    yield rparams.popleft().children
                elif isinstance(spec, Optional):
                    if oparams:
                        arg = oparams.popleft()
                    else:
                        arg = None

                    if arg is None:
                        yield spec.default
                    else:
                        yield arg.children
                else:
                    raise TypeError()

        try:
            parameters = tuple(argument_values())
        except IndexError as ie:
            raise UserCommandParseError(
                f"Mismatch of arguments between definition and call of "
                f"“\\{command.command}”.",
                location=command.parser_location) from ie

        def walk(nodes):
            for node in nodes:
                if isinstance(node, Placeholder):
                    yield from parameters[node.no-1]
                else:
                    yield node.copy(walk(node._children))

        yield from walk(self.definition)


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
        super().__init__()

        self.parser_location = command.parser_location

        optparams = command.optional_parameters
        self.rparams = rparams = command.required_parameters

        if len(optparams) == 0:
            nargs = 0
            optargdefault = None
        elif len(optparams) > 0:
            try:
                nargs = int(str(optparams[0]))
            except ValueError:
                raise UserCommandParseError(
                    f"Can’t parse number of arguments “{nargs}”",
                    location=self.command.parser_location)

        if len(optparams) > 1:
            optargdefault = str(optparams[-1])
            wants_optional_parameter = True
        else:
            wants_optional_parameter = False

        if len(self.rparams) != 2:
            raise UserCommandParseError(
                f"\(re)newcommand requires two parameters.",
                location=self.command.parser_location)

        argspecs = []
        if wants_optional_parameter:
            argspecs.append(Optional(Text(optargdefault)))
            nargs -= 1

        for a in range(nargs):
            argspecs.append(Mandetory())

        self.argspecs = tuple(argspecs)

    @cached_property
    def name(self):
        command = self.rparams[0].first(Command)
        if command is None:
            raise UserCommandParseError(
                "\(re)newcommand’s first param "
                "must be a command to (re-)define.",
                location=self.command.parser_location)
        return command.name

    @property
    def definition(self):
        yield from self.rparams[-1].children

    def __repr__(self):
        me = self.__class__.__name__
        return f"<{me}({self.nargs}, {repr(self.optargdefault)})>"

class XParseDocumentCommand(UserCommand):
    def __init__(self, command, newcommand):
        super().__init__()

        self.parser_location = command.parser_location
        self.name = newcommand.name

        if len(newcommand.required_parameters) != 2:
            raise UserCommandParseError(
                "NewDocumentCommand must provide the command with two required "
                "parameters: argspec and the definition body.",
                location=self.parser_location)

        argspecs, definition = newcommand.required_parameters
        self.argspecs = tuple(self.parse_argspecs(argspecs))
        self.definition = definition.children

    def parse_argspecs(self, rargs):
        nodes = rargs.children
        for node in nodes:
            if isinstance(node, Text):
                letters = node.text
                for letter in letters:
                    if letter in " \t\n":
                        pass
                    elif letter == "m":
                        yield Mandetory()
                    elif letter == "o":
                        yield Optional()
                    elif letter == "O":
                        yield Optional.from_nodes(node, nodes)
