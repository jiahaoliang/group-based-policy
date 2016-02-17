import sys
import os
import oslo_messaging as messaging
from oslo_log import log
from gbpservice.neutron.nsf.core.main import RpcAgent
from gbpservice.neutron.nsf.configurator.lib import topics
from gbpservice.neutron.nsf.configurator.lib.demuxer import ConfiguratorDemuxer

LOG = log.getLogger(__name__)


class ConfiguratorRpcManager(object):
    def __init__(self, sc, sa, conf, demuxer):
        self.sc = sc
        self.conf = conf
        self.sa = sa
        self.demuxer = demuxer

    def _get_service_agent_obj(self, service_type):
        return self.service_agents[service_type]

    def _invoke_service_agent_method(self, method, request_data):

        try:
            sa_info = self.demuxer.get_service_agent_info(method, request_data)
        except Exception as e:
            raise e

        try:
            sa_obj = self._get_service_agent_obj(sa_info['service_type'])
        except Exception as e:
            raise e

        '''TODO:(pritam) fetch context from request_data
        '''
        context = ''
        try:
            sa_obj.sa_info['method'](context, request_data['config'])
        except Exception as e:
            raise e

    def create_network_device_config(self, context, request_data):
        self._invoke_service_agent_method('create', request_data)

    def delete_network_device_config(self, context, request_data):
        self._invoke_service_agent_method('delete', request_data)

    def create_network_service_config(self, context, request_data):
        self._invoke_service_agent_method('create', request_data)

    def delete_network_service_config(self, context, request_data):
        self._invoke_service_agent_method('delete', request_data)


class ConfiguratorModule(object):
    def __init__(self):
        self.service_agent_objs = {}
        self.imported_service_agents = []

    def import_service_agents(self):
        pkg = 'gbpservice.neutron.nsf.configurator.agents'
        base_agent = __import__(pkg,
                                globals(), locals(), ['agents'], -1)
        agents_dir = base_agent.__path__[0]
        syspath = sys.path
        sys.path = [agents_dir] + syspath
        try:
            files = os.listdir(agents_dir)
        except OSError:
            print "Failed to read files"
            files = []

        for fname in files:
            if fname.endswith(".py") and fname != '__init__.py':
                agent = __import__(pkg, globals(),
                                   locals(), [fname[:-3]], -1)
                self.imported_service_agents += [
                                eval('agent.%s' % (fname[:-3]))]
                # modules += [__import__(fname[:-3])]
        sys.path = syspath

    def register_service_agent(self, service_type, service_agent):
        if service_type not in self.service_agent_objs:
            self.service_agent_objs[service_type] = service_agent
            LOG.info(" Registered service_agent [%s] to handle"
                     " service [%s]" % (service_agent, service_type))
        else:
            LOG.warn(" Same service type [%s] being registered again with"
                     " service agent [%s] " % (service_type, service_agent))
            self.service_agent_objs[service_type] = service_agent

    def init_service_agents(self, sc, conf):
        for agent in self.imported_service_agents:
            try:
                agent.init_agent(self, sc, conf)
            except AttributeError as s:
                LOG.error(agent.__dict__)
                raise AttributeError(agent.__file__ + ': ' + str(s))
            except Exception as e:
                LOG.error(e)
                raise e

    def init_service_agents_complete(self, sc, conf):
        for agent in self.imported_service_agents:
            try:
                agent.init_agent_complete(self, sc, conf)
            except AttributeError as s:
                LOG.error(agent.__dict__)
                raise AttributeError(agent.__file__ + ': ' + str(s))
            except Exception as e:
                LOG.error(e)
                raise e


def init_rpc(sc, cm, conf, demuxer):
    rpc_mgr = ConfiguratorRpcManager(sc, cm, conf, demuxer)
    configurator_agent = RpcAgent(sc,
                                  topics.CONFIGURATOR,
                                  rpc_mgr)

    sc.register_rpc_agents([configurator_agent])


def get_configurator_module_handle():
    cm = ConfiguratorModule()
    cm.import_service_agents()
    return cm


def module_init(sc, conf):
    cm = get_configurator_module_handle()
    demuxer = ConfiguratorDemuxer()
    cm.init_service_agents(sc, conf)
    init_rpc(sc, cm, conf, demuxer)


def init_complete(sc, conf):
    cm = get_configurator_module_handle()
    cm.init_service_agents_complete(sc, conf)
