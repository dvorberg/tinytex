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

from tinymarkup.exceptions import ParseError
from .nodes import (RootReached, Node, Root, Environment, Command,
                    OptionalParameter, RequiredParameter,
                    LineBreak, ParagraphBreak, BeginScope, EndScope,
                    Whitespace, Text, Placeholder)

def find_user_commands(root):
    r"""
    Recursively search for user command definitions (\newcommand,
    \renewcommand and \NewDocumentCommand) and yield UserCommand
    objects.
    """
    children = iter(root.children)
    for child in children:
        if isinstance(child, Command):
            if child.command in { "newcommand", "renewcommand", }:
                yield OldStyleNewCommand(child)
            elif child.command == "NewDocumentCommand":
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
            for child in children:
                if isinstance(child, Command):
                    if child.command in { "newcommand", "renewcommand",
                                          "NewDocumentCommand",}:
                        pass
                    elif child.command in user_commands:
                        usercmd = user_commands[child.command]
                        for newnode in usercmd.call(child):
                            yield process(newnode)
                    else:
                        yield process(child)
                else:
                    yield process(child)

        return node.copy(newchildren(node.children))

    return process(root)




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
                    yield node.copy(walk(node._children))

        yield from walk(self.definition)


    def __repr__(self):
        me = self.__class__.__name__
        return f"<{me}({self.nargs}, {repr(self.optargdefault)})>"

class XParseDocumentCommand(UserCommand):
    pass
