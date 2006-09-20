# $Id$

_xlat = {91: u'{', 92: u'|', 93: u'}', 94: u'~'}
def irc_ulower(str):
    if str is None: return str
    if len(str) == 0: return str
    return str.translate(_xlat).lower()
