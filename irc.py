#!/usr/bin/python
# $Id$
version = 'CVS ' + '$Revision$'.split()[1]
#
# IRC transport
# January 2004 Copyright (c) Mike Albon
# 2006 Copyright (c) Norman Rasmussen
#
# This program is free software licensed with the GNU Public License Version 2.
# For a full copy of the license please go here http://www.gnu.org/licenses/licenses.html#GPL

import codecs, ConfigParser, os, platform, re, select, shelve, signal, socket, sys, time, traceback
import irclib, xmpp.client
from xmpp.protocol import *
from xmpp.browser import *
from xmpp.jep0106 import *
import config, xmlconfig
from adhoc import AdHocCommands
from irc_helpers import irc_ulower

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
NODE_ADMIN='admin'
NODE_ADMIN_USERS='users'
NODE_ADMIN_REGISTERED_USERS='registered-users'
NODE_ADMIN_ONLINE_USERS='online-users'
NODE_ADMIN_REGISTERED_SERVERS='registered-servers'
NODE_ADMIN_ONLINE_SERVERS='online-servers'

## Unicode Notes
#
# All data between irc and jabber must be translated to and from the connection character set.
#
# All internal datastructures are held in UTF8 unicode objects.

# This is the list of charsets that python supports.  Detecting this list at runtime is really difficult, so it's hardcoded here.
charsets = ['','ascii','big5','big5hkscs','cp037','cp424','cp437','cp500','cp737','cp775','cp850','cp852','cp855','cp856','cp857','cp860','cp861','cp862','cp863','cp864','cp865','cp866','cp869','cp874','cp875','cp932','cp949','cp950','cp1006','cp1026','cp1140','cp1250','cp1251','cp1252','cp1253','cp1254','cp1255','cp1256','cp1257','cp1258','euc-jp','euc-jis-2004','euc-jisx0213','euc-kr','gb2312','gbk','gb18030','hz','iso2022-jp','iso2022-jp-1','iso2022-jp-2','iso2022-jp-2004','iso2022-jp-3','iso2022-jp-ext','iso2022-kr','latin-1','iso8859-1','iso8859-2','iso8859-3','iso8859-4','iso8859-5','iso8859-6','iso8859-7','iso8859-8','iso8859-9','iso8859-10','iso8859-13','iso8859-14','iso8859-15','johab','koi8-r','koi8-u','mac-cyrillic','mac-greek','mac-iceland','mac-latin2','mac-roman','mac-turkish','ptcp154','shift-jis','shift-jis-2004','shift-jisx0213','utf-16','utf-16-be','utf-16-le','utf-7','utf-8']
irccolour = ['#FFFFFF','#000000','#0000FF','#00FF00','#FF0000','#F08000','#8000FF','#FFF000','#FFFF00','#80FF00','#00FF80','#00FFFF','#0080FF','#FF80FF','#808080','#A0A0A0']

def colourparse(str,charset):
    # Each tuple consists of String, foreground, background, bold.
    #str = str.replace('/','//')
    foreground=None
    background=None
    bold=None
    underline=None
    italic=None
    s = ''
    html=[]
    hs = ''
    ctrseq=None
    ctrfor=None #Has forground been processed?
    for e in str:
        if ctrseq == True:
            if e.isdigit():
                if not ctrfor:
                    if not foreground: foreground = ''
                    if len(foreground) < 2:
                        foreground += e
                    else:
                        ctrseq=None
                else:
                    if not background: background = ''
                    if len(background) < 2:
                        background += e
                    else:
                        ctrseq=None
                        ctrfor=None
            elif e == ',':
                ctrfor=True
                background = None
            else:
                if not foreground and not ctrfor: background = None
                ctrfor = None
                ctrseq = None
        if ctrseq == True:
            pass
        elif e == '\x02': # Bold
            html.append((hs,foreground,background,bold,underline,italic))
            if bold == True:
                bold = None
            else:
                bold = True
            hs = ''
        elif e == '\x12': # Reverse
            if config.dumpProtocol: print 'Reverse'
        elif e == '\x16' or e == '\x1d': # Deprecated Italic or Italic
            html.append((hs,foreground,background,bold,underline,italic))
            if italic == True:
                italic = None
            else:
                italic = True
            hs = ''
        elif e == '\x1f': # Underline
            html.append((hs,foreground,background,bold,underline,italic))
            if underline == True:
                underline = None
            else:
                underline = True
            hs = ''
        elif e == '\x03': # Colour Code
            html.append((hs,foreground,background,bold,underline,italic))
            foreground = None
            if not ctrseq:
                ctrseq = True
            hs = ''
        elif e == '\x0f': # Normal
            html.append((hs,foreground,background,bold,underline,italic))
            foreground = None
            background = None
            bold = None
            underline = None
            hs = ''
        elif e in ['\x00', '\x01', '\x04', '\x05', '\x06', '\x07', '\x08', '\x09', '\x0a', '\x0b', '\x0c', '\x0d', '\x0e']:
            if config.dumpProtocol: print 'Odd Escape'
        elif e in ['\x10', '\x11', '\x12', '\x13', '\x14', '\x15', '\x17', '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1e']:
            if config.dumpProtocol: print 'Other Escape'
        else:
            s = '%s%s'%(s,e)
            hs = '%s%s'%(hs,e)
    html.append((hs,foreground,background,bold,underline,italic))
    chtml = []
    try:
        s = unicode(s,'utf8','strict') # Language detection stuff should go here.
        for each in html:
            chtml.append((unicode(each[0],'utf-8','strict'),each[1],each[2],each[3],each[4],each[5]))
    except:
        s = unicode(s, charset,'replace')
        for each in html:
            chtml.append((unicode(each[0],charset,'replace'),each[1],each[2],each[3],each[4],each[5]))
    if len(chtml) > 1:
        html = Node('html')
        html.setNamespace('http://jabber.org/protocol/xhtml-im')
        xhtml = html.addChild('body',namespace='http://www.w3.org/1999/xhtml')
        #if config.dumpProtocol: print chtml
        for each in chtml:
            style = ''
            if each[1] != None and int(each[1])<16:
                foreground = irccolour[int(each[1])]
                #if config.dumpProtocol: print foreground
                style = '%scolor:%s;'%(style,foreground)
            if each[2] != None and int(each[2])<16:
                background = irccolour[int(each[2])]
                style = '%sbackground-color:%s;'%(style,background)
            if each[3]:
                style = '%sfont-weight:bold;'%style
            if each[4]:
                style = '%stext-decoration:underline;'%style
            if each[5]:
                style = '%sfont-style:italic;'%style
            if each[0] != '':
                if style == '':
                    xhtml.addData(each[0])
                else:
                    xhtml.addChild(name = 'span', attrs = {'style':style},payload=each[0])
    else:
        html = ''
    return s,html

def pendingop_push(conn, op, callback, data):
    if not conn.pendingoperations.has_key(op):
        conn.pendingoperations[op]=[]
    conn.pendingoperations[op].append((op, callback, data))
    conn.allpendingoperations.append((op, callback, data))
    if config.dumpProtocol: print 'pendingoperations:',repr(conn.pendingoperations),'\nallpendingoperations:',repr(conn.allpendingoperations)

def pendingop_call(conn, op, event):
    #if config.dumpProtocol: print 'pendingoperations:',repr(conn.pendingoperations),'\nallpendingoperations:',repr(conn.allpendingoperations)
    if conn.pendingoperations.has_key(op):
        info = conn.pendingoperations[op][0]
        return info[1](conn,event,op,info[2])
    return None

def pendingop_pop(conn, op):
    if conn.pendingoperations.has_key(op):
        info = conn.pendingoperations[op].pop(0)
        if conn.pendingoperations[op] == []:
            del conn.pendingoperations[op]
        conn.allpendingoperations.remove(info)
        if config.dumpProtocol: print 'pendingoperations:',repr(conn.pendingoperations),'\nallpendingoperations:',repr(conn.allpendingoperations)
        return info[2]
    if config.dumpProtocol: print 'pendingoperations:',repr(conn.pendingoperations),'\nallpendingoperations:',repr(conn.allpendingoperations)

def pendingop_fail(conn, event):
    if conn.allpendingoperations == []:
        return None
    info = conn.allpendingoperations[0]
    pendingop_pop(conn, info[0])
    if config.dumpProtocol: print 'pendingoperation',info[0],'failed!'
    return info[1](conn,event,'fail',info[2])

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
    #   pendingoperations   - hash      - key is internal name of operation, joined with nick if applicable, value a list of tuples of (op,callback,data)
    #       op                  - string
    #       callback            - function
    #       data                - generally an xmpp message to send on completion
    #   allpendingoperations- list      - list of tuples of all pending operations
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
        self.irc.add_global_handler('endofservices',self.irc_motd)
        self.irc.add_global_handler('308',self.irc_motdstart)
        self.irc.add_global_handler('309',self.irc_endofmotd)
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
        self.irc.add_global_handler('disconnect',self.irc_disconnected)
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
        self.irc.add_global_handler('tryagain',self.irc_tryagain)
        self.jabber.RegisterHandler('message',self.xmpp_message)
        self.jabber.RegisterHandler('presence',self.xmpp_presence)
        #Disco stuff now done by disco object
        self.jabber.RegisterHandler('iq',self.xmpp_iq_version,typ = 'get', ns=NS_VERSION)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucadmin_set,typ = 'set', ns=NS_MUC_ADMIN)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucadmin_get,typ = 'get', ns=NS_MUC_ADMIN)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucowner_set,typ = 'set', ns=NS_MUC_OWNER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucowner_get,typ = 'get', ns=NS_MUC_OWNER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_register_set,typ = 'set', ns=NS_REGISTER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_register_get,typ = 'get', ns=NS_REGISTER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_search_set,typ = 'set', ns=NS_SEARCH)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_search_get,typ = 'get', ns=NS_SEARCH)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_vcard,typ = 'get', ns=NS_VCARD)
        self.disco = Browser()
        self.disco.PlugIn(self.jabber)
        self.adhoccommands = AdHocCommands(userfile)
        self.adhoccommands.PlugIn(self)
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
            sys.exc_clear()
        #Type is either 'info' or 'items'
        if to == config.jid:
            if node == None:
                if type == 'info':
                    return {
                        'ids':[
                            {'category':'conference','type':'irc','name':VERSTR},
                            {'category':'gateway','type':'irc','name':VERSTR}],
                        'features':[NS_DISCO_INFO,NS_DISCO_ITEMS,NS_REGISTER,NS_VERSION,NS_MUC,NS_COMMANDS]}
                if type == 'items':
                    list = [
                        {'node':NODE_REGISTERED_SERVERS,'name':config.discoName + ' Registered Servers','jid':config.jid},
                        {'node':NODE_ONLINE_SERVERS,'name':config.discoName + ' Online Servers','jid':config.jid}]
                    if fromjid in config.admins:
                        list.append({'node':NODE_ADMIN,'name':config.discoName + ' Admin','jid':config.jid})
                    return list
            elif node == NODE_ADMIN:
                if type == 'info':
                    return {'ids':[],'features':[NS_DISCO_ITEMS]}
                if type == 'items':
                    if not fromjid in config.admins:
                        return []
                    return [
                        {'node':NS_COMMANDS,'name':config.discoName + ' Commands','jid':config.jid},
                        {'node':NODE_ADMIN_REGISTERED_USERS,'name':config.discoName + ' Registered Users','jid':config.jid},
                        {'node':NODE_ADMIN_ONLINE_USERS,'name':config.discoName + ' Online Users','jid':config.jid}]
            elif node == NODE_REGISTERED_SERVERS:
                if type == 'info':
                    return {'ids':[],'features':[NS_DISCO_ITEMS]}
                if type == 'items':
                    list = []
                    servers = []
                    if userfile.has_key(fromstripped) \
                      and userfile[fromstripped].has_key('servers'):
                        servers = userfile[fromstripped]['servers']
                    for each in servers:
                        list.append({'name':each,'jid':'%s@%s' % (each, config.jid)})
                    return list
            elif node == NODE_ONLINE_SERVERS:
                if type == 'info':
                    return {'ids':[],'features':[NS_DISCO_ITEMS]}
                if type == 'items':
                    list = []
                    if self.users.has_key(fromjid):
                        for each in self.users[fromjid].keys():
                            list.append({'name':each,'jid':'%s@%s' % (each, config.jid)})
                    return list
            elif node == NODE_ADMIN_REGISTERED_USERS:
                if type == 'info':
                    return {'ids':[],'features':[NS_DISCO_ITEMS]}
                if type == 'items':
                    if not fromjid in config.admins:
                        return []
                    list = []
                    for each in userfile.keys():
                        list.append({'node':'/'.join([NODE_ADMIN_USERS, each]),'name':each,'jid':config.jid})
                    return list
            elif node == NODE_ADMIN_ONLINE_USERS:
                if type == 'info':
                    return {'ids':[],'features':[NS_DISCO_ITEMS]}
                if type == 'items':
                    if not fromjid in config.admins:
                        return []
                    list = []
                    for each in self.users.keys():
                        list.append({'node':'/'.join([NODE_ADMIN_USERS, each]),'name':each,'jid':config.jid})
                    return list
            elif node.startswith(NODE_ADMIN_USERS):
                if type == 'info':
                    return {'ids':[],'features':[NS_DISCO_ITEMS]}
                if type == 'items':
                    if not fromjid in config.admins:
                        return []
                    nodeinfo = node.split('/')
                    list = []
                    if len(nodeinfo) == 2:
                        fromjid = nodeinfo[1]
                        list = [
                            {'name':fromjid + ' JID','jid':fromjid},
                            {'node':'/'.join([NODE_ADMIN_USERS, fromjid, NODE_ADMIN_REGISTERED_SERVERS]),'name':fromjid + ' Registered Servers','jid':config.jid},
                            {'node':'/'.join([NODE_ADMIN_USERS, fromjid, NODE_ADMIN_ONLINE_SERVERS]),'name':fromjid + ' Online Servers','jid':config.jid}]
                    elif len(nodeinfo) == 3:
                        fromjid = nodeinfo[1]
                        fromstripped = fromjid.encode('utf8')
                        node = nodeinfo[2]
                        if node == NODE_ADMIN_REGISTERED_SERVERS:
                            servers = []
                            if userfile.has_key(fromstripped) \
                              and userfile[fromstripped].has_key('servers'):
                                servers = userfile[fromstripped]['servers']
                            for each in servers:
                                address = each
                                if servers[each]['address']:
                                    address = servers[each]['address']
                                nick = ''
                                if servers[each]['nick']:
                                    nick = servers[each]['nick']
                                list.append({'node':'/'.join([NODE_ADMIN_USERS, fromjid, NODE_ADMIN_REGISTERED_SERVERS, each]),'name':'%s/%s'%(address,nick),'jid':config.jid})
                        elif node == NODE_ADMIN_ONLINE_SERVERS:
                            if self.users.has_key(fromjid):
                                for each in self.users[fromjid].keys():
                                    conn = self.users[fromjid][each]
                                    list.append({'node':'/'.join([NODE_ADMIN_USERS, fromjid, NODE_ADMIN_ONLINE_SERVERS, each]),'name':'%s:%s/%s'%(conn.address,conn.port,conn.nickname),'jid':config.jid})
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
                        'features':[NS_DISCO_INFO,NS_DISCO_ITEMS,NS_REGISTER,NS_VERSION,NS_MUC,NS_COMMANDS,NS_SEARCH]}
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
                            return {'ids':[],'features':[NS_DISCO_ITEMS]}
                        if type == 'items':
                            rep=event.buildReply('result')
                            rep.setQuerynode(node)
                            conn = self.users[fromjid][server]
                            pendingop_push(conn, 'list', self.irc_list_items, rep)
                            conn.list()
                            raise NodeProcessed
                self.jabber.send(Error(event,ERR_REGISTRATION_REQUIRED))
                raise NodeProcessed
            elif node == NODE_ACTIVE_CHANNELS:
                if self.users.has_key(fromjid):
                    if self.users[fromjid].has_key(server):
                        if type == 'info':
                            return {'ids':[],'features':[NS_DISCO_ITEMS]}
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
                        rep=event.buildReply('result')
                        q=rep.getTag('query')
                        q.addChild('feature',{'var':NS_DISCO_INFO})
                        q.addChild('feature',{'var':NS_MUC})
                        conn = self.users[fromjid][server]
                        pendingop_push(conn, 'list', self.irc_list_info, rep)
                        conn.list([channel.encode(conn.charset,'replace')])
                        raise NodeProcessed
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
            sys.exc_clear()
        x = event.getTag(name='x', namespace=NS_MUC)
        try:
            password = x.getTagData('password')
        except AttributeError:
            password = None
            sys.exc_clear()
        if to == config.jid or channel == '':
            conf = None
            if userfile.has_key(fromstripped):
                if to == config.jid:
                    conf = userfile[fromstripped]
                elif server \
                  and userfile[fromstripped].has_key('servers') \
                  and userfile[fromstripped]['servers'].has_key(server):
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
                    if config.dumpProtocol: print 'disconnect %s'%repr(server)
                    self.irc_disconnect('',server,fromjid,status)
                    self.xmpp_presence_do_update(event,server,fromstripped)
                else:
                    self.jabber.send(Presence(to=fromjid, frm = to, typ = 'unavailable'))
                    if config.dumpProtocol: print 'disconnect all'
                    if self.users.has_key(fromjid.getStripped()):
                        for each in self.users[fromjid.getStripped()].keys():
                            self.irc_disconnect('',each,fromjid,status)
            else:
                #call self.irc_connect to connect to the server
                #when you see the user's presence become available
                if server:
                    if config.dumpProtocol: print 'connect %s'%repr(server)
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
            elif type == 'error':
                return
            else:
                self.jabber.send(Error(event,ERR_FEATURE_NOT_IMPLEMENTED))
        else:
            nick = channel
            conf = None
            if server \
              and userfile.has_key(fromstripped) \
              and userfile[fromstripped].has_key('servers') \
              and userfile[fromstripped]['servers'].has_key(server):
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
                        conn = self.users[fromjid.getStripped()][server]
                        conn.send_raw('WATCH +%s' % nick.encode(conn.charset,'replace'))
            elif type == 'unsubscribe' or type == 'unsubscribed':
                self.jabber.send(Presence(to=fromjid, frm = to, typ = 'unsubscribed'))
                if nick in subscriptions:
                    subscriptions.remove(nick)
                    if self.users.has_key(fromjid.getStripped()) \
                      and self.users[fromjid.getStripped()].has_key(server) \
                      and self.users[fromjid.getStripped()][server].features.has_key('WATCH'):
                        conn = self.users[fromjid.getStripped()][server]
                        conn.send_raw('WATCH -%s' % nick.encode(conn.charset,'replace'))

            conf['subscriptions'] = subscriptions
            user = userfile[fromstripped]
            user['servers'][server] = conf
            userfile[fromstripped] = user
            userfile.sync()

            if (type == 'subscribe' or type == 'unsubscribe' or type == 'unsubscribed') \
              and self.users.has_key(fromjid.getStripped()) \
              and self.users[fromjid.getStripped()].has_key(server):
                if not self.users[fromjid.getStripped()][server].features.has_key('WATCH'):
                    self.irc_doison(self.users[fromjid.getStripped()][server],1)

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
                    conn.send_raw('AWAY :%s'%show.encode(conn.charset,'replace'))

    def xmpp_message(self, con, event):
        type = event.getType()
        fromjid = event.getFrom().getStripped().__str__()
        to = event.getTo()
        room = irc_ulower(to.getNode())
        try:
            if event.getSubject.strip() == '':
                event.setSubject(None)
        except AttributeError:
            sys.exc_clear()
        try:
            channel, server = room.split('%',1)
            channel = JIDDecode(channel)
        except ValueError:
            channel=''
            server=room
            sys.exc_clear()
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
            if config.dumpProtocol: print "Groupchat"
            if irclib.is_channel(channel) and conn.channels.has_key(channel):
                if config.dumpProtocol: print "channel:", event.getBody().encode('utf8')
                if event.getSubject():
                    if config.dumpProtocol: print "subject"
                    if conn.channels[channel].topic:
                        if config.dumpProtocol: print "topic"
                        if conn.channels[channel].members[conn.nickname]['role'] == 'moderator':
                            if config.dumpProtocol: print "set topic ok"
                            self.irc_settopic(conn,channel,event.getSubject())
                        else:
                            if config.dumpProtocol: print "set topic forbidden"
                            self.jabber.send(Error(event,ERR_FORBIDDEN))
                    else:
                        if config.dumpProtocol: print "anyone can set topic"
                        self.irc_settopic(conn,channel,event.getSubject())
                elif event.getBody() != '':
                    if config.dumpProtocol: print "body isn't empty:" , event.getBody().encode('utf8')
                    if event.getBody()[0:3] == '/me':
                        if config.dumpProtocol: print "action"
                        self.irc_sendctcp('ACTION',conn,channel,event.getBody()[4:])
                    else:
                        if config.dumpProtocol: print "room message"
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
                if not channel and nick == to.getResource():
                    conn.send_raw('%s %s' % (nick.upper().encode(conn.charset,'replace'),event.getBody().encode(conn.charset,'replace')))
                elif event.getBody()[0:3] == '/me':
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
            sys.exc_clear()
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
        conn.whois([(nick + ' ' + nick).encode(conn.charset,'replace')])

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
                if config.dumpProtocol: print '%s:%s'%(repr(each),repr(datafrm[each]))
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
            sys.exc_clear()
        if not channel == '':
            self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
            raise xmpp.NodeProcessed

        instructionText = 'Please provide your IRC connection information, along with the charset to use. (eg cp437, cp1250, iso-8859-1, koi8-r)'
        queryPayload = [Node('instructions', payload = instructionText)]

        serverdetails = {'address':'','nick':'','password':'','realname':'','username':''}
        if userfile.has_key(fromjid):
            charset = userfile[fromjid]['charset']
            if not server == '' and userfile[fromjid].has_key('servers'):
                servers = userfile[fromjid]['servers']
                if servers.has_key(server):
                    serverdetails = servers[server]
                    charset = serverdetails['charset']
            queryPayload += [Node('registered')]

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
        form.setInstructions(instructionText)
        queryPayload += [
            Node('charset'  ,payload=charset),
            Node('address'  ,payload=serverdetails['address']),
            Node('nick'     ,payload=serverdetails['nick']),
            Node('password' ,payload=serverdetails['password']),
            Node('name'     ,payload=serverdetails['realname']),
            Node('username' ,payload=serverdetails['username']),
            form]

        m = event.buildReply('result')
        m.setQueryNS(NS_REGISTER)
        m.setQueryPayload(queryPayload)
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
            sys.exc_clear()
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

    def xmpp_iq_search_get(self, con, event):
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
            sys.exc_clear()
        if not server or not channel == '':
            self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
            raise xmpp.NodeProcessed

        if self.users.has_key(fromjid):
            if self.users[fromjid].has_key(server):

                instructionText = 'Fill in the form to search for any matching room (Add * to the end of field to match substring)'
                queryPayload = [Node('instructions', payload = instructionText)]
        
                form = DataForm(typ='form',data=[
                    DataField(desc='Name of the channel',name='name',typ='text-single')])
                form.setInstructions(instructionText)
                queryPayload += [
                    Node('name'),
                    form]
        
                m = event.buildReply('result')
                m.setQueryNS(NS_SEARCH)
                m.setQueryPayload(queryPayload)
                self.jabber.send(m)
                raise xmpp.NodeProcessed

        self.jabber.send(Error(event,ERR_REGISTRATION_REQUIRED))
        raise NodeProcessed

    def xmpp_iq_search_set(self, con, event):
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
            sys.exc_clear()
        if not channel == '':
            self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
            raise xmpp.NodeProcessed

        query = event.getTag('query')
        if query.getTag(name='x',namespace=NS_DATA):
            form = DataForm(node=query.getTag(name='x',namespace=NS_DATA))
            if form.getField('name'):
                name = form.getField('name').getValue()
        elif query.getTag('name'):
            name = query.getTagData('name')

        if self.users.has_key(fromjid):
            if self.users[fromjid].has_key(server):
                rep=event.buildReply('result')
                q=rep.getTag('query')
                reported = Node('reported',payload=[
                    DataField(label='JID'                ,name='jid'                   ,typ='jid-single'),
                    DataField(label='Channel'            ,name='name'                  ,typ='text-single'),
                    DataField(label='Subject'            ,name='muc#roominfo_subject'  ,typ='text-single'),
                    DataField(label='Number of occupants',name='muc#roominfo_occupants',typ='text-single')])
                form = DataForm(typ='result')
                form.setPayload([reported])
                q.addChild(node=form)
                conn = self.users[fromjid][server]
                pendingop_push(conn, 'list', self.irc_list_search, rep)
                conn.list([name.encode(conn.charset,'replace')])
                raise NodeProcessed
        self.jabber.send(Error(event,ERR_REGISTRATION_REQUIRED))
        raise NodeProcessed

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
        if userfile.has_key(fromstripped) \
          and userfile[fromstripped].has_key('servers') \
          and userfile[fromstripped]['servers'].has_key(conn.server):
            inuse = True
        if inuse == False:
            self.irc_doquit(conn,message)

    def irc_disconnected(self,conn,event):
        if config.dumpProtocol: print "disconnected by %s" % conn.address
        self.irc_doquit(conn)

    def irc_settopic(self,conn,channel,line):
        try:
            conn.topic(channel.encode(conn.charset,'replace'),line.encode(conn.charset,'replace'))
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
            #if config.dumpProtocol: print channel, each
            if each != '' or each == None:
               try:
                    conn.privmsg(channel.encode(conn.charset,'replace'),each.encode(conn.charset,'replace'))
               except:
                    self.irc_doquit(conn)

    def irc_sendctcp(self,type,conn,channel,line):
        lines = line.split('\x0a')
        for each in lines:
            #if config.dumpProtocol: print channel, each
            try:
                conn.ctcp(type,channel.encode(conn.charset,'replace'),each.encode(conn.charset,'replace'))
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
                    self.irc_newroom(conn,channel)
                    conn.channels[channel].resources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),time.time())
                    if config.dumpProtocol: print "New channel login: %s" % conn.channels[channel].resources
                else:
                    if conn.channels[channel].resources.has_key(resource):
                        #update resource record
                        conn.channels[channel].resources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),conn.channels[channel].resources[resource][3])
                        if config.dumpProtocol: print "Update channel resource login: %s" % conn.channels[channel].resources
                    else:
                        #new resource login
                        conn.channels[channel].resources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),time.time())
                        if config.dumpProtocol: print "New channel resource login: %s" % conn.channels[channel].resources
                        # resource is joining an existing resource on the same channel
                        # TODO: Send topic to new resource
                        # TODO: Alert existing resources that a new resource has joined
                        name = '%s%%%s@%s' % (channel, server, config.jid)
                        for cnick in conn.channels[channel].members.keys():
                            if cnick == conn.nickname:
                                #if config.dumpProtocol: print 'nnick %s %s %s'%(name,cnick,nick)
                                m = Presence(to=conn.fromjid,frm='%s/%s' %(name, nick))
                            else:
                                #if config.dumpProtocol: print 'cnick %s %s %s'%(name,cnick,nick)
                                m = Presence(to=conn.fromjid,frm='%s/%s' %(name, cnick))
                            t=m.addChild(name='x',namespace=NS_MUC_USER)
                            p=t.addChild(name='item',attrs=conn.channels[channel].members[cnick])
                            self.jabber.send(m)
                return 1
            else:
                if conn.xresources.has_key(resource):
                    #update resource record
                    conn.xresources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),conn.xresources[resource][3])
                    if config.dumpProtocol: print "Update server resource login: %s" % conn.xresources
                else:
                    #new resource login
                    conn.xresources[resource]=(event.getShow(),event.getPriority(),event.getStatus(),time.time())
                    if config.dumpProtocol: print "New server resource login: %s" % conn.xresources
                    self.jabber.send(Presence(to=frm, frm='%s@%s' % (server, config.jid)))
                    if conn.features.has_key('WATCH'):
                        conn.send_raw('WATCH')
                    else:
                        self.irc_doison(conn,1)
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
            conn.port = port
            conn.fromjid = fromjid
            conn.features = {}
            conn.joinchan = channel
            conn.joinresource = resource
            conn.xresources = {}
            conn.channels = {}
            conn.pendingoperations = {}
            conn.allpendingoperations = []
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

    def irc_newroom(self,conn,channel):
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
                        if config.dumpProtocol: print "Deleted channel resource login: %s" % conn.channels[channel].resources
                        if conn.channels[channel].resources == {}:
                            self.irc_leaveroom(conn,channel)
                            del conn.channels[channel]
                            self.irc_testinuse(conn,message)
                        return 1
                else:
                    if conn.xresources.has_key(resource):
                        del conn.xresources[resource]
                    if config.dumpProtocol: print "Deleted server resource login: %s" % conn.xresources
                    if conn.xresources == {}:
                        if config.dumpProtocol: print 'No more resource logins'
                        self.irc_doquit(conn,message)
                    return 1
        return None

    def find_highest_resource(self,resources):
        age = None
        priority = None
        resource = None
        for each in resources.keys():
            #if config.dumpProtocol: print each,resources
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
           conn.part([channel.encode(conn.charset,'replace')])
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
                    sys.exc_clear()
                conn.features[key] = value
        #if config.dumpProtocol: print 'features:%s'%repr(conn.features)

        fromstripped = conn.fromjid.encode('utf8')
        if userfile.has_key(fromstripped) \
          and userfile[fromstripped].has_key('servers') \
          and userfile[fromstripped]['servers'].has_key(conn.server):
            conf = userfile[fromstripped]['servers'][conn.server]
            if conf.has_key('subscriptions'):
                subscriptions = conf['subscriptions']
                if conn.features.has_key('WATCH'):
                    if conn.isontimer in timerlist:
                        timerlist.remove(conn.isontimer)
                        for nick in subscriptions:
                            conn.send_raw('WATCH +%s' % nick.encode(conn.charset,'replace'))

    def irc_doison(self,conn,force=0):
        if force or time.time() - conn.lastdoison > 10:
            fromstripped = conn.fromjid.encode('utf8')
            if userfile.has_key(fromstripped) \
              and userfile[fromstripped].has_key('servers') \
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
            conn.lastdoison = time.time()

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
        conn.lastdoison=0
        timerlist.append(conn.isontimer)

        if conn.joinchan:
            self.irc_newroom(conn,conn.joinchan)
        #TODO: channel join operations should become pending operations
        #       so that they can be tracked correctly
        #       and so that we can send errors to the right place
        conn.joinchan = None
        conn.joinresource = None

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
        if not conn.channels.has_key(channel):
            self.irc_newroom(conn,channel)
        if nick not in conn.channels[channel].members.keys():
            conn.channels[channel].members[nick]={'affiliation':'none','role':'visitor','jid':jid}
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, config.jid, nick))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs=conn.channels[channel].members[nick])
        #if config.dumpProtocol: print m.__str__()
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
        key = "whois:" + nick
        if conn.pendingoperations.has_key(key):
            m = conn.pendingoperations[key]
            return m.getTag('vCard', namespace=NS_VCARD)
        else:
            self.irc_rawtext(conn,'whois',event,' '.join(event.arguments()[1:]))

    def irc_whoisuser(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        if p:
            p.setTagData(tag='FN', val=unicode(event.arguments()[4],conn.charset,'replace'))
            p.setTagData(tag='NICKNAME', val=unicode(event.arguments()[0],conn.charset,'replace'))
            e = p.addChild(name='EMAIL')
            e.setTagData(tag='USERID', val=unicode(event.arguments()[1],conn.charset,'replace') + '@' + unicode(event.arguments()[2],conn.charset,'replace'))

    def irc_whoisserver(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        if p:
            o = p.addChild(name='ORG')
            o.setTagData(tag='ORGUNIT', val=unicode(event.arguments()[1],conn.charset,'replace'))
            o.setTagData(tag='ORGNAME', val=unicode(event.arguments()[2],conn.charset,'replace'))

    def irc_whoisoperator(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        if p:
            p.setTagData(tag='ROLE', val=unicode(event.arguments()[1],conn.charset,'replace'))

    def irc_whoisidle(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        if p:
            seconds = int(event.arguments()[1])
            minutes, seconds = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            p.setTagData(tag='DESC', val=p.getTagData(tag='DESC') + '\x0a' + 'Idle: %s hours %s mins %s secs' % (hours, minutes, seconds))
            if len(event.arguments()) > 3:
                p.setTagData(tag='DESC', val=p.getTagData(tag='DESC') + '\x0a' + 'Signon Time: ' + time.ctime(float(event.arguments()[2])))

    def irc_whoischannels(self,conn,event):
        p = self.irc_whoisgetvcard(conn,event)
        if p:
            p.setTagData(tag='TITLE', val=unicode(event.arguments()[1],conn.charset,'replace'))

    def irc_endofwhois(self,conn,event):
        nick = irc_ulower(unicode(event.arguments()[0],conn.charset,'replace'))
        key = "whois:" + nick
        if conn.pendingoperations.has_key(key):
            m = conn.pendingoperations[key]
            del conn.pendingoperations[key]
            self.jabber.send(m)
        else:
            self.irc_rawtext(conn,'whois',event,' '.join(event.arguments()[1:]))

    def irc_list(self,conn,event):
        if not pendingop_call(conn, 'list', event):
            self.irc_rawtext(conn,'list',event,' '.join(event.arguments()))

    def irc_list_items(self,conn,event,op,rep):
        if op == 'fail':
            self.jabber.send(Error(rep,ERR_RESOURCE_CONSTRAINT,reply=0))
            return True
        chan = event.arguments()[0]
        if irclib.is_channel(chan):
            chan = unicode(chan,conn.charset,'replace')
            q=rep.getTag('query')
            q.addChild('item',{'name':chan,'jid':'%s%%%s@%s' % (JIDEncode(chan), conn.server, config.jid)})
        return True

    def irc_list_info(self,conn,event,op,rep):
        if op == 'fail':
            self.jabber.send(Error(rep,ERR_RESOURCE_CONSTRAINT,reply=0))
            return True
        chan = event.arguments()[0]
        if irclib.is_channel(chan):
            membercount = event.arguments()[1]
            line,xhtml = colourparse(event.arguments()[2],conn.charset)
            chan = unicode(chan,conn.charset,'replace')
            q=rep.getTag('query')
            q.addChild('identity',{'category':'conference','type':'irc','name':chan})
            form = DataForm(typ='result',data=[
                DataField(                            name='FORM_TYPE'             ,value=NS_MUC_ROOMINFO,typ='hidden'),
                DataField(label='Subject'            ,name='muc#roominfo_subject'  ,value=line           ,typ='text-single'),
                DataField(label='Number of occupants',name='muc#roominfo_occupants',value=membercount    ,typ='text-single')])
            q.addChild(node=form)
        return True

    def irc_list_search(self,conn,event,op,rep):
        if op == 'fail':
            self.jabber.send(Error(rep,ERR_RESOURCE_CONSTRAINT,reply=0))
            return True
        chan = event.arguments()[0]
        if irclib.is_channel(chan):
            membercount = event.arguments()[1]
            line,xhtml = colourparse(event.arguments()[2],conn.charset)
            chan = unicode(chan,conn.charset,'replace')
            q=rep.getTag('query')
            form = q.getTag('x',namespace=NS_DATA)
            item = Node('item',payload=[
                DataField(name='jid'                   ,value='%s%%%s@%s' % (JIDEncode(chan), conn.server, config.jid)),
                DataField(name='name'                  ,value=chan),
                DataField(name='muc#roominfo_subject'  ,value=line),
                DataField(name='muc#roominfo_occupants',value=membercount)])
            form.addChild(node=item)
        return True

    def irc_listend(self,conn,event):
        rep = pendingop_pop(conn,'list')
        if rep:
            self.jabber.send(rep)
        else:
            self.irc_rawtext(conn,'list',event,' '.join(event.arguments()))

    def irc_tryagain(self,conn,event):
        if not pendingop_fail(conn, event):
            self.irc_rawtext(conn,conn.get_server_name(),event,' '.join(event.arguments()))

    def irc_motdstart(self,conn,event):
        try:
            nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        except:
            nick = conn.server
            sys.exc_clear()
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

    def irc_rawtext(self,conn,resource,event,msg):
        frm = '%s@%s/%s' %(conn.server,config.jid,resource)
        line,xhtml = colourparse(msg,conn.charset)
        m = Message(to=conn.fromjid,body=line,typ='chat',frm=frm,payload = [xhtml])
        self.jabber.send(m)

    def nm_is_service(self,conn,nickmask):
        if not nickmask:
            return True
        try:
            userhost = unicode(irclib.nm_to_uh(nickmask),conn.charset,'replace')
        except IndexError:
            sys.exc_clear()
            return True
        try:
            user,host = userhost.lower().split('@', 1)
            servername = conn.get_server_name().lower()
            serverprefix,serverdomain = servername.split('.', 1)
            #server_name        nickname!ident@host
            #irc.zanet.net:     NickServ!services@zanet.net
            #irc.lagnet.org.za: NickServ!services@lagnet.org.za
            #irc.zanet.org.za:  NickServ!NickServ@zanet.org.za
            if host == serverdomain: return True
            #irc.za.ethereal.web.za: Nik!services@ethereal.web.za
            if user == 'services' and ('.%s'%host == servername[-len(host)-1:]): return True
            #irc.oftc.net:      NickServ!services@services.oftc.net
            #irc.za.somewhere:  NickServ!services@services.somewhere
            if user == 'services' and (host == 'services%s'%servername[-len(host)+8:]): return True
            #irc.freenode.net:  NickServ!NickServ@services.
            if host == 'services.': return True
        except:
            sys.exc_clear()
        return False

    def nm_to_jidinfo(self,conn,nickmask):
        try:
            nick = unicode(irclib.nm_to_n(nickmask),conn.charset,'replace')
        except:
            nick = conn.server
            sys.exc_clear()
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
                sys.exc_clear()

            if conn.channels.has_key(channel):
                resources = conn.channels[channel].resources
            else:
                resources = conn.xresources

            if resources != {}:
                return chat[0],'%s/%s'%(conn.fromjid,self.find_highest_resource(resources)),chat[3]
            else:
                return chat[0],conn.fromjid,chat[3]
        if self.nm_is_service(conn,nickmask):
            frm = '%s@%s/%s' %(conn.server,config.jid,nick)
        else:
            frm = '%s%%%s@%s' %(nick,conn.server,config.jid)
        return frm,conn.fromjid,{}

    def irc_privmsg(self,conn,event,msg):
        if irclib.is_channel(event.target()):
            type = 'groupchat'
            channel = irc_ulower(unicode(event.target(),conn.charset,'replace'))
            line,xhtml = colourparse(msg,conn.charset)
            #if config.dumpProtocol: print (line,xhtml)
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

    def irc_nowaway(self,conn,event):
        self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(conn.server, config.jid), show='away'))

    def irc_unaway(self,conn,event):
        self.jabber.send(Presence(to=conn.fromjid, frm = '%s@%s' %(conn.server, config.jid)))

    def irc_ctcp(self,conn,event):
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if event.arguments()[0] == 'ACTION':
            self.irc_privmsg(conn,event,'/me '+event.arguments()[1])
        elif event.arguments()[0] == 'VERSION':
            conn.ctcp_reply(irclib.nm_to_n(event.source()).encode(conn.charset,'replace'),'VERSION ' + VERSTR + ' ' + version)
        elif event.arguments()[0] == 'CAPABILITIES':
            conn.ctcp_reply(irclib.nm_to_n(event.source()).encode(conn.charset,'replace'),'CAPABILITIES version,x:event')
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

    def xmpp_connect(self):
        connected = self.jabber.connect((config.mainServer,config.port))
        if config.dumpProtocol: print "connected:",connected
        while not connected:
            time.sleep(5)
            connected = self.jabber.connect((config.mainServer,config.port))
            if config.dumpProtocol: print "connected:",connected
        self.register_handlers()
        if config.dumpProtocol: print "trying auth"
        connected = self.jabber.auth(config.saslUsername,config.secret)
        if config.dumpProtocol: print "auth return:",connected
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
    print "Configuration file not found. You need to create a config file and put it in one of these locations:\n    " + "\n    ".join(config.configFiles)
    sys.exit(1)

def irc_add_conn(conn):
    socketlist[conn]='irc'

def irc_del_conn(conn):
    if socketlist.has_key(conn):
        del socketlist[conn]

def logError():
    err = '%s - %s\n'%(time.strftime('%a %d %b %Y %H:%M:%S'),version)
    if logfile != None:
        logfile.write(err)
        traceback.print_exc(file=logfile)
        logfile.flush()
    sys.stderr.write(err)
    traceback.print_exc()
    sys.exc_clear()

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

    if config.compjid:
        xcp=1
    else:
        xcp=0
        config.compjid = config.jid

    if config.saslUsername:
        sasl = 1
    else:
        config.saslUsername = config.jid
        sasl = 0

    userfile = shelve.open(config.spoolFile)
    logfile = None
    if config.debugFile:
        logfile = open(config.debugFile,'a')

    ircobj = irclib.IRC(fn_to_add_socket=irc_add_conn,fn_to_remove_socket=irc_del_conn)
    if config.dumpProtocol:
        debug=['always', 'nodebuilder']
    else:
        debug=[]
    connection = xmpp.client.Component(config.compjid,config.port,debug=debug,sasl=sasl,bind=config.useComponentBinding,route=config.useRouteWrap,xcp=xcp)
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
                        if config.dumpProtocol: print "disconnected by %s" % server.address
                        transport.irc_doquit(server)
            for each in socketlist.keys():
                try:
                    (ci, co, ce) = select.select([],[],[each],0)
                except socket.error:
                    irc_del_conn(each)
            sys.exc_clear()
            (i , o, e) = select.select(socketlist.keys(),[],[],1)
        for each in i:
            if socketlist[each] == 'xmpp':
                try:
                    connection.Process(1)
                except IOError:
                    transport.xmpp_disconnect()
                    sys.exc_clear()
                except:
                    logError()
                if not connection.isConnected(): transport.xmpp_disconnect()
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
    for each in [x for x in transport.users.keys()]:
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
        if os.name == 'nt': args = ["\"%s\"" % a for a in args]
        if config.dumpProtocol: print sys.executable, args
        os.execv(sys.executable, args)
