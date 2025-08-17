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

from io import StringIO

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
        yield from iter(self._children)

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

    def copy(self, children):
        ret = self.__class__()
        ret._children = list(children)
        return ret

    @property
    def last_child(self):
        if self._children:
            return self._children[-1]
        else:
            return None

    @property
    def first_child(self):
        if self._children:
            return self._children[0]
        else:
            return None

class Root(Node):
    pass

class Environment(Node):
    def __init__(self, environment):
        super().__init__()
        self.environment = environment

    def copy(self, children):
        ret = self.__class__(self.environment)
        ret._children = list(children)
        return ret

    def _repr_info(self):
        return self.environment

class Command(Node):
    def __init__(self, command, parser_location=None):
        super().__init__()
        self.command = command
        self.parser_location = parser_location

    def copy(self, children):
        ret = self.__class__(self.command, self.parser_location)
        ret._children = list(children)
        return ret

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

    def copy(self, children=None):
        return self.__class__(self._text)

    @property
    def text(self):
        return self._text

    def __str__(self):
        return self._text

    def __repr__(self):
        return f"{self.__class__.__name__}(“{self.text}”)"

class Placeholder(Text):
    def __init__(self, text):
        super().__init__(text)
        self.no = int(text[1:])
