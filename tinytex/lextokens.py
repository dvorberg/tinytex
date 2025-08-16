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

from tinymarkup.exceptions import Location, LexerSetupError


tokens = ( "begin_environment", "end_environment",
           "command",
           "open_oparam", "close_oparam",
           "open_curly", "close_curly", # curly is either ProcMarkup or ReqParam
           "linebreak", "eols",
           "comment", "whitespace",
           "placeholder",
           "word", "text", )

#def t_begin_procedural_markup(token):
#    r"\{\\(?P<proc>\w+)"
#    token.value = token.lexer.lexmatch.groupdict()["proc"]
#    return token

def t_begin_environment(token):
    r"\\begin{(?P<benv>\w+)}"
    token.value = token.lexer.lexmatch.groupdict()["benv"]
    return token

def t_end_environment(token):
    r"\\end{(?P<eenv>\w+)}"
    token.value = token.lexer.lexmatch.groupdict()["eenv"]
    return token

def t_command(token):
    r"\\(?P<command>[a-zA-Z][a-zA-Z0-9]*\*?)"
    token.value = token.lexer.lexmatch.groupdict()["command"]
    return token

t_open_oparam = r"\["
t_close_oparam = r"\]"

t_open_curly = r"\{"
t_close_curly = r"\}"

t_linebreak = r"\\\\"

def t_eols(t):
    r"\n\n+"
    t.value = "\n" * t.value.count("\n")
    return t

t_comment = "%.*?[\n$]\s*"
t_whitespace = r"[ \t]+|\n(?!\n)"

t_placeholder = r"#(\d+)"
t_word = r"\w[\w \t]*\w"
t_text = r"."

def t_error(t):
    raise LexerSetupError(repr(t), location=Location.from_baselexer(t.lexer))
