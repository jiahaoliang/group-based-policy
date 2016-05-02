import socket

from neutron.common import exceptions
from neutron.common import rpc as n_rpc
from neutron.db import agents_db
from neutron.db import agentschedulers_db
from neutron import manager
from neutron_vpnaas.db.vpn import vpn_validator
from neutron_vpnaas.services.vpn.common import constants as const
from neutron_vpnaas.services.vpn.common import topics
from neutron_vpnaas.services.vpn.plugin import VPNPlugin
from neutron_vpnaas.services.vpn import service_drivers
from neutron_vpnaas.services.vpn.service_drivers import base_ipsec

from oslo_log import log as logging
import oslo_messaging

LOG = logging.getLogger(__name__)

BASE_VPN_VERSION = '1.0'


class VPNAgentHostingServiceNotFound(exceptions.NeutronException):
    message = _("VPN Agent hosting vpn service '%(vpnservice_id)s' not found")


class VPNAgentNotFound(exceptions.NeutronException):
    message = _("VPN Agent not found in agent_db")


class VPNPluginExt(VPNPlugin, agentschedulers_db.AgentSchedulerDbMixin):
    """
    Extends the base VPN Plugin class to inherit agentdb too.
    Required to get agent entry into the database.
    """

    def __init__(self):
        super(VPNPluginExt, self).__init__()


class OCIPsecVpnDriverCallBack(object):
    """Callback for IPSecVpnDriver rpc."""

    target = oslo_messaging.Target(version=BASE_VPN_VERSION)

    def __init__(self, driver):
        self.driver = driver

    def update_status(self, context, **status):
        """Update status of vpnservices."""
        status = status['status']
        if 'ipsec_site_connections' not in status[0]:
            status[0]['ipsec_site_connections'] = {}
        plugin = self.driver.service_plugin
        plugin.update_status_by_agent(context, status)

    def ipsec_site_conn_deleted(self, context, **resource_id):
        """ Delete ipsec connection notification from driver."""
        plugin = self.driver.service_plugin
        plugin._delete_ipsec_site_connection(context, resource_id['id'])

    def vpnservice_deleted(self, context, **kwargs):
        vpnservice_id = kwargs['id']
        plugin = self.driver.service_plugin
        plugin._delete_vpnservice(context, vpnservice_id)

class OCIpsecVpnAgentApi(service_drivers.BaseIPsecVpnAgentApi):
    """API and handler for OC IPSec plugin to agent RPC messaging."""
    target = oslo_messaging.Target(version=BASE_VPN_VERSION)

    def __init__(self, topic, default_version, driver):
        super(OCIpsecVpnAgentApi, self).__init__(
            topic, default_version, driver)

    def _is_agent_hosting_vpnservice(self, agent):
        """
        In case we have agent running on each compute node.
        We have to write logic here to get
        the agent which is hosting this vpn service
        """
        host = agent['host']
        lhost = socket.gethostname()
        if host == lhost:
            return True
        return False

    def _get_agent_hosting_vpnservice(self, admin_context, vpnservice_id):
        filters = {'agent_type': [const.AGENT_TYPE_VPN]}
        agents = manager.NeutronManager.get_plugin().get_agents(
            admin_context,  filters=filters)

        try:
            for agent in agents:
                if not agent['alive']:
                    continue
                res = self._is_agent_hosting_vpnservice(agent)
                if res is True:
                    return agent

            # valid vpn agent is not found, hostname comparison might be
            # failed. Return whichever agent is available.
            for agent in agents:
                if not agent['alive']:
                    continue
                return agent
        except:
            raise VPNAgentNotFound()

        LOG.error(_('No active vpn agent found. Configuration will fail.'))
        raise VPNAgentHostingServiceNotFound(vpnservice_id=vpnservice_id)

    def _agent_notification(self, context, method, vpnservice_id,
                            version=None, **kwargs):
        """Notify update for the agent.
            For some reason search with
            'agent_type=AGENT_TYPE_VPN is not working.
            Hence, get all the agents,
            loop and find AGENT_TYPE_VPN, and also the one which
            is hosting that vpn service and
            implementing OC_IPSEC_TOPIC
        """
        admin_context = context.is_admin and context or context.elevated()

        if not version:
            version = self.target.version
        vpn_agent = self._get_agent_hosting_vpnservice(
            admin_context, vpnservice_id)

        LOG.debug(_('Notify agent at %(topic)s.%(host)s the message '
                    '%(method)s %(args)s'), {
            'topic': self.topic, 'host': vpn_agent['host'],
            'method': method, 'args': kwargs})

        cctxt = self.client.prepare(server=vpn_agent['host'],
                                    version=version)
        cctxt.cast(context, method, **kwargs)

    def vpnservice_updated(self, context, vpnservice_id, **kwargs):
        """
        Make rpc to agent for 'vpnservice_updated'
        """
        try:
            self._agent_notification(
                context, 'vpnservice_updated',
                vpnservice_id, **kwargs)
        except:
            LOG.error(_('Notifying agent failed'))


class OCIPsecVPNDriver(base_ipsec.BaseIPsecVPNDriver):
    """VPN Service Driver class for IPsec."""

    def __init__(self, service_plugin):
        super(OCIPsecVPNDriver, self).__init__(
            service_plugin, None)

    def create_rpc_conn(self):
        self._core_plugin = None
        self.endpoints = [
            OCIPsecVpnDriverCallBack(self),
            agents_db.AgentExtRpcCallback(VPNPluginExt())]

        self.conn = n_rpc.create_connection(new=True)
        self.conn.create_consumer(
            topics.VPN_PLUGIN_TOPIC, self.endpoints, fanout=False)
        self.conn.consume_in_threads()
        self.agent_rpc = OCIpsecVpnAgentApi(
            topics.VPN_AGENT_TOPIC, BASE_VPN_VERSION, self)

    def _get_service_vendor(self, context, vpnservice_id):
        vpnservice = self.service_plugin.get_vpnservice(
                context, vpnservice_id)
        desc = vpnservice['description']
        # if the call is through GBP workflow,
        # fetch the service profile from description
        # else, use 'VYOS' as the service profile
        if 'service_vendor=' in desc:
            tokens = desc.split(';')
            service_vendor = tokens[5].split('=')[1]
        else:
            service_vendor = 'VYOS'
        return service_vendor

    def create_ipsec_site_connection(self, context, ipsec_site_connection):
        service_vendor = self._get_service_vendor(context,
                          ipsec_site_connection['vpnservice_id'])
        self.agent_rpc.vpnservice_updated(
            context,
            ipsec_site_connection['vpnservice_id'],
            rsrc_type='ipsec_site_connection',
            svc_type=const.SERVICE_TYPE_IPSEC,
            rsrc_id=ipsec_site_connection['id'],
            resource=ipsec_site_connection,
            reason='create', service_vendor=service_vendor)

    def delete_ipsec_site_connection(self, context, ipsec_site_connection):
        service_vendor = self._get_service_vendor(context,
                          ipsec_site_connection['vpnservice_id'])
        self.agent_rpc.vpnservice_updated(
            context,
            ipsec_site_connection['vpnservice_id'],
            rsrc_type='ipsec_site_connection',
            svc_type=const.SERVICE_TYPE_IPSEC,
            rsrc_id=ipsec_site_connection['id'],
            resource=ipsec_site_connection,
            reason='delete', service_vendor=service_vendor)

    def create_vpnservice(self, context, vpnservice):
        service_vendor = self._get_service_vendor(context,
                                                  vpnservice['id'])
        self.agent_rpc.vpnservice_updated(
            context,
            vpnservice['id'],
            rsrc_type='vpn_service',
            svc_type=const.SERVICE_TYPE_IPSEC,
            rsrc_id=vpnservice['id'],
            resource=vpnservice,
            reason='create', service_vendor=service_vendor)

    def delete_vpnservice(self, context, vpnservice):
        service_vendor = self._get_service_vendor(context,
                                                  vpnservice['id'])
        self.agent_rpc.vpnservice_updated(
            context,
            vpnservice['id'],
            rsrc_type='vpn_service',
            svc_type=const.SERVICE_TYPE_IPSEC,
            rsrc_id=vpnservice['id'],
            resource=vpnservice,
            reason='delete', service_vendor=service_vendor)
