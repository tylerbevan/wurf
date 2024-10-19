#   -------------------------------------------------------------
#   wurf :: Web Upload and Receive Files
#   - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
#   Project:        Nasqueron
#   License:        GPLv2+
#   -------------------------------------------------------------

CP=cp -p
MKDIR=mkdir -p
RMDIR=rm -rf
PYTHON=python
TOUCH=touch

#   -------------------------------------------------------------
#   Main targets
#   - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

all:

package: src/wurf/wurf.py LICENSE README.md dist

clean: clean-package


#   -------------------------------------------------------------
#   Packaging targets
#   - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

README.md:
	${CP} ../../README.md .

LICENSE:
	${CP} ../../LICENSE .

src/wurf/wurf.py:
	${MKDIR} src/wurf
	${TOUCH} src/wurf/__init__.py
	${CP} ../../src/wurf.py src/wurf/

dist:
	${PYTHON} -m build

clean-package:
	${RMDIR} dist src README.md LICENSE
