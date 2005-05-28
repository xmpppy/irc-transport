
# Service administration commands Jep-0133 for the xmpppy based transports written by Mike Albon
import xmpp
from xmpp.protocol import *
import xmpp.commands

administrators = []

"""This file is the JEP-0133 commands I feel are applicable to the transports.

Implemented commands as follows:

4.12 Active_Users_Command : Return a list of Active Users
4.13 Registered_Users_Command: Return a list of Registered Users
4.20 Edit_Admin_List_Command: Edit the Administrators list


"""

NS_ADMIN = 'http://jabber.org/protocol/admin'
NS_ADMIN_ACTIVE_USERS = NS_ADMIN+'#get-active-users'
NS_ADMIN_REGISTERED_USERS = NS_ADMIN+'#get-registered-users'
NS_ADMIN_EDIT_ADMIN = NS_ADMIN+'#edit-admin'
NS_COMMAND = 'http://jabber.org/protocol/commands'

class Active_Users_Command(xmpp.commands.Command_Handler_Prototype):
	"""This is the active users command as documented in section 4.12  of JEP-0133.
	At the current time, no provision is made for splitting the userlist into sections"""
	name = NS_ADMIN_ACTIVE_USERS
	description = 'The command to list the current users of the transport'
	discofeatures = [xmpp.commands.NS_COMMANDS,xmpp.NS_DATA]
	
	def __init__(self,transport, jabber):
		"""Initialise the command object"""
		xmpp.commands.Command_Handler_Prototype.__init__(self)
		self.initial = { 'execute':self.cmdFirstStage }
		self.transport = transport
		self.jabber = jabber
		
	def cmdFirstStage(self,conn,request):
		"""Build the reply to complete the request"""
		if request.getFrom().getStripped() in administrators:
		    reply = request.buildReply('result')
		    form = DataForm(typ='result',data=[DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='The list of active users',name='activeuserjids',value=self.transport.users.keys(),typ='jid-multi')])
        	    reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=form)
        	    self.jabber.send(reply)
        	else:
        	    self.jabber.send(Error(request,ERR_FORBIDDEN))
        	raise NodeProcessed
        	
class Registered_Users_Command(xmpp.commands.Command_Handler_Prototype):
	"""This is the active users command as documented in section 4.12  of JEP-0133.
	At the current time, no provision is made for splitting the userlist into sections"""
	name = NS_ADMIN_REGISTERED_USERS
	description = 'The command to list the registered users of the transport'
	discofeatures = [xmpp.commands.NS_COMMANDS,xmpp.NS_DATA]
	
	def __init__(self,transport, jabber):
		"""Initialise the command object"""
		xmpp.commands.Command_Handler_Prototype.__init__(self)
		self.initial = { 'execute':self.cmdFirstStage }
		self.transport = transport
		self.jabber = jabber
		
	def cmdFirstStage(self,conn,request):
		"""Build the reply to complete the request"""
		if request.getFrom().getStripped() in administrators:
		    reply = request.buildReply('result')
		    form = DataForm(typ='result',data=[DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='The list of registered users',name='registereduserjids',value=self.transport.userfile.keys(),typ='jid-multi')])
        	    reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':self.getSessionID(),'status':'completed'},payload=form)
        	    self.jabber.send(reply)
        	else:
        	    self.jabber.send(Error(request,ERR_FORBIDDEN))
        	raise NodeProcessed


class Edit_Admin_List_Command(xmpp.commands.Command_Handler_Prototype):
	"""This command enables the editing of the administrators list (the users of JEP-0133 commands in this case)"""
	name = NS_ADMIN_EDIT_ADMIN
	description = 'Edit the Administrator list'
	discofeatures = [xmpp.commands.NS_COMMANDS, xmpp.NS_DATA]
	
	def __init__(self,transport,jabber,configfile, configfilename, administrators):
		"""Initialise the command object"""
		xmpp.commands.Command_Handler_Prototype.__init__(self)
		self.initial = {'execute':self.cmdFirstStage }
		self.transport = transport
		self.jabber = jabber
		self.configfile = configfile
		self.configfilename = configfilename
		self.administrators = administrators
		
	def cmdFirstStage(self,conn,request):
		"""Set the session ID, and return the form containing the current administrators"""
		if request.getFrom().getStripped() in administrators:
		   # Setup session ready for form reply
		   session = self.getSessionID()
		   self.sessions[session] = {'jid':request.getFrom(),'actions':{'cancel':self.cmdCancel,'next':self.cmdSecondStage}}
		   # Setup form with existing data in
		   reply = request.buildReply('result')
		   form = DataForm(title='Editing the Admin List',data=['Fill out this form to edit the list of entities who have administrative privileges', DataField(typ='hidden',name='FORM_TYPE',value=NS_ADMIN),DataField(desc='The Admin List', typ='jid-multi', name='adminjids',value=self.administrators)])
		   replypayload = [Node('actions',attrs={'execute':'next'},payload=[Node('next')]),form]
		   reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'executing'},payload=replypayload)
		   self.jabber.send(reply)
		else:
		   self.jabber.send(Error(request,ERR_FORBIDDEN))
		raise NodeProcessed
		   
	def cmdSecondStage(self,conn,request):
		"""Apply and save the config"""
		form = DataForm(node=result.getTag(name='command').getTag(namespace=NS_DATA))
		if self.sessions.has_key(request.getTagAttr('command','sessionid')):
			if self.sessions[request.getTagAttr('command','sessionid')]['jid'] == request.getFrom():
				self.administrators = form.getField('adminjids').getValues()
				adminstr = ''
				for each in self.administrators:
				   adminstr = adminstr+each+','
				self.configfile.set('transport','Administrators',adminstr)
				f = open(self.configfilename,'w')
				self.configfile.write(f)
				f.close()
				reply = requst.buildReply('result')
				reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'completed'})
				self.jabber.send(reply)
			else:
				self.jabber.send(Error(request,ERR_BAD_REQUEST))
		else:
			self.jabber.send(Error(request,ERR_BAD_REQUEST))   

	def cmdCancel(self,conn,request):
		self.sessions.remove(self.getSessionID())
		reply = requst.buildReply('result')
		reply.addChild(name='command',attrs={'xmlns':NS_COMMAND,'node':request.getTagAttr('command','node'),'sessionid':session,'status':'canceled'})
		self.jabber.send(reply)
		raise NodeProcessed
