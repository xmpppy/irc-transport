#!/usr/bin/python
# $Id$
#
# xmpp->IRC transport
# Jan 2004 Copyright (c) Mike Albon
#
# This program is free software licensed with the GNU Public License Version 2.
# For a full copy of the license please go here http://www.gnu.org/licenses/licenses.html#GPL

import xmpp, urllib2, sys, time, irclib, re, ConfigParser, os, select, codecs, shelve, socket
from xmpp.protocol import *
from xmpp.features import *
from xmpp.browser import *
from xmpp.commands import *
from jep0133 import *
import xmpp.commands
import jep0133

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
NS_MUC = 'http://jabber.org/protocol/muc'
NS_MUC_USER = NS_MUC+'#user'
NS_MUC_ADMIN = NS_MUC+'#admin'
NS_MUC_OWNER = NS_MUC+'#owner'
NS_COMMAND = 'http://jabber.org/protocol/commands'
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
        self.irc.add_global_handler('motd',self.irc_message)
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
        self.disco = Browser()
        self.disco.plugin(self.jabber)
        self.command = Commands()
        self.command.plugin(self.jabber,self.disco)
        self.cmdactiveusers = Active_Users_Command(self, self.jabber)
        self.cmdactiveusers.plugin(self.command)
        self.cmdregisteredusers = Registered_Users_Command(self, self.jabber)
        self.cmdregisteredusers.plugin(self.command)
        self.cmdeditadminusers = Edit_Admin_List_Command(self, self.jabber, configfile, configfilename, administrators)
        self.cmdeditadminusers.plugin(self.command)
        self.disco.setDiscoHandler(self.xmpp_base_disco,node='',jid='')

    # New Disco Handlers
    def xmpp_base_disco(self, con, event, type):
        #Type is either 'info' or 'items'
        if type == 'info':
            return {'ids':[{'category':'conference','type':'irc','name':'IRC Transport'}],'features':[xmpp.NS_REGISTER,xmpp.NS_VERSION,NS_MUC,NS_COMMAND]}
        if type == 'items':
            return []

    #XMPP Handlers
    def xmpp_presence(self, con, event):
        # Add ACL support
        fromjid = str(event.getFrom())
        fromstripped = fromjid.encode('utf-8')
        type = event.getType()
        #if type == None: type = 'available'
        to = event.getTo()
        room = to.getNode().lower()
        nick = to.getResource()
        try:
            channel, server = room.split('%')
        except ValueError:
            channel=''
        if irclib.is_channel(channel):
            if type == None:
                if nick != '':
                    if not self.users.has_key(fromjid): # if a new user session
                        c=self.irc_newconn(channel,server,nick,fromjid)
                        if c != None:
                            self.users[fromjid] = {server:c}
                    else:
                        if self.users[fromjid].has_key(server):
                            if self.users[fromjid][server].memberlist.has_key(channel):
                                self.users[fromjid][server].joinchan = channel
                                self.irc_sendnick(self.users[fromjid][server],nick)
                            elif self.users[fromjid].has_key(server): # if user already has a session open on same server
                                self.irc_newroom(self.users[fromjid][server],channel)
                        else: # the other cases
                            c=self.irc_newconn(channel,server,nick,fromjid)
                            if c != None:
                                self.users[fromjid][server]=c
            elif type == 'unavailable':
                if self.users.has_key(fromjid):
                    if self.users[fromjid].has_key(server):
                        if event.getTo().getResource() == self.users[fromjid][server].nickname or event.getTo().getResource() == '':
                            if self.users[fromjid][server].memberlist.has_key(channel):
                                connection = self.users[fromjid][server]
                                self.irc_leaveroom(connection,channel)
                                del self.users[fromjid][server].memberlist[channel]
                                self.test_inuse(connection)
                        else:
                            self.jabber.send(Error(event,ERR_BAD_REQUEST))
            else:
                self.jabber.send(Error(event,ERR_FEATURE_NOT_IMPLEMENTED))
        elif to == hostname:
            if type == 'subscribe':
                if userfile.has_key(event.getFrom().getStripped().encode('utf8')):
                    self.jabber.send(Presence(to=fromjid, frm = to, typ = 'subscribed'))
                    conf = userfile[event.getFrom().getStripped().encode('utf8')]
                    conf['usubscribed']=True
                    userfile[event.getFrom().getStripped().encode('utf8')]=conf
                else:
                    self.jabber.send(Error(event,ERR_BAD_REQUEST))
            elif type == 'subscribed':
                if userfile.has_key(event.getFrom().getStripped().encode('utf8')):
                    conf = userfile[event.getFrom().getStripped().encode('utf8')]
                    conf['subscribed']=True
                    userfile[event.getFrom().getStripped().encode('utf8')]=conf
                else:
                    self.jabber.send(Error(event,ERR_BAD_REQUEST))
            #
            #Add code so people can see transport presence here
            #
            elif type == 'probe':
	    	self.jabber.send(Presence(to=fromjid, frm = to))
                if not userfile.has_key(event.getFrom().getStripped().encode('utf8')):
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribe'))
                    self.jabber.send(Presence(to=fromjid, frm=to, typ = 'unsubscribed'))
            elif type == 'unavailable':
	    	self.jabber.send(Presence(to=fromjid, frm = to, typ = 'unavailable'))
	    else:
	    	self.jabber.send(Presence(to=fromjid, frm = to))
        else:
            self.jabber.send(Error(event,MALFORMED_JID))
            return

    def test_inuse(self,connection):
        inuse = False
        for each in self.users[connection.fromjid].keys():
            if self.users[connection.fromjid][each].memberlist != {}:
                inuse = True
        if inuse == False:
            self.irc_doquit(connection)

    def xmpp_message(self, con, event):
        type = event.getType()
        fromjid = str(event.getFrom())
        to = event.getTo()
        room = to.getNode().lower()
        try:
            if event.getSubject.strip() == '':
                event.setSubject(None)
        except AttributeError:
            pass
        try:
            channel, server = room.split('%')
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            return
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
                print "channel:", event.getBody()
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
                    print "body isn't empty:" , event.getBody()
                    if event.getBody()[0:3] == '/me':
                        print "action"
                        self.irc_sendctcp('ACTION',self.users[fromjid][server],channel,event.getBody()[4:])
                    else:
                        print "room message"
                        self.irc_sendroom(self.users[fromjid][server],channel,event.getBody())
                    t = Message(to=fromjid,body=event.getBody(),typ=type,frm='%s@%s/%s' %(room, hostname,self.users[fromjid][server].nickname))
                    self.jabber.send(t)
            else:
                self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))  # or ERR_JID_MALFORMED maybe?
        elif type in ['chat', None]:
            if not irclib.is_channel(channel):
                # ARGH! need to know channel to find out nick. :(
                if event.getBody()[0:3] == '/me':
                    self.irc_sendctcp('ACTION',self.users[fromjid][server],channel,event.getBody()[4:])
                else:
                    self.irc_sendroom(self.users[fromjid][server],channel,event.getBody())
            else:
                if event.getBody()[0:3] == '/me':
                    self.irc_sendctcp('ACTION',self.users[fromjid][server],channel,event.getBody()[4:])
                else:
                    self.irc_sendroom(self.users[fromjid][server],event.getTo().getResource(),event.getBody())

    def xmpp_iq_discoinfo(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        id = event.getID()
        m = Iq(to=fromjid,frm=to, typ='result', queryNS=NS_DISCO_INFO, payload=[Node('identity',attrs={'category':'conference','type':'irc','name':'IRC Transport'}),Node('feature', attrs={'var':xmpp.NS_REGISTER}),Node('feature',attrs={'var':NS_MUC})])
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
        m = Iq(to = event.getFrom(), frm = event.getTo(), typ = 'result', queryNS = NS_BROWSE)
        if event.getTo() == hostname:
            m.setTagAttr('query','catagory','conference')
            m.setTagAttr('query','name','xmpp IRC Transport')
            m.setTagAttr('query','type','irc')
            m.setTagAttr('query','jid','hostname')
            m.setPayload([Node('ns',payload=NS_MUC),Node('ns',payload=xmpp.NS_REGISTER)])
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_version(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        id = event.getID()
        m = Iq(to = fromjid, frm = to, typ = 'result', queryNS=NS_VERSION, payload=[Node('name',payload='xmpp IRC Transport'), Node('version',payload='early release 12feb04'),Node('os',payload='%s %s %s' % (os.uname()[0],os.uname()[2],os.uname()[4]))])
        m.setID(id)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_mucadmin_get(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        room = to.getNode().lower()
        id = event.getID()
        try:
            channel, server = room.split('%')
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            return
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].memberlist.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            return
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
        room = to.getNode().lower()
        id = event.getID()
        try:
            channel, server = room.split('%')
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            return
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].memberlist.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            return
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['role'] != 'moderator' or self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            return
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
        room = to.getNode().lower()
        id = event.getID()
        try:
            channel, server = room.split('%')
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            return
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].memberlist.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            return
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['role'] != 'moderator' or self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            return
        datafrm = DataForm(data=self.users[fromjid][server].chanlist[channel])
        m = Iq(frm = to, to = fromjid, id = id, type='result', queryNS= ns, queryPayload = datafrm)
        m.setID(id)
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_mucowner_set(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        room = to.getNode().lower()
        id = event.getID()
        try:
            channel, server = room.split('%')
        except ValueError:
            self.jabber.send(Error(event,MALFORMED_JID))
            return
        if fromjid not in self.users.keys() \
          or server not in self.users[fromjid].keys() \
          or channel not in self.users[fromjid][server].memberlist.keys():
            self.jabber.send(Error(event,ERR_ITEM_NOT_FOUND))
            return
        ns = event.getQueryNS()
        t = event.getQueryPayload()
        if self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['role'] != 'moderator' or self.users[fromjid][server].memberlist[channel][self.users[fromjid][server].nickname]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            return
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
        if userfile.has_key(fromjid):
            charset = userfile[fromjid]['charset']
        m = event.buildReply('result')
        m.setQueryNS(NS_REGISTER)
        m.setQueryPayload([Node('instructions', payload = 'Please provide your legacy Character set or codepage. (eg cp437, cp1250, iso-8859-1, koi8-r)'),Node('charset',payload=charset)])
        self.jabber.send(m)
        raise xmpp.NodeProcessed

    def xmpp_iq_register_set(self, con, event):
        remove = False

        fromjid = event.getFrom().getStripped().encode('utf8')
        ucharset = charset
        #for each in event.getQueryPayload():
        #    if type(each ) == u'':
        #        pass
        #    if each.getName() == 'charset':
        #        ucharset = each.getData()
        #    elif each.getName() == 'remove':
        #        remove = True
        #    else:
        #        self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
        query = event.getTag('query')
        if query.getTag('remove'):
            remove = True
        elif query.getTag('charset'):
            ucharset = query.getTagData('charset')
        else:
            self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
        if not remove:
            if userfile.has_key(fromjid):
                conf = userfile[fromjid]
            else:
                conf = {}
            try:
                codecs.lookup(ucharset)
            except LookupError:
                self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
                return
            except ValueError:
                self.jabber.send(Error(event,ERR_NOT_ACCEPTABLE))
                return
            conf['charset']=ucharset
            userfile[fromjid]=conf
            self.jabber.send(Presence(to=event.getFrom(), frm = event.getTo()))
            if not conf.has_key('subscribed'):
                self.jabber.send(Presence(typ='subscribe',to=fromjid, frm=hostname))
        else:
            if userfile.has_key(fromjid):
                del userfile[fromjid]
            m = event.buildReply('result')
            self.jabber.send(m)
            m = Presence(to = event.getFrom(), frm = hostname, typ = 'unsubscribe')
            self.jabber.send(m)
            m = Presence(to = event.getFrom(), frm = hostname, typ = 'unsubscribed')
            self.jabber.send(m)
       	raise xmpp.NodeProcessed

    #IRC methods
    def irc_doquit(self,con):
        server = con.server
        nickname = con.nickname
        if self.users[con.fromjid].has_key(server):
            del self.users[con.fromjid][server]
            con.close()

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

    def irc_newconn(self,channel,server,nick,fromjid):
        try:
            c=self.irc.server().connect(server,6667,nick,localaddress=localaddress)
            c.fromjid = fromjid
            fromstripped = JID(fromjid).getStripped().encode('utf-8')
            c.joinchan = channel
            c.memberlist = {}
            c.chanmode = {}
            if userfile.has_key(fromstripped):
                c.charset = userfile[fromstripped]['charset']
            else:
                c.charset = charset
            return c
        except irclib.ServerConnectionError:
            self.jabber.send(Error(Presence(to = fromjid, frm = '%s%%%s@%s/%s' % (channel,server,hostname,nick)),ERR_SERVICE_UNAVAILABLE,reply=0))  # Other candidates: ERR_GONE, ERR_REMOTE_SERVER_NOT_FOUND, ERR_REMOTE_SERVER_TIMEOUT
            return None

    def irc_newroom(self,conn,channel):
        try:
           conn.join(channel)
           conn.who(channel)
        except:
           self.irc_doquit(connection)
        conn.memberlist[channel] = {}
        conn.chanmode[channel] = {'private':False, 'secret':False, 'invite':False, 'topic':False, 'notmember':False, 'moderated':False, 'banlist':[], 'limit':False, 'key':''}

    def irc_leaveroom(self,conn,channel):
        try:
           conn.part([channel])
        except:
            self.irc_doquit(connection)

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
        nick = irclib.nm_to_n(event.source())
        for each in conn.memberlist.keys():
            if nick in conn.memberlist[each].keys():
                del conn.memberlist[each][nick]
                name = '%s%%%s' % (each, conn.server)
                m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname,event.source().split('!')[0]))
                self.jabber.send(m)
                if activitymessages == True:
                    line,xhtml = colourparse(event.arguments()[0],conn.charset)
                    m = Message(to=conn.fromjid, typ='groupchat',frm='%s@%s' % (name, hostname), body='%s (%s) has quit (%s)' % (nick, irclib.nm_to_uh(event.source()), line))
                    self.jabber.send(m)

    def irc_nick(self, conn, event):
        old = irclib.nm_to_n(event.source())
        new = event.target()
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
        self.irc_newroom(conn,conn.joinchan)
        del conn.joinchan

    def irc_nicknameinuse(self,conn,event):
        error=ErrorNode(ERR_CONFLICT,text='Nickname is in use')
        self.jabber.send(Error(Presence(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' %(conn.joinchan, conn.server, hostname)),error,reply=0))

    def irc_nosuchchannel(self,conn,event):
        error=ErrorNode(ERR_ITEM_NOT_FOUND,'The channel is not found')
        self.jabber.send(Presence(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' %(event.arguments()[0], conn.server, hostname),payload=[error]))

    def irc_notregistered(self,conn,event):
        error=ErrorNode(ERR_FORBIDDEN,text='Not registered and registration is not supported')
        self.jabber.send(Presence(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' %(conn.joinchan, conn.server, hostname),payload=[error]))

    def irc_nosuchnick(self, conn, event):
        error=ErrorNode(ERR_ITEM_NOT_FOUND,text='Nickname not found')
        self.jabber.send(Message(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' % (event.source(), conn.server, hostname),payload=[error]))

    def irc_cannotsend(self,conn,event):
        error=ErrorNode(ERR_FORBIDDEN)
        self.jabber.send(Message(to=conn.fromjid, typ = 'error', frm = '%s%%%s@%s' % (event.source(), conn.server, hostname),payload=[error]))

    def irc_redirect(self,conn,event):
        new = '%s%%%s@%s'% (event.arguments()[1],conn.server, hostname)
        old = '%s%%%s@%s'% (event.arguments()[0],conn.server, hostname)
        error=ErrorNode(ERR_REDIRECT,new)
        self.jabber.send(Presence(to=conn.fromjid, typ='error', frm = old, payload=[error]))
        conn.memberlist[event.arguments()[1]]={}
        try:
           conn.part(event.arguments()[1])
        except:
           self.irc_doquit(connection)

    def irc_mode(self,conn,event):
    # Mode handling currently is very poor.
    #
    # Issues:
    # Multiple +b's currently not handled
    # +l or -l with no parameter not handled
        faddr = '%s%%%s@%s' %(event.target().lower(),conn.server,hostname)
        if irclib.is_channel(event.target()):
            if event.arguments()[0] == '+o':
                # Give Chanop
                if irclib.irc_lower(event.target().lower()) in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        conn.memberlist[event.target().lower()][each]['role']='moderator'
                        if each == conn.nickname:
                            conn.memberlist[event.target().lower()][each]['affiliation']='owner'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,each))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.memberlist[event.target().lower()][each])
                        self.jabber.send(m)
            elif event.arguments()[0] in ['-o', '-v']:
                # Take Chanop or Voice
                if irclib.irc_lower(event.target().lower()) in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        conn.memberlist[event.target().lower()][each]['role']='visitor'
                        conn.memberlist[event.target().lower()][each]['affiliation']='none'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,each))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.memberlist[event.target().lower()][each])
                        self.jabber.send(m)
            elif event.arguments()[0] == '+v':
                # Give Voice
                if irclib.irc_lower(event.target().lower()) in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        conn.memberlist[event.target().lower()][each]['role']='participant'
                        conn.memberlist[event.target().lower()][each]['affiliation']='none'
                        m = Presence(to=conn.fromjid,typ=None,frm = '%s/%s' %(faddr,each))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.memberlist[event.target().lower()][each])
                        self.jabber.send(m)

    def irc_chanmode(self,conn,event):
        # Very buggy, multiple items cases, ban etc.
        faddr = '%s%%%s@%s' %(event.target().lower(),conn.server,hostname)
        channel = event.target().lower()
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
                conn.chanmode[event.target().lower()]['private'] = plus
            elif each == 's': #Secret
                conn.chanmode[event.target().lower()]['secret'] = plus
            elif each == 'i': #invite only
                conn.chanmode[event.target().lower()]['invite'] = plus
            elif each == 't': #only chanop can set topic
                conn.chanmode[event.target().lower()]['topic'] = plus
            elif each == 'n': #no not in channel messages
                conn.chanmode[event.target().lower()]['notmember'] = plus
            elif each == 'm': #moderated chanel
                conn.chanmode[event.target().lower()]['moderated'] = plus
            elif each == 'l': #set channel limit
                conn.chanmode[event.target().lower()]['private'] = event.arguments()[1]
            elif each == 'b': #ban users
                # Need to fix multiple ban case.
                if plus:
                    conn.chanmode[event.target().lower()]['banlist'].append(event.arguments()[1])
                else:
                    if event.arguments()[1] in conn.chanmode[event.target().lower()]['banlist']:
                        conn.chanmode[event.target().lower()]['banlist'].remove(event.arguments()[1])
            elif each == 'k': #set channel key
                pass

    def irc_part(self,conn,event):
        type = 'unavailable'
        name = '%s%%%s' % (irclib.irc_lower(event.target()), conn.server)
        nick = irclib.nm_to_n(event.source())
        try:
            if nick in conn.memberlist[irclib.irc_lower(event.target())].keys():
                del conn.memberlist[irclib.irc_lower(event.target())][event.source().split('!')[0]]
        except KeyError:
            pass
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname,event.source().split('!')[0]))
        self.jabber.send(m)
        if activitymessages == True:
            m = Message(to=conn.fromjid, typ='groupchat',frm='%s@%s' % (name, hostname), body='%s (%s) has left' % (nick, irclib.nm_to_uh(event.source())))
            self.jabber.send(m)

    def irc_kick(self,conn,event):
        type = 'unavailable'
        name = '%s%%%s' % (irclib.irc_lower(event.target()), conn.server)
        jid = '%s%%%s@%s' % (irclib.irc_lower(event.arguments()[0]), conn.server, hostname)
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname,irclib.irc_lower(event.arguments()[0])))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs={'affiliation':'none','role':'none','jid':jid})
        p.addChild(name='reason',payload=[colourparse(event.arguments()[1],conn.charset)][0])
        t.addChild(name='status',attrs={'code':'307'})
        self.jabber.send(m)
        if event.arguments()[0] == conn.nickname:
            if conn.memberlist.has_key(irclib.irc_lower(event.target())):
                del conn.memberlist[irclib.irc_lower(event.target())]
        self.test_inuse(conn)

    def irc_topic(self,conn,event):
        nick = unicode(event.source().split('!')[0],conn.charset,'replace')
        if len(event.arguments())==2:
            channel = event.arguments()[0].lower()
            line,xhtml = colourparse(event.arguments()[1],conn.charset)
        else:
            channel = event.target().lower()
            line,xhtml = colourparse(event.arguments()[0],conn.charset)
        if activitymessages == True:
            m = Message(to=conn.fromjid,frm = '%s%%%s@%s/%s' % (unicode(channel,conn.charset,'replace'),conn.server,hostname,nick),body='/me set the topic to: %s' % line, typ='groupchat', subject = line)
        else:
            m = Message(to=conn.fromjid,frm = '%s%%%s@%s/%s' % (unicode(channel,conn.charset,'replace'),conn.server,hostname,nick), typ='groupchat', subject = line)
        self.jabber.send(m)

    def irc_join(self,conn,event):
        type = None
        name = '%s%%%s' % (unicode(irclib.irc_lower(event.target()),conn.charset,'replace'), conn.server)
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        jid = '%s%%%s@%s' % (nick, conn.server, hostname)
        if nick not in conn.memberlist[irclib.irc_lower(unicode(event.target(),'utf-8','replace').encode('utf-8'))].keys():
            conn.memberlist[irclib.irc_lower(event.target())][nick]={'affiliation':'none','role':'visitor','jid':jid}	
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname, nick))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs=conn.memberlist[irclib.irc_lower(event.target())][nick])
        #print m.__str__()
        self.jabber.send(m)
        if activitymessages == True:
            m = Message(to=conn.fromjid, typ='groupchat',frm='%s@%s' % (name, hostname), body='%s (%s) has joined' % (nick, irclib.nm_to_uh(event.source())))
            self.jabber.send(m)

    def irc_whoreply(self,conn,event):
        name = '%s%%%s' % (event.arguments()[0], conn.server)
        faddr = '%s@%s/%s' % (name, hostname, unicode(event.arguments()[4],conn.charset,'replace'))
        m = Presence(to=conn.fromjid,typ=None,frm=faddr)
        t = m.addChild(name='x', namespace=NS_MUC_USER)
        affiliation = 'none'
        role = 'none'
        if '@' in event.arguments()[5]:
            role = 'moderator'
            if event.arguments()[4] == conn.nickname:
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
            if (event.arguments()[0] != '*') and (unicode(event.arguments()[4],conn.charset,'replace') not in conn.memberlist[event.arguments()[0].lower()].keys()):
                conn.memberlist[event.arguments()[0].lower()][unicode(event.arguments()[4],conn.charset,'replace')]={'affiliation':affiliation,'role':role,'jid':jid}
        except KeyError:
            pass

    def irc_message(self,conn,event):
        try:
            nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        except:
            nick = conn.server
        if irclib.is_channel(event.target()):
            type = 'groupchat'
            room = '%s%%%s' %(event.target().lower(),conn.server)
            line,xhtml = colourparse(event.arguments()[0],conn.charset)
            #print (line,xhtml)
            m = Message(to=conn.fromjid,body= line,typ=type,frm='%s@%s/%s' %(room, hostname,nick),payload = [xhtml])
        else:
            type = 'chat'
            name = event.source()
            name = '%s%%%s' %(nick,conn.server)
            line,xhtml = colourparse(event.arguments()[0],conn.charset)
            m = Message(to=conn.fromjid,body= line,typ=type,frm='%s@%s' %(name, hostname),payload = [xhtml])
        self.jabber.send(m)

    def irc_ctcp(self,conn,event):
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if event.arguments()[0] == 'ACTION':
            if irclib.is_channel(event.target()):
                type = 'groupchat'
                room = '%s%%%s' %(event.target().lower(),conn.server)
                line,xhtml = colourparse('/me '+event.arguments()[1],conn.charset)
                m = Message(to=conn.fromjid,body=line,typ=type,frm='%s@%s/%s' %(room, hostname,nick),payload =[xhtml])
            else:
                type = 'chat'
                name = event.source()
                try:
                    name = '%s%%%s' %(nick,conn.server)
                except:
                    name = '%s%%%s' %(conn.server,conn.server)
                line,xhtml = colourparse('/me '+event.arguments()[1],conn.charset)
                m = Message(to=conn.fromjid,body= line,typ=type,frm='%s@%s' %(name, hostname),payload = [xhtml])
            self.jabber.send(m)
        elif event.arguments()[0] == 'VERSION':
            self.irc_sendctcp('VERSION',conn,event.source(),'xmpp IRC Transport')

    def xmpp_disconnect(self):
        for each in self.users.keys():
            for item in self.users[each].keys():
                self.irc_doquit(item)
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

    ircobj = irclib.IRC(fn_to_add_socket=irc_add_conn,fn_to_remove_socket=irc_del_conn)
    global connection
    connection = xmpp.client.Component(hostname,port)
    transport = Transport(connection,ircobj)
    transport.userfile = userfile
    if not connectxmpp(transport.register_handlers):
        print "Password mismatch!"
        sys.exit(1)
    socketlist[connection.Connection._sock]='xmpp'
    while 1:
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
                if not connection.isConnected():  transport.xmpp_disconnect()
            else:
                ircobj.process_data([each])
