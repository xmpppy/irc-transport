
# Service administration commands Jep-0133 for the xmpppy based transports written by Mike Albon
import xmpp, string
from xmpp.protocol import *
import xmpp.commands
import config
from xml.dom.minidom import parse

"""This file is the JEP-0133 commands I feel are applicable to the transports.

Implemented commands as follows:

4.18 Registered_Users_Command: Return a list of Registered Users
4.21 Active_Users_Command : Return a list of Active Users
4.29 Edit_Admin_List_Command: Edit the Administrators list
4.31 Shutdown_Service_Command: Shuts down the Service


"""

NS_ADMIN = 'http://jabber.org/protocol/admin'
NS_ADMIN_ONLINE_USERS = NS_ADMIN+'#get-online-users'
NS_ADMIN_ACTIVE_USERS = NS_ADMIN+'#get-active-users'
NS_ADMIN_REGISTERED_USERS = NS_ADMIN+'#get-registered-users'
NS_ADMIN_EDIT_ADMIN = NS_ADMIN+'#edit-admin'
NS_ADMIN_RESTART = NS_ADMIN+'#restart'
NS_ADMIN_SHUTDOWN = NS_ADMIN+'#shutdown'
NS_COMMAND = 'http://jabber.org/protocol/commands'

class Online_Users_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the online users command as documented in section 4.20 of JEP-0133.
    At the current time, no provision is made for splitting the userlist into sections"""
    name = NS_ADMIN_ONLINE_USERS
    description = 'Get List of Online Users'
    discofeatures = [xmpp.commands.NS_COMMANDS,xmpp.NS_DATA]

    def __init__(self,users,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
        self.initial = { 'execute':self.cmdFirstStage }
        self.users = users

    def _DiscoHandler(self,conn,request,type):
        """The handler for discovery events"""
        if request.getFrom().getStripped() in config.admins:
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,request,type)
        else:
            return None

    def cmdFirstStage(self,conn,request):
        """Build the reply to complete the request"""
        if request.getFrom().getStripped() in config.admins:
            reply = request.buildReply('result')
            form = DataForm(typ='result',data=[DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='The list of online users',name='onlineuserjids',value=self.users.keys(),typ='jid-multi')])
            reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
            self._owner.send(reply)
        else:
            self._owner.send(Error(request,ERR_FORBIDDEN))
        raise NodeProcessed

class Active_Users_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the active users command as documented in section 4.21 of JEP-0133.
    At the current time, no provision is made for splitting the userlist into sections"""
    name = NS_ADMIN_ACTIVE_USERS
    description = 'Get List of Active Users'
    discofeatures = [xmpp.commands.NS_COMMANDS,xmpp.NS_DATA]

    def __init__(self,users,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
        self.initial = { 'execute':self.cmdFirstStage }
        self.users = users

    def _DiscoHandler(self,conn,request,type):
        """The handler for discovery events"""
        if request.getFrom().getStripped() in config.admins:
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,request,type)
        else:
            return None

    def cmdFirstStage(self,conn,request):
        """Build the reply to complete the request"""
        if request.getFrom().getStripped() in config.admins:
            reply = request.buildReply('result')
            form = DataForm(typ='result',data=[DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='The list of active users',name='activeuserjids',value=self.users.keys(),typ='jid-multi')])
            reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
            self._owner.send(reply)
        else:
            self._owner.send(Error(request,ERR_FORBIDDEN))
        raise NodeProcessed

class Registered_Users_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the active users command as documented in section 4.18 of JEP-0133.
    At the current time, no provision is made for splitting the userlist into sections"""
    name = NS_ADMIN_REGISTERED_USERS
    description = 'Get List of Registered Users'
    discofeatures = [xmpp.commands.NS_COMMANDS,xmpp.NS_DATA]

    def __init__(self,userfile,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
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
            reply = request.buildReply('result')
            form = DataForm(typ='result',data=[DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='The list of registered users',name='registereduserjids',value=self.userfile.keys(),typ='jid-multi')])
            reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=[form])
            self._owner.send(reply)
        else:
            self._owner.send(Error(request,ERR_FORBIDDEN))
        raise NodeProcessed


class Edit_Admin_List_Command(xmpp.commands.Command_Handler_Prototype):
    """This command enables the editing of the administrators list as documented in section 4.29 of JEP-0133.
    (the users of JEP-0133 commands in this case)"""
    name = NS_ADMIN_EDIT_ADMIN
    description = 'Edit Admin List'
    discofeatures = [xmpp.commands.NS_COMMANDS, xmpp.NS_DATA]

    def __init__(self,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
        self.initial = {'execute':self.cmdFirstStage }

    def _DiscoHandler(self,conn,request,type):
        """The handler for discovery events"""
        if request.getFrom().getStripped() in config.admins:
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,request,type)
        else:
            return None

    def cmdFirstStage(self,conn,request):
        """Set the session ID, and return the form containing the current administrators"""
        if request.getFrom().getStripped() in config.admins:
           # Setup session ready for form reply
           session = self.getSessionID()
           self.sessions[session] = {'jid':request.getFrom(),'actions':{'cancel':self.cmdCancel,'next':self.cmdSecondStage,'execute':self.cmdSecondStage}}
           # Setup form with existing data in
           reply = request.buildReply('result')
           form = DataForm(title='Editing the Admin List',data=['Fill out this form to edit the list of entities who have administrative privileges', DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='The Admin List', typ='jid-multi', name='adminjids',value=config.admins)])
           replypayload = [Node('actions',attrs={'execute':'next'},payload=[Node('next')]),form]
           reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'executing'},payload=replypayload)
           self._owner.send(reply)
        else:
           self._owner.send(Error(request,ERR_FORBIDDEN))
        raise NodeProcessed

    def cmdSecondStage(self,conn,request):
        """Apply and save the config"""
        form = DataForm(node=request.getTag(name='command').getTag(name='x',namespace=NS_DATA))
        session = request.getTagAttr('command','sessionid')
        if self.sessions.has_key(session):
            if self.sessions[session]['jid'] == request.getFrom():
                config.admins = form.getField('adminjids').getValues()
                doc = parse(config.configFile)
                admins = doc.getElementsByTagName('admins')[0]
                for el in [x for x in admins.childNodes]:
                    admins.removeChild(el)
                    el.unlink()
                for admin in config.admins:
                    txt = doc.createTextNode('\n        ')
                    admins.appendChild(txt)
                    txt = doc.createTextNode(admin)
                    el = doc.createElement('jid')
                    el.appendChild(txt)
                    admins.appendChild(el)
                txt = doc.createTextNode('\n    ')
                admins.appendChild(txt)
                attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'completed'}
                payload=[]
                try:
                    f = open(config.configFile,'w')
                    doc.writexml(f)
                    f.close()
                except IOError, (errno, strerror):
                    # attrs['status'] = 'canceled' # Psi doesn't display the form if we cancel the command
                    form = DataForm(typ='result',data=[DataField(value="I/O error(%s): %s" % (errno, strerror),typ='fixed')])
                    payload.append(form)
                doc.unlink()
                reply = request.buildReply('result')
                reply.addChild(name='command',attrs=attrs,payload=payload)
                self._owner.send(reply)
            else:
                self._owner.send(Error(request,ERR_BAD_REQUEST))
        else:
            self._owner.send(Error(request,ERR_BAD_REQUEST))   
        raise NodeProcessed

    def cmdCancel(self,conn,request):
        session = request.getTagAttr('command','sessionid')
        if self.sessions.has_key(session):
            del self.sessions[session]
            reply = request.buildReply('result')
            reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'canceled'})
            self._owner.send(reply)
        else:
            self._owner.send(Error(request,ERR_BAD_REQUEST))
        raise NodeProcessed


class Restart_Service_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the restart service command as documented in section 4.30 of JEP-0133."""
    name = NS_ADMIN_RESTART
    description = 'Restart Service'
    discofeatures = [xmpp.commands.NS_COMMANDS, xmpp.NS_DATA]

    def __init__(self,transport,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
        self.initial = {'execute':self.cmdFirstStage }
        self.transport = transport

    def _DiscoHandler(self,conn,request,type):
        """The handler for discovery events"""
        if request.getFrom().getStripped() in config.admins:
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,request,type)
        else:
            return None

    def cmdFirstStage(self,conn,request):
        """Set the session ID, and return the form containing the restart reason"""
        if request.getFrom().getStripped() in config.admins:
           # Setup session ready for form reply
           session = self.getSessionID()
           self.sessions[session] = {'jid':request.getFrom(),'actions':{'cancel':self.cmdCancel,'next':self.cmdSecondStage,'execute':self.cmdSecondStage}}
           # Setup form with existing data in
           reply = request.buildReply('result')
           form = DataForm(title='Restarting the Service',data=['Fill out this form to restart the service', DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='Announcement', typ='text-multi', name='announcement')])
           replypayload = [Node('actions',attrs={'execute':'next'},payload=[Node('next')]),form]
           reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'executing'},payload=replypayload)
           self._owner.send(reply)
        else:
           self._owner.send(Error(request,ERR_FORBIDDEN))
        raise NodeProcessed

    def cmdSecondStage(self,conn,request):
        """Apply and save the config"""
        form = DataForm(node=request.getTag(name='command').getTag(name='x',namespace=NS_DATA))
        session = request.getTagAttr('command','sessionid')
        if self.sessions.has_key(session):
            if self.sessions[session]['jid'] == request.getFrom():
                self.transport.offlinemsg = '\n'.join(form.getField('announcement').getValues())
                self.transport.restart = 1
                self.transport.online = 0
                reply = request.buildReply('result')
                reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'completed'})
                self._owner.send(reply)
            else:
                self._owner.send(Error(request,ERR_BAD_REQUEST))
        else:
            self._owner.send(Error(request,ERR_BAD_REQUEST))   
        raise NodeProcessed

    def cmdCancel(self,conn,request):
        session = request.getTagAttr('command','sessionid')
        if self.sessions.has_key(session):
            del self.sessions[session]
            reply = request.buildReply('result')
            reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'canceled'})
            self._owner.send(reply)
        else:
            self._owner.send(Error(request,ERR_BAD_REQUEST))
        raise NodeProcessed

class Shutdown_Service_Command(xmpp.commands.Command_Handler_Prototype):
    """This is the shutdown service command as documented in section 4.31 of JEP-0133."""
    name = NS_ADMIN_SHUTDOWN
    description = 'Shut Down Service'
    discofeatures = [xmpp.commands.NS_COMMANDS, xmpp.NS_DATA]

    def __init__(self,transport,jid=''):
        """Initialise the command object"""
        xmpp.commands.Command_Handler_Prototype.__init__(self,jid)
        self.initial = {'execute':self.cmdFirstStage }
        self.transport = transport

    def _DiscoHandler(self,conn,request,type):
        """The handler for discovery events"""
        if request.getFrom().getStripped() in config.admins:
            return xmpp.commands.Command_Handler_Prototype._DiscoHandler(self,conn,request,type)
        else:
            return None

    def cmdFirstStage(self,conn,request):
        """Set the session ID, and return the form containing the shutdown reason"""
        if request.getFrom().getStripped() in config.admins:
           # Setup session ready for form reply
           session = self.getSessionID()
           self.sessions[session] = {'jid':request.getFrom(),'actions':{'cancel':self.cmdCancel,'next':self.cmdSecondStage,'execute':self.cmdSecondStage}}
           # Setup form with existing data in
           reply = request.buildReply('result')
           form = DataForm(title='Shutting Down the Service',data=['Fill out this form to shut down the service', DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='Announcement', typ='text-multi', name='announcement')])
           replypayload = [Node('actions',attrs={'execute':'next'},payload=[Node('next')]),form]
           reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'executing'},payload=replypayload)
           self._owner.send(reply)
        else:
           self._owner.send(Error(request,ERR_FORBIDDEN))
        raise NodeProcessed

    def cmdSecondStage(self,conn,request):
        """Apply and save the config"""
        form = DataForm(node=request.getTag(name='command').getTag(name='x',namespace=NS_DATA))
        session = request.getTagAttr('command','sessionid')
        if self.sessions.has_key(session):
            if self.sessions[session]['jid'] == request.getFrom():
                self.transport.offlinemsg = '\n'.join(form.getField('announcement').getValues())
                self.transport.online = 0
                reply = request.buildReply('result')
                reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'completed'})
                self._owner.send(reply)
            else:
                self._owner.send(Error(request,ERR_BAD_REQUEST))
        else:
            self._owner.send(Error(request,ERR_BAD_REQUEST))   
        raise NodeProcessed

    def cmdCancel(self,conn,request):
        session = request.getTagAttr('command','sessionid')
        if self.sessions.has_key(session):
            del self.sessions[session]
            reply = request.buildReply('result')
            reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'canceled'})
            self._owner.send(reply)
        else:
            self._owner.send(Error(request,ERR_BAD_REQUEST))
        raise NodeProcessed
