# One Convergence, Inc. CONFIDENTIAL
# Copyright (c) 2012-2016, One Convergence, Inc., USA
# All Rights Reserved.
#
# All information contained herein is, and remains the property of
# One Convergence, Inc. and its suppliers, if any. The intellectual and
# technical concepts contained herein are proprietary to One Convergence,
# Inc. and its suppliers.
#
# Dissemination of this information or reproduction of this material is
# strictly forbidden unless prior written permission is obtained from
# One Convergence, Inc., USA

import os
import json
import requests

import oslo_messaging as messaging
from oslo_config import cfg
from oslo_log import log as logging
from oslo_messaging import MessagingTimeout

from neutron import context

from gbpservice.neutron.nsf.configurator.lib import vpn_constants as const
from gbpservice.neutron.nsf.configurator.lib import exceptions as exc
from gbpservice.neutron.nsf.configurator.agents import agent_base
from gbpservice.neutron.nsf.core.main import Event
from gbpservice.neutron.nsf.core.main import RpcAgent
from gbpservice.neutron.nsf.configurator.lib import utils
''' TO DO: Avoid the following imports. Do dynamic driver imports
'''


LOG = logging.getLogger(__name__)

auth_server_opts = [
    cfg.StrOpt(
        'auth_uri',
        default="",
        help=_("Keystone auth URI")),
    cfg.StrOpt(
        'admin_user',
        default="cloud_admin",
        help=_("Cloud admin user name")),
    cfg.StrOpt(
        'admin_password',
        default="",
        help=_("Cloud admin user password")),
    cfg.StrOpt(
        'admin_tenant_name',
        default="admin",
        help=_("Cloud admin tenant name")),
    cfg.StrOpt(
        'remote_vpn_role_name',
        default="vpn",
        help=_("Name of kv3 role for remote vpn users")),
]
cfg.CONF.register_opts(auth_server_opts, 'keystone_authtoken')

OPTS = [
    cfg.StrOpt('driver', required=True,
               help='driver to be used for vyos configuration'),
]

cfg.CONF.register_opts(OPTS, "VYOS_CONFIG")

vpn_agent_opts = [
    cfg.MultiStrOpt(
        'vpn_device_driver',
        default=[],
        help=_("The vpn device drivers Neutron will use")),
]
cfg.CONF.register_opts(vpn_agent_opts, 'vpnagent')
rest_timeout = [
    cfg.IntOpt(
        'rest_timeout',
        default=30,
        help=_("rest api timeout"))]

cfg.CONF.register_opts(rest_timeout)


class RestApi(object):
    def __init__(self, vm_mgmt_ip):
        self.vm_mgmt_ip = vm_mgmt_ip
        self.timeout = cfg.CONF.rest_timeout

    def _dict_to_query_str(self, args):
        return '&'.join([str(k) + '=' + str(v) for k, v in args.iteritems()])

    def post(self, api, args):
        url = const.request_url % (
            self.vm_mgmt_ip,
            const.CONFIGURATION_SERVER_PORT, api)
        data = json.dumps(args)

        try:
            resp = requests.post(url, data=data, timeout=self.timeout)
            message = json.loads(resp.text)
            msg = ("POST url %s %d" % (url, resp.status_code))
            LOG.debug(msg)
            if resp.status_code == 200 and message.get("status", False):
                msg = ("POST Rest API %s - Success" % (url))
                LOG.info(msg)
            else:
                msg = ("POST Rest API %s - Failed with status %s, %s"
                       % (url, resp.status_code,
                          message.get("reason", None)))
                LOG.error(msg)
                raise Exception(msg)
        except Exception as err:
            msg = ("Post Rest API %s - Failed. Reason: %s"
                   % (url, str(err).capitalize()))
            LOG.error(msg)
            raise Exception(msg)

    def put(self, api, args):
        url = const.request_url % (
            self.vm_mgmt_ip,
            const.CONFIGURATION_SERVER_PORT, api)
        data = json.dumps(args)

        try:
            resp = requests.put(url, data=data, timeout=self.timeout)
            msg = ("PUT url %s %d" % (url, resp.status_code))
            LOG.debug(msg)
            if resp.status_code == 200:
                msg = ("REST API PUT %s succeeded." % url)
                LOG.debug(msg)
            else:
                msg = ("REST API PUT %s failed with status: %d."
                       % (url, resp.status_code))
                LOG.error(msg)
        except Exception as err:
            msg = ("REST API for PUT %s failed. %s"
                   % (url, str(err).capitalize()))
            LOG.error(msg)

    def delete(self, api, args, data=None):
        url = const.request_url % (
            self.vm_mgmt_ip,
            const.CONFIGURATION_SERVER_PORT, api)

        if args:
            url += '?' + self._dict_to_query_str(args)

        if data:
            data = json.dumps(data)
        try:
            resp = requests.delete(url, timeout=self.timeout, data=data)
            message = json.loads(resp.text)
            msg = ("DELETE url %s %d" % (url, resp.status_code))
            LOG.debug(msg)
            if resp.status_code == 200 and message.get("status", False):
                msg = ("DELETE Rest API %s - Success" % (url))
                LOG.info(msg)
            else:
                msg = ("DELETE Rest API %s - Failed %s"
                       % (url, message.get("reason", None)))
                LOG.error(msg)
                raise Exception(msg)
        except Exception as err:
            msg = ("Delete Rest API %s - Failed. Reason: %s"
                   % (url, str(err).capitalize()))
            LOG.error(msg)
            raise Exception(msg)

    def get(self, api, args):
        output = ''

        url = const.request_url % (
            self.vm_mgmt_ip,
            const.CONFIGURATION_SERVER_PORT, api)

        try:
            resp = requests.get(url, params=args, timeout=self.timeout)
            msg = ("GET url %s %d" % (url, resp.status_code))
            LOG.debug(msg)
            if resp.status_code == 200:
                msg = ("REST API GET %s succeeded." % url)
                LOG.debug(msg)
                json_resp = resp.json()
                return json_resp
            else:
                msg = ("REST API GET %s failed with status: %d."
                       % (url, resp.status_code))
                LOG.error(msg)
        except requests.exceptions.Timeout as err:
            msg = ("REST API GET %s timed out. %s."
                   % (url, str(err).capitalize()))
            LOG.error(msg)
        except Exception as err:
            msg = ("REST API for GET %s failed. %s"
                   % (url, str(err).capitalize()))
            LOG.error(msg)

        return output


class VPNSvcValidator(object):
    def __init__(self, agent):
        self.agent = agent

    def _error_state(self, context, vpnsvc, message=''):
        self.agent.update_service_status(
            context,
            vpnsvc,
            const.STATE_ERROR)
        raise exc.ResourceErrorState(name='vpn_service', id=vpnsvc['id'],
                                     message=message)

    def _active_state(self, context, vpnsvc):
        self.agent.update_service_status(
            context,
            vpnsvc,
            const.STATE_ACTIVE)

    def _get_local_cidr(self, vpn_svc):
        svc_desc = vpn_svc['description']
        tokens = svc_desc.split(';')
        local_cidr = tokens[1].split('=')[1]
        return local_cidr

    def validate(self, context, vpnsvc):
        lcidr = self._get_local_cidr(vpnsvc)
        """
        Get the vpn services for this tenant
        Check for overlapping lcidr - not allowed
        """
        filters = {'tenant_id': [context.tenant_id]}
        t_vpnsvcs = self.agent.get_vpn_services(
            context, filters=filters)
        vpnsvc.pop("status", None)
        for svc in t_vpnsvcs:
            del svc['status']
        if vpnsvc in t_vpnsvcs:
            t_vpnsvcs.remove(vpnsvc)
        for svc in t_vpnsvcs:
            t_lcidr = self._get_local_cidr(svc)
            if t_lcidr == lcidr:
                msg = ("Local cidr %s conflicts with existing vpnservice %s"
                       % (lcidr, svc['id']))
                LOG.error(msg)
                self._error_state(
                    context,
                    vpnsvc, msg)
        self._active_state(context, vpnsvc)


class VpnaasRpcSender(object):
    """ RPC APIs to VPNaaS Plugin.
    """
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, topic, context):
        self.context = context

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
        return self.cast(
            context,
            self.make_msg('update_status', status=status),
            version=self.API_VERSION)

    def ipsec_site_conn_deleted(self, context, resource_id):
        """ Notify VPNaaS plugin about delete of ipsec-site-conn """
        try:
            self.call(context,
                      self.make_msg('ipsec_site_connection_deleted',
                                    id=resource_id),
                      version=self.API_VERSION)
        except Exception as err:
            LOG.error("Failed agent to plugin call"
                      " ipsec_site_connection_deleted() with reason %s"
                      % str(err).capitalize())


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
    def __init__(self, sc, drivers):
        self._sc = sc
        self.drivers = drivers
        self.needs_sync = True
        self.context = context.get_admin_context_without_session()
        self.plugin_rpc = VpnaasRpcSender(
            const.VPN_PLUGIN_TOPIC,
            self.context)

    def _get_driver(self, data):
        ''' TO DO: Do demultiplexing logic based on vendor
        '''
        svc_type = data.get('kwargs').get('svc_type')
        if svc_type == const.SERVICE_TYPE_IPSEC:
            self.ipsec_driver = self.drivers["vyos_ipsec_vpnaas"]
            return self.ipsec_driver
        elif svc_type == const.SERVICE_TYPE_OPENVPN:
            self.ssl_driver = self.drivers["vyos_ssl_vpnaas"]
            return self.ssl_driver

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
        elif (reason == 'delete' and rsrc == 'ssl_vpn_connection'):
            conn = kwargs['resource']
            resource_id = conn['id']
            self.plugin_rpc.ssl_vpn_conn_deleted(context,
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

    def _sync_openvpn_conns(self, context, vendor, svc_context):
        try:
            self.ssl_driver.check_status(context, svc_context)
        except Exception as err:
            msg = ("Failed to sync openvpn connection information. %s."
                   % str(err).capitalize())
            LOG.error(msg)
            pass

    def sync(self, context,  args=None):
        self.needs_sync = True
        s2s_contexts = self.get_ipsec_contexts(context)
        for svc_context in s2s_contexts:
            svc_vendor = self._get_service_vendor(svc_context['service'])
            self._sync_ipsec_conns(context, svc_vendor, svc_context)

        ssl_contexts = self.get_sslvpn_contexts(context)
        for svc_context in ssl_contexts:
            svc_vendor = self._get_service_vendor(svc_context['service'])
            self._sync_openvpn_conns(context, svc_vendor, svc_context)

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

    def _resync_openvpn_conns(self, context, vendor, svc_context):
        for ssl_conn in svc_context['sslvpnconns']:
            conn = ssl_conn['connection']
            keywords = {'resource': conn}
            try:
                self.ssl_driver.delete_sslvpn_conn(self.context, **keywords)
            except Exception as err:
                LOG.error("Delete ssl-vpn-conn: %s failed"
                          " with Exception %s "
                          % (conn['id'], str(err).capitalize()))

            self.plugin_rpc.ssl_vpn_conn_deleted(self.context,
                                                 resource_id=conn['id'])

    def resync(self, context):
        try:
            s2s_contexts = self.plugin_rpc.get_vpn_servicecontext(
                context,
                const.SERVICE_TYPE_IPSEC,
                filters={'status': ['PENDING_DELETE']})
        except MessagingTimeout as err:
            LOG.error("Failed in get_vpn_servicecontext for"
                      " IPSEC connections. Error: %s" % str(err).capitalize())
        else:
            for svc_context in s2s_contexts:
                svc_vendor = self._get_service_vendor(svc_context['service'])
                self._resync_ipsec_conns(context, svc_vendor, svc_context)

        try:
            ssl_contexts = self.plugin_rpc.get_vpn_servicecontext(
                context,
                const.SERVICE_TYPE_OPENVPN,
                filters={'status': ['PENDING_DELETE']})
        except MessagingTimeout as err:
            LOG.error("Failed in get_vpn_servicecontext for"
                      " OPENVPN connections. Error: %s"
                      % str(err).capitalize())
        else:
            for svc_context in ssl_contexts:
                svc_vendor = self._get_service_vendor(svc_context['service'])
                self._resync_openvpn_conns(context, svc_vendor, svc_context)

    def update_conn_status(self,  context, svc_type, conn, status):
        """
        Driver will call this API to report
        status of a connection - only if there is any change.
        """
        msg = ("Driver informing connection status "
               "changed to %s" % status)
        LOG.debug(msg)
        if svc_type == const.SERVICE_TYPE_IPSEC:
            vpnsvc_status = [{
                'id': conn['vpnservice_id'],
                'status':'ACTIVE',
                'updated_pending_status':False,
                'ipsec_site_connections':{
                    conn['id']: {
                        'status': status,
                        'updated_pending_status': True}}}]

        if svc_type == const.SERVICE_TYPE_OPENVPN:
            vpnsvc_status = [{
                'id': conn['vpnservice_id'],
                'status':'ACTIVE',
                'updated_pending_status':False,
                'ssl_vpn_connections': {
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
                const.SERVICE_TYPE_IPSEC, filters)

    def get_ipsec_conns(self, context, filters):
        return self.plugin_rpc.\
            get_ipsec_conns(context, filters)


def events_init(sc, drivers):
    evs = [
        Event(id='VPNSERVICE_UPDATED',
              handler=VPNaasEventHandler(sc, drivers))]
    sc.register_events(evs)


def load_drivers():

    ld = utils.ConfiguratorUtils()
    return ld.load_drivers(const.DRIVERS_DIR)


def register_service_agent(cm, sc, conf):
    service_type = const.SERVICE_TYPE
    rpc_mgr = VPNaasRpcManager(sc, conf)
    cm.register_service_agent(service_type, rpc_mgr)


def init_agent(cm, sc, conf):
    try:
        drivers = load_drivers()
    except Exception as err:
        LOG.error("VPNaas failed to load drivers. %s"
                  % (str(err).capitalize()))
        raise err
    else:
        LOG.debug("VPNaas loaded drivers successfully.")

    try:
        events_init(sc, drivers)
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

