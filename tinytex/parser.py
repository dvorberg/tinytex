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

import ply.lex

from tinymarkup.exceptions import (InternalError, ParseError, UnknownMacro,
                                   Location, UnsuitableMacro)
from tinymarkup.parser import Parser

from .compiler import TexCompiler
from . import lextokens
from .nodes import (RootReached, Node, Root, Environment, Command,
                    OptionalParameter, RequiredParameter,
                    LineBreak, ParagraphBreak, BeginScope, EndScope,
                    Whitespace, Text, Placeholder)
from .user_commands import resolve_user_commands

tex_base_lexer = ply.lex.lex(module=lextokens,
                             reflags=re.MULTILINE|re.IGNORECASE|re.DOTALL,
                             optimize=False,
                             lextab=None)

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
                    if here.scope_stack:
                        raise ParseError("Can’t begin an environment within "
                                         "a scope.", location=self.location)

                    here = here.append(Environment(token.value))

                case "end_environment":
                    if here.scope_stack:
                        raise ParseError("Environment not closed.",
                                         location=self.location)

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
                                        # These currently won’t work.
                                        # "newcommand*", "renewcommand*",
                                        "NewDocumentCommand", }:
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
                        begin = BeginScope(self.location)
                        here.scope_stack.append(begin)
                        here.append(begin)

                case "close_curly":
                    if here.scope_stack:
                        begin = here.scope_stack.pop()

                        end = EndScope()

                        end.begin = begin
                        begin.end = end
                        here.append(end)
                    else:
                        if isinstance(here, Command):
                            # There was a command without parameters?
                            try:
                                here = here.parent.walk_up_to(Command)
                            except RootReached:
                                raise ParseError(
                                    "Closing curly brace without opening (1).",
                                    location=self.location)

                        elif isinstance(here, RequiredParameter):
                            # This is the end of a RequiredParameter
                            here = here.walk_up_to(Command)
                        else:
                            # A } without context.
                            raise ParseError(
                                "Closing curly brace without opening (2).",
                                location=self.location)

                case "linebreak":
                    here.append(LineBreak())

                case "eols":
                    if isinstance(here, Command):
                        here = here.parent
                    if not isinstance(here.last_child, ParagraphBreak):
                        here.append(ParagraphBreak())

                case "comment":
                    pass

                case "whitespace":
                    if isinstance(here, Command):
                        here = here.parent

                    if not isinstance(here.last_child, Whitespace):
                        here.append(Whitespace())

                case "placeholder":
                    here.append(Placeholder(token.value))

                case "word"|"text":
                    if isinstance(here, Command):
                        here = here.parent
                    here.append(Text(token.value))

        root = resolve_user_commands(root)
