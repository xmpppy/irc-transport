#!/usr/bin/python
# $Id$yeah
#
# xmpp->IRC transport
# Jan 2004 Copyright (c) Mike Albon
#
# This program is free software licensed with the GNU Public License Version 2.
# For a full copy of the license please go here http://www.gnu.org/licenses/licenses.html#GPL

import xmpp, urllib2, sys, time, irclib, re, ConfigParser, os, select, codecs, shelve
from xmpp.protocol import *
from xmpp.features import *

#import IPython.ultraTB
#sys.excepthook = IPython.ultraTB.FormattedTB(mode='Verbose', color_schme="Linux", call_pdb=0)


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
#server = '127.0.0.1'
#hostname = 'irc.localhost'
#port = 9000
#secret = 'secret'
socketlist = {}
timerlist = []

MALFORMED_JID=ErrorNode(ERR_JID_MALFORMED,text='Invalid JID, must be in form #room%server@transport')
NS_MUC = 'http://jabber.org/protocol/muc'
NS_MUC_USER = NS_MUC+'#user'
NS_MUC_ADMIN = NS_MUC+'#admin'
NS_MUC_OWNER = NS_MUC+'#owner'

def irc_add_conn(con):
    socketlist[con]='irc'
    
def irc_del_conn(con):
    #print "Have:" ,socketlist
    #print "Deleting:", con
    if socketlist.has_key(con):
        del socketlist[con]
    #print "Now have:", socketlist

#def irclib.irc_lower(nick):
#    nick=nick.lower()
#    nick=nick.replace'[','{').replace(']','}')
    #nick=nick.replace('\\','|')
    #return nick

def colourparse(str,charset):
    # Each tuple consists of String, foreground, background, bold.
    foreground=None
    background=None
    bold=None
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
            html.append((hs,foreground,background,bold))
            if bold == True:
                bold = None
            else:
                bold = True
            hs = ''
        elif e == '\x03':#'Cyan' Also Colour
            html.append((hs,foreground,background,bold))
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
            print 'White'
        elif e in ['\x10', '\x11', '\x12', '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1d', '\x1e', '\x1f']:
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
    try:
        s = unicode(s,'utf8','strict') # Language detection stuff should go here.
    except:
        s = unicode(s, charset,'replace')
    return s
  
  
def connectxmpp():
    global connection
    connection = xmpp.client.Component(hostname,port)
    try: connection.auth(hostname,secret)
    except: pass
    connection.connect((server,port))
    while 1:
        time.sleep(5)
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
        self.register_handlers()
    
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
        self.jabber.RegisterHandler('iq',self.xmpp_iq_discoinfo,typ = 'get', ns=NS_DISCO_INFO)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_discoitems,typ = 'get', ns=NS_DISCO_ITEMS)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_version,typ = 'get', ns=NS_VERSION)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_agents,typ = 'get', ns=NS_AGENTS)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_browse,typ = 'get', ns=NS_BROWSE)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucadmin_set,typ = 'set', ns=NS_MUC_ADMIN)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_mucadmin_get,typ = 'get', ns=NS_MUC_ADMIN)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_register_set,typ = 'set', ns=NS_REGISTER)
        self.jabber.RegisterHandler('iq',self.xmpp_iq_register_get,typ = 'get', ns=NS_REGISTER)
#        self.jabber.RegisterDisconnectHandler(self.xmpp_disconnect)
    #XMPP Handlers
    def xmpp_presence(self, con, event):
        # Add ACL support
        fromjid = event.getFrom().getStripped()
        fromstripped = fromjid.encode('utf-8')
        type = event.getType()
        if type == None: type = 'available'
        to = event.getTo()
        room = to.getNode().lower()
        nick = to.getResource()
        try:
            channel, server = room.split('%')
        except ValueError:
            channel=''
        if irclib.is_channel(channel):
            if type == 'available':
                #print nick
                if nick != '':
                    if not self.users.has_key(fromjid): # if a new user session
                        c=self.irc_newconn(channel,server,nick,fromjid)
                        if c != None:
                            self.users[fromjid] = {server:c}
                    else:
                        if self.users[fromjid].has_key(server):
                            if self.users[fromjid][server].memberlist.has_key(channel):
                                #pass # This is the nickname change case -- need to do something with this.
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
                        if event.getTo().getResource() == self.users[fromjid][server].nickname:
                            if self.users[fromjid][server].memberlist.has_key(channel):
                                connection = self.users[fromjid][server]
                                self.irc_leaveroom(connection,channel)
                                del self.users[fromjid][server].memberlist[channel]
                                #del self.users[fromjid][0][(channel,server)]
                                #need to add server connection tidying
                                self.test_inuse(connection)
                        else:
                            self.jabber.send(Error(event,ERR_BAD_REQUEST))
            else:
                self.jabber.send(Error(event,ERR_FEATURE_NOT_IMPLEMENTED))
        elif to == hostname:
            if type == 'subscribe':
                self.jabber.send(Presence(to=fromjid, frm = to, typ = 'subscribed'))
                conf = userfile[fromstripped]
                conf['usubscribed']=True
                userfile[fromstripped]=conf
            elif type == 'subscribed':
                if userfile.has_key(fromstripped):
                    conf = userfile[fromstripped]
                    conf['subscribed']=True
                    userfile[fromstripped]=conf
                else:
                    self.jabber.send(Error(event,ERR_BAD_REQUEST))
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
        fromjid = event.getFrom().getStripped()
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
        #print channel, server, fromjid, self.users[fromjid][0][(channel,server)]
        if type == 'groupchat':
            if irclib.is_channel(channel):
                if event.getSubject():
                    if (self.users[fromjid][server].chanmode['topic']==True and self.users[fromjid][server].memberlist[self.users[fromjid][server].nickname]['role'] == 'moderator') or self.users[fromjid][server].chanmode['topic']==False:
                        self.irc_settopic(self.users[fromjid][server],channel,event.getSubject())
                    else:
                        self.jabber.send(Error(event,ERR_FORBIDDEN))
                elif event.getBody() != '':
                    if event.getBody()[0:3] == '/me':
                        self.irc_sendctcp('ACTION',self.users[fromjid][server],channel,event.getBody()[4:])
                    else:
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
        #raise xmpp.NodeProcessed
        
    def xmpp_iq_discoitems(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        id = event.getID()
        m = Iq(to=fromjid,frm=to, typ='result', queryNS=NS_DISCO_ITEMS)
        m.setID(id)
        self.jabber.send(m)
        #raise xmpp.NodeProcessed
        
    
    def xmpp_iq_agents(self, con, event):
        m = Iq(to=event.getFrom(), frm=event.getTo(), typ='result', payload=[Node('agent', attrs={'jid':hostname},payload=[Node('service',payload='irc'),Node('name',payload='xmpp IRC Transport'),Node('groupchat')])])
        m.setID(event.getID())
        self.jabber.send(m)
        #raise xmpp.NodeProcessed
    
    def xmpp_iq_browse(self, con, event):
        m = Iq(to = event.getFrom(), frm = event.getTo(), typ = 'result', queryNS = NS_BROWSE)
        if event.getTo() == hostname:
            m.setTagAttr('query','catagory','conference')
            m.setTagAttr('query','name','xmpp IRC Transport')
            m.setTagAttr('query','type','irc')
            m.setTagAttr('query','jid','hostname')
            m.setPayload([Node('ns',payload=NS_MUC),Node('ns',payload=xmpp.NS_REGISTER)])
        self.jabber.send(m)
        #raise xmpp.NodeProcessed
    
    def xmpp_iq_version(self, con, event):
        fromjid = event.getFrom()
        to = event.getTo()
        id = event.getID()
        m = Iq(to = fromjid, frm = to, typ = 'result', queryNS=NS_VERSION, payload=[Node('name',payload='xmpp IRC Transport'), Node('version',payload='early release 12feb04'),Node('os',payload='%s %s %s' % (os.uname()[0],os.uname()[2],os.uname()[4]))])
        m.setID(id)
        self.jabber.send(m)
        #raise xmpp.NodeProcessed
    
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
        if self.users[fromjid][server].memberlist[self.users[fromjid][server].nick]['role'] != 'moderator' or self.users[fromjid][server].memberlist[self.users[fromjid][server].nick]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            return
        for each in t:
            if t[0].getName() == 'item':
                attr = t[0].getAttrs()
                if attr.has_key('role'):
                    if attr['role'] == 'moderator':
                        self.users[fromjid][server].mode(channel,'%s %s'%('+o',attr['nick']))    
                    elif attr['role'] == 'participant':
                        self.users[fromjid][server].mode(channel,'%s %s'%('+v',attr['nick']))
                    elif attr['role'] == 'visitor':
                        self.users[fromjid][server].mode(channel,'%s %s'%('-v',attr['nick']))
                        self.users[fromjid][server].mode(channel,'%s %s'%('-o',attr['nick']))
                    elif attr['role'] == 'none':
                        self.users[fromjid][server].kick(channel,attr['nick'],'Kicked')#Need to add reason gathering
    
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
        if self.users[fromjid][server].memberlist[self.users[fromjid][server].nick]['role'] != 'moderator' or self.users[fromjid][server].memberlist[self.users[fromjid][server].nick]['affiliation'] != 'owner':
            self.jabber.send(Error(event,ERR_FORBIDDEN))
            return
        datafrm = DataForm(data=self.users[fromjid][server].chanlist[channel])
        self.jabber.send(Iq(frm = to, to = fromjid, id = id, type='result', queryNS= ns, queryPayload = datafrm))
        
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
        if self.users[fromjid][server].memberlist[self.users[fromjid][server].nick]['role'] != 'moderator' or self.users[fromjid][server].memberlist[self.users[fromjid][server].nick]['affiliation'] != 'owner':
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
                    for item in self.users[fromjid][server].chanmode[each]:
                        if item not in datafrm[each]:
                            self.users[fromjid][server].mode(channel,'-b %s' % item)
                elif each == 'limit':
                    cmd = 'l'
                    typ = '+'
                    val = True
                    self.users[fromjid][server].mode(channel,'+l %s' % each)
                elif each == 'key':
                    cmd = 'k'
                    typ = '+'
                    val = True
                    self.users[fromjid][server].mode(channel, '+k %s' % each)
                if not val:    
                    self.users[fromjid][server].mode(channel,'%s%s' % (typ,cmd))
                              
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
                        
    def xmpp_iq_register_set(self, con, event):
        remove = False
        
        fromjid = event.getFrom().getStripped().encode('utf8')
        ucharset = charset
        for each in event.getQueryPayload():
            if each.getName() == 'charset':
                ucharset = each.getData()
            elif each.getName() == 'remove':
                remove = True
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
            
    #IRC methods
    def irc_doquit(self,con):
        server = con.server
        nickname = con.nickname
        if self.users[con.fromjid].has_key(server):
            del self.users[con.fromjid][server]
            con.close()
        
    def irc_settopic(self,connection,channel,line):
        connection.topic(channel.encode(connection.charset),line.encode(connection.charset))
    
    def irc_sendnick(self,connection,nick):
        connection.nick(nick)
    
    def irc_sendroom(self,connection,channel,line):
        lines = line.split('/n')
        for each in lines:
            #print channel, each
            connection.privmsg(channel.encode(connection.charset),each.encode(connection.charset))

    def irc_sendctcp(self,type,connection,channel,line):
        lines = line.split('/n')
        for each in lines:
            #print channel, each
            connection.ctcp(type,channel.encode(connection.charset),each.encode(connection.charset))

    def irc_newconn(self,channel,server,nick,fromjid):
        try:
            c=self.irc.server().connect(server,6667,nick,localaddress=localaddress)
            c.fromjid = fromjid
            fromstripped = fromjid.encode('utf-8')
            c.joinchan = channel
            c.memberlist = {}
            c.chanmode = {}
            if userfile.has_key(fromstripped):
                c.charset = userfile[fromstripped]['charset']
            else:
                c.charset = charset
            #c.join(channel)
            #c.who(channel) 
            return c
        except irclib.ServerConnectionError:
            self.jabber.send(Error(Presence(to = fromjid, frm = '%s%%%s@%s/%s' % (channel,server,hostname,nick)),ERR_SERVICE_UNAVAILABLE,reply=0))  # Other candidates: ERR_GONE, ERR_REMOTE_SERVER_NOT_FOUND, ERR_REMOTE_SERVER_TIMEOUT
            return None
            
    def irc_newroom(self,conn,channel):
        conn.join(channel)
        conn.who(channel)
        #conn.topic(channel)
        conn.memberlist[channel] = {}
        conn.chanmode[channel] = {'private':False, 'secret':False, 'invite':False, 'topic':False, 'notmember':False, 'moderated':False, 'banlist':[], 'limit':False, 'key':''}

    def irc_leaveroom(self,conn,channel):
        conn.part([channel])
    
    # IRC message handlers

    def irc_error(self,conn,event):
        #conn.close()
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
                m = Presence(to=conn.fromjid,typ = 'available', frm = '%s%%%s@%s/%s' % (each,conn.server,hostname,new))
                self.jabber.send(m)
                t=conn.memberlist[each][old]
                del conn.memberlist[each][old]
                conn.memberlist[each][new] = t
                

    def irc_welcome(self,conn,event):
        self.irc_newroom(conn,conn.joinchan)
        del conn.joinchan
    
    def irc_nicknameinuse(self,conn,event):
        #if conn.joinchan:
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
        new = '%s%%%s@%s'% (event.arguments[1],conn.server, hostname)
        old = '%s%%%s@%s'% (event.arguments[0],conn.server, hostname)
        error=ErrorNode(ERR_REDIRECT,new)
        self.jabber.send(Presence(to=conn.fromjid, typ='error', frm = old, payload=[error]))
        conn.memberlist[event.arguments[1]]={}
        conn.part(event.arguments[1])
        
    
    def irc_mode(self,conn,event):
        #modelist = irclib.parse_channel_modes(event.arguments())
        faddr = '%s%%%s@%s' %(event.target().lower(),conn.server,hostname)
        if irclib.is_channel(event.target()):
            if event.arguments()[0] == '+o':
                # Give Chanop
                if irclib.irc_lower(event.target().lower()) in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        conn.memberlist[event.target().lower()][each]['role']='moderator'
                        m = Presence(to=conn.fromjid,typ='available',frm = '%s/%s' %(faddr,each))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.memberlist[event.target().lower()][each])
                        self.jabber.send(m)
            elif event.arguments()[0] in ['-o', '-v']:
                # Take Chanop or Voice
                if irclib.irc_lower(event.target().lower()) in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        conn.memberlist[event.target().lower()][each]['role']='visitor'
                        m = Presence(to=conn.fromjid,typ='available',frm = '%s/%s' %(faddr,each))
                        t = m.addChild(name='x',namespace=NS_MUC_USER)
                        p = t.addChild(name='item',attrs=conn.memberlist[event.target().lower()][each])
                        self.jabber.send(m)
            elif event.arguments()[0] == '+v':
                # Give Voice
                if irclib.irc_lower(event.target().lower()) in conn.memberlist.keys():
                    for each in event.arguments()[1:]:
                        conn.memberlist[event.target().lower()][each]['role']='participant'
                        m = Presence(to=conn.fromjid,typ='available',frm = '%s/%s' %(faddr,each))
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
                for each in event.arguments()[1:]:
                    conn.who(channel,each)
            elif each == 'v': #Voice status
                for each in event.arguments()[1:]:
                    conn.who(channel,each)
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
    
    def irc_kick(self,conn,event):
        type = 'unavailable'
        name = '%s%%%s' % (irclib.irc_lower(event.target()), conn.server)
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname,irclib.irc_lower(event.arguments()[0])))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs={'affiliation':'none','role':'none'})
        p.addChild(name='reason',payload=[colourparse(event.arguments()[1],conn.charset)])
        t.addChild(name='status',attrs={'code':'307'})
        self.jabber.send(m)
        #print self.users[conn.fromjid]
        if event.arguments()[0] == conn.nickname:
            if conn.memberlist.has_key(irclib.irc_lower(event.target())):
                del conn.memberlist[irclib.irc_lower(event.target())]
        self.test_inuse(conn)
        
    def irc_topic(self,conn,event):
        nick = unicode(event.source().split('!')[0],conn.charset,'replace')
        channel = event.target().lower()
        if len(event.arguments())==2:
            line = colourparse(event.arguments()[1],conn.charset)
        else:
            line = colourparse(event.arguments()[0],conn.charset)
        m = Message(to=conn.fromjid,frm = '%s%%%s@%s/%s' % (event.arguments()[0].lower(),conn.server,hostname,nick), typ='groupchat', subject = line)
        self.jabber.send(m)
        
    def irc_join(self,conn,event):
        type = 'available'
        name = '%s%%%s' % (irclib.irc_lower(event.target()), conn.server)
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if nick not in conn.memberlist[irclib.irc_lower(unicode(event.target(),'utf-8','replace').encode('utf-8'))].keys():
            conn.memberlist[irclib.irc_lower(event.target())][nick]={'affiliation':'none','role':'none'}
        m = Presence(to=conn.fromjid,typ=type,frm='%s@%s/%s' %(name, hostname, nick))
        t=m.addChild(name='x',namespace=NS_MUC_USER)
        p=t.addChild(name='item',attrs={'affiliation':'none','role':'visitor'})
        #print m.__str__()
        self.jabber.send(m)
      
    def irc_whoreply(self,conn,event):
        name = '%s%%%s' % (event.arguments()[0].lower(), conn.server)
        faddr = '%s@%s/%s' % (name, hostname, unicode(event.arguments()[4],conn.charset,'replace'))
        m = Presence(to=conn.fromjid,typ='available',frm=faddr)
        t = m.addChild(name='x', namespace=NS_MUC_USER)
        affiliation = 'none'
        role = 'none'
        if '@' in event.arguments()[5]:
            role = 'moderator'
            #affiliation = 'admin' 
        elif '+' in event.arguments()[5]:
            role = 'participant'
            #affiliation = 'member'
        elif '*' in event.arguments()[5]:
            affiliation = 'admin'
        elif role == 'none':
            role = 'visitor'
            #affiliation = 'none'
        p=t.addChild(name='item',attrs={'affiliation':affiliation,'role':role})
        self.jabber.send(m)
        try:
            if (event.arguments()[0] != '*') and (unicode(event.arguments()[4],conn.charset,'replace') not in conn.memberlist[event.arguments()[0].lower()].keys()):
                conn.memberlist[event.arguments()[0].lower()][unicode(event.arguments()[4],conn.charset,'replace')]={'affiliation':affiliation,'role':role}
        except KeyError:
            pass
        #conn.mode(event.arguments()[4],'')
        #add mode request in here
        
    def irc_message(self,conn,event):
        try:
            nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        except:
            nick = conn.server
        if irclib.is_channel(event.target()):
            type = 'groupchat'
            room = '%s%%%s' %(event.target().lower(),conn.server)
            m = Message(to=conn.fromjid,body=colourparse(event.arguments()[0].lower(),conn.charset),typ=type,frm='%s@%s/%s' %(room, hostname,nick))
        else:
            type = 'chat'
            name = event.source()
            name = '%s%%%s' %(nick,conn.server)
            m = Message(to=conn.fromjid,body=colourparse(event.arguments()[0].lower(),conn.charset),typ=type,frm='%s@%s' %(name, hostname))
        #print m.__str__()
        self.jabber.send(m)                     
     
    def irc_ctcp(self,conn,event):
        nick = unicode(irclib.nm_to_n(event.source()),conn.charset,'replace')
        if event.arguments()[0] == 'ACTION':
            if irclib.is_channel(event.target()):
                type = 'groupchat'
                room = '%s%%%s' %(event.target().lower(),conn.server)
                
                m = Message(to=conn.fromjid,body='/me '+colourparse(event.arguments()[1],conn.charset),typ=type,frm='%s@%s/%s' %(room, hostname,nick))
            else:
                type = 'chat'
                name = event.source()
                try:
                    name = '%s%%%s' %(nick,conn.server)
                except:
                    name = '%s%%%s' %(conn.server,conn.server)
                m = Message(to=conn.fromjid,body='/me '+colourparse(event.arguments()[1],conn.charset),typ=type,frm='%s@%s' %(name, hostname))
            #print m.__str__()
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
#        self.register_handlers()
            
import pdb
if __name__ == '__main__':
    userfile = shelve.open('user.dbm')
    configfile = ConfigParser.ConfigParser()
    configfile.add_section('transport')
    try:
        cffile = open('transport.ini','r')
    except IOError:
        print "Transport requires configuration file, please supply"    
        sys.exit(1)
    configfile.readfp(cffile)
    server = configfile.get('transport','Server')
    #print server
    hostname = configfile.get('transport','Hostname')
    #print hostname
    port = int(configfile.get('transport','Port'))
    secret = configfile.get('transport','Secret')
    if configfile.has_option('transport','LocalAddress'):
        localaddress = configfile.get('transport','LocalAddress')
    if configfile.has_option('transport','Charset'):
        charset = configfile.get('transport','Charset')
    #connection = xmpp.client.Component(hostname,port)
    #connection.connect((server,port))
    #connection.auth(hostname,secret)
    if not connectxmpp():
        print "Password mismatch!"
        sys.exit(1)
    ircobj = irclib.IRC(fn_to_add_socket=irc_add_conn,fn_to_remove_socket=irc_del_conn)
    socketlist[connection.Connection._sock]='xmpp'
    #jabber = ComponentThread(connection)
    #irc = IrcThread(ircobj)
    transport = Transport(connection,ircobj)
    while 1:
        (i , o, e) = select.select(socketlist.keys(),[],[],1)
        for each in i:
            if socketlist[each] == 'xmpp':
                #connection.Connection.receive()
#                pdb.run("connection.Process(0)")
#                print 1
                connection.Process(1)
                if not connection.isConnected():  transport.xmpp_disconnect()
#                print '=========================='
            else:
                ircobj.process_data([each])
