XMPP IRC-Transport Readme.
==========================


Installing the transport:
-------------------------

To install the transport you need a copy of the xmpppy (by Alexey Nezhdanov) library on your system and a copy of the irclib (by Joel Rosdahl). You can find both of these at the following addresses:

http://xmpppy.sourceforge.net
http://python-irclib.sourceforge.net

To make the irclib library integrate with the transport more effectively you need to patch it with the supplied diff file: irclib.py.diff.  (patch <irclib.py.diff works for me). This allows the external select function without needing lambda functions. This is required for the transport to operate.

Configure the Transport:
------------------------

To configure the transport you need to modify your jabber server configuration to expose the irc-transport to users. The transport itself has a configuration file which it reads on startup.  A sample configuration file is provided, copy it as config.xml and change the settings as required.

The default Python Encoding:
----------------------------

Some people may have set the python site.py encoding to something other than ascii. The transport relies on this being a non-unicode value, if you have set this to utf-8 it may not work.

Thanks to:
----------

The Jabber.org.uk crew who let me abuse their server while doing testing.
Alexey Nezhadanov for his help and the library.
Joel Rosdhal for the irclib library.
