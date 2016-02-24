import json
import os
import requests

from gbpservice.neutron.nsf.configurator.lib import vpn_constants as const
from gbpservice.neutron.nsf.configurator.lib import exceptions as exc
from gbpservice.neutron.nsf.configurator.agents import agent_base
from gbpservice.neutron.nsf.core import main
from gbpservice.neutron.nsf.configurator.lib import utils

from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_messaging import MessagingTimeout

from neutron import context


LOG = logging.getLogger(__name__)


class VpnaasRpcSender(object):
    """ RPC APIs to VPNaaS Plugin.
    """
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, topic, context, nqueue):
        self.context = context
        self.qu = nqueue
        # self.host = host why we need host in FIREWALL

    def get_vpn_services(self, context, ids, filters):
        """Get list of vpnservices on this host.
        """
        return self.call(
            context,
            self.make_msg('get_vpn_services', ids=ids, filters=filters))

    def get_vpn_servicecontext(self, context, svctype,  filters):
        """Get list of vpnservice context on this host.
           For IPSEC connections :
                List of vpnservices -->
                lIst of ipsec connections -->
                ike policy & ipsec policy
        """
        return self.call(
            context,
            self.make_msg(
                'get_vpn_servicecontext',
                svctype=svctype,  filters=filters),
            version=self.API_VERSION)

    def get_ipsec_conns(self, context, filters):
        """
        Get list of ipsec conns with filters
        specified.
        """
        return self.call(
            context,
            self.make_msg(
                'get_ipsec_conns',
                filters=filters),
            version=self.API_VERSION)

    def update_status(self, context, status):
        """Update local status.

        This method call updates status attribute of
        VPNServices.
        """
        msg = {'receiver': const.NEUTRON,
               'resource': const.SERVICE_TYPE,
               'method': 'update_status',
               'data': {'context': context,
                        'status': status}
               }
        self.qu.put(msg)

    def ipsec_site_conn_deleted(self, context, resource_id):
        """ Notify VPNaaS plugin about delete of ipsec-site-conn """

        msg = {'receiver': const.NEUTRON,
               'resource': const.SERVICE_TYPE,
               'method': 'ipsec_site_conn_deleted',
               'data': {'context': context,
                        'resource_id': resource_id}
               }
        self.qu.put(msg)


class VPNaasRpcManager(agent_base.AgentBaseRPCManager):
    """
    APIs for receiving RPC messages from vpn plugin.
    """
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, conf, sc):
        self.conf = conf
        self._sc = sc

    def vpnservice_updated(self, context, **kwargs):
        arg_dict = {'context': context,
                    'kwargs': kwargs}

        ev = self._sc.event(id='UPDATE_VPN_SERVICE', data=arg_dict)
        self._sc.rpc_event(ev)


class VPNaasEventHandler(object):
    """
    Handler class for demultiplexing vpn configuration
    requests from VPNaas Plugin and sending to appropriate driver.
    """
    def __init__(self, sc, drivers, nqueue):
        self._sc = sc
        self.drivers = drivers
        self.needs_sync = True
        self.context = context.get_admin_context_without_session()
        self.plugin_rpc = VpnaasRpcSender(
            const.VPN_PLUGIN_TOPIC,
            self.context,
            nqueue)

    def _get_driver(self, data):
        ''' TO DO: Do demultiplexing logic based on vendor
        '''
        svc_type = data.get('kwargs').get('svc_type')
        if svc_type == const.SERVICE_TYPE:
            self.ipsec_driver = self.drivers["vyos_ipsec_vpnaas"]
            return self.ipsec_driver

    def handle_event(self, ev):
        try:
            msg = ("Worker process with ID: %s starting "
                   "to handle task: %s of topic: %s. "
                   % (os.getpid(), ev.id, const.VPN_GENERIC_CONFIG_RPC_TOPIC))
            LOG.debug(msg)

            driver = self._get_driver(ev.data)
            method = getattr(driver, "%s" % (ev.id.lower()))
            method(ev)
        except Exception as err:
            LOG.error("Failed to perform the operation: %s. %s"
                      % (ev.id, str(err).capitalize()))
        finally:
            self._sc.event_done(ev)

    def vpnservice_updated(self, ev, driver):
        context = ev.data.get('context')
        kwargs = ev.data.get('kwargs')
        LOG.debug(_("Vpn service updated from server side"))

        try:
            driver.vpnservice_updated(context,  **kwargs)
        except Exception as err:
            LOG.error("Failed to update VPN service. %s"
                      % str(err).capitalize())

        reason = kwargs.get('reason')
        rsrc = kwargs.get('rsrc_type')

        if (reason == 'delete' and rsrc == 'ipsec_site_connection'):
            conn = kwargs['resource']
            resource_id = conn['id']
            self.plugin_rpc.ipsec_site_conn_deleted(context,
                                                    resource_id=resource_id)

    def update_service_status(self, context, vpnsvc, status):
        """
        Driver will call this API to report
        status of VPN service.
        """
        msg = ("Driver informing status: %s."
               % status)
        LOG.debug(msg)
        vpnsvc_status = [{
            'id': vpnsvc['id'],
            'status': status,
            'updated_pending_status':True}]
        self.plugin_rpc.update_status(context, vpnsvc_status)

    def get_vpn_services(self, context, ids=None, filters=None):
        return self.plugin_rpc.get_vpn_services(context, ids, filters)

    def _get_service_vendor(self, vpn_svc):
        svc_desc = vpn_svc['description']
        tokens = svc_desc.split(';')
        vendor = tokens[5].split('=')[1]
        return vendor

    def _sync_ipsec_conns(self, context, vendor, svc_context):
        try:
            self.ipsec_driver.check_status(context, svc_context)
        except Exception as err:
            msg = ("Failed to sync ipsec connection information. %s."
                   % str(err).capitalize())
            LOG.error(msg)
            pass

    def sync(self, context,  args=None):
        self.needs_sync = True
        s2s_contexts = self.get_ipsec_contexts(context)
        for svc_context in s2s_contexts:
            svc_vendor = self._get_service_vendor(svc_context['service'])
            self._sync_ipsec_conns(context, svc_vendor, svc_context)

    def _resync_ipsec_conns(self, context, vendor, svc_context):
        for site_conn in svc_context['siteconns']:
            conn = site_conn['connection']
            keywords = {'resource': conn}
            try:
                self.ipsec_driver.delete_ipsec_conn(self.context, **keywords)
            except Exception as err:
                LOG.error("Delete ipsec-site-conn: %s failed"
                          " with Exception %s "
                          % (conn['id'], str(err).capitalize()))

            self.plugin_rpc.ipsec_site_conn_deleted(self.context,
                                                    resource_id=conn['id'])

    def update_conn_status(self,  context, svc_type, conn, status):
        """
        Driver will call this API to report
        status of a connection - only if there is any change.
        """
        msg = ("Driver informing connection status "
               "changed to %s" % status)
        LOG.debug(msg)
        if svc_type == const.SERVICE_TYPE:
            vpnsvc_status = [{
                'id': conn['vpnservice_id'],
                'status':'ACTIVE',
                'updated_pending_status':False,
                'ipsec_site_connections':{
                    conn['id']: {
                        'status': status,
                        'updated_pending_status': True}}}]

        self.plugin_rpc.update_status(context, vpnsvc_status)

    def get_ipsec_contexts(self, context, tenant_id=None,
                           vpnservice_id=None, conn_id=None,
                           peer_address=None):
        filters = {}
        if tenant_id:
            filters['tenant_id'] = tenant_id
        if vpnservice_id:
            filters['vpnservice_id'] = vpnservice_id
        if conn_id:
            filters['siteconn_id'] = conn_id
        if peer_address:
            filters['peer_address'] = peer_address

        return self.plugin_rpc.\
            get_vpn_servicecontext(
                context,
                const.SERVICE_TYPE, filters)

    def get_ipsec_conns(self, context, filters):
        return self.plugin_rpc.\
            get_ipsec_conns(context, filters)


def events_init(sc, drivers, nqueue):
    evs = [
        main.Event(id='VPNSERVICE_UPDATED',
                   handler=VPNaasEventHandler(sc, drivers, nqueue))]
    sc.register_events(evs)


def load_drivers():

    ld = utils.ConfiguratorUtils()
    return ld.load_drivers(const.DRIVERS_DIR)


def register_service_agent(cm, sc, conf):

    rpcmgr = VPNaasRpcManager(sc, conf)
    cm.register_service_agent(const.SERVICE_TYPE, rpcmgr)


def init_agent(cm, sc, conf, nqueue):
    try:
        drivers = load_drivers()
    except Exception as err:
        LOG.error("VPNaas failed to load drivers. %s"
                  % (str(err).capitalize()))
        raise err
    else:
        LOG.debug("VPNaas loaded drivers successfully.")

    try:
        events_init(sc, drivers, nqueue)
    except Exception as err:
        LOG.error("VPNaas Events initialization unsuccessful. %s"
                  % (str(err).capitalize()))
        raise err
    else:
        LOG.debug("VPNaas Events initialization successful.")

    try:
        register_service_agent(cm, sc, conf)
    except Exception as err:
        LOG.error("VPNaas service agent registration unsuccessful. %s"
                  % (str(err).capitalize()))
        raise err
    else:
        LOG.debug("VPNaas service agent registration successful.")

    msg = ("VPN as a Service Module Initialized.")
    LOG.info(msg)


def init_agent_complete(cm, sc, conf):
    LOG.info(" vpn agent init complete")

