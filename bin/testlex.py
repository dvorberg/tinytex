import sys
import icecream; icecream.install()
from tinytex import parser
from tinytex.parser import TexParser

p = TexParser()
p.parse(open(sys.argv[1]).read(), None)
