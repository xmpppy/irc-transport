# $Id$

import sys, xmpp
from xmpp.protocol import *
import config
from jep0133 import *
from irc_helpers import irc_ulower

class CommandFactory:

    def __init__(self, userfile):
        self.userfile = userfile

    def PlugIn(self, transport):
        self.commands = xmpp.commands.Commands(transport.disco)
        self.commands.PlugIn(transport.jabber)

        # jep-0133 commands:
        transport.cmdonlineusers = Online_Users_Command(transport.users,jid=config.jid)
        transport.cmdonlineusers.plugin(self.commands)
        transport.cmdactiveusers = Active_Users_Command(transport.users,jid=config.jid)
        transport.cmdactiveusers.plugin(self.commands)
        transport.cmdregisteredusers = Registered_Users_Command(self.userfile,jid=config.jid)
        transport.cmdregisteredusers.plugin(self.commands)
        transport.cmdeditadminusers = Edit_Admin_List_Command(jid=config.jid)
        transport.cmdeditadminusers.plugin(self.commands)
        transport.cmdrestartservice = Restart_Service_Command(transport,jid=config.jid)
        transport.cmdrestartservice.plugin(self.commands)
        transport.cmdshutdownservice = Shutdown_Service_Command(transport,jid=config.jid)
        transport.cmdshutdownservice.plugin(self.commands)

        # transport wide commands:
        transport.cmdconnectusers = Connect_Registered_Users_Command(self.userfile)
        transport.cmdconnectusers.plugin(self.commands)

        # server commands
        transport.cmdconnectserver = Connect_Server_Command(transport)
        transport.cmdconnectserver.plugin(self.commands)
        transport.cmddisconnectserver = Disconnect_Server_Command(transport)
        transport.cmddisconnectserver.plugin(self.commands)
        transport.cmdretrievemessageoftheday = Retrieve_Message_Of_The_Day(transport)
        transport.cmdretrievemessageoftheday.plugin(self.commands)
        transport.cmdretrieverules = Retrieve_Rules(transport)
        transport.cmdretrieverules.plugin(self.commands)

class Connect_Registered_Users_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the """
    name = "connect-users"
    description = 'Connect all registered users'
    discofeatures = [xmpp.commands.NS_COMMANDS]

    def __init__(self,userfile):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,config.jid)
        self.initial = { 'execute':self.cmdFirstStage }
        self.userfile = userfile

    def _DiscoHandler(self,conn,request,type):
        """The handler for discovery events"""
        if request.getFrom().getStripped() in config.admins:
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,request,type)
        else:
            return None

    def cmdFirstStage(self,conn,request):
        """Build the reply to complete the request"""
        if request.getFrom().getStripped() in config.admins:
            for each in self.userfile.keys():
                conn.send(Presence(to=each, frm = config.jid, typ = 'probe'))
                if self.userfile[each].has_key('servers'):
                    for server in self.userfile[each]['servers']:
                        conn.send(Presence(to=each, frm = '%s@%s'%(server,config.jid), typ = 'probe'))
            reply = request.buildReply('result')
            form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
            reply.addChild(name='command',namespace=NS_COMMANDS,attrs={'node':request.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
            self._owner.send(reply)
        else:
            self._owner.send(Error(request,ERR_FORBIDDEN))
        raise NodeProcessed

class Connect_Server_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the connect server command"""
    name = 'connect-server'
    description = 'Connect to server'
    discofeatures = [xmpp.commands.NS_COMMANDS]

    def __init__(self,transport):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,'')
        self.initial = { 'execute':self.cmdFirstStage }
        self.transport = transport

    def _DiscoHandler(self,conn,event,type):
        """The handler for discovery events"""
        fromjid = event.getFrom().getStripped().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
        if channel == '' and (not self.transport.users.has_key(fromjid) or not self.transport.users[fromjid].has_key(server)):
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,event,type)
        else:
            return None

    def cmdFirstStage(self,conn,event):
        """Build the reply to complete the request"""
        frm = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
        if channel == '':
            if self.transport.irc_connect('',server,'','',frm,Presence()):
                self.transport.xmpp_presence_do_update(Presence(),server,frm.getStripped())
                reply = event.buildReply('result')
                form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
                reply.addChild(name='command',namespace=NS_COMMANDS,attrs={'node':event.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
                self._owner.send(reply)
                raise NodeProcessed
            else:
                self._owner.send(Error(event,ERR_CONFLICT))
                raise NodeProcessed
        else:
            self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise NodeProcessed

class Disconnect_Server_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the disconnect server command"""
    name = 'disconnect-server'
    description = 'Disconnect from server'
    discofeatures = [xmpp.commands.NS_COMMANDS]

    def __init__(self,transport):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,'')
        self.initial = { 'execute':self.cmdFirstStage }
        self.transport = transport

    def _DiscoHandler(self,conn,event,type):
        """The handler for discovery events"""
        fromjid = event.getFrom().getStripped().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
        if channel == '' and self.transport.users.has_key(fromjid) and self.transport.users[fromjid].has_key(server):
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,event,type)
        else:
            return None

    def cmdFirstStage(self,conn,event):
        """Build the reply to complete the request"""
        frm = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
        if channel == '':
            if self.transport.irc_disconnect('',server,frm,None):
                self.transport.xmpp_presence_do_update(None,server,frm.getStripped())
                reply = event.buildReply('result')
                form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
                reply.addChild(name='command',namespace=NS_COMMANDS,attrs={'node':event.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
                self._owner.send(reply)
                raise NodeProcessed
            else:
                self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
                raise NodeProcessed
        else:
            self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise NodeProcessed

class Retrieve_Message_Of_The_Day(xmpp.commands.Command_Handler_Prototype):
    """This is the message of the day server command"""
    name = 'motd'
    description = 'Retrieve Message of the Day'
    discofeatures = [xmpp.commands.NS_COMMANDS]

    def __init__(self,transport):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,'')
        self.initial = { 'execute':self.cmdFirstStage }
        self.transport = transport

    def _DiscoHandler(self,conn,event,type):
        """The handler for discovery events"""
        fromjid = event.getFrom().getStripped().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
        if channel == '' and self.transport.users.has_key(fromjid) and self.transport.users[fromjid].has_key(server):
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,event,type)
        else:
            return None

    def cmdFirstStage(self,conn,event):
        """Build the reply to complete the request"""
        fromjid = event.getFrom().getStripped().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
        if channel == '':
            if self.transport.users.has_key(fromjid) \
              and self.transport.users[fromjid].has_key(server):
                # TODO: MOTD must become pending event, so it can go back to the right resource
                self.transport.users[fromjid][server].motdhash = ''
                self.transport.users[fromjid][server].motd()
                reply = event.buildReply('result')
                form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
                reply.addChild(name='command',namespace=NS_COMMANDS,attrs={'node':event.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
                self._owner.send(reply)
                raise NodeProcessed
            else:
                self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
                raise NodeProcessed
        else:
            self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise NodeProcessed

class Retrieve_Rules(xmpp.commands.Command_Handler_Prototype):
    """This is the message of the day server command"""
    name = 'rules'
    description = 'Retrieve Rules'
    discofeatures = [xmpp.commands.NS_COMMANDS]

    def __init__(self,transport):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,'')
        self.initial = { 'execute':self.cmdFirstStage }
        self.transport = transport

    def _DiscoHandler(self,conn,event,type):
        """The handler for discovery events"""
        fromjid = event.getFrom().getStripped().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
        if channel == '' and self.transport.users.has_key(fromjid) and self.transport.users[fromjid].has_key(server):
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,event,type)
        else:
            return None

    def cmdFirstStage(self,conn,event):
        """Build the reply to complete the request"""
        fromjid = event.getFrom().getStripped().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
        if channel == '':
            if self.transport.users.has_key(fromjid) \
              and self.transport.users[fromjid].has_key(server):
                # TODO: RULES must become pending event, so it can go back to the right resource
                self.transport.users[fromjid][server].ruleshash = ''
                self.transport.users[fromjid][server].send_raw('RULES')
                reply = event.buildReply('result')
                form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
                reply.addChild(name='command',namespace=NS_COMMANDS,attrs={'node':event.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
                self._owner.send(reply)
                raise NodeProcessed
            else:
                self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
                raise NodeProcessed
        else:
            self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise NodeProcessed
