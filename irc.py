#!/usr/bin/python
# $Id$
version = 'CVS ' + '$Revision$'.split()[1]
#
# xmpp->IRC transport
# Jan 2004 Copyright (c) Mike Albon
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
import jep0106
from jep0106 import *
import traceback

#Global definitions
True = 1
False = 0
server = None
hostname = None
port = None
secret = None
localaddress = ""
connection = None
charset = 'utf-8'
socketlist = {}
timerlist = []

MALFORMED_JID=ErrorNode(ERR_JID_MALFORMED,text='Invalid room, must be in form #room%server')
NODE_REGISTERED_SERVERS='registered-servers'
NODE_ONLINE_SERVERS='online-servers'
NODE_ONLINE_CHANNELS='online-channels'
NODE_ACTIVE_CHANNELS='active-channels'
# This is the list of charsets that python supports.  Detecting this list at runtime is really difficult, so it's hardcoded here.
charsets = ['','ascii','big5','big5hkscs','cp037','cp424','cp437','cp500','cp737','cp775','cp850','cp852','cp855','cp856','cp857','cp860','cp861','cp862','cp863','cp864','cp865','cp866','cp869','cp874','cp875','cp932','cp949','cp950','cp1006','cp1026','cp1140','cp1250','cp1251','cp1252','cp1253','cp1254','cp1255','cp1256','cp1257','cp1258','euc_jp','euc_jis_2004','euc_jisx0213','euc_kr','gb2312','gbk','gb18030','hz','iso2022_jp','iso2022_jp_1','iso2022_jp_2','iso2022_jp_2004','iso2022_jp_3','iso2022_jp_ext','iso2022_kr','latin_1','iso8859_2','iso8859_3','iso8859_4','iso8859_5','iso8859_6','iso8859_7','iso8859_8','iso8859_9','iso8859_10','iso8859_13','iso8859_14','iso8859_15','johab','koi8_r','koi8_u','mac_cyrillic','mac_greek','mac_iceland','mac_latin2','mac_roman','mac_turkish','ptcp154','shift_jis','shift_jis_2004','shift_jisx0213','utf_16','utf_16_be','utf_16_le','utf_7','utf_8']
irccolour = ['#FFFFFF','#000000','#0000FF','#00FF00','#FF0000','#F08000','#8000FF','#FFF000','#FFFF00','#80FF00','#00FF80','#00FFFF','#0080FF','#FF80FF','#808080','#A0A0A0']
def irc_add_conn(con):
    socketlist[con]='irc'

def irc_del_conn(con):
    if socketlist.has_key(con):
        del socketlist[con]

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

def connectxmpp(handlerreg = None):
    connected = connection.connect((server,port))
    print connected
    if connected == 'tcp':
        if handlerreg != None:
            handlerreg()
        print "try auth"
        connected = connection.auth(hostname,secret)
        print "auth return",connected
        return connected
    while 1:
        time.sleep(5)
        xmpp.transports.TCPsocket((server,port)).PlugOut()
        connected=connection.reconnectAndReauth()
        if connected: break
    connection.UnregisterDisconnectHandler(connection.DisconnectHandler)
    return connected

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
        self.users = transport.users
        
    def _DiscoHandler(self,conn,event,type):
        """The handler for discovery events"""
        fromjid = event.getFrom().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        if not self.transport.users.has_key(fromjid) or not self.transport.users[fromjid].has_key(server):
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,event,type)
        else:
            return None

    def cmdFirstStage(self,conn,event):
        """Build the reply to complete the request"""
        frm = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        if channel == '':
            if self.transport.irc_connect('',server,'','',frm):
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
        self.users = transport.users
        
    def _DiscoHandler(self,conn,event,type):
        """The handler for discovery events"""
        fromjid = event.getFrom().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        if self.transport.users.has_key(fromjid) and self.transport.users[fromjid].has_key(server):
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,event,type)
        else:
            return None
        
    def cmdFirstStage(self,conn,event):
        """Build the reply to complete the request"""
        frm = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        if channel == '':
            if self.transport.irc_disconnect('',server,'',frm,None):
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
    #This structure consists of each user of the transport having their own location of store.
    #The store per jid is then devided into two sections.
    #The first is the room and server for each room in use, used for directing messages, iq and subsiquent presence traffic
    #The second is used when adding channels in use. This will identify the servers and nick's in use.
    #Contrary to the above the new structure is dictionary of fromjid and a dictionary of servers connected.
    #All other information is stored in the connection.

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
        self.irc.add_global_handler('nick',self.irc_nick)
        self.irc.add_global_handler('join',self.irc_join)
        self.irc.add_global_handler('part',self.irc_part)
        self.irc.add_global_handler('quit',self.irc_quit)
        self.irc.add_global_handler('kick',self.irc_kick)
        self.irc.add_global_handler('mode',self.irc_chanmode)
        self.irc.add_global_handler('error',self.irc_error)
        self.irc.add_global_handler('topic',self.irc_topic)
        self.irc.add_global_handler('nicknameinuse',self.irc_nicknameinuse)
        self.irc.add_global_handler('nosuchchannel',self.irc_nosuchchannel)
        self.irc.add_global_handler('nosuchnick',self.irc_nosuchnick)
        self.irc.add_global_handler('notregistered',self.irc_notregistered)
        self.irc.add_global_handler('cannotsendtochan',self.irc_cannotsend)
        self.irc.add_global_handler('379',self.irc_redirect)
        self.irc.add_global_handler('welcome',self.irc_welcome)
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
        self.jabber.RegisterHandler('iq',self.xmpp_iq_register_set,typ = 'set', ns=NS_REGISTER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_register_get,typ = 'get', ns=NS_REGISTER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_vcard,typ = 'get', ns=NS_VCARD)
        self.disco = Browser()
        self.disco.PlugIn(self.jabber)
        self.command = Commands(self.disco)
        self.command.PlugIn(self.jabber)
        self.cmdonlineusers = Online_Users_Command(self,jid=hostname)
        self.cmdonlineusers.plugin(self.command)
        self.cmdactiveusers = Active_Users_Command(self,jid=hostname)
        self.cmdactiveusers.plugin(self.command)
        self.cmdregisteredusers = Registered_Users_Command(self,jid=hostname)
        self.cmdregisteredusers.plugin(self.command)
        self.cmdeditadminusers = Edit_Admin_List_Command(self, configfile, configfilename,jid=hostname)
        self.cmdeditadminusers.plugin(self.command)
        self.cmdrestartservice = Restart_Service_Command(self,jid=hostname)
        self.cmdrestartservice.plugin(self.command)
        self.cmdshutdownservice = Shutdown_Service_Command(self,jid=hostname)
        self.cmdshutdownservice.plugin(self.command)
        self.cmdconnectserver = Connect_Server_Command(self,jid='')
        self.cmdconnectserver.plugin(self.command)
        self.cmddisconnectserver = Disconnect_Server_Command(self,jid='')
        self.cmddisconnectserver.plugin(self.command)
        self.disco.setDiscoHandler(self.xmpp_base_disco,node='',jid=hostname)
        self.disco.setDiscoHandler(self.xmpp_base_disco,node='',jid='')

    # New Disco Handlers
    def xmpp_base_disco(self, con, event, type):
        fromjid = event.getFrom().__str__()
        fromstripped = event.getFrom().getStripped().encode('utf8')
        to = event.getTo()
        node = event.getQuerynode();
        room = irc_ulower(to.getNode())
        nick = to.getResource()
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        #Type is either 'info' or 'items'
        if to == hostname:
            if node == None:
                if type == 'info':
                    return {
                        'ids':[
                            {'category':'conference','type':'irc','name':'IRC Transport'},
                            {'category':'gateway','type':'irc','name':'IRC Transport'}],
                        'features':[NS_REGISTER,NS_VERSION,NS_MUC,NS_COMMANDS]}
                if type == 'items':
                    return [
                        {'node':NS_COMMANDS,'name':'IRC Transport Commands','jid':hostname},
                        {'node':NODE_REGISTERED_SERVERS,'name':'IRC Transport Registered Servers','jid':hostname},
                        {'node':NODE_ONLINE_SERVERS,'name':'IRC Transport Online Servers','jid':hostname}]
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
                        list.append({'name':each,'jid':'%s@%s' % (each, hostname)})
                    return list
            elif node == NODE_ONLINE_SERVERS:
                if type == 'info':
                    return {'ids':[],'features':[]}
                if type == 'items':
                    list = []
                    if self.users.has_key(fromjid):
                        for each in self.users[fromjid].keys():
                            list.append({'name':each,'jid':'%s@%s' % (each, hostname)})
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
                    list = [{'node':NS_COMMANDS,'name':'%s Commands'%server,'jid':'%s@%s' % (server, hostname)}]
                    if self.users.has_key(fromjid):
                        if self.users[fromjid].has_key(server):
                            list.append({'node':NODE_ONLINE_CHANNELS,'name':'%s Online Channels'%server,'jid':'%s@%s' % (server, hostname)})
                            list.append({'node':NODE_ACTIVE_CHANNELS,'name':'%s Active Channels'%server,'jid':'%s@%s' % (server, hostname)})
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
                            self.users[fromjid][server].pendingoperations["list"] = rep
                            self.users[fromjid][server].list()
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
                                    for each in self.users[fromjid][server].memberlist.keys():
                                        list.append({'name':each,'jid':'%s%%%s@%s' % (JIDEncode(each), server, hostname)})
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
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
        x = event.getTag(name='x', namespace=NS_MUC)
        try:
            password = x.getTagData('password')
        except AttributeError:
            password = None
        if to == hostname or channel == '':
            conf = None
            if userfile.has_key(fromstripped):
                if to == hostname:
                    conf = userfile[fromstripped]
                elif server and userfile[fromstripped].has_key('servers') and userfile[fromstripped]['servers'].has_key(server):
                    conf = userfile[fromstripped]['servers'][server]
            if type == 'subscribe':
                if conf:
                    self.jabber.send(Presence(to=fromjid, frm = to, typ = 'subscribed'))
                    conf['usubscribed']=True
                else:
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribe'))
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribed'))
                    self.jabber.send(Error(event,ERR_BAD_REQUEST))
            elif type == 'subscribed':
                if conf:
                    conf['subscribed']=True
                else:
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribe'))
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribed'))
                    self.jabber.send(Error(event,ERR_BAD_REQUEST))
            #
            #Add code so people can see transport presence here
            #
            elif type == 'probe':
                self.jabber.send(Presence(to=fromjid, frm = to))
                if not conf:
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribe'))
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribed'))
            elif type == 'unavailable':
                #call self.irc_disconnect to disconnect from the server
                #when you see the user's presence become unavailable
                if server:
                    print 'disconnect %s'%repr(server)
                    self.irc_disconnect('',server,'',fromjid,status)
                else:
                    self.jabber.send(Presence(to=fromjid, frm = to, typ = 'unavailable'))
                    print 'disconnect all'
                    if self.users.has_key(fromjid):
                        for each in self.users[fromjid].keys():
                            self.irc_disconnect('',each,'',fromjid,status)
            elif type == 'error':
                return
            else:
                #call self.irc_connect to connect to the server
                #when you see the user's presence become available
                if server:
                    print 'connect %s'%repr(server)
                    self.irc_connect('',server,nick,password,fromjid)
                else:
                    self.jabber.send(Presence(to=fromjid, frm = to))
            if userfile.has_key(fromstripped):
                if to == hostname:
                    userfile[fromstripped]=conf
                else:
                    userfile[fromstripped]['servers'][server]=conf
        elif irclib.is_channel(channel):
            if type == None:
                if nick != '':
                    self.irc_connect(channel,server,nick,password,fromjid)
            elif type == 'unavailable':
                self.irc_disconnect(channel,server,nick,fromjid,status)
            else:
                self.jabber.send(Error(event,ERR_FEATURE_NOT_IMPLEMENTED))
        else:
            self.jabber.send(Error(event,MALFORMED_JID))
            return

    def xmpp_message(self, con, event):
        type = event.getType()
        fromjid = event.getFrom().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            if event.getSubject.strip() == '':
                event.setSubject(None)
        except AttributeError:
            pass
        try:
            channel, server = room.split('%')
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
        if event.getBody() == None:
            return
        if type == 'groupchat':
            print "Groupchat"
            if irclib.is_channel(channel):
                print "channel:", event.getBody().encode('utf8')
                if event.getSubject():
                    print "subject"
                    if self.users[fromjid][server].chanmode.has_key('topic'):
                        print "topic"
                        if (self.users[fromjid][server].chanmode['topic']==True and self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['role'] == 'moderator') or self.users[fromjid][server].chanmode['topic']==False:
                            print "set topic ok"
                            self.irc_settopic(self.users[fromjid][server],channel,event.getSubject())
                        else:
                            print "set topic forbidden"
                            self.jabber.send(Error(event,ERR_FORBIDDEN))
                    else:
                        print "anyone can set topic"
                        self.irc_settopic(self.users[fromjid][server],channel,event.getSubject())
                elif event.getBody() != '':
                    print "body isn't empty:" , event.getBody().encode('utf8')
                    if event.getBody()[0:3] == '/me':
                        print "action"
                        self.irc_sendctcp('ACTION',self.users[fromjid][server],channel,event.getBody()[4:])
                    else:
                        print "room message"
                        self.irc_sendroom(self.users[fromjid][server],channel,event.getBody())
                    t = Message(to=fromjid,body=event.getBody(),typ=type,frm='%s@%s/%s' %(room, hostname,self.users[fromjid][server].nickname))
                    self.jabber.send(t)
            else:
                self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))  # or MALFORMED_JID maybe?
        elif type in ['chat', None]:
            if channel and not irclib.is_channel(channel):
                # ARGH! need to know channel to find out nick. :(
                nick = channel
            else:
                nick = to.getResource()
            if nick:
                if event.getBody()[0:3] == '/me':
                    self.irc_sendctcp('ACTION',self.users[fromjid][server],nick,event.getBody()[4:])
                else:
                    self.irc_sendroom(self.users[fromjid][server],nick,event.getBody())
            else:
                self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))

    def xmpp_iq_vcard(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        # need to store this ID somewhere for the return trip
        try:
            channel, server = room.split('%')
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
        nick = None
        if channel and not irclib.is_channel(channel):
            # ARGH! need to know channel to find out nick. :(
            nick = channel
        else:
            nick = to.getResource()
        
        m = Iq(to=fromjid,frm=to, typ='result')
        m.setID(id)
        p = m.addChild(name='vCard', namespace=NS_VCARD)
        p.setTagData(tag='DESC', val='Additional Information:')
        
        self.users[fromjid][server].pendingoperations["whois:" + irc_ulower(nick)] = m
        self.users[fromjid][server].whois([(nick + ' ' + nick).encode(self.users[fromjid][server].charset)])
        
        raise xmpp.NodeProcessed

    def xmpp_iq_discoinfo(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        id = event.getID()
        m = Iq(to=fromjid,frm=to, typ='result', queryNS=NS_DISCO_INFO, payload=[Node('identity',attrs={'category':'conference','type':'irc','name':'IRC Transport'}),Node('feature', attrs={'var':NS_REGISTER}),Node('feature',attrs={'var':NS_MUC})])
        m.setID(id)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_discoitems(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        id = event.getID()
        m = Iq(to=fromjid,frm=to, typ='result', queryNS=NS_DISCO_ITEMS)
        m.setID(id)
        self.jabber.send(m)
        raise xmpp.NodeProcessed


    def xmpp_iq_agents(self, con, event):
        m = Iq(to=event.getFrom(), frm=event.getTo(), typ='result', payload=[Node('agent', attrs={'jid':hostname},payload=[Node('service',payload='irc'),Node('name',payload='xmpp IRC Transport'),Node('groupchat')])])
        m.setID(event.getID())
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_browse(self, con, event):
        m = event.buildReply('result')
        if event.getTo() == hostname:
            m.setTagAttr('query','catagory','conference')
            m.setTagAttr('query','name','xmpp IRC Transport')
            m.setTagAttr('query','type','irc')
            m.setTagAttr('query','jid','hostname')
            m.setPayload([Node('ns',payload=NS_MUC),Node('ns',payload=NS_REGISTER)])
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_version(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        id = event.getID()
        uname = platform.uname()
        m = Iq(to = fromjid, frm = to, typ = 'result', queryNS=NS_VERSION, payload=[Node('name',payload='xmpp IRC Transport'), Node('version',payload=version),Node('os',payload=('%s %s %s' % (uname[0],uname[2],uname[4])).strip())])
        m.setID(id)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_mucadmin_get(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise xmpp.NodeProcessed
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].memberlist.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise xmpp.NodeProcessed
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
        m = Iq(to= fromjid, frm=to, typ='result', queryNS=ns)
        m.setID(id)
        payload = []
        for each in self.users[fromjid][server].memberlist[channel]:
            if role != None:
                if self.users[fromjid][server].memberlist[channel][each]['role']  == role:
                    zattr = self.users[fromjid][server].memberlist[channel][each]
                    zattr['nick'] = each
                    payload.append(Node('item',attrs = zattr))
            if affiliation != None:
                if self.users[fromjid][server].memberlist[channel][each]['affiliation']  == affiliation:
                    zattr = self.users[fromjid][server].memberlist[channel][each]
                    zattr['nick'] = each
                    payload.append(Node('item',attrs = zattr))
        m.setQueryPayload(payload)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_mucadmin_set(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise xmpp.NodeProcessed
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].memberlist.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise xmpp.NodeProcessed
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['role'] != 'moderator' or self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            raise xmpp.NodeProcessed
        for each in t:
            if t[0].getName() == 'item':
                attr = t[0].getAttrs()
                if attr.has_key('role'):
                    if attr['role'] == 'moderator':
                        self.users[fromjid][server].mode(channel,'%s %s'%('+o',attr['nick']))
                        raise xmpp.NodeProcessed
                    elif attr['role'] == 'participant':
                        self.users[fromjid][server].mode(channel,'%s %s'%('+v',attr['nick']))
                        raise xmpp.NodeProcessed
                    elif attr['role'] == 'visitor':
                        self.users[fromjid][server].mode(channel,'%s %s'%('-v',attr['nick']))
                        self.users[fromjid][server].mode(channel,'%s %s'%('-o',attr['nick']))
                        raise xmpp.NodeProcessed
                    elif attr['role'] == 'none':
                        self.users[fromjid][server].kick(channel,attr['nick'],'Kicked')#Need to add reason gathering
                        raise xmpp.NodeProcessed
                if attr.has_key('affiliation'):
                    nick, room = attr['jid'].split('%')
                    if attr['affiliation'] == 'member':
                        self.users[fromjid][server].mode(channel,'%s %s'%('+v',nick))
                        raise xmpp.NodeProcessed
                    elif attr['affiliation'] == 'none':
                        self.users[fromjid][server].mode(channel,'%s %s'%('-v',nick))
                        self.users[fromjid][server].mode(channel,'%s %s'%('-o',nick))
                        raise xmpp.NodeProcessed

    def xmpp_iq_mucowner_get(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise xmpp.NodeProcessed
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].memberlist.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise xmpp.NodeProcessed
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['role'] != 'moderator' or self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            raise xmpp.NodeProcessed
        datafrm = DataForm(data=self.users[fromjid][server].chanlist[channel])
        m = Iq(frm = to, to = fromjid, id = id, type='result', queryNS= ns, queryPayload = datafrm)
        m.setID(id)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_mucowner_set(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        id = event.getID()
        try:
            channel, server = room.split('%')
            channel = JIDDecode(channel)
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            raise xmpp.NodeProcessed
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].memberlist.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            raise xmpp.NodeProcessed
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['role'] != 'moderator' or self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            raise xmpp.NodeProcessed
        datadrm = event.getQueryPayload()[0].asDict()
        for each in dataform.keys():
            if datafrm[each] != self.users[fromjid][server].chanmode[each]:
                val = False
                if datafrm[each] == True:
                    typ='+'
                else:
                    typ='-'
                if each == 'private':
                    cmd = 'b'
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
                    cmd = 'b'
                    typ = '+'
                    val = True
                    for item in datafrm[each]:
                        if item not in self.users[fromjid][server].chanmode[each]:
                            self.users[fromjid][server].mode(channel,'+b %s' % item)
                            raise xmpp.NodeProcessed
                    for item in self.users[fromjid][server].chanmode[each]:
                        if item not in datafrm[each]:
                            self.users[fromjid][server].mode(channel,'-b %s' % item)
                            raise xmpp.NodeProcessed
                elif each == 'limit':
                    cmd = 'l'
                    typ = '+'
                    val = True
                    self.users[fromjid][server].mode(channel,'+l %s' % each)
                    raise xmpp.NodeProcessed
                elif each == 'key':
                    cmd = 'k'
                    typ = '+'
                    val = True
                    self.users[fromjid][server].mode(channel, '+k %s' % each)
                    raise xmpp.NodeProcessed
                if not val:
                    self.users[fromjid][server].mode(channel,'%s%s' % (typ,cmd))
                    raise xmpp.NodeProcessed

    # Registration code
    def xmpp_iq_register_get(self, con, event):
        charset = ''
        fromjid = event.getFrom().getStripped().encode('utf8')
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%')
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
            DataField(desc='Server alias used for jids'             ,name='alias'   ,value=server               ,typ=nametype),
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
        ucharset = charset
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            channel, server = room.split('%')
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
                    server = form.getField('address').getValue().split(':')[0]
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
                    server = query.getTagData('address').split(':')[0]
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
                    self.jabber.send(Presence(typ='subscribe',to=fromjid, frm='%s@%s'%(server,hostname)))
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
                        m = Presence(to = fromjid, frm = '%s@%s'%(server,hostname), typ = 'unsubscribe')
                        self.jabber.send(m)
                        m = Presence(to = fromjid, frm = '%s@%s'%(server,hostname), typ = 'unsubscribed')
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
        self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' % (conn.server, hostname), typ = 'unavailable'))
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
            if self.users[conn.fromjid][each].memberlist != {}:
                inuse = True
        fromstripped = JID(conn.fromjid).getStripped().encode('utf8')
        if userfile.has_key(fromstripped) and userfile[fromstripped].has_key('servers') and userfile[fromstripped]['servers'].has_key(conn.server):
            inuse = True
        if inuse == False:
            self.irc_doquit(conn,message)

    def irc_settopic(self,connection,channel,line):
        try:
            connection.topic(channel.encode(connection.charset),line.encode(connection.charset))
        except:
            self.irc_doquit(connection)

    def irc_sendnick(self,connection,nick):
        try:
            connection.nick(nick)
        except:
            self.irc_doquit(connection)

    def irc_sendroom(self,connection,channel,line):
        lines = line.split('\x0a')
        for each in lines:
            #print channel, each
            if each != '' or each == None:
               try:
                    connection.privmsg(channel.encode(connection.charset),each.encode(connection.charset))
               except:
                    self.irc_doquit(connection)

    def irc_sendctcp(self,type,connection,channel,line):
        lines = line.split('\x0a')
        for each in lines:
            #print channel, each
            try:
                connection.ctcp(type,channel.encode(connection.charset),each.encode(connection.charset))
            except:
                self.irc_doquit(connection)

    def irc_connect(self,channel,server,nick,password,frm):
        fromjid = frm.__str__()
        if not self.users.has_key(fromjid): # if a new user session
            self.users[fromjid] = {}
        if self.users[fromjid].has_key(server):
            if channel == '': return None
            if self.users[fromjid][server].memberlist.has_key(channel):
                if nick == '': return None
                self.users[fromjid][server].joinchan = channel
                self.irc_sendnick(self.users[fromjid][server],nick)
            elif self.users[fromjid].has_key(server): # if user already has a session open on same server
                self.irc_newroom(self.users[fromjid][server],channel)
            return 1
        else: # the other cases
            c=self.irc_newconn(channel,server,nick,password,frm)
            if c != None:
                self.users[fromjid][server]=c
                return 1
            else:
                return None

    def irc_newconn(self,channel,server,nick,password,frm):

        fromjid = frm.__str__()
        fromstripped = frm.getStripped().encode('utf8')

        address = server
        username = realname = nick
        if userfile.has_key(fromstripped):
            charset = userfile[fromstripped]['charset']
            if userfile[fromstripped].has_key('servers'):
                servers = userfile[fromstripped]['servers']
                if servers.has_key(server):
                    serverdetails = servers[server]
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
            c=self.irc.server().connect(address,port,nick,password,username,realname,localaddress)
            c.server = server
            c.address = address
            c.fromjid = fromjid
            c.joinchan = channel
            c.memberlist = {}
            c.chanmode = {}
            c.pendingoperations = {}
            if userfile.has_key(fromstripped):
                c.charset = userfile[fromstripped]['charset']
                if userfile[fromstripped].has_key('servers'):
                    servers = userfile[fromstripped]['servers']
                    if servers.has_key(server):
                        serverdetails = servers[server]
                        c.charset = serverdetails['charset']
            else:
                c.charset = charset
            self.jabber.send(Presence(to=fromjid, frm = '%s@%s' % (server, hostname)))
            return c
        except irclib.ServerConnectionError:
            self.jabber.send(Error(Presence(to = fromjid, frm = '%s%%%s@%s/%s' % (channel,server,hostname,nick)),ERR_SERVICE_UNAVAILABLE,reply=0))  # Other candidates: ERR_GONE, ERR_REMOTE_SERVER_NOT_FOUND, ERR_REMOTE_SERVER_TIMEOUT
            return None

    def irc_newroom(self,conn,channel):
        try:
           conn.join(channel)
           conn.who(channel)
        except:
           self.irc_doquit(conn)
        conn.memberlist[channel] = {}
        conn.chanmode[channel] = {'private':False, 'secret':False, 'invite':False, 'topic':False, 'notmember':False, 'moderated':False, 'banlist':[], 'limit':False, 'key':''}

    def irc_disconnect(self,channel,server,nick,frm,message):
        fromjid = frm.__str__()
        if self.users.has_key(fromjid):
            if self.users[fromjid].has_key(server):
                connection = self.users[fromjid][server]
                if channel:
                    if self.users[fromjid][server].memberlist.has_key(channel):
                        self.irc_leaveroom(connection,channel)
                        del self.users[fromjid][server].memberlist[channel]
                        self.irc_testinuse(connection,message)
                        return 1
                else:
                    self.irc_doquit(connection,message)
                    return 1
        return None

    def irc_leaveroom(self,conn,channel):
        try:
           conn.part([channel.encode(conn.charset)])
        except:
            self.irc_doquit(conn)

    # IRC message handlers
    def irc_error(self,conn,event):
        if conn.server in self.users[conn.fromjid].keys():
            try:
                for each in conn.memberlist.keys():
                    t = Presence(to=conn.fromjid, typ = 'unavailable', frm='%s%%%s@%s' %(each,conn.server,hostname))
                    self.jabber.send(t)
                del self.users[conn.fromjid][conn.server]
            except AttributeError:
                pass

    def irc_quit(self,conn,event):
        type = 'unavailable'
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        for each in conn.memberlist.keys():
            if nick in conn.memberlist[each].keys():
                del conn.memberlist[each][nick]
                name = '%s%%%s' % (each, conn.server)
                m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname,nick))
                self.jabber.send(m)
                if activitymessages == True:
                    line,xhtml = colourparse(event.arguments()[0],conn.charset)
                    m = Message(to=conn.fromjid, typ='groupchat',frm='%s@%s' % (name, hostname), body='%s (%s) has quit (%s)' % (nick, unicode(irclib.nm_to_uh(event.source()),conn.charset,'replace'), line))
                    self.jabber.send(m)

    def irc_nick(self, conn, event):
        old = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        new = unicode(event.target(),conn.charset,'replace')
        if old == conn.nickname:
            conn.nickname = new
        for each in conn.memberlist.keys():
            if old in conn.memberlist[each].keys():
                m = Presence(to=conn.fromjid,typ = 'unavailable',frm = '%s%%%s@%s/%s' % (each,conn.server,hostname,old))
                p = m.addChild(name='x', namespace=NS_MUC_USER)
                p.addChild(name='item', attrs={'nick':new})
                p.addChild(name='status', attrs={'code':'303'})
                self.jabber.send(m)
                m = Presence(to=conn.fromjid,typ = None, frm = '%s%%%s@%s/%s' % (each,conn.server,hostname,new))
                t = m.addChild(name='x',namespace=NS_MUC_USER)
                p = t.addChild(name='item',attrs=conn.memberlist[each][old])
                self.jabber.send(m)
                t=conn.memberlist[each][old]
                del conn.memberlist[each][old]
                conn.memberlist[each][new] = t
                if activitymessages == True:
                    m = Message(to=conn.fromjid, typ='groupchat',frm='%s%%%s@%s' % (each,conn.server,hostname), body='%s is now known as %s' % (old, new))
                    self.jabber.send(m)


    def irc_welcome(self,conn,event):
        if conn.joinchan != '':
            self.irc_newroom(conn,conn.joinchan)
        del conn.joinchan

    def irc_nicknameinuse(self,conn,event):
        if conn.joinchan:
            name = '%s%%%s' % (conn.joinchan, conn.server)
        else:
            name = conn.server
        error=ErrorNode(ERR_CONFLICT,text='Nickname is in use')
        self.jabber.send(Presence(to=conn.fromjid, typ = 'error', frm = '%s@%s' %(name, hostname),payload=[error]))

    def irc_nosuchchannel(self,conn,event):
        error=ErrorNode(ERR_ITEM_NOT_FOUND,'The channel is not found')
        self.jabber.send(Presence(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' %(unicode(event.arguments()[0],conn.charset,'replace'), conn.server, hostname),payload=[error]))

    def irc_notregistered(self,conn,event):
        if conn.joinchan:
            name = '%s%%%s' % (conn.joinchan, conn.server)
        else:
            name = conn.server
        error=ErrorNode(ERR_FORBIDDEN,text='Not registered and registration is not supported')
        self.jabber.send(Presence(to=conn.fromjid, typ = 'error', frm = '%s@%s' %(name, hostname),payload=[error]))

    def irc_nosuchnick(self, conn, event):
        error=ErrorNode(ERR_ITEM_NOT_FOUND,text='Nickname not found')
        self.jabber.send(Message(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' % (event.source(), conn.server, hostname),payload=[error]))

    def irc_cannotsend(self,conn,event):
        error=ErrorNode(ERR_FORBIDDEN)
        self.jabber.send(Message(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' % (event.source(), conn.server, hostname),payload=[error]))

    def irc_redirect(self,conn,event):
        new = '%s%%%s@%s'% (unicode(event.arguments()[1],conn.charset,'replace'),conn.server, hostname)
        old = '%s%%%s@%s'% (unicode(event.arguments()[0],conn.charset, 'replace'),conn.server, hostname)
        error=ErrorNode(ERR_REDIRECT,new)
        self.jabber.send(Presence(to=conn.fromjid, typ='error', frm = old, payload=[error]))
        conn.memberlist[unicode(event.arguments()[1],conn.charset,'replace')]={}
        try:
           conn.part(event.arguments()[1])
        except:
           self.irc_doquit(conn)

    def irc_mode(self,conn,event):
    # Mode handling currently is very poor.
    #
    # Issues:
    # Multiple +b's currently not handled
    # +l or -l with no parameter not handled
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        faddr = '%s%%%s@%s' %(channel,conn.server,hostname)
        if irclib.is_channel(event.target()):
            if event.arguments()[0] == '+o':
                # Give Chanop
                if channel in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        nick = unicode(each,conn.charset,'replace')
                        conn.memberlist[channel][nick]['role']='moderator'
                        if each == conn.nickname:
                            conn.memberlist[channel][nick]['affiliation']='owner'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,nick))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.memberlist[channel][nick])
                        self.jabber.send(m)
            elif event.arguments()[0] in ['-o', '-v']:
                # Take Chanop or Voice
                if channel in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        nick = unicode(each,conn.charset,'replace')
                        conn.memberlist[channel][nick]['role']='visitor'
                        conn.memberlist[channel][nick]['affiliation']='none'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,nick))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.memberlist[channel][nick])
                        self.jabber.send(m)
            elif event.arguments()[0] == '+v':
                # Give Voice
                if channel in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        nick = unicode(each,conn.charset,'replace')
                        conn.memberlist[channel][nick]['role']='participant'
                        conn.memberlist[channel][nick]['affiliation']='none'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,nick))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.memberlist[channel][nick])
                        self.jabber.send(m)

    def irc_chanmode(self,conn,event):
        # Very buggy, multiple items cases, ban etc.
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        faddr = '%s%%%s@%s' %(channel,conn.server,hostname)
        plus = None
        for each in event.arguments()[0]:
            if each == '+':
                plus = True
            elif each == '-':
                plus = False
            elif each == 'o': #Chanop status
                self.irc_mode(conn,event)
                #for each in event.arguments()[1:]:
                #    conn.who(channel,each)
            elif each == 'v': #Voice status
                self.irc_mode(conn,event)
                #for each in event.arguments()[1:]:
                #    conn.who(channel,each)
            elif each == 'p': #Private Room
                conn.chanmode[channel]['private'] = plus
            elif each == 's': #Secret
                conn.chanmode[channel]['secret'] = plus
            elif each == 'i': #invite only
                conn.chanmode[channel]['invite'] = plus
            elif each == 't': #only chanop can set topic
                conn.chanmode[channel]['topic'] = plus
            elif each == 'n': #no not in channel messages
                conn.chanmode[channel]['notmember'] = plus
            elif each == 'm': #moderated chanel
                conn.chanmode[channel]['moderated'] = plus
            elif each == 'l': #set channel limit
                conn.chanmode[channel]['private'] = event.arguments()[1]
            elif each == 'b': #ban users
                # Need to fix multiple ban case.
                if plus:
                    conn.chanmode[channel]['banlist'].append(unicode(event.arguments()[1],conn.charset,'replace'))
                else:
                    if unicode(event.arguments()[1],conn.charset,'replace') in conn.chanmode[channel]['banlist']:
                        conn.chanmode[channel]['banlist'].remove(unicode(event.arguments()[1],conn.charset,'replace'))
            elif each == 'k': #set channel key
                pass

    def irc_part(self,conn,event):
        type = 'unavailable'
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        name = '%s%%%s' % (channel, conn.server)
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        try:
            if nick in conn.memberlist[channel].keys():
                del conn.memberlist[channel][nick]
        except KeyError:
            pass
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname,nick))
        self.jabber.send(m)
        if activitymessages == True:
            m = Message(to=conn.fromjid, typ='groupchat',frm='%s@%s' % (name, hostname), body='%s (%s) has left' % (nick, unicode(irclib.nm_to_uh(event.source()),conn.charset,'replace')))
            self.jabber.send(m)

    def irc_kick(self,conn,event):
        type = 'unavailable'
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        name = '%s%%%s' % (channel, conn.server)
        jid = '%s%%%s@%s' % (irc_ulower(unicode(event.arguments()[0],conn.charset,'replace')), conn.server, hostname)
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname,unicode(event.arguments()[0],conn.charset,'replace')))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs={'affiliation':'none','role':'none','jid':jid})
        p.addChild(name='reason',payload=[colourparse(event.arguments()[1],conn.charset)][0])
        t.addChild(name='status',attrs={'code':'307'})
        self.jabber.send(m)
        if event.arguments()[0] == conn.nickname:
            if conn.memberlist.has_key(channel):
                del conn.memberlist[channel]
        self.irc_testinuse(conn)

    def irc_topic(self,conn,event):
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if len(event.arguments())==2:
            channel = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
            line,xhtml = colourparse(event.arguments()[1],conn.charset)
        else:
            channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
            line,xhtml = colourparse(event.arguments()[0],conn.charset)
        if activitymessages == True:
            m = Message(to=conn.fromjid,frm = '%s%%%s@%s/%s' % (channel,conn.server,hostname,nick), body='/me set the topic to: %s' % line, typ='groupchat', subject = line)
        else:
            m = Message(to=conn.fromjid,frm = '%s%%%s@%s/%s' % (channel,conn.server,hostname,nick), typ='groupchat', subject = line)
        self.jabber.send(m)

    def irc_join(self,conn,event):
        type = None
        channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
        name = '%s%%%s' % (channel, conn.server)
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        jid = '%s%%%s@%s' % (nick, conn.server, hostname)
        if nick not in conn.memberlist[channel].keys():
            conn.memberlist[channel][nick]={'affiliation':'none','role':'visitor','jid':jid}
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname, nick))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs=conn.memberlist[channel][nick])
        #print m.__str__()
        self.jabber.send(m)
        if activitymessages == True:
            m = Message(to=conn.fromjid, typ='groupchat',frm='%s@%s' % (name, hostname), body='%s (%s) has joined' % (nick, unicode(irclib.nm_to_uh(event.source()),conn.charset,'replace')))
            self.jabber.send(m)

    def irc_whoreply(self,conn,event):
        channel = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        nick = unicode(event.arguments()[4],conn.charset,'replace')
        faddr = '%s%%%s@%s/%s' % (channel, conn.server, hostname, nick)
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
        jid = '%s%%%s@%s' % (unicode(event.arguments()[4],conn.charset,'replace'), conn.server, hostname)
        p=t.addChild(name='item',attrs={'affiliation':affiliation,'role':role,'jid':jid})
        self.jabber.send(m)
        try:
            if (event.arguments()[0] != '*') and (nick not in conn.memberlist[channel].keys()):
                conn.memberlist[channel][nick]={'affiliation':affiliation,'role':role,'jid':jid}
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
            q.addChild('item',{'name':chan,'jid':'%s%%%s@%s' % (JIDEncode(chan), conn.server, hostname)})
        
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
        m = Message(to=conn.fromjid,body= line,typ='chat',frm='%s@%s/%s' %(conn.server, hostname,nick),payload = [xhtml])
        conn.pendingoperations["motd"] = m

    def irc_motd(self,conn,event):
        line,xhtml = colourparse(event.arguments()[0],conn.charset)
        m = conn.pendingoperations["motd"]
        m.setBody(m.getBody() + '\x0a' + line)

    def irc_endofmotd(self,conn,event):
        m = conn.pendingoperations["motd"]
        del conn.pendingoperations["motd"]
        self.jabber.send(m)

    def irc_message(self,conn,event):
        try:
            nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        except:
            nick = conn.server
        if irclib.is_channel(event.target()):
            type = 'groupchat'
            room = '%s%%%s' %(irc_ulower(unicode(event.target(),conn.charset,'replace')),conn.server)
            line,xhtml = colourparse(event.arguments()[0],conn.charset)
            #print (line,xhtml)
            m = Message(to=conn.fromjid,body= line,typ=type,frm='%s@%s/%s' %(room, hostname,nick),payload = [xhtml])
        else:
            type = 'chat'
            line,xhtml = colourparse(event.arguments()[0],conn.charset)
            try:
                userhost = unicode(irclib.nm_to_uh(event.source()),conn.charset,'replace')
                try:
                    host = unicode(irclib.nm_to_h(event.source()),conn.charset,'replace')
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
                frm = '%s%%%s@%s' %(nick,conn.server, hostname)
            else:
                frm = '%s@%s/%s' %(conn.server, hostname,nick)
            m = Message(to=conn.fromjid,body= line,typ=type,frm=frm,payload = [xhtml])
        self.jabber.send(m)

    def irc_ctcp(self,conn,event):
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if event.arguments()[0] == 'ACTION':
            if irclib.is_channel(event.target()):
                type = 'groupchat'
                room = '%s%%%s' %(irc_ulower(unicode(event.target(),conn.charset,'replace')),conn.server)
                line,xhtml = colourparse('/me '+event.arguments()[1],conn.charset)
                m = Message(to=conn.fromjid,body=line,typ=type,frm='%s@%s/%s' %(room, hostname,nick),payload =[xhtml])
            else:
                type = 'chat'
                name = unicode(event.source(),conn.charset,'replace')
                try:
                    name = '%s%%%s' %(nick,conn.server)
                except:
                    name = '%s%%%s' %(conn.server,conn.server)
                line,xhtml = colourparse('/me '+event.arguments()[1],conn.charset)
                m = Message(to=conn.fromjid,body= line,typ=type,frm='%s@%s' %(name, hostname),payload = [xhtml])
            self.jabber.send(m)
        elif event.arguments()[0] == 'VERSION':
            self.irc_sendctcp('VERSION',conn,irclib.nm_to_n(event.source()),'xmpp IRC Transport ' + version)

    def xmpp_disconnect(self):
        for each in self.users.keys():
            for item in self.users[each].keys():
                self.irc_doquit(self.users[each][item])
            del self.users[each]
        #del connection
        while not connection.reconnectAndReauth():
            time.sleep(5)

import pdb
if __name__ == '__main__':
    if 'PID' in os.environ:
        open(os.environ['PID'],'w').write(`os.getpid()`)
    configfile = ConfigParser.ConfigParser()
    configfile.add_section('transport')
    try:
        configfilename = 'transport.ini'
        cffile = open(configfilename,'r')
    except IOError:
        try:
            configfilename = '/etc/jabber/jabber-irc.conf'
            cffile = open(configfilename,'r')
        except IOError:
            print "Transport requires configuration file, please supply either transport.ini in the current directory or /etc/jabber/jabber-irc.conf"
            sys.exit(1)
    configfile.readfp(cffile)
    cffile.close()
    server = configfile.get('transport','Server')
    hostname = configfile.get('transport','Hostname')
    port = int(configfile.get('transport','Port'))
    secret = configfile.get('transport','Secret')
    if configfile.has_option('transport','LocalAddress'):
        localaddress = configfile.get('transport','LocalAddress')
    if configfile.has_option('transport','Charset'):
        charset = configfile.get('transport','Charset')
    #JEP-0133 addition for administrators, comma seperated list of jids.
    if configfile.has_option('transport','Administrators'):
        jep0133.administrators = configfile.get('transport','Administrators').split(',')
    else:
        jep0133.administrators = []
    activitymessages = True # For displaying user acitivity messages
    if configfile.has_option('transport','UserFile'):
        userfilepath = configfile.get('transport','UserFile')
    else:
        userfilepath = 'user.dbm'
    userfile = shelve.open(userfilepath)
    logfile = None
    if configfile.has_option('transport','LogFile'):
        logfilepath = configfile.get('transport','LogFile')
        logfile = open(logfilepath,'a')
    fatalerrors = True
    if configfile.has_option('transport','FatalErrors'):
        if not configfile.get('transport','FatalErrors').lower() in ['true', '1', 'yes', 'false', '0', 'no']:
             print "Invalid setting for FatalErrors: " + configfile.get('transport','FatalErrors')
             sys.exit(1)
        fatalerrors = configfile.get('transport','FatalErrors').lower() in ['true', '1', 'yes']

    ircobj = irclib.IRC(fn_to_add_socket=irc_add_conn,fn_to_remove_socket=irc_del_conn)
    connection = xmpp.client.Component(hostname,port)
    transport = Transport(connection,ircobj)
    transport.userfile = userfile
    if not connectxmpp(transport.register_handlers):
        print "Password mismatch!"
        sys.exit(1)
    socketlist[connection.Connection._sock]='xmpp'
    transport.online = 1
    transport.restart = 0
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
                    if logfile != None:
                        traceback.print_exc(file=logfile)
                        logfile.flush()
                    if fatalerrors:
                        _pendingException = sys.exc_info()
                        raise _pendingException[0], _pendingException[1], _pendingException[2]
                    traceback.print_exc()
                if not connection.isConnected():  transport.xmpp_disconnect()
            else:
                try:
                    ircobj.process_data([each])
                except:
                    if logfile != None:
                        traceback.print_exc(file=logfile)
                        logfile.flush()
                    if fatalerrors:
                        _pendingException = sys.exc_info()
                        raise _pendingException[0], _pendingException[1], _pendingException[2]
                    traceback.print_exc()
    userfile.close()
    connection.disconnect()
    if transport.restart:
        args=[sys.executable]+sys.argv
        if os.name == 'nt':
            def quote(a): return "\"%s\"" % a
            args = map(quote, args)
        print sys.executable, args
        os.execv(sys.executable, args)