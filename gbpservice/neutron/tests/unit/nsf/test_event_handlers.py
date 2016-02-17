import os
from gbpservice.neutron.nsf.core import periodic_task as core_periodic_task
from gbpservice.neutron.nsf.core.main import Event
from oslo_log import log as logging
from oslo_config import cfg
import time
LOG = logging.getLogger(__name__)


class Handler_Class(core_periodic_task.PeriodicTasks):
	def __init__(self, sc):
		self._sc = sc
		self.counter = 0
		self.timer = 0
	
	def handle_poll_event(self, ev):
		if os.getpid() == ev.worker_attached and \
			ev.id == 'DUMMY_SERVICE_EVENT2' and self.counter == 0:
			self._sc._event.set()
		if ev.id == 'DUMMY_SERVICE_EVENT3':
			self.counter = self.counter + 1
		if ev.id == 'DUMMY_SERVICE_EVENT4':
			self.counter = self.counter + 1
			if self.counter == 2:
				self._sc._event.set()			
		LOG.debug("Poll event (%s)" % (str(ev)))
		print "Poll event %s" % (ev.key)

	def handle_event(self, ev):
		LOG.debug("Process ID :%d" % (os.getpid()))
		if ev.id == 'DUMMY_SERVICE_EVENT1':
			self._handle_dummy_event1(ev)
		elif ev.id == 'DUMMY_SERVICE_EVENT2':
			self._handle_dummy_event2(ev)
		elif ev.id == 'DUMMY_SERVICE_EVENT3':
			self._handle_dummy_event3(ev)
		elif ev.id == 'DUMMY_SERVICE_EVENT4':
			self._handle_dummy_event4(ev)
		elif ev.id == 'DUMMY_SERVICE_EVENT5':
			self._handle_dummy_event5(ev)
		elif ev.id == 'DUMMY_SERVICE_EVENT6':
			self._handle_dummy_event6(ev)

	def _handle_dummy_event6(self, ev):
		self._sc.event_done(ev)
		self._sc.poll_event(ev, max_times=2)

	def _handle_dummy_event5(self, ev):
		self._sc.event_done(ev)
		self._sc.poll_event(ev, max_times=2)

	def _handle_dummy_event4(self, ev):
		self._sc.poll_event(ev, max_times=1)
	
	def _handle_dummy_event3(self, ev):
		self._sc.poll_event(ev, max_times=2)
	
	def _handle_dummy_event1(self, ev):
		if os.getpid() == ev.worker_attached:
			self._sc._event.set()

	def _handle_dummy_event2(self, ev):
		self._sc.event_done(ev)
		self._sc.poll_event(ev, max_times=1)
	
	def poll_event_cancel(self, ev):
		if os.getpid() == ev.worker_attached and self.counter == 2:
			self._sc._event.set()
		LOG.debug("Poll event Canceled counter(%s)" % (str(ev)))
	
	@core_periodic_task.periodic_task(event='DUMMY_SERVICE_EVENT5', spacing=10)
	def dummy_event5_poll_event(self, ev):
		if self.counter == 0:
			self.timer = time.time()
			self.counter = self.counter + 1
		else:
			time_now = time.time()
			time_elapsed = int(round(time_now - self.timer)) 
			if ev.id == 'DUMMY_SERVICE_EVENT5' and time_elapsed == 10:
				self._sc._event.set()
		LOG.debug("Poll event (%s)" % (str(ev)))
		print "Decorator Poll event %s" % (ev.key)

	@core_periodic_task.periodic_task(event='DUMMY_SERVICE_EVENT6', spacing=20)
	def dummy_event6_poll_event(self, ev):
		if self.counter == 0:
			self.timer = time.time()
			self.counter = self.counter + 1
		else:
			time_now = time.time()
			time_elapsed = int(round(time_now - self.timer))
			if ev.id == 'DUMMY_SERVICE_EVENT6' and time_elapsed == 20:
				self._sc._event.set()
		LOG.debug("Poll event (%s)" % (str(ev)))
		print "Decorator Poll event %s" % (ev.key)
	



def module_init(sc, conf):
	evs = [
		Event(id='DUMMY_SERVICE_EVENT1', handler=Handler_Class(sc)),
		Event(id='DUMMY_SERVICE_EVENT2', handler=Handler_Class(sc)),
		Event(id='DUMMY_SERVICE_EVENT3', handler=Handler_Class(sc)),
		Event(id='DUMMY_SERVICE_EVENT4', handler=Handler_Class(sc)),
		Event(id='DUMMY_SERVICE_EVENT5', handler=Handler_Class(sc)),
		Event(id='DUMMY_SERVICE_EVENT6', handler=Handler_Class(sc))
	]
	sc.register_events(evs) 
