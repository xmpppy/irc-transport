#!/usr/bin/python
# $Id$
version = 'CVS ' + '$Revision$'.split()[1]
#
# xmpp->IRC transport
# Jan 2004 Copyright (c) Mike Albon
# 2006 Copyright (c) Norman Rasmussen
#
# This program is free software licensed with the GNU Public License Version 2.
# For a full copy of the license please go here http://www.gnu.org/licenses/licenses.html#GPL


## Unicode Notes
#
# All data between irc and jabber must be translated to and from the connection character set.
#
# All internal datastructures are held in UTF8 unicode objects.

import xmpp, urllib2, sys, time, irclib, re, ConfigParser, os, platform, select, codecs, shelve, socket
from xmpp.protocol import *
from xmpp.features import *
from xmpp.browser import *
from xmpp.commands import *
from jep0133 import *
import xmpp.commands
import jep0133
from xmpp.jep0106 import *
import traceback
import config, xmlconfig, signal

#Global definitions
VERSTR = 'IRC Transport'
socketlist = {}
#each item is a tuple of 4 values, 0 == frequency in seconds, 1 == offset from 0, 2 == function, 3 == arguments
timerlist = []

MALFORMED_JID=ErrorNode(ERR_JID_MALFORMED,text='Invalid room, must be in form #room%server')
NODE_REGISTERED_SERVERS='registered-servers'
NODE_ONLINE_SERVERS='online-servers'
NODE_ONLINE_CHANNELS='online-channels'
NODE_ACTIVE_CHANNELS='active-channels'
# This is the list of charsets that python supports.  Detecting this list at runtime is really difficult, so it's hardcoded here.
charsets = ['','ascii','big5','big5hkscs','cp037','cp424','cp437','cp500','cp737','cp775','cp850','cp852','cp855','cp856','cp857','cp860','cp861','cp862','cp863','cp864','cp865','cp866','cp869','cp874','cp875','cp932','cp949','cp950','cp1006','cp1026','cp1140','cp1250','cp1251','cp1252','cp1253','cp1254','cp1255','cp1256','cp1257','cp1258','euc-jp','euc-jis-2004','euc-jisx0213','euc-kr','gb2312','gbk','gb18030','hz','iso2022-jp','iso2022-jp-1','iso2022-jp-2','iso2022-jp-2004','iso2022-jp-3','iso2022-jp-ext','iso2022-kr','latin-1','iso8859-1','iso8859-2','iso8859-3','iso8859-4','iso8859-5','iso8859-6','iso8859-7','iso8859-8','iso8859-9','iso8859-10','iso8859-13','iso8859-14','iso8859-15','johab','koi8-r','koi8-u','mac-cyrillic','mac-greek','mac-iceland','mac-latin2','mac-roman','mac-turkish','ptcp154','shift-jis','shift-jis-2004','shift-jisx0213','utf-16','utf-16-be','utf-16-le','utf-7','utf-8']
irccolour = ['#FFFFFF','#000000','#0000FF','#00FF00','#FF0000','#F08000','#8000FF','#FFF000','#FFFF00','#80FF00','#00FF80','#00FFFF','#0080FF','#FF80FF','#808080','#A0A0A0']

def colourparse(str,charset):
    # Each tuple consists of String, foreground, background, bold.
    #str = str.replace('/','//')
    foreground=None
    background=None
    bold=None
    underline = None
    s = ''
    html=[]
    hs = ''
    ctrseq=None
    ctrfor=None #Has forground been processed?
    for e in str:
        if e == '\x00':
            pass #'Black'
        elif e == '\x01':
            pass #'Blue' CtCP Code
        elif e == '\x02':#'Green' Also Bold
            html.append((hs,foreground,background,bold,underline))
            if bold == True:
                bold = None
            else:
                bold = True
            hs = ''
        elif e == '\x03':#'Cyan' Also Colour
            html.append((hs,foreground,background,bold,underline))
            foreground = None
            #background = None
            if not ctrseq:
                ctrseq = True
            hs = ''
        elif e == '\x04':
            print 'Red'
        elif e == '\x05':
            print 'Purple'
        elif e == '\x06':
            print 'Brown'
        elif e == '\x07':
            print "Light Grey"
        elif e == '\x08':
            print 'Grey'
        elif e == '\x09':
            print 'Light Blue'
        elif e == '\x0a':
            print 'Light Green'
        elif e == '\x0b':
            print 'Light Cyan'
        elif e == '\x0c':
            print 'Light Red'
        elif e == '\x0d':
            print 'Pink'
        elif e == '\x0e':
            print 'Yellow'
        elif e == '\x0f':
            #go back to normal
            html.append((hs,foreground,background,bold,underline))
            foreground = None
            background = None
            bold = None
            underline = None
            hs = ''
            #print 'White'
        elif e == '\x1f':
            html.append((hs,foreground,background,bold,underline))
            if bold == True:
                bold = None
            else:
                bold = True
            hs = ''
        elif e in ['\x10', '\x11', '\x12', '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1d', '\x1e']:
            print 'Other Escape'
        elif ctrseq == True:
            if e.isdigit():
                if not ctrfor:
                    try:
                        if not foreground.len() <2:
                            foreground = foreground +e
                        else:
                            ctrseq=None
                            foreground = int(foreground)
                            s = '%s%s'%(s,e)
                            hs = '%s%s'%(hs,e)
                    except AttributeError:
                        foreground = e
                else:
                    try:
                        if background.len() <=2:
                            foreground = foreground +e
                        else:
                            ctrseq=None
                            ctrfor=None
                            background = int(background)
                            s = '%s%s'%(s,e)
                            hs= '%s%s'%(hs,e)
                    except AttributeError:
                        background = e
            elif e == ',':
                ctrfor=True
                background = None
            else:
                ctrfor = None
                ctrseq = None
                s = '%s%s'%(s,e)
                hs = '%s%s'%(hs,e)
        else:
            s = '%s%s'%(s,e)
            hs = '%s%s'%(hs,e)
    html.append((hs,foreground,background,bold,underline))
    chtml = []
    try:
        s = unicode(s,'utf8','strict') # Language detection stuff should go here.
        for each in html:
            chtml.append((unicode(each[0],'utf-8','strict'),each[1],each[2],each[3],each[4]))
    except:
        s = unicode(s, charset,'replace')
        for each in html:
            chtml.append((unicode(each[0],charset,'replace'),each[1],each[2],each[3],each[4]))
    if len(chtml) >1:
        html = Node('html')
        html.setNamespace('http://jabber.org/protocol/xhtml-im')
        xhtml = html.addChild('body',namespace='http://www.w3.org/1999/xhtml')
        #print chtml
        for each in chtml:
            style = ''
            if each[1] != None and int(each[1])<16:
                foreground = irccolour[int(each[1])]
                print foreground
                style = '%scolor:%s;'%(style,foreground)
            if each[2] != None and int(each[2])<16:
                background = irccolour[int(each[2])]
                style = '%sbackground-color:%s;'%(style,background)
            if each[3]:
                style = '%sfont-weight:bold;'%style
            if each[4]:
                style = '%stext-decoration:underline;'%style
            if each[0] != '':
                if style == '':
                    xhtml.addData(each[0])
                else:
                    xhtml.addChild(name = 'span', attrs = {'style':style},payload=each[0])
    else:
        html = ''
    return s,html

_xlat = {91: u'{', 92: u'|', 93: u'}', 94: u'~'}
def irc_ulower(str):
    if str is None: return str
    if len(str) == 0: return str
    return str.translate(_xlat).lower()

class Connect_Registered_Users_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the """
    name = "connect-users"
    description = 'Connect all registered users'
    discofeatures = [xmpp.commands.NS_COMMANDS]

    def __init__(self,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
        self.initial = { 'execute':self.cmdFirstStage }

    def _DiscoHandler(self,conn,request,type):
        """The handler for discovery events"""
        if request.getFrom().getStripped() in config.admins:
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,request,type)
        else:
            return None

    def cmdFirstStage(self,conn,request):
        """Build the reply to complete the request"""
        if request.getFrom().getStripped() in config.admins:
            for each in userfile.keys():
                connection.send(Presence(to=each, frm = config.jid, typ = 'probe'))
                if userfile[each].has_key('servers'):
                    for server in userfile[each]['servers']:
                        connection.send(Presence(to=each, frm = '%s@%s'%(server,config.jid), typ = 'probe'))
            reply = request.buildReply('result')
            form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
            reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
            self._owner.send(reply)
        else:
            self._owner.send(Error(request,ERR_FORBIDDEN))
        raise NodeProcessed

class Connect_Server_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the connect server command"""
    name = 'connect-server'
    description = 'Connect to server'
    discofeatures = [xmpp.commands.NS_COMMANDS]

    def __init__(self,transport,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
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
        if channel == '':
            if self.transport.irc_connect('',server,'','',frm,Presence()):
                self.transport.xmpp_presence_do_update(Presence(),server,frm.getStripped())
                reply = event.buildReply('result')
                form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
                reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':event.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
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

    def __init__(self,transport,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
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
        if channel == '':
            if self.transport.irc_disconnect('',server,frm,None):
                self.transport.xmpp_presence_do_update(None,server,frm.getStripped())
                reply = event.buildReply('result')
                form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
                reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':event.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
                self._owner.send(reply)
                raise NodeProcessed
            else:
                self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
                raise NodeProcessed
        else:
            self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise NodeProcessed

class Message_Of_The_Day(xmpp.commands.Command_Handler_Prototype):
    """This is the message of the day server command"""
    name = 'motd'
    description = 'Retrieve Message of the Day'
    discofeatures = [xmpp.commands.NS_COMMANDS]

    def __init__(self,transport,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
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
        if channel == '':
            if self.transport.users.has_key(fromjid) \
              and self.transport.users[fromjid].has_key(server):
                # TODO: MOTD must become pending event, so it can go back to the right resource
                self.transport.users[fromjid][server].motdhash = ''
                self.transport.users[fromjid][server].motd()
                reply = event.buildReply('result')
                form = DataForm(typ='result',data=[DataField(value='Command completed.',typ='fixed')])
                reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':event.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
                self._owner.send(reply)
                raise NodeProcessed
            else:
                self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
                raise NodeProcessed
        else:
            self._owner.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise NodeProcessed

class Transport:
    # This class is the main collection of where all the handlers for both the IRC and Jabber

    #Global structures
    users = {}
    online = 1
    restart = 0
    offlinemsg = ''

    # This structure consists of each user of the transport having their own location of store.
    # users         - hash          - key is barejid, value is a hash:
    #                   - hash        - key is server alias, value is irc connection object, with:
    #   server              - string
    #   address             - string
    #   fromjid             - string
    #   joinchan            - string
    #   joinresource        - string
    #   xresources          - hash      - key is resource, value is tuple of: show, priority, status, login time
    #   channels            - hash      - key is channel name, value is channel object:
    #       private             - bool
    #       secret              - bool
    #       invite              - bool
    #       topic               - bool
    #       notmember           - bool
    #       moderated           - bool
    #       banlist             - list
    #       limit               - number
    #       key                 - string
    #       currenttopic        - string
    #       members             - hash      - key is nick of member, value is hash, key is 'affiliation', 'role', 'jid', 'nick'
    #       resources           - hash      - key is resource, value is tuple of: show, priority, status, login time
    #   pendingoperations   - hash      - key is internal name of operation, joined with nick if applicable, value is xmpp message #TODO: make value into a list
    #   activechats         - hash      - key is nick, value is list of: irc jid, xmpp jid, last message time, capabilities
    #   charset             - string

    # Parameter order. Connection then options.

    def __init__(self,jabber,irc):
        self.jabber = jabber
        self.irc = irc

    def register_handlers(self):
        self.irc.add_global_handler('motd',self.irc_motd)
        self.irc.add_global_handler('motdstart',self.irc_motdstart)
        self.irc.add_global_handler('endofmotd',self.irc_endofmotd)
        self.irc.add_global_handler('pubmsg',self.irc_message)
        self.irc.add_global_handler('pubnotice',self.irc_message)
        self.irc.add_global_handler('privmsg',self.irc_message)
        self.irc.add_global_handler('privnotice',self.irc_message)
        self.irc.add_global_handler('468',self.irc_message)
        self.irc.add_global_handler('whoreply',self.irc_whoreply)
        self.irc.add_global_handler('ctcp',self.irc_ctcp)
        self.irc.add_global_handler('ctcpreply',self.irc_ctcpreply)
        self.irc.add_global_handler('nick',self.irc_nick)
        self.irc.add_global_handler('join',self.irc_join)
        self.irc.add_global_handler('part',self.irc_part)
        self.irc.add_global_handler('quit',self.irc_quit)
        self.irc.add_global_handler('kick',self.irc_kick)
        self.irc.add_global_handler('mode',self.irc_mode)
        self.irc.add_global_handler('channelmodeis',self.irc_channelmodeis)
        self.irc.add_global_handler('error',self.irc_error)
        self.irc.add_global_handler('topic',self.irc_topic)
        self.irc.add_global_handler('away',self.irc_away)
        self.irc.add_global_handler('nowaway',self.irc_nowaway)
        self.irc.add_global_handler('unaway',self.irc_unaway)
        self.irc.add_global_handler('nicknameinuse',self.irc_nicknameinuse)
        self.irc.add_global_handler('nosuchchannel',self.irc_nosuchchannel)
        self.irc.add_global_handler('nosuchnick',self.irc_nosuchnick)
        self.irc.add_global_handler('notregistered',self.irc_notregistered)
        self.irc.add_global_handler('cannotsendtochan',self.irc_cannotsend)
        self.irc.add_global_handler('nochanmodes',self.irc_notregistered)
        self.irc.add_global_handler('379',self.irc_redirect)
        self.irc.add_global_handler('featurelist',self.irc_featurelist)
        self.irc.add_global_handler('ison',self.irc_ison)
        self.irc.add_global_handler('welcome',self.irc_welcome)
        self.irc.add_global_handler('600',self.irc_watchonline)
        self.irc.add_global_handler('604',self.irc_watchonline)
        self.irc.add_global_handler('601',self.irc_watchoffline)
        self.irc.add_global_handler('605',self.irc_watchoffline)
        self.irc.add_global_handler('whoisuser',self.irc_whoisuser)
        self.irc.add_global_handler('whoisserver',self.irc_whoisserver)
        self.irc.add_global_handler('whoisoperator',self.irc_whoisoperator)
        self.irc.add_global_handler('whoisidle',self.irc_whoisidle)
        self.irc.add_global_handler('whoischannels',self.irc_whoischannels)
        self.irc.add_global_handler('endofwhois',self.irc_endofwhois)
        self.irc.add_global_handler('list',self.irc_list)
        self.irc.add_global_handler('listend',self.irc_listend)
        self.jabber.RegisterHandler('message',self.xmpp_message)
        self.jabber.RegisterHandler('presence',self.xmpp_presence)
        #Disco stuff now done by disco object
        self.jabber.RegisterHandler('iq',self.xmpp_iq_version,typ = 'get', ns=NS_VERSION)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_agents,typ = 'get', ns=NS_AGENTS)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_browse,typ = 'get', ns=NS_BROWSE)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucadmin_set,typ = 'set', ns=NS_MUC_ADMIN)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucadmin_get,typ = 'get', ns=NS_MUC_ADMIN)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucowner_set,typ = 'set', ns=NS_MUC_OWNER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucowner_get,typ = 'get', ns=NS_MUC_OWNER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_register_set,typ = 'set', ns=NS_REGISTER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_register_get,typ = 'get', ns=NS_REGISTER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_vcard,typ = 'get', ns=NS_VCARD)
        self.disco = Browser()
        self.disco.PlugIn(self.jabber)
        self.command = Commands(self.disco)
        self.command.PlugIn(self.jabber)
        self.cmdconnectusers = Connect_Registered_Users_Command(jid=config.jid)
        self.cmdconnectusers.plugin(self.command)
        self.cmdonlineusers = Online_Users_Command(self.users,jid=config.jid)
        self.cmdonlineusers.plugin(self.command)
        self.cmdactiveusers = Active_Users_Command(self.users,jid=config.jid)
        self.cmdactiveusers.plugin(self.command)
        self.cmdregisteredusers = Registered_Users_Command(userfile,jid=config.jid)
        self.cmdregisteredusers.plugin(self.command)
        self.cmdeditadminusers = Edit_Admin_List_Command(jid=config.jid)
        self.cmdeditadminusers.plugin(self.command)
        self.cmdrestartservice = Restart_Service_Command(self,jid=config.jid)
        self.cmdrestartservice.plugin(self.command)
        self.cmdshutdownservice = Shutdown_Service_Command(self,jid=config.jid)
        self.cmdshutdownservice.plugin(self.command)
        self.cmdconnectserver = Connect_Server_Command(self,jid='')
        self.cmdconnectserver.plugin(self.command)
        self.cmddisconnectserver = Disconnect_Server_Command(self,jid='')
        self.cmddisconnectserver.plugin(self.command)
        self.cmdmessageoftheday = Message_Of_The_Day(self,jid='')
        self.cmdmessageoftheday.plugin(self.command)
        self.disco.setDiscoHandler(self.xmpp_base_disco,node='',jid=config.jid)
        self.disco.setDiscoHandler(self.xmpp_base_disco,node='',jid='')

    # New Disco Handlers
    def xmpp_base_disco(self, con, event, type):
        fromjid = event.getFrom().getStripped().__str__()
        fromstripped = event.getFrom().getStripped().encode('utf8')
        to = event.getTo()
        node = event.getQuerynode();
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        #Type is either 'info' or 'items'
        if to == config.jid:
            if node == None:
                if type == 'info':
                    return {
                        'ids':[
                            {'category':'conference','type':'irc','name':VERSTR},
                            {'category':'gateway','type':'irc','name':VERSTR}],
                        'features':[NS_REGISTER,NS_VERSION,NS_MUC,NS_COMMANDS]}
                if type == 'items':
                    return [
                        {'node':NS_COMMANDS,'name':config.discoName + ' Commands','jid':config.jid},
                        {'node':NODE_REGISTERED_SERVERS,'name':config.discoName + ' Registered Servers','jid':config.jid},
                        {'node':NODE_ONLINE_SERVERS,'name':config.discoName + ' Online Servers','jid':config.jid}]
            elif node == NODE_REGISTERED_SERVERS:
                if type == 'info':
                    return {'ids':[],'features':[]}
                if type == 'items':
                    list = []
                    servers = []
                    if userfile.has_key(fromstripped):
                        if userfile[fromstripped].has_key('servers'):
                            servers = userfile[fromstripped]['servers']
                    for each in servers:
                        list.append({'name':each,'jid':'%s@%s' % (each, config.jid)})
                    return list
            elif node == NODE_ONLINE_SERVERS:
                if type == 'info':
                    return {'ids':[],'features':[]}
                if type == 'items':
                    list = []
                    if self.users.has_key(fromjid):
                        for each in self.users[fromjid].keys():
                            list.append({'name':each,'jid':'%s@%s' % (each, config.jid)})
                    return list
            else:
                self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
                raise NodeProcessed
        elif channel == '':
            if node == None:
                if type == 'info':
                    return {
                        'ids':[
                            {'category':'conference','type':'irc','name':server},
                            {'category':'gateway','type':'irc','name':server}],
                        'features':[NS_REGISTER,NS_VERSION,NS_MUC,NS_COMMANDS]}
                if type == 'items':
                    list = [{'node':NS_COMMANDS,'name':'%s Commands'%server,'jid':'%s@%s' % (server, config.jid)}]
                    if self.users.has_key(fromjid):
                        if self.users[fromjid].has_key(server):
                            list.append({'node':NODE_ONLINE_CHANNELS,'name':'%s Online Channels'%server,'jid':'%s@%s' % (server, config.jid)})
                            list.append({'node':NODE_ACTIVE_CHANNELS,'name':'%s Active Channels'%server,'jid':'%s@%s' % (server, config.jid)})
                    return list
            elif node == NODE_ONLINE_CHANNELS:
                if self.users.has_key(fromjid):
                    if self.users[fromjid].has_key(server):
                        if type == 'info':
                            return {'ids':[],'features':[]}
                        if type == 'items':
                            rep=event.buildReply('result')
                            rep.setQuerynode(node)
                            q=rep.getTag('query')
                            conn = self.users[fromjid][server]
                            conn.pendingoperations["list"] = rep
                            conn.list()
                            raise NodeProcessed
                self.jabber.send(Error(event,ERR_REGISTRATION_REQUIRED))
                raise NodeProcessed
            elif node == NODE_ACTIVE_CHANNELS:
                if self.users.has_key(fromjid):
                    if self.users[fromjid].has_key(server):
                        if type == 'info':
                            return {'ids':[],'features':[]}
                        if type == 'items':
                            list = []
                            if self.users.has_key(fromjid):
                                if self.users[fromjid].has_key(server):
                                    for each in self.users[fromjid][server].channels.keys():
                                        list.append({'name':each,'jid':'%s%%%s@%s' % (JIDEncode(each), server, config.jid)})
                            return list
                self.jabber.send(Error(event,ERR_REGISTRATION_REQUIRED))
                raise NodeProcessed
            else:
                self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
                raise NodeProcessed
        elif irclib.is_channel(channel):
            if self.users.has_key(fromjid):
                if self.users[fromjid].has_key(server):
                    if type == 'info':
                        return {'ids':[{'category':'conference','type':'irc','name':channel}],'features':[NS_MUC]}
                    if type == 'items':
                        return []
            self.jabber.send(Error(event,ERR_REGISTRATION_REQUIRED))
            raise NodeProcessed
        else:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise NodeProcessed

    #XMPP Handlers
    def xmpp_presence(self, con, event):
        # Add ACL support
        fromjid = event.getFrom()
        fromstripped = fromjid.getStripped().encode('utf8')
        type = event.getType()
        #if type == None: type = 'available'
        to = event.getTo()
        status = event.getStatus()
        room = irc_ulower(to.getNode())
        nick = to.getResource()
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        x = event.getTag(name='x', namespace=NS_MUC)
        try:
            password = x.getTagData('password')
        except AttributeError:
            password = None
        if to == config.jid or channel == '':
            conf = None
            if userfile.has_key(fromstripped):
                if to == config.jid:
                    conf = userfile[fromstripped]
                elif server and userfile[fromstripped].has_key('servers') and userfile[fromstripped]['servers'].has_key(server):
                    conf = userfile[fromstripped]['servers'][server]
            if not conf:
                if type != 'unsubscribed' and type != 'error':
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribe'))
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribed'))
                    if type != 'unsubscribe':
                        self.jabber.send(Error(event,ERR_BAD_REQUEST))
                return
            if type == 'subscribe':
                self.jabber.send(Presence(to=fromjid, frm = to, typ = 'subscribe'))
                conf['usubscribed']=True
            elif type == 'subscribed':
                self.jabber.send(Presence(to=fromjid, frm = to, typ = 'subscribed'))
                conf['subscribed']=True
            elif type == 'unsubscribe':
                self.jabber.send(Presence(to=fromjid, frm = to, typ = 'unsubscribe'))
                conf['usubscribed']=False
            elif type == 'unsubscribed':
                self.jabber.send(Presence(to=fromjid, frm = to, typ = 'unsubscribed'))
                conf['subscribed']=False
            #
            #Add code so people can see transport presence here
            #
            elif type == 'probe':
                self.jabber.send(Presence(to=fromjid, frm = to))
            elif type == 'error':
                return
            elif type == 'unavailable':
                #call self.irc_disconnect to disconnect from the server
                #when you see the user's presence become unavailable
                if server:
                    print 'disconnect %s'%repr(server)
                    self.irc_disconnect('',server,fromjid,status)
                    self.xmpp_presence_do_update(event,server,fromstripped)
                else:
                    self.jabber.send(Presence(to=fromjid, frm = to, typ = 'unavailable'))
                    print 'disconnect all'
                    if self.users.has_key(fromjid.getStripped()):
                        for each in self.users[fromjid.getStripped()].keys():
                            self.irc_disconnect('',each,fromjid,status)
            else:
                #call self.irc_connect to connect to the server
                #when you see the user's presence become available
                if server:
                    print 'connect %s'%repr(server)
                    self.irc_connect('',server,nick,password,fromjid,event)
                    self.xmpp_presence_do_update(event,server,fromstripped)
                else:
                    if not self.users.has_key(fromjid.getStripped()):
                        self.users[fromjid.getStripped()] = {}
                    self.jabber.send(Presence(to=fromjid, frm = to))
            if userfile.has_key(fromstripped):
                if to == config.jid:
                    userfile[fromstripped] = conf
                else:
                    user = userfile[fromstripped]
                    user['servers'][server] = conf
                    userfile[fromstripped] = user
                userfile.sync()
        elif irclib.is_channel(channel):
            if type == None:
                if nick != '':
                    self.irc_connect(channel,server,nick,password,fromjid,event)
                    self.xmpp_presence_do_update(event,server,fromstripped)
            elif type == 'unavailable':
                self.irc_disconnect(channel,server,fromjid,status)
                self.xmpp_presence_do_update(event,server,fromstripped)
            else:
                self.jabber.send(Error(event,ERR_FEATURE_NOT_IMPLEMENTED))
        else:
            nick = channel
            conf = None
            if server and userfile.has_key(fromstripped) and userfile[fromstripped].has_key('servers') and userfile[fromstripped]['servers'].has_key(server):
                conf = userfile[fromstripped]['servers'][server]
            if not conf:
                if type != 'unsubscribed' and type != 'error':
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribe'))
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribed'))
                    if type != 'unsubscribe':
                        self.jabber.send(Error(event,ERR_BAD_REQUEST))
                return
            subscriptions = []
            if conf.has_key('subscriptions'):
                subscriptions = conf['subscriptions']

            if type == 'subscribe':
                self.jabber.send(Presence(to=fromjid, frm = to, typ = 'subscribed'))
                if not nick in subscriptions:
                    subscriptions.append(nick)
                    if self.users.has_key(fromjid.getStripped()) \
                      and self.users[fromjid.getStripped()].has_key(server) \
                      and self.users[fromjid.getStripped()][server].features.has_key('WATCH'):
                        self.users[fromjid.getStripped()][server].send_raw('WATCH +%s' % nick)
            elif type == 'unsubscribe' or type == 'unsubscribed':
                self.jabber.send(Presence(to=fromjid, frm = to, typ = 'unsubscribed'))
                if nick in subscriptions:
                    subscriptions.remove(nick)
                    if self.users.has_key(fromjid.getStripped()) \
                      and self.users[fromjid.getStripped()].has_key(server) \
                      and self.users[fromjid.getStripped()][server].features.has_key('WATCH'):
                        self.users[fromjid.getStripped()][server].send_raw('WATCH -%s' % nick)

            conf['subscriptions'] = subscriptions
            user = userfile[fromstripped]
            user['servers'][server] = conf
            userfile[fromstripped] = user
            userfile.sync()

            if (type == 'subscribe' or type == 'unsubscribe' or type == 'unsubscribed') \
              and self.users.has_key(fromjid.getStripped()) \
              and self.users[fromjid.getStripped()].has_key(server):
                if not self.users[fromjid.getStripped()][server].features.has_key('WATCH'):
                    self.irc_doison(self.users[fromjid.getStripped()][server])

    def xmpp_presence_do_update(self,event,server,fromjid):
        if fromjid not in self.users.keys() or \
            server not in self.users[fromjid].keys():
            return
        conn = self.users[fromjid][server]
        resources = []
        for resource in conn.xresources.keys():
            resources.append((resource,conn.xresources[resource]))
        for channel in conn.channels.keys():
            for resource in conn.channels[channel].resources.keys():
                resources.append((resource,conn.channels[channel].resources[resource]))

        age = None
        priority = None
        resource = None
        for each in resources:
            if each[1][1]>priority:
                #if priority is higher then take the highest
                age = each[1][3]
                priority = each[1][1]
                resource = each[0]
            elif each[1][1]==priority:
                #if priority is the same then take the oldest
                if each[1][3]<age:
                    age = each[1][3]
                    priority = each[1][1]
                    resource = each[0]

        if event and event.getFrom() and resource == event.getFrom().getResource():
            #only update shown status if resource is current datasource
            if event.getShow() == None:
                if conn.away != '':
                    conn.away = ''
                    conn.send_raw('AWAY')
            elif event.getShow() == 'xa' or event.getShow() == 'away' or event.getShow() == 'dnd':
                show = 'Away'
                if event.getStatus():
                    show = event.getStatus()
                if conn.away != show:
                    conn.away = show
                    conn.send_raw('AWAY :%s'%show)

    def xmpp_message(self, con, event):
        type = event.getType()
        fromjid = event.getFrom().getStripped().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            if event.getSubject.strip() == '':
                event.setSubject(None)
        except AttributeError:
            pass
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        if not self.users.has_key(fromjid):
            self.jabber.send(Error(event,ERR_REGISTRATION_REQUIRED))         # another candidate: ERR_SUBSCRIPTION_REQUIRED
            return
        if not self.users[fromjid].has_key(server):
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))        # Another candidate: ERR_REMOTE_SERVER_NOT_FOUND (but it means that server doesn't exist at all)
            return
        conn = self.users[fromjid][server]
        if channel and not irclib.is_channel(channel):
            nick = channel
        else:
            nick = to.getResource()
        if event.getBody() == None:
            xevent = event.getTag('x',namespace=NS_EVENT)
            if xevent and conn.activechats.has_key(irc_ulower(nick)):
                chat = conn.activechats[irc_ulower(nick)]
                if 'x:event' in chat[3]:
                    states=[]
                    for state in xevent.getChildren():
                        states.append(state.getName())
                    self.irc_sendctcp('X:EVENT',conn,nick,','.join(states))
            return
        if type == 'groupchat':
            print "Groupchat"
            if irclib.is_channel(channel):
                print "channel:", event.getBody().encode('utf8')
                if event.getSubject():
                    print "subject"
                    if conn.channels[channel].topic:
                        print "topic"
                        if conn.channels[channel].members[conn.nickname]['role'] == 'moderator':
                            print "set topic ok"
                            self.irc_settopic(conn,channel,event.getSubject())
                        else:
                            print "set topic forbidden"
                            self.jabber.send(Error(event,ERR_FORBIDDEN))
                    else:
                        print "anyone can set topic"
                        self.irc_settopic(conn,channel,event.getSubject())
                elif event.getBody() != '':
                    print "body isn't empty:" , event.getBody().encode('utf8')
                    if event.getBody()[0:3] == '/me':
                        print "action"
                        self.irc_sendctcp('ACTION',conn,channel,event.getBody()[4:])
                    else:
                        print "room message"
                        self.irc_sendroom(conn,channel,event.getBody())
                    for resource in conn.channels[channel].resources.keys():
                        t = Message(to='%s/%s'%(fromjid,resource),body=event.getBody(),typ=type,frm='%s@%s/%s' %(room, config.jid,conn.nickname))
                        self.jabber.send(t)
            else:
                self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))  # or MALFORMED_JID maybe?
        elif type in ['chat', None]:
            if nick:
                if conn.activechats.has_key(irc_ulower(nick)):
                    conn.activechats[irc_ulower(nick)] = [to,event.getFrom(),time.time(),conn.activechats[irc_ulower(nick)][3]]
                else:
                    conn.activechats[irc_ulower(nick)] = [to,event.getFrom(),time.time(),{}]
                    if len(room.split('%',1)) > 1:
                        self.irc_sendctcp('CAPABILITIES',conn,nick,'')
                if event.getBody()[0:3] == '/me':
                    self.irc_sendctcp('ACTION',conn,nick,event.getBody()[4:])
                else:
                    self.irc_sendroom(conn,nick,event.getBody())
            else:
                self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))

    def xmpp_iq_vcard(self, con, event):
        fromjid = event.getFrom().getStripped()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        # need to store this ID somewhere for the return trip
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        if not self.users.has_key(fromjid):
            self.jabber.send(Error(event,ERR_REGISTRATION_REQUIRED))         # another candidate: ERR_SUBSCRIPTION_REQUIRED
            raise xmpp.NodeProcessed
        if not self.users[fromjid].has_key(server):
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))        # Another candidate: ERR_REMOTE_SERVER_NOT_FOUND (but it means that server doesn't exist at all)
            raise xmpp.NodeProcessed
        conn = self.users[fromjid][server]
        nick = None
        if channel and not irclib.is_channel(channel):
            # ARGH! need to know channel to find out nick. :(
            nick = channel
        else:
            nick = to.getResource()

        m = Iq(to=event.getFrom(),frm=to, typ='result')
        m.setID(id)
        p = m.addChild(name='vCard', namespace=NS_VCARD)
        p.setTagData(tag='DESC', val='Additional Information:')

        conn.pendingoperations["whois:" + irc_ulower(nick)] = m
        conn.whois([(nick + ' ' + nick).encode(conn.charset)])

        raise xmpp.NodeProcessed

    def xmpp_iq_agents(self, con, event):
        m = Iq(to=event.getFrom(), frm=event.getTo(), typ='result', payload=[Node('agent', attrs={'jid':config.jid},payload=[Node('service',payload='irc'),Node('name',payload=config.discoName),Node('groupchat')])])
        m.setID(event.getID())
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_browse(self, con, event):
        m = event.buildReply('result')
        if event.getTo() == config.jid:
            m.setTagAttr('query','catagory','conference')
            m.setTagAttr('query','name',config.discoName)
            m.setTagAttr('query','type','irc')
            m.setTagAttr('query','jid','config.jid')
            m.setPayload([Node('ns',payload=NS_MUC),Node('ns',payload=NS_REGISTER)])
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_version(self, con, event):
        # TODO: maybe real version requests via irc? - or maybe via ad hoc?
        fromjid = event.getFrom()
        to = event.getTo()
        id = event.getID()
        uname = platform.uname()
        m = Iq(to = fromjid, frm = to, typ = 'result', queryNS=NS_VERSION, payload=[Node('name',payload=VERSTR), Node('version',payload=version),Node('os',payload=('%s %s %s' % (uname[0],uname[2],uname[4])).strip())])
        m.setID(id)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_mucadmin_get(self, con, event):
        fromjid = event.getFrom().getStripped()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise xmpp.NodeProcessed
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].channels.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise xmpp.NodeProcessed
        conn = self.users[fromjid][server]
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if t[0].getName() == 'item':
            attr = t[0].getAttrs()
            if 'role' in attr.keys():
                role = attr['role']
                affiliation = None
            elif 'affiliation' in attr.keys():
                affiliation = attr['affiliation']
                role = None
        m = Iq(to=event.getFrom(), frm=to, typ='result', queryNS=ns)
        m.setID(id)
        payload = []
        for each in conn.channels[channel].members:
            if role != None:
                if conn.channels[channel].members[each]['role']  == role:
                    zattr = conn.channels[channel].members[each]
                    zattr['nick'] = each
                    payload.append(Node('item',attrs = zattr))
            if affiliation != None:
                if conn.channels[channel].members[each]['affiliation']  == affiliation:
                    zattr = conn.channels[channel].members[each]
                    zattr['nick'] = each
                    payload.append(Node('item',attrs = zattr))
        m.setQueryPayload(payload)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_mucadmin_set(self, con, event):
        fromjid = event.getFrom().getStripped()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise xmpp.NodeProcessed
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].channels.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise xmpp.NodeProcessed
        conn = self.users[fromjid][server]
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if conn.nickname not in conn.channels[channel].members.keys() \
          or conn.channels[channel].members[conn.nickname]['role'] != 'moderator' \
          or conn.channels[channel].members[conn.nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            raise xmpp.NodeProcessed
        for each in t:
            if t[0].getName() == 'item':
                attr = t[0].getAttrs()
                if attr.has_key('role'):
                    if attr['role'] == 'moderator':
                        conn.mode(channel,'%s %s'%('+o',attr['nick']))
                        raise xmpp.NodeProcessed
                    elif attr['role'] == 'participant':
                        conn.mode(channel,'%s %s'%('+v',attr['nick']))
                        raise xmpp.NodeProcessed
                    elif attr['role'] == 'visitor':
                        conn.mode(channel,'%s %s'%('-v',attr['nick']))
                        conn.mode(channel,'%s %s'%('-o',attr['nick']))
                        raise xmpp.NodeProcessed
                    elif attr['role'] == 'none':
                        conn.kick(channel,attr['nick'],'Kicked')#Need to add reason gathering
                        raise xmpp.NodeProcessed
                if attr.has_key('affiliation'):
                    nick, room = attr['jid'].split('%',1)
                    if attr['affiliation'] == 'member':
                        conn.mode(channel,'%s %s'%('+v',nick))
                        raise xmpp.NodeProcessed
                    elif attr['affiliation'] == 'none':
                        conn.mode(channel,'%s %s'%('-v',nick))
                        conn.mode(channel,'%s %s'%('-o',nick))
                        raise xmpp.NodeProcessed

    def xmpp_iq_mucowner_get(self, con, event):
        fromjid = event.getFrom().getStripped()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise xmpp.NodeProcessed
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].channels.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise xmpp.NodeProcessed
        conn = self.users[fromjid][server]
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if conn.nickname not in conn.channels[channel].members.keys() \
          or conn.channels[channel].members[conn.nickname]['role'] != 'moderator' \
          or conn.channels[channel].members[conn.nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            raise xmpp.NodeProcessed

        chan = conn.channels[channel]
        datafrm = DataForm(typ='form',data=[
            DataField(desc='Private'                        ,name='private'     ,value=chan.private     ,typ='boolean'),
            DataField(desc='Secret'                         ,name='secret'      ,value=chan.secret      ,typ='boolean'),
            DataField(desc='Invite Only'                    ,name='invite'      ,value=chan.invite      ,typ='boolean'),
            DataField(desc='Only ops can change the Topic'  ,name='topic'       ,value=chan.topic       ,typ='boolean'),
            DataField(desc='No external channel messages'   ,name='notmember'   ,value=chan.notmember   ,typ='boolean'),
            DataField(desc='Moderated Channel'              ,name='moderated'   ,value=chan.moderated   ,typ='boolean'),
            DataField(desc='Ban List'                       ,name='banlist'     ,value=chan.banlist     ,typ='text-multi'),
            DataField(desc='Channel Limit'                  ,name='limit'       ,value=chan.limit       ,typ='text-single'),
            DataField(desc='Channel Key'                    ,name='key'         ,value=chan.key         ,typ='text-single')])
        datafrm.setInstructions('Configure the room')

        m = Iq(frm = to, to = event.getFrom(), typ='result', queryNS=ns)
        m.setID(id)
        m.setQueryPayload([datafrm])
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_mucowner_set(self, con, event):
        fromjid = event.getFrom().getStripped()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise xmpp.NodeProcessed
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].channels.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise xmpp.NodeProcessed
        conn = self.users[fromjid][server]
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if conn.nickname not in conn.channels[channel].members.keys() \
          or conn.channels[channel].members[conn.nickname]['role'] != 'moderator' \
          or conn.channels[channel].members[conn.nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            raise xmpp.NodeProcessed
        for each in t:
            datafrm = DataForm(node=each).asDict()
            for each in datafrm.keys():
                print '%s:%s'%(repr(each),repr(datafrm[each]))
                fieldValue = False
                if type(datafrm[each]) in [type(''),type(u'')] and (datafrm[each] == '1' or datafrm[each].lower() == 'true'):
                    fieldValue = True
                handled = False
                if fieldValue:
                    typ='+'
                else:
                    typ='-'
                if each == 'private':
                    cmd = 'p'
                elif each == 'secret':
                    cmd = 's'
                elif each == 'invite':
                    cmd = 'i'
                elif each == 'topic':
                    cmd = 't'
                elif each == 'notmember':
                    cmd = 'n'
                elif each == 'moderated':
                    cmd = 'm'
                elif each == 'banlist':
                    handled = True
                    for item in datafrm[each]:
                        if item not in conn.channels[channel].banlist:
                            conn.mode(channel,'+b %s' % item)
                    for item in conn.channels[channel].banlist:
                        if item not in datafrm[each]:
                            conn.mode(channel,'-b %s' % item)
                elif each == 'limit':
                    fieldValue = datafrm[each]
                    if datafrm[each]:
                        typ='+'
                        cmd='l %s' % datafrm[each]
                    else:
                        typ='-'
                        cmd='l'
                elif each == 'key':
                    fieldValue = datafrm[each]
                    if datafrm[each]:
                        typ='+'
                        cmd='k %s' % datafrm[each]
                    else:
                        typ='-'
                        cmd='k %s' % conn.channels[channel].key
                if not handled and fieldValue != getattr(conn.channels[channel], each):
                    conn.mode(channel,'%s%s' % (typ,cmd))
        m = Iq(frm = to, to = event.getFrom(), typ='result', queryNS=ns)
        m.setID(id)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    # Registration code
    def xmpp_iq_register_get(self, con, event):
        charset = config.charset
        fromjid = event.getFrom().getStripped().encode('utf8')
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        if not channel == '':
            self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
            raise xmpp.NodeProcessed

        serverdetails = {'address':'','nick':'','password':'','realname':'','username':''}
        if userfile.has_key(fromjid):
            charset = userfile[fromjid]['charset']
            if not server == '' and userfile[fromjid].has_key('servers'):
                servers = userfile[fromjid]['servers']
                if servers.has_key(server):
                    serverdetails = servers[server]
                    charset = serverdetails['charset']

        m = event.buildReply('result')
        m.setQueryNS(NS_REGISTER)
        if server:
            nametype='hidden'
        else:
            nametype='text-single'
        form = DataForm(typ='form',data=[
            DataField(desc='Character set'                          ,name='charset' ,value=charset                  ,typ='list-single',options=charsets),
            DataField(desc='Server alias used for jids'             ,name='alias'   ,value=server                   ,typ=nametype),
            DataField(desc='Server to connect to'                   ,name='address' ,value=serverdetails['address'] ,typ='text-single'),
            DataField(desc='Familiar name of the user'              ,name='nick'    ,value=serverdetails['nick']    ,typ='text-single'),
            DataField(desc='Password or secret for the user'        ,name='password',value=serverdetails['password'],typ='text-private'),
            DataField(desc='Full name of the user'                  ,name='name'    ,value=serverdetails['realname'],typ='text-single'),
            DataField(desc='Account name associated with the user'  ,name='username',value=serverdetails['username'],typ='text-single')])
        form.setInstructions('Please provide your legacy Character set or charset. (eg cp437, cp1250, iso-8859-1, koi8-r)')
        m.setQueryPayload([
            Node('instructions', payload = 'Please provide your legacy Character set or charset. (eg cp437, cp1250, iso-8859-1, koi8-r)'),
            Node('charset'  ,payload=charset),
            Node('address'  ,payload=serverdetails['address']),
            Node('nick'     ,payload=serverdetails['nick']),
            Node('password' ,payload=serverdetails['password']),
            Node('name'     ,payload=serverdetails['realname']),
            Node('username' ,payload=serverdetails['username']),
            form])
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_register_set(self, con, event):
        remove = False

        fromjid = event.getFrom().getStripped().encode('utf8')
        ucharset = config.charset
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        if not channel == '':
            self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
            raise xmpp.NodeProcessed
        serverdetails = {}

        query = event.getTag('query')
        if query.getTag('remove'):
            remove = True
        elif query.getTag(name='x',namespace=NS_DATA):
            form = DataForm(node=query.getTag(name='x',namespace=NS_DATA))
            if form.getField('charset'):
                ucharset = form.getField('charset').getValue()
            else:
                self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
                raise xmpp.NodeProcessed
            if form.getField('address'):
                if not server and form.getField('alias'):
                    server = form.getField('alias').getValue()
                if not server:
                    server = form.getField('address').getValue().split(':',1)[0]
                serverdetails['address'] = form.getField('address').getValue()
                serverdetails['charset'] = ucharset
                if form.getField('nick'):
                    serverdetails['nick'] = form.getField('nick').getValue()
                if form.getField('password'):
                    serverdetails['password'] = form.getField('password').getValue()
                if form.getField('name'):
                    serverdetails['realname'] = form.getField('name').getValue()
                if form.getField('username'):
                    serverdetails['username'] = form.getField('username').getValue()
        elif query.getTag('charset'):
            ucharset = query.getTagData('charset')
            if query.getTag('address'):
                if not server:
                    server = query.getTagData('address').split(':',1)[0]
                serverdetails['address'] = query.getTagData('address')
                serverdetails['charset'] = ucharset
                if query.getTag('nick'):
                    serverdetails['nick'] = query.getTagData('nick')
                if query.getTag('password'):
                    serverdetails['password'] = query.getTagData('password')
                if query.getTag('name'):
                    serverdetails['realname'] = query.getTagData('name')
                if query.getTag('username'):
                    serverdetails['username'] = query.getTagData('username')
        else:
            self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
            raise xmpp.NodeProcessed

        if not remove:
            if userfile.has_key(fromjid):
                conf = userfile[fromjid]
            else:
                conf = {}
            try:
                codecs.lookup(ucharset)
            except LookupError:
                self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
                raise xmpp.NodeProcessed
            except ValueError:
                self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
                raise xmpp.NodeProcessed
            if server == '':
                conf['charset']=ucharset
                if not conf.has_key('subscribed'):
                    self.jabber.send(Presence(typ='subscribe',to=fromjid, frm=to))
            else:
                servers = {}
                if conf.has_key('servers'):
                    servers = conf['servers']
                if irc_ulower(to.getNode()) == '' and servers.has_key(server):
                    self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
                    raise xmpp.NodeProcessed
                if not serverdetails.has_key('nick') or serverdetails['nick'] == '':
                    self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
                    raise xmpp.NodeProcessed
                if not conf.has_key('charset'):
                    conf['charset']=ucharset
                if not serverdetails.has_key('subscribed'):
                    self.jabber.send(Presence(typ='subscribe',to=fromjid, frm='%s@%s'%(server,config.jid)))
                servers[server] = serverdetails
                conf['servers'] = servers

            userfile[fromjid]=conf
            self.jabber.send(Presence(to=event.getFrom(), frm = to))
            self.jabber.send(event.buildReply('result'))
        else:
            if userfile.has_key(fromjid):
                conf = userfile[fromjid]
            else:
                conf = {}
            if server == '':
                if conf.has_key('servers'):
                    servers = conf['servers']
                    for server in servers:
                        m = Presence(to = fromjid, frm = '%s@%s'%(server,config.jid), typ = 'unsubscribe')
                        self.jabber.send(m)
                        m = Presence(to = fromjid, frm = '%s@%s'%(server,config.jid), typ = 'unsubscribed')
                        self.jabber.send(m)
                if userfile.has_key(fromjid):
                    del userfile[fromjid]
            else:
                servers = {}
                if conf.has_key('servers'):
                    servers = conf['servers']
                if not servers.has_key(server):
                    self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
                    raise xmpp.NodeProcessed
                del servers[server]
                conf['servers'] = servers
                userfile[fromjid]=conf

            m = Presence(to = fromjid, frm = to, typ = 'unsubscribe')
            self.jabber.send(m)
            m = Presence(to = fromjid, frm = to, typ = 'unsubscribed')
            self.jabber.send(m)
            self.jabber.send(event.buildReply('result'))
        userfile.sync()
        raise xmpp.NodeProcessed

    #IRC methods
    def irc_doquit(self,conn,message=None):
        server = conn.server
        nickname = conn.nickname
        if conn.isontimer in timerlist:
            timerlist.remove(conn.isontimer)
        if self.jabber.isConnected():
            fromstripped = conn.fromjid.encode('utf8')
            if userfile.has_key(fromstripped) \
              and userfile[fromstripped].has_key('servers') \
              and userfile[fromstripped]['servers'].has_key(conn.server):
                conf = userfile[fromstripped]['servers'][conn.server]
                if conf.has_key('subscriptions'):
                    subscriptions = conf['subscriptions']
                    for nick in subscriptions:
                        self.jabber.send(Presence(to=conn.fromjid, frm = '%s%%%s@%s' % (nick, conn.server, config.jid), typ = 'unavailable'))
            self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' % (conn.server, config.jid), typ = 'unavailable'))
        if self.users[conn.fromjid].has_key(server):
            del self.users[conn.fromjid][server]
            try:
                conn.quit(message)
            except:
                pass
            conn.close()

    def irc_testinuse(self,conn,message=None):
        inuse = False
        for each in self.users[conn.fromjid].keys():
            if self.users[conn.fromjid][each].channels != {}:
                inuse = True
        fromstripped = JID(conn.fromjid).getStripped().encode('utf8')
        if userfile.has_key(fromstripped) and userfile[fromstripped].has_key('servers') and userfile[fromstripped]['servers'].has_key(conn.server):
            inuse = True
        if inuse == False:
            self.irc_doquit(conn,message)

    def irc_settopic(self,conn,channel,line):
        try:
            conn.topic(channel.encode(conn.charset),line.encode(conn.charset))
        except:
            self.irc_doquit(conn)

    def irc_sendnick(self,conn,nick):
        try:
            conn.nick(nick)
        except:
            self.irc_doquit(conn)

    def irc_sendroom(self,conn,channel,line):
        lines = line.split('\x0a')
        for each in lines:
            #print channel, each
            if each != '' or each == None:
               try:
                    conn.privmsg(channel.encode(conn.charset),each.encode(conn.charset))
               except:
                    self.irc_doquit(conn)

    def irc_sendctcp(self,type,conn,channel,line):
        lines = line.split('\x0a')
        for each in lines:
            #print channel, each
            try:
                conn.ctcp(type,channel.encode(conn.charset),each.encode(conn.charset))
            except:
                self.irc_doquit(conn)

    def irc_connect(self,channel,server,nick,password,frm,event):
        fromjid = frm.getStripped().__str__()
        resource = frm.getResource()
        if not self.users.has_key(fromjid): # if a new user session
            self.users[fromjid] = {}
        if self.users[fromjid].has_key(server):
            conn = self.users[fromjid][server]
            if channel:
                if channel == '': return None
                if conn.nickname != nick and nick != '':
                    conn.joinchan = channel
                    conn.joinresource = resource
                    self.irc_sendnick(conn,nick)
                if not conn.channels.has_key(channel):
                    # it's a new channel, just join it
                    self.irc_newroom(conn,channel,resource)
                    conn.channels[channel].resources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),time.time())
                    print "New channel login: %s" % conn.channels[channel].resources
                else:
                    if conn.channels[channel].resources.has_key(resource):
                        #update resource record
                        conn.channels[channel].resources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),conn.channels[channel].resources[resource][3])
                        print "Update channel resource login: %s" % conn.channels[channel].resources
                    else:
                        #new resource login
                        conn.channels[channel].resources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),time.time())
                        print "New channel resource login: %s" % conn.channels[channel].resources
                        # resource is joining an existing resource on the same channel
                        # TODO: Send topic to new resource
                        # TODO: Alert existing resources that a new resource has joined
                        name = '%s%%%s@%s' % (channel, server, config.jid)
                        for cnick in conn.channels[channel].members.keys():
                            if cnick == conn.nickname:
                                #print 'nnick %s %s %s'%(name,cnick,nick)
                                m = Presence(to=conn.fromjid,frm='%s/%s' %(name, nick))
                            else:
                                #print 'cnick %s %s %s'%(name,cnick,nick)
                                m = Presence(to=conn.fromjid,frm='%s/%s' %(name, cnick))
                            t=m.addChild(name='x',namespace=NS_MUC_USER)
                            p=t.addChild(name='item',attrs=conn.channels[channel].members[cnick])
                            self.jabber.send(m)
                return 1
            else:
                if conn.xresources.has_key(resource):
                    #update resource record
                    conn.xresources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),conn.xresources[resource][3])
                    print "Update server resource login: %s" % conn.xresources
                else:
                    #new resource login
                    conn.xresources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),time.time())
                    print "New server resource login: %s" % conn.xresources
                    self.jabber.send(Presence(to=frm, frm='%s@%s' % (server, config.jid)))
                    if conn.features.has_key('WATCH'):
                        conn.send_raw('WATCH')
                    else:
                        self.irc_doison(conn)
        else: # the other cases
            conn=self.irc_newconn(channel,server,nick,password,frm)
            if conn != None:
                conn.xresources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),time.time())
                self.users[fromjid][server] = conn
                return 1
            else:
                return None

    def irc_newconn(self,channel,server,nick,password,frm):

        fromjid = frm.getStripped().__str__()
        fromstripped = frm.getStripped().encode('utf8')
        resource = frm.getResource()

        address = server
        username = realname = nick
        ucharset = config.charset
        motdhash = ''
        if userfile.has_key(fromstripped):
            ucharset = userfile[fromstripped]['charset']
            if userfile[fromstripped].has_key('servers'):
                servers = userfile[fromstripped]['servers']
                if servers.has_key(server):
                    serverdetails = servers[server]
                    ucharset = serverdetails['charset']
                    if serverdetails['address']:
                        address = serverdetails['address']
                    if not nick:
                        nick = serverdetails['nick']
                    if not password:
                        password = serverdetails['password']
                    if serverdetails['username']:
                        username = serverdetails['username']
                    if serverdetails['realname']:
                        realname = serverdetails['realname']
                    if serverdetails.has_key('motdhash'):
                        motdhash = serverdetails['motdhash']

        if not nick:
            return None

        try:
            addressdetails = address.split(':')
            if len(addressdetails) > 2: addressdetails = address.split('/') #probably ipv6, so split on /
            if len(addressdetails) > 2:
                return None
            port = 6667
            if len(addressdetails) > 1:
                port = int(addressdetails[1]);
            address = addressdetails[0];
            conn=self.irc.server().connect(address,port,nick,password,username,realname,config.host)
            conn.server = server
            conn.address = address
            conn.fromjid = fromjid
            conn.features = {}
            conn.joinchan = channel
            conn.joinresource = resource
            conn.xresources = {}
            conn.channels = {}
            conn.pendingoperations = {}
            conn.activechats = {}
            conn.away = ''
            conn.charset = ucharset
            conn.connectstatus = 'Connecting: '
            conn.isonlist = []
            conn.isontimer = None
            conn.motdhash = motdhash
            self.jabber.send(Presence(to=frm, frm = '%s@%s' % (server, config.jid), status='Connecting...'))
            return conn
        except irclib.ServerConnectionError:
            self.jabber.send(Error(Presence(to = frm, frm = '%s%%%s@%s/%s' % (channel,server,config.jid,nick)),ERR_SERVICE_UNAVAILABLE,reply=0))  # Other candidates: ERR_GONE, ERR_REMOTE_SERVER_NOT_FOUND, ERR_REMOTE_SERVER_TIMEOUT
            return None

    def irc_newroom(self,conn,channel,resource):
        try:
           conn.join(channel)
           conn.who(channel)
           conn.mode(channel,'')
        except:
           self.irc_doquit(conn)
        class Channel:
            pass

        chan = Channel()
        chan.private = False
        chan.secret = False
        chan.invite = False
        chan.topic = False
        chan.notmember = False
        chan.moderated = False
        chan.banlist = []
        chan.limit = 0
        chan.key = ''
        chan.currenttopic = ''
        chan.members = {}   # irc nicks in the channel
        chan.resources = {}

        conn.channels[channel] = chan

    def irc_disconnect(self,channel,server,frm,message):
        fromjid = frm.getStripped().__str__()
        resource = frm.getResource()
        if self.users.has_key(fromjid):
            if self.users[fromjid].has_key(server):
                conn = self.users[fromjid][server]
                for nick in conn.activechats.keys():
                    # TODO: remove any activechats with this resource, or with this room
                    # irc jid, xmpp jid, last message time
                    pass
                if channel:
                    if conn.channels.has_key(channel):
                        if conn.channels[channel].resources.has_key(resource):
                            del conn.channels[channel].resources[resource]
                        print "Deleted channel resource login: %s" % conn.channels[channel].resources
                        if conn.channels[channel].resources == {}:
                            self.irc_leaveroom(conn,channel)
                            del conn.channels[channel]
                            self.irc_testinuse(conn,message)
                        return 1
                else:
                    if conn.xresources.has_key(resource):
                        del conn.xresources[resource]
                    print "Deleted server resource login: %s" % conn.xresources
                    if conn.xresources == {}:
                        print 'No more resource logins'
                        self.irc_doquit(conn,message)
                    return 1
        return None

    def find_highest_resource(self,resources):
        age = None
        priority = None
        resource = None
        for each in resources.keys():
            #print each,resources
            if resources[each][1]>priority:
                #if priority is higher then take the highest
                age = resources[each][3]
                priority = resources[each][1]
                resource = each
            elif resources[each][1]==priority:
                #if priority is the same then take the oldest
                if resources[each][3]<age:
                    age = resources[each][3]
                    priority = resources[each][1]
                    resource = each
        return resource

    def irc_leaveroom(self,conn,channel):
        try:
           conn.part([channel.encode(conn.charset)])
        except:
            self.irc_doquit(conn)

    # IRC message handlers
    def irc_error(self,conn,event):
        if conn.server in self.users[conn.fromjid].keys():
            try:
                for each in conn.channels.keys():
                    t = Presence(to=conn.fromjid, typ = 'unavailable', frm='%s%%%s@%s' %(each,conn.server,config.jid))
                    self.jabber.send(t)
                del self.users[conn.fromjid][conn.server]
            except AttributeError:
                pass

    def irc_quit(self,conn,event):
        type = 'unavailable'
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        for channel in conn.channels.keys():
            if nick in conn.channels[channel].members.keys():
                del conn.channels[channel].members[nick]
                name = '%s%%%s' % (channel, conn.server)
                m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, config.jid,nick))
                self.jabber.send(m)
                if config.activityMessages == True:
                    line,xhtml = colourparse(event.arguments()[0],conn.charset)
                    m = Message(to=conn.fromjid, typ='groupchat',frm='%s@%s' % (name, config.jid), body='%s (%s) has quit (%s)' % (nick, unicode(irclib.nm_to_uh(event.source()),conn.charset,'replace'), line))
                    self.jabber.send(m)

    def irc_nick(self, conn, event):
        old = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        new = unicode(event.target(),conn.charset,'replace')
        if old == conn.nickname:
            conn.nickname = new
        for channel in conn.channels.keys():
            if old in conn.channels[channel].members.keys():
                m = Presence(to=conn.fromjid,typ = 'unavailable',frm = '%s%%%s@%s/%s' % (channel,conn.server,config.jid,old))
                p = m.addChild(name='x', namespace=NS_MUC_USER)
                p.addChild(name='item', attrs={'nick':new})
                p.addChild(name='status', attrs={'code':'303'})
                self.jabber.send(m)
                m = Presence(to=conn.fromjid,typ = None, frm = '%s%%%s@%s/%s' % (channel,conn.server,config.jid,new))
                t = m.addChild(name='x',namespace=NS_MUC_USER)
                p = t.addChild(name='item',attrs=conn.channels[channel].members[old])
                self.jabber.send(m)
                t=conn.channels[channel].members[old]
                del conn.channels[channel].members[old]
                conn.channels[channel].members[new] = t
                if config.activityMessages == True:
                    for resource in conn.channels[channel].resources.keys():
                        m = Message(to='%s/%s'%(conn.fromjid,resource), typ='groupchat',frm='%s%%%s@%s' % (channel,conn.server,config.jid), body='%s is now known as %s' % (old, new))
                        self.jabber.send(m)


    def irc_featurelist(self,conn,event):
        for feature in event.arguments():
            if feature != 'are supported by this server':
                try:
                    key,value = feature.split('=',1)
                except ValueError:
                    key = feature
                    value = None
                conn.features[key] = value
        #print 'features:%s'%repr(conn.features)

        fromstripped = conn.fromjid.encode('utf8')
        if userfile[fromstripped].has_key('servers') \
          and userfile[fromstripped]['servers'].has_key(conn.server):
            conf = userfile[fromstripped]['servers'][conn.server]
            if conf.has_key('subscriptions'):
                subscriptions = conf['subscriptions']
                if conn.features.has_key('WATCH'):
                    if conn.isontimer in timerlist:
                        timerlist.remove(conn.isontimer)
                        for nick in subscriptions:
                            conn.send_raw('WATCH +%s' % nick)

    def irc_doison(self,conn):
        fromstripped = conn.fromjid.encode('utf8')
        if userfile[fromstripped].has_key('servers') \
          and userfile[fromstripped]['servers'].has_key(conn.server):
            conf = userfile[fromstripped]['servers'][conn.server]
            if conf.has_key('subscriptions'):
                subscriptions = conf['subscriptions']
                if not conn.features.has_key('WATCH'):
                    if len(subscriptions) > 0:
                        conn.ison(subscriptions)
                    else:
                        for nick in conn.isonlist:
                            name = '%s%%%s' % (nick, conn.server)
                            self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(name, config.jid), typ = 'unavailable'))
                        conn.isonlist = []

    def irc_ison(self,conn,event):
        newlist = event.arguments()[0].split()
        for nick in newlist:
            if not nick in conn.isonlist:
                name = '%s%%%s' % (nick, conn.server)
                self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(name, config.jid)))
        for nick in conn.isonlist:
            if not nick in newlist:
                name = '%s%%%s' % (nick, conn.server)
                self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(name, config.jid), typ = 'unavailable'))
        conn.isonlist = newlist

    def irc_watchonline(self,conn,event):
        # TODO: store contact status for when new resource comes online
        #  or, do we spam a watch list?
        nick = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        name = '%s%%%s' % (nick, conn.server)
        self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(name, config.jid)))

    def irc_watchoffline(self,conn,event):
        # TODO: store contact status for when new resource comes online
        #  or, do we spam a watch list?
        nick = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        name = '%s%%%s' % (nick, conn.server)
        self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(name, config.jid), typ = 'unavailable'))

    def irc_welcome(self,conn,event):
        conn.connectstatus = None
        self.jabber.send(Presence(to = conn.fromjid, frm = '%s@%s' %(conn.server,config.jid)))

        freq = 90 # ison query frequency in seconds
        offset = int(time.time())%freq
        conn.isontimer=(freq,offset,self.irc_doison,[conn])
        timerlist.append(conn.isontimer)

        if conn.joinchan != '':
            self.irc_newroom(conn,conn.joinchan,conn.joinresource)
        #TODO: channel join operations should become pending operations
        #       so that they can be tracked correctly
        #       and so that we can send errors to the right place
        del conn.joinchan
        del conn.joinresource

    def irc_nicknameinuse(self,conn,event):
        if conn.joinchan:
            name = '%s%%%s' % (conn.joinchan, conn.server)
        else:
            name = conn.server
        if conn.joinresource:
            to = '%s/%s'%(conn.fromjid,conn.joinresource)
        else:
            to = conn.fromjid
        error=ErrorNode(ERR_CONFLICT,text='Nickname is in use')
        self.jabber.send(Presence(to=to, typ = 'error', frm = '%s@%s' %(name, config.jid),payload=[error]))

    def irc_nosuchchannel(self,conn,event):
        error=ErrorNode(ERR_ITEM_NOT_FOUND,'The channel is not found')
        self.jabber.send(Presence(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' %(unicode(event.arguments()[0],conn.charset,'replace'), conn.server, config.jid),payload=[error]))

    def irc_notregistered(self,conn,event):
        if conn.joinchan:
            name = '%s%%%s' % (conn.joinchan, conn.server)
        else:
            name = conn.server
        if conn.joinresource:
            to = '%s/%s'%(conn.fromjid,conn.joinresource)
        else:
            to = conn.fromjid
        error=ErrorNode(ERR_FORBIDDEN,text='Not registered and registration is not supported')
        self.jabber.send(Presence(to=to, typ = 'error', frm = '%s@%s' %(name, config.jid),payload=[error]))

    def irc_nosuchnick(self, conn, event):
        error=ErrorNode(ERR_ITEM_NOT_FOUND,text='Nickname not found')
        #TODO: resource handling?
        self.jabber.send(Message(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' % (event.source(), conn.server, config.jid),payload=[error]))

    def irc_cannotsend(self,conn,event):
        error=ErrorNode(ERR_FORBIDDEN)
        #TODO: resource handling?
        self.jabber.send(Message(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' % (event.source(), conn.server, config.jid),payload=[error]))

    def irc_redirect(self,conn,event):
        new = '%s%%%s@%s'% (unicode(event.arguments()[1],conn.charset,'replace'),conn.server, config.jid)
        old = '%s%%%s@%s'% (unicode(event.arguments()[0],conn.charset,'replace'),conn.server, config.jid)
        error=ErrorNode(ERR_REDIRECT,new)
        self.jabber.send(Presence(to=conn.fromjid, typ='error', frm = old, payload=[error]))
        del conn.channels[unicode(event.arguments()[1],conn.charset,'replace')]
        try:
           conn.part(event.arguments()[1])
        except:
           self.irc_doquit(conn)

    def irc_modeparseadmin(self,conn,event):
    # Mode handling currently is very poor.
    #
    # Issues:
    # Multiple +b's currently not handled
    # +l or -l with no parameter not handled
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        faddr = '%s%%%s@%s' %(channel,conn.server,config.jid)
        if irclib.is_channel(event.target()):
            if event.arguments()[0] == '+o':
                # Give Chanop
                if channel in conn.channels.keys():
                    for each in event.arguments()[1:]:
                        nick = unicode(each,conn.charset,'replace')
                        conn.channels[channel].members[nick]['role']='moderator'
                        if each == conn.nickname:
                            conn.channels[channel].members[nick]['affiliation']='owner'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,nick))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.channels[channel].members[nick])
                        self.jabber.send(m)
            elif event.arguments()[0] in ['-o', '-v']:
                # Take Chanop or Voice
                if channel in conn.channels.keys():
                    for each in event.arguments()[1:]:
                        nick = unicode(each,conn.charset,'replace')
                        conn.channels[channel].members[nick]['role']='visitor'
                        conn.channels[channel].members[nick]['affiliation']='none'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,nick))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.channels[channel].members[nick])
                        self.jabber.send(m)
            elif event.arguments()[0] == '+v':
                # Give Voice
                if channel in conn.channels.keys():
                    for each in event.arguments()[1:]:
                        nick = unicode(each,conn.charset,'replace')
                        conn.channels[channel].members[nick]['role']='participant'
                        conn.channels[channel].members[nick]['affiliation']='none'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,nick))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.channels[channel].members[nick])
                        self.jabber.send(m)

    def irc_channelmodeis(self,conn,event):
        channel = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        self.irc_modeparse(conn,event,channel,event.arguments()[1:])

    def irc_mode(self,conn,event):
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        self.irc_modeparse(conn,event,channel,event.arguments())

    def irc_modeparse(self,conn,event,channel,args):
        # Very buggy, multiple items cases, ban etc.
        plus = None
        for each in args[0]:
            if each == '+':
                plus = True
            elif each == '-':
                plus = False
            elif each == 'o': #Chanop status
                self.irc_modeparseadmin(conn,event)
            elif each == 'v': #Voice status
                self.irc_modeparseadmin(conn,event)
            elif each == 'p': #Private Room
                conn.channels[channel].private = plus
            elif each == 's': #Secret
                conn.channels[channel].secret = plus
            elif each == 'i': #invite only
                conn.channels[channel].invite = plus
            elif each == 't': #only chanop can set topic
                conn.channels[channel].topic = plus
            elif each == 'n': #no not in channel messages
                conn.channels[channel].notmember = plus
            elif each == 'm': #moderated chanel
                conn.channels[channel].moderated = plus
            elif each == 'l': #set channel limit
                if plus:
                    conn.channels[channel].limit = args[1]
                else:
                    conn.channels[channel].limit = 0
            elif each == 'b': #ban users
                # TODO: maybe move to irc_modeparseadmin
                #       handle as outcasts, would need to map @ to %
                # Need to fix multiple ban case.
                for each in args[1:]:
                    if plus:
                        conn.channels[channel].banlist.append(unicode(each,conn.charset,'replace'))
                    else:
                        if unicode(each,conn.charset,'replace') in conn.channels[channel].banlist:
                            conn.channels[channel].banlist.remove(unicode(each,conn.charset,'replace'))
            elif each == 'k': #set channel key
                if plus:
                    conn.channels[channel].key = args[1]
                else:
                    conn.channels[channel].key = ''
                pass

    def irc_part(self,conn,event):
        type = 'unavailable'
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        name = '%s%%%s' % (channel, conn.server)
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        try:
            if nick in conn.channels[channel].members.keys():
                del conn.channels[channel].members[nick]
        except KeyError:
            pass
        if config.activityMessages == True and conn.channels.has_key(channel):
            for resource in conn.channels[channel].resources.keys():
                m = Message(to='%s/%s'%(conn.fromjid,resource), typ='groupchat',frm='%s@%s' % (name, config.jid), body='%s (%s) has left' % (nick, unicode(irclib.nm_to_uh(event.source()),conn.charset,'replace')))
                self.jabber.send(m)
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, config.jid,nick))
        self.jabber.send(m)

    def irc_kick(self,conn,event):
        type = 'unavailable'
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        name = '%s%%%s' % (channel, conn.server)
        jid = '%s%%%s@%s' % (irc_ulower(unicode(event.arguments()[0],conn.charset,'replace')), conn.server, config.jid)
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, config.jid,unicode(event.arguments()[0],conn.charset,'replace')))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs={'affiliation':'none','role':'none','jid':jid})
        p.addChild(name='reason',payload=[colourparse(event.arguments()[1],conn.charset)][0])
        t.addChild(name='status',attrs={'code':'307'})
        self.jabber.send(m)
        if event.arguments()[0] == conn.nickname:
            if conn.channels.has_key(channel):
                del conn.channels[channel].members
        self.irc_testinuse(conn)

    def irc_topic(self,conn,event):
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if len(event.arguments())==2:
            channel = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
            line,xhtml = colourparse(event.arguments()[1],conn.charset)
        else:
            channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
            line,xhtml = colourparse(event.arguments()[0],conn.charset)
        conn.channels[channel].currenttopic = line
        for resource in conn.channels[channel].resources.keys():
            m = Message(to='%s/%s'%(conn.fromjid,resource),frm = '%s%%%s@%s/%s' % (channel,conn.server,config.jid,nick), typ='groupchat', subject = line)
            if config.activityMessages == True:
                m.setBody('/me set the topic to: %s' % line)
            self.jabber.send(m)

    def irc_join(self,conn,event):
        type = None
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        name = '%s%%%s' % (channel, conn.server)
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        jid = '%s%%%s@%s' % (nick, conn.server, config.jid)
        if nick not in conn.channels[channel].members.keys():
            conn.channels[channel].members[nick]={'affiliation':'none','role':'visitor','jid':jid}
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, config.jid, nick))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs=conn.channels[channel].members[nick])
        #print m.__str__()
        self.jabber.send(m)
        if config.activityMessages == True:
            for resource in conn.channels[channel].resources.keys():
                m = Message(to='%s/%s'%(conn.fromjid,resource), typ='groupchat',frm='%s@%s' % (name, config.jid), body='%s (%s) has joined' % (nick, unicode(irclib.nm_to_uh(event.source()),conn.charset,'replace')))
                self.jabber.send(m)

    def irc_whoreply(self,conn,event):
        channel = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        nick = unicode(event.arguments()[4],conn.charset,'replace')
        faddr = '%s%%%s@%s/%s' % (channel, conn.server, config.jid, nick)
        m = Presence(to=conn.fromjid,typ=None,frm=faddr)
        t = m.addChild(name='x', namespace=NS_MUC_USER)
        affiliation = 'none'
        role = 'none'
        if '@' in event.arguments()[5]:
            role = 'moderator'
            if unicode(event.arguments()[4],conn.charset,'replace') == conn.nickname:
                affiliation='owner'
        elif '+' in event.arguments()[5]:
            role = 'participant'
        elif '*' in event.arguments()[5]:
            affiliation = 'admin'
        elif role == 'none':
            role = 'visitor'
        jid = '%s%%%s@%s' % (unicode(event.arguments()[4],conn.charset,'replace'), conn.server, config.jid)
        p=t.addChild(name='item',attrs={'affiliation':affiliation,'role':role,'jid':jid})
        self.jabber.send(m)
        try:
            if (event.arguments()[0] != '*') and (nick not in conn.channels[channel].members.keys()):
                conn.channels[channel].members[nick]={'affiliation':affiliation,'role':role,'jid':jid}
        except KeyError:
            pass

    def irc_whoisgetvcard(self,conn,event):
        nick = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        m = conn.pendingoperations["whois:" + nick]
        return m.getTag('vCard', namespace=NS_VCARD)

    def irc_whoisuser(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        p.setTagData(tag='FN', val=unicode(event.arguments()[4],conn.charset,'replace'))
        p.setTagData(tag='NICKNAME', val=unicode(event.arguments()[0],conn.charset,'replace'))
        e = p.addChild(name='EMAIL')
        e.setTagData(tag='USERID', val=unicode(event.arguments()[1],conn.charset,'replace') + '@' + unicode(event.arguments()[2],conn.charset,'replace'))

    def irc_whoisserver(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        o = p.addChild(name='ORG')
        o.setTagData(tag='ORGUNIT', val=unicode(event.arguments()[1],conn.charset,'replace'))
        o.setTagData(tag='ORGNAME', val=unicode(event.arguments()[2],conn.charset,'replace'))

    def irc_whoisoperator(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        p.setTagData(tag='ROLE', val=unicode(event.arguments()[1],conn.charset,'replace'))

    def irc_whoisidle(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        seconds = int(event.arguments()[1])
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        p.setTagData(tag='DESC', val=p.getTagData(tag='DESC') + '\x0a' + 'Idle: %s hours %s mins %s secs' % (hours, minutes, seconds))
        if len(event.arguments()) > 3:
            p.setTagData(tag='DESC', val=p.getTagData(tag='DESC') + '\x0a' + 'Signon Time: ' + time.ctime(float(event.arguments()[2])))

    def irc_whoischannels(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        p.setTagData(tag='TITLE', val=unicode(event.arguments()[1],conn.charset,'replace'))

    def irc_endofwhois(self,conn,event):
        nick = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        m = conn.pendingoperations["whois:" + nick]
        del conn.pendingoperations["whois:" + nick]
        self.jabber.send(m)

    def irc_list(self,conn,event):
        chan = event.arguments()[0]
        if irclib.is_channel(chan):
            chan = unicode(chan,conn.charset,'replace')
            rep = conn.pendingoperations["list"]
            q=rep.getTag('query')
            q.addChild('item',{'name':chan,'jid':'%s%%%s@%s' % (JIDEncode(chan), conn.server, config.jid)})

    def irc_listend(self,conn,event):
        rep = conn.pendingoperations["list"]
        del conn.pendingoperations["list"]
        self.jabber.send(rep)

    def irc_motdstart(self,conn,event):
        try:
            nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        except:
            nick = conn.server
        line,xhtml = colourparse(event.arguments()[0],conn.charset)
        if line[-3:] == ' - ': line = line[:-3]
        if line[:2] == '- ': line = line[2:]
        #TODO: resource handling? conn.joinresource? what about adhoc?
        m = Message(to=conn.fromjid,subject=line,typ='headline',frm='%s@%s/%s' %(conn.server, config.jid,nick))
        conn.pendingoperations["motd"] = m

    def irc_motd(self,conn,event):
        line,xhtml = colourparse(event.arguments()[0],conn.charset)
        if line[:2] == '- ': line = line[2:]
        m = conn.pendingoperations["motd"]
        if m.getBody():
            body = m.getBody() + '\x0a'
        else:
            body = ''
        m.setBody(body + line)

    def irc_endofmotd(self,conn,event):
        m = conn.pendingoperations["motd"]
        del conn.pendingoperations["motd"]
        #motdhash = md5.new(m.getBody()).hexdigest()
        #if motdhash != conn.motdhash:
        #  conn.motdhash = motdhash
        #  if userfile.has_key(conn.fromjid) \
        #    and userfile[conn.fromjid].has_key('servers') \
        #    and userfile[conn.fromjid]['servers'].has_key(conn.server):
        #      userfile[conn.fromjid]['servers'][conn.server]['motdhash'] = motdhash
        self.jabber.send(m)

    def nm_to_jidinfo(self,conn,nickmask):
        try:
            nick = unicode(irclib.nm_to_n(nickmask),conn.charset,'replace')
        except:
            nick = conn.server
        if conn.activechats.has_key(irc_ulower(nick)):
            chat = conn.activechats[irc_ulower(nick)] # irc jid, xmpp jid, last message time, capabilites
            if chat[2] + 300 > time.time():
                return chat[0],chat[1],chat[3]

            room = irc_ulower(chat[0].getNode())
            try:
                channel, server = room.split('%',1)
                channel = JIDDecode(channel)
            except ValueError:
                channel=''
                server=room

            if conn.channels.has_key(channel):
                resources = conn.channels[channel].resources
            else:
                resources = conn.xresources

            if resources != {}:
                return chat[0],'%s/%s'%(conn.fromjid,self.find_highest_resource(resources)),chat[3]
            else:
                return chat[0],conn.fromjid,chat[3]
        try:
            userhost = unicode(irclib.nm_to_uh(nickmask),conn.charset,'replace')
            try:
                host = unicode(irclib.nm_to_h(nickmask),conn.charset,'replace')
                serverprefix,serverdomain = conn.address.split('.', 1)
                #irc.zanet.net:     NickServ!services@zanet.net
                #irc.lagnet.org.za: NickServ!services@lagnet.org.za
                #irc.zanet.org.za:  NickServ!NickServ@zanet.org.za
                if host == '%s'%serverdomain: userhost=''
                #irc.oftc.net:      NickServ!services@services.oftc.net
                if host == 'services.%s'%serverdomain: userhost=''
                #irc.freenode.net:  NickServ!NickServ@services.
                if host == 'services.': userhost=''
            except:
                pass
        except:
            userhost = ''
        if userhost:
            frm = '%s%%%s@%s' %(nick,conn.server,config.jid)
        else:
            frm = '%s@%s/%s' %(conn.server,config.jid,nick)
        return frm,conn.fromjid,{}

    def irc_privmsg(self,conn,event,msg):
        if irclib.is_channel(event.target()):
            type = 'groupchat'
            channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
            line,xhtml = colourparse(msg,conn.charset)
            #print (line,xhtml)
            if conn.channels.has_key(channel):
                nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
                for resource in conn.channels[channel].resources.keys():
                    m = Message(to='%s/%s'%(conn.fromjid,resource),body= line,typ=type,frm='%s%%%s@%s/%s' %(channel,conn.server,config.jid,nick),payload = [xhtml])
                    self.jabber.send(m)
        else:
            type = 'chat'
            line,xhtml = colourparse(msg,conn.charset)
            frm,to,caps = self.nm_to_jidinfo(conn,event.source())
            # if we're still connecting then send server messages as presence information
            if conn.connectstatus != None and frm.find('/') > -1:
                if line[:4] == '*** ': line = line[4:]
                m = Presence(to=to,frm='%s@%s'%(conn.server,config.jid), status=conn.connectstatus + line)
            else:
                m = Message(to=to,body=line,typ=type,frm=frm,payload = [xhtml])
            if 'x:event' in caps:
                m.setTag('x',namespace=NS_EVENT).setTag('composing')
            self.jabber.send(m)

    def irc_message(self,conn,event):
        self.irc_privmsg(conn,event,event.arguments()[0])

    def irc_away(self,conn,event):
        # TODO: store a contacts away status? (or later broadcast with new resources)
        nick = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        name = '%s%%%s'%(nick,conn.server)
        line,xhtml = colourparse(event.arguments()[1],conn.charset)
        self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(name, config.jid), show='away', status=line))
        # TODO: poll (via whois?) away status of online contacts
        pass

    def irc_nowaway(self,conn,event):
        self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(conn.server, config.jid), show='away'))
        pass

    def irc_unaway(self,conn,event):
        self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(conn.server, config.jid)))
        pass

    def irc_ctcp(self,conn,event):
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if event.arguments()[0] == 'ACTION':
            self.irc_privmsg(conn,event,'/me '+event.arguments()[1])
        elif event.arguments()[0] == 'VERSION':
            conn.ctcp_reply(irclib.nm_to_n(event.source()).encode(conn.charset),'VERSION ' + VERSTR + ' ' + version)
        elif event.arguments()[0] == 'CAPABILITIES':
            conn.ctcp_reply(irclib.nm_to_n(event.source()).encode(conn.charset),'CAPABILITIES version,x:event')
        elif event.arguments()[0] == 'X:EVENT':
            frm,to,caps = self.nm_to_jidinfo(conn,event.source())
            m = Message(to=to,frm=frm)
            xevent = m.setTag('x',namespace=NS_EVENT)
            if len(event.arguments()) > 1:
                for each in event.arguments()[1].split(','):
                    xevent.setTag(each)
            self.jabber.send(m)

    def irc_ctcpreply(self,conn,event):
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if event.arguments()[0] == 'CAPABILITIES':
            if conn.activechats.has_key(irc_ulower(nick)):
                if len(event.arguments()) > 1:
                    caps = event.arguments()[1].split(',')
                    conn.activechats[irc_ulower(nick)][3] = caps
        elif event.arguments()[0] == 'VERSION':
            # TODO: real version reply back to the xmpp world?
            pass
        pass

    def xmpp_connect(self):
        connected = self.jabber.connect((config.mainServer,config.port))
        if connected == 'tcp':
            self.register_handlers()
            #print "try auth"
            connected = self.jabber.auth(config.saslUsername,config.secret)
            #print "auth return",connected
        return connected

    def xmpp_disconnect(self):
        for each in self.users.keys():
            for item in self.users[each].keys():
                self.irc_doquit(self.users[each][item])
            del self.users[each]
        del socketlist[self.jabber.Connection._sock]
        time.sleep(5)
        while not self.jabber.reconnectAndReauth():
            time.sleep(5)
        socketlist[self.jabber.Connection._sock]='xmpp'

def loadConfig():
    configOptions = {}
    for configFile in config.configFiles:
        if os.path.isfile(configFile):
            xmlconfig.reloadConfig(configFile, configOptions)
            config.configFile = configFile
            return
    print "Configuration file not found. You need to create a config file and put it in one of these locations:\n    " + "\n    ".join(configFiles)
    sys.exit(1)

def irc_add_conn(con):
    socketlist[con]='irc'

def irc_del_conn(con):
    if socketlist.has_key(con):
        del socketlist[con]

def logError():
    if logfile != None:
        logfile.write(time.strftime('%a %d %b %Y %H:%M:%S\n'))
        traceback.print_exc(file=logfile)
        logfile.flush()
    sys.stderr.write(time.strftime('%a %d %b %Y %H:%M:%S\n'))
    traceback.print_exc()

def sigHandler(signum, frame):
    #transport.offlinemsg = 'Signal handler called with signal %s'%signum
    transport.online = 0

if __name__ == '__main__':
    if 'PID' in os.environ:
        config.pid = os.environ['PID']
    loadConfig()
    if config.pid:
        pidfile = open(config.pid,'w')
        pidfile.write(`os.getpid()`)
        pidfile.close()

    if config.saslUsername:
        component = 1
    else:
        config.saslUsername = config.jid
        component = 0

    userfile = shelve.open(config.spoolFile)
    logfile = None
    if config.debugFile:
        logfile = open(config.debugFile,'a')

    ircobj = irclib.IRC(fn_to_add_socket=irc_add_conn,fn_to_remove_socket=irc_del_conn)
    connection = xmpp.client.Component(config.jid,config.port,component=component)
    transport = Transport(connection,ircobj)
    if not transport.xmpp_connect():
        print "Could not connect to server, or password mismatch!"
        sys.exit(1)
    # Set the signal handlers
    signal.signal(signal.SIGINT, sigHandler)
    signal.signal(signal.SIGTERM, sigHandler)
    socketlist[connection.Connection._sock]='xmpp'
    while transport.online:
        try:
            (i , o, e) = select.select(socketlist.keys(),[],[],1)
        except socket.error:
            for userkey in transport.users:
                user = transport.users[userkey]
                for serverkey, server in user.items():
                    if server._get_socket() == None:
                        print "disconnected by %s" % server.get_server_name()
                        transport.irc_doquit(server)
            for each in socketlist.keys():
                try:
                    (ci, co, ce) = select.select([],[],[each],0)
                except socket.error:
                    irc_del_conn(each)
            (i , o, e) = select.select(socketlist.keys(),[],[],1)
        for each in i:
            if socketlist[each] == 'xmpp':
                try:
                    connection.Process(1)
                except IOError:
                    transport.xmpp_disconnect()
                except:
                    logError()
                if not connection.isConnected(): transport.xmpp_disconnect(connection)
            elif socketlist[each] == 'irc':
                try:
                    ircobj.process_data([each])
                except:
                    logError()
            else:
                try:
                    raise Exception("Unknown socket type: %s" % repr(socketlist[each]))
                except:
                    logError()
        #delayed execution method modified from python-irclib written by Joel Rosdahl <joel@rosdahl.net>
        for each in timerlist:
            #print int(time.time())%each[0]-each[1]
            if not (int(time.time())%each[0]-each[1]):
                try:
                    apply(each[2],each[3])
                except:
                    logError()
    for each in transport.users.keys():
        for item in transport.users[each].keys():
            transport.irc_doquit(transport.users[each][item])
        connection.send(Presence(to=each, frm = config.jid, typ = 'unavailable', status = transport.offlinemsg))
        del transport.users[each]
    del socketlist[connection.Connection._sock]
    userfile.close()
    connection.disconnect()
    if config.pid:
        os.unlink(config.pid)
    if logfile:
        logfile.close()
    if transport.restart:
        args=[sys.executable]+sys.argv
        if os.name == 'nt':
            def quote(a): return "\"%s\"" % a
            args = map(quote, args)
        #print sys.executable, args
        os.execv(sys.executable, args)
