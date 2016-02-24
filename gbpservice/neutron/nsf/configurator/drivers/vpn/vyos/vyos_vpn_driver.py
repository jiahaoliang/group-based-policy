import copy
import json
import requests

from gbpservice.neutron.nsf.configurator.drivers.base.\
                            base_driver import BaseDriver
from gbpservice.neutron.nsf.configurator.lib import exceptions as exc
from gbpservice.neutron.nsf.configurator.lib import vpn_constants as const
from gbpservice.neutron.nsf.configurator.agents import vpn

from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class VpnGenericConfigDriver(object):
    """
    Driver class for implementing VPN configuration
    requests from Orchestrator.
    """

    def __init__(self):
        self.timeout = cfg.CONF.rest_timeout

    def configure_source_routes(self, context, kwargs):

        # REVISIT(VK): This was all along bad way, don't know why at all it
        # was done like this.

        url = const.request_url % (kwargs['vm_mgmt_ip'],
                                   const.CONFIGURATION_SERVER_PORT,
                                   'add-source-route')
        active_configured = False
        route_info = []
        for source_cidr in kwargs['source_cidrs']:
            route_info.append({'source_cidr': source_cidr,
                               'gateway_ip': kwargs['gateway_ip']})
        data = json.dumps(route_info)
        msg = ("Initiating POST request to configure route of "
               "primary service at: %r" % kwargs['vm_mgmt_ip'])
        LOG.info(msg)
        try:
            resp = requests.post(url, data=data, timeout=60)
        except requests.exceptions.ConnectionError, err:
            msg = ("Failed to establish connection to service at: "
                   "%r. ERROR: %r" % (kwargs['vm_mgmt_ip'],
                                      str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while configuring "
                   "route of service at: %r ERROR: %r" % (
                    kwargs['vm_mgmt_ip'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)

        if resp.status_code in const.SUCCESS_CODES:
            message = json.loads(resp.text)
            if message.get("status", False):
                msg = ("Route configured successfully for VYOS"
                       " service at: %r" % kwargs['vm_mgmt_ip'])
                LOG.info(msg)
                active_configured = True
            else:
                msg = ("Configure source route failed on service with"
                       " status %s %s"
                       % (resp.status_code, message.get("reason", None)))
                LOG.error(msg)
                raise Exception(msg)

        msg = ("Route configuration status : %r "
               % (active_configured))
        LOG.info(msg)

    def delete_source_routes(self, context, kwargs):

        # REVISIT(VK): This was all along bad way, don't know why at all it
        # was done like this.
        active_configured = False
        url = const.request_url % (kwargs['vm_mgmt_ip'],
                                   const.CONFIGURATION_SERVER_PORT,
                                   'delete-source-route')
        route_info = []
        for source_cidr in kwargs['source_cidrs']:
            route_info.append({'source_cidr': source_cidr})
        data = json.dumps(route_info)
        msg = ("Initiating DELETE route request to primary service at: %r"
               % kwargs['vm_mgmt_ip'])
        LOG.info(msg)
        try:
            resp = requests.delete(url, data=data, timeout=self.timeout)
        except requests.exceptions.ConnectionError, err:
            msg = ("Failed to establish connection to primary service at: "
                   " %r. ERROR: %r" % (kwargs['vm_mgmt_ip'], err))
            LOG.error(msg)
            raise Exception(err)
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while deleting "
                   " route of service at: %r ERROR: %r"
                   % (kwargs['vm_mgmt_ip'],  err))
            LOG.error(msg)
            raise Exception(err)

        if resp.status_code in const.SUCCESS_CODES:
            active_configured = True

        msg = ("Route deletion status : %r "
               % (active_configured))
        LOG.info(msg)

    def configure_interfaces(self, context, kwargs):

        rule_info = kwargs['rule_info']

        active_rule_info = dict(
            provider_mac=rule_info['active_provider_mac'],
            stitching_mac=rule_info['active_stitching_mac'])

        active_fip = rule_info['active_fip']

        url = const.request_url % (active_fip,
                                   const.CONFIGURATION_SERVER_PORT, 'add_rule')
        data = json.dumps(active_rule_info)
        msg = ("Initiating POST request to add persistent rule to primary "
               "service with SERVICE ID: %r of tenant: %r at: %r" % (
                    rule_info['service_id'], rule_info['tenant_id'],
                    active_fip))
        LOG.info(msg)
        try:
            resp = requests.post(url, data, timeout=self.timeout)
        except requests.exceptions.ConnectionError, err:
            msg = ("Failed to establish connection to primary service at: "
                   "%r of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while adding "
                   "persistent rule of primary service at: %r "
                   "of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)

        try:
            result = resp.json()
        except ValueError as err:
            msg = ("Unable to parse response, invalid JSON. URL: "
                   "%r" % (url, str(err).capitalize()))
            LOG.error(msg)
            raise Exception(msg)
        if not result['status']:
            msg = ("Error adding persistent rule. URL: %r" % url)
            LOG.error(msg)
            raise Exception(msg)

        msg = ("Persistent rule successfully added for SERVICE ID: %r"
               " of tenant: %r" % (rule_info['service_id'],
                                   rule_info['tenant_id']))
        LOG.info(msg)

    def clear_interfaces(self, context, kwargs):

        rule_info = kwargs['rule_info']

        active_rule_info = dict(
            provider_mac=rule_info['provider_mac'],
            stitching_mac=rule_info['stitching_mac'])

        active_fip = rule_info['fip']

        msg = ("Initiating DELETE persistent rule for SERVICE ID: %r of "
               "tenant: %r " %
               (rule_info['service_id'], rule_info['tenant_id']))
        LOG.info(msg)
        url = const.request_url % (active_fip,
                                   const.CONFIGURATION_SERVER_PORT,
                                   'delete_rule')

        try:
            data = json.dumps(active_rule_info)
            resp = requests.delete(url, data=data, timeout=self.timeout)
        except requests.exceptions.ConnectionError, err:
            msg = ("Failed to establish connection to service at: %r "
                   "of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)
        except requests.exceptions.RequestException, err:
            msg = ("Unexpected ERROR happened  while deleting "
                   "persistent rule of service at: %r "
                   "of SERVICE ID: %r of tenant: %r . ERROR: %r" % (
                    active_fip, rule_info['service_id'],
                    rule_info['tenant_id'], str(err).capitalize()))
            LOG.error(msg)
            raise Exception(err)

        try:
            result = resp.json()
        except ValueError as err:
            msg = ("Unable to parse response, invalid JSON. URL: "
                   "%r" % (url, str(err).capitalize()))
            LOG.error(msg)
            raise Exception(msg)
        if not result['status'] or resp.status_code not in [200, 201, 202]:
            msg = ("Error deleting persistent rule. URL: %r" % url)
            LOG.error(msg)
            raise Exception(msg)
        msg = ("Persistent rule successfully deleted for SERVICE ID: %r"
               " of tenant: %r " % (rule_info['service_id'],
                                    rule_info['tenant_id']))


class VpnaasIpsecDriver(VpnGenericConfigDriver, BaseDriver):
    """
    Driver class for implementing VPN IPSEC configuration
    requests from VPNaas Plugin.
    """
    service_type = const.SERVICE_TYPE

    def __init__(self, vpn_agent):
        self.agent = vpn_agent
        self.handlers = {
            'vpn_service': {
                'create': self.create_vpn_service},
            'ipsec_site_connection': {
                'create': self.create_ipsec_conn,
                'update': self.update_ipsec_conn,
                'delete': self.delete_ipsec_conn}}

    @property
    def service_type(self):
        return "%s-%s" % (const.VYOS, const.SERVICE_TYPE)

    def _error_state(self, context, conn, message=''):
        self.agent.update_conn_status(
            context,
            const.SERVICE_TYPE,
            conn,
            const.STATE_ERROR)
        raise exc.ResourceErrorState(
            name='ipsec-site-conn',
            id=conn['id'], message=message)

    def _init_state(self, context, conn):
        LOG.emit("info", "IPSec: Configured successfully- %s " % conn['id'])
        self.agent.update_conn_status(
            context,
            const.SERVICE_TYPE,
            conn,
            const.STATE_INIT)

    def _get_fip_from_vpnsvc(self, vpn_svc):
        svc_desc = vpn_svc['description']
        tokens = svc_desc.split(';')
        fip = tokens[0].split('=')[1]
        return fip

    def _get_fip(self, svc_context):
        return self._get_fip_from_vpnsvc(svc_context['service'])

    def _get_ipsec_tunnel_local_cidr_from_vpnsvc(self, vpn_svc):
        svc_desc = vpn_svc['description']
        tokens = svc_desc.split(';')
        tunnel_local_cidr = tokens[1].split('=')[1]
        return tunnel_local_cidr

    def _get_ipsec_tunnel_local_cidr(self, svc_context):
        # Provider PTG is local cidr for the tunnel
        # - which is passed in svc description as of now
        return self.\
            _get_ipsec_tunnel_local_cidr_from_vpnsvc(
                svc_context['service'])

    def _get_stitching_fixed_ip(self, conn):
        desc = conn['description']
        tokens = desc.split(';')
        fixed_ip = tokens[3].split('=')[1]
        return fixed_ip

    def _get_user_access_ip(self, conn):
        desc = conn['description']
        tokens = desc.split(';')
        access_ip = tokens[2].split('=')[1]
        return access_ip

    def _ipsec_conn_correct_enc_algo(self, conn):
        ike_enc_algo = conn['ikepolicy']['encryption_algorithm']
        ipsec_enc_algo = conn['ipsecpolicy']['encryption_algorithm']

        algos = {
            'aes-128': "aes128",
            'aes-256': "aes256",
            'aes-192': "aes256"}

        if ike_enc_algo in algos.keys():
            ike_enc_algo = algos[ike_enc_algo]
        if ipsec_enc_algo in algos.keys():
            ipsec_enc_algo = algos[ipsec_enc_algo]

        conn['ikepolicy']['encryption_algorithm'] = ike_enc_algo
        conn['ipsecpolicy']['encryption_algorithm'] = ipsec_enc_algo

    def _ipsec_create_conn(self, context, mgmt_fip, conn):
        """
        Get the context for this conn
        Issue POST to the vyos agenet
        """
        svc_context = self.agent.get_ipsec_contexts(
            context, conn_id=conn['id'])[0]

        tunnel_local_cidr = self.\
            _get_ipsec_tunnel_local_cidr(svc_context)

        conn = svc_context['siteconns'][0]['connection']
        svc_context['siteconns'][0]['connection']['stitching_fixed_ip'] = (
            self._get_stitching_fixed_ip(conn))
        svc_context['siteconns'][0]['connection']['access_ip'] = (
            self._get_user_access_ip(conn))
        LOG.emit("info", "IPSec: Pushing ipsec configuration %s" % conn)
        conn['tunnel_local_cidr'] = tunnel_local_cidr
        self._ipsec_conn_correct_enc_algo(svc_context['siteconns'][0])
        vpn.RestApi(mgmt_fip).post("create-ipsec-site-conn", svc_context)
        self._init_state(context, conn)

    def _ipsec_create_tunnel(self, context, mgmt_fip, conn):
        svc_context = self.agent.get_ipsec_contexts(
            context, conn_id=conn['id'])[0]

        tunnel_local_cidr = self.\
            _get_ipsec_tunnel_local_cidr(svc_context)

        tunnel = {}
        tunnel['peer_address'] = conn['peer_address']
        tunnel['local_cidr'] = tunnel_local_cidr
        tunnel['peer_cidrs'] = conn['peer_cidrs']

        vpn.RestApi(mgmt_fip).post("create-ipsec-site-tunnel", tunnel)
        self._init_state(context, conn)

    def _ipsec_get_tenant_conns(self, context, mgmt_fip, conn,
                                on_delete=False):
        filters = {
            'tenant_id': [context.tenant_id],
            # 'vpnservice_id': [conn['vpnservice_id']],
            'peer_address': [conn['peer_address']]}

        tenant_conns = self.agent.get_ipsec_conns(
            context, filters)
        if not tenant_conns:
            if not on_delete:
                # Something went wrong - atleast the current
                # connection should be there
                msg = _("No tenant conns for filters (%s)" % (str(filters)))
                LOG.emit("error", msg)
                # Move conn into err state
                self._error_state(context, conn, msg)

        conn_to_remove = None
        for connection in tenant_conns:
            if connection['id'] == conn['id']:
                conn_to_remove = connection
                break
        if conn_to_remove:
            tenant_conns.remove(conn_to_remove)
        if not tenant_conns:
            return tenant_conns

        conn_list = []
        # get fip from connn description
        svc_ids = [conn['vpnservice_id'] for conn in tenant_conns]
        vpnservices = self.agent.get_vpn_services(context, ids=svc_ids)
        copy_svc = copy.deepcopy(vpnservices)
        # if service's fip matches new service's fip then both services
        # lie on same instance, in this case we should only create tunnel
        for vpn in copy_svc:
            if mgmt_fip in vpn['description']:
                continue
            else:
                vpnservices.remove(vpn)
        # we have all the vpnservices matching on this fip
        for vpn in vpnservices:
            matching_conn = [conn for conn in tenant_conns
                             if conn['vpnservice_id'] == vpn['id']]
            conn_list.extend(matching_conn)
        if not on_delete:
            # Remove the conns which are in pending_create
            # state. It might be possible that more than one
            # conns could get created in database before the rpc
            # method of dev driver is invoked.
            # We have to separate first conn creation from rest.
            copy_conns = copy.deepcopy(conn_list)
            for tconn in copy_conns:
                if tconn['status'] == (
                                const.STATE_PENDING and tconn in conn_list):
                    conn_list.remove(tconn)

        return conn_list

    def _ipsec_check_overlapping_peer(self, context,
                                      tenant_conns, conn):
        pcidrs = conn['peer_cidrs']
        for t_conn in tenant_conns:
            t_pcidrs = t_conn['peer_cidrs']
            if conn['vpnservice_id'] != t_conn['vpnservice_id']:
                continue

            for pcidr in pcidrs:
                if pcidr in t_pcidrs:
                    msg = _("Overlapping peer cidr (%s)" % (pcidr))
                    LOG.emit("error", msg)
                    self._error_state(
                        context, conn, msg)

    def _ipsec_delete_tunnel(self, context, mgmt_fip,
                             conn):
        lcidr = self.\
            _get_ipsec_tunnel_local_cidr_from_vpnsvc(conn)

        tunnel = {}
        tunnel['peer_address'] = conn['peer_address']
        tunnel['local_cidr'] = lcidr
        tunnel['peer_cidrs'] = conn['peer_cidrs']
        try:
            vpn.RestApi(mgmt_fip).delete(
                "delete-ipsec-site-tunnel", tunnel)
        except Exception as err:
            msg = ("IPSec: Failed to delete IPSEC tunnel. %s"
                   % str(err).capitalize())
            LOG.emit("error", msg)

    def _ipsec_delete_connection(self, context, mgmt_fip,
                                 conn):
        try:
            vpn.RestApi(mgmt_fip).delete(
                "delete-ipsec-site-conn",
                {'peer_address': conn['peer_address']})
        except Exception as err:
            msg = ("IPSec: Failed to delete IPSEC conn. %s"
                   % str(err).capitalize())
            LOG.emit("error", msg)

    def _ipsec_is_state_changed(self, svc_context, conn, fip):
        c_state = None
        lcidr = self.\
            _get_ipsec_tunnel_local_cidr(svc_context)
        if conn['status'] == const.STATE_INIT:
            tunnel = {
                'peer_address': conn['peer_address'],
                'local_cidr': lcidr,
                'peer_cidr': conn['peer_cidrs'][0]}
            output = vpn.RestApi(fip).get(
                "get-ipsec-site-tunnel-state",
                tunnel)
            state = output['state']

            if state.upper() == 'UP' and\
               conn['status'] != const.STATE_ACTIVE:
                c_state = const.STATE_ACTIVE
            if state.upper() == 'DOWN' and\
               conn['status'] == const.STATE_ACTIVE:
                c_state = const.STATE_PENDING

        if c_state:
            return c_state, True
        return c_state, False

    def _get_vm_mgmt_ip_from_desc(self, desc):
        svc_desc = desc['description']
        tokens = svc_desc.split(';')
        vm_mgmt_ip = tokens[0].split('=')[1]
        return vm_mgmt_ip

    def create_vpn_service(self, ev):
        context = ev.data.get('context')
        kwargs = ev.data.get('kwargs')
        svc = kwargs.get('resource')
        LOG.debug("Validating VPN service " + svc)
        validator = vpn.VPNSvcValidator(self)
        validator.validate(context, svc)

    def create_ipsec_conn(self, ev):
        context = ev.data.get('context')
        kwargs = ev.data.get('kwargs')
        conn = kwargs.get('resource')
        mgmt_fip = self._get_vm_mgmt_ip_from_desc(conn)

        LOG.emit("info", "IPsec: create siteconnection %s" % conn)
        # vpnservice_id = conn['vpnservice_id']
        """
        Following conditions -
        0) Conn with more than one peer_address
        is not allowed. This is because vyos has
        conns and tunnels inside conn. But openstack
        doesnt have tunnels. So conn will itslef need
        to be mapped to tunnel.
        a) Already conns exist for this tenant
            . In this case just add a tunnel
                . For same peer
                . Add peer for different peer
        b) First conn, create complete ipsec profile
        """
        t_lcidr = self._get_ipsec_tunnel_local_cidr_from_vpnsvc(conn)
        if t_lcidr in conn['peer_cidrs']:
            message = _("IPSec: Tunnel remote cidr %s conflicts "
                        "with local cidr." % t_lcidr)
            LOG.emit("error", message)
            self._error_state(context, conn, message)
        if len(conn['peer_cidrs']) != 1:
            msg = ("IPSec: Invalid number of peer CIDR. Should not be"
                   " less than 1.")
            LOG.emit("error", msg)
            self._error_state(context, conn, msg)

        try:
            tenant_conns = self._ipsec_get_tenant_conns(
                context, mgmt_fip, conn)
        except Exception as err:
            msg = ("IPSec: Failed to get tenant conns for IPSEC create. %s"
                   % str(err).capitalize())
            LOG.emit("error", msg)
        try:
            if not tenant_conns:
                self._ipsec_create_conn(context, mgmt_fip, conn)
            else:
                """
                Check if this conn has overlapping peer
                cidr with any other conn for the same
                tenant - we do not support this model.
                """
                self._ipsec_check_overlapping_peer(
                    context, tenant_conns, conn)
                self._ipsec_create_tunnel(context, mgmt_fip, conn)
        except exc.ResourceErrorState as rex:
            raise rex
        except Exception as ex:
            msg = "IPSec: Exception in creating ipsec conn: %s" % ex
            LOG.emit("error", msg)
            self._error_state(context, conn, msg)

    def update_ipsec_conn(self,  context, mgmt_fip, **kwargs):
        pass
        # svc_contexts = self.agent.get_ipsec_contexts(
        #    context, conn_id=kwargs.get('id'))
        # svc_context = svc_contexts[0]

        # self.pending_q.push(Resource(svc_context,  **kwargs))

        # Talk to service manager and get floating ip
        # (with tenant_id & svc_type as criteria)
        # Might have to send some commands to
        # update ipsec_conn params
        # Can IPSEC policy params / IKE policy params
        # be changed with connection intact ?
        # Need to figure out which all params can be
        # changed based on what vyos vm will support
        # Maintain this resource ? will be useful in case of update ?

    def delete_ipsec_conn(self, context, mgmt_fip, **kwargs):
        conn = kwargs.get('resource')
        msg = ("IPsec: delete siteconnection %s" % conn)
        LOG.emit("info", msg)
        # vpn_svc = self.agent.get_vpn_services(
        #    context, ids=[conn['vpnservice_id']])[0]

        # Get list of conns for tenant and peer
        tenant_conns = self._ipsec_get_tenant_conns(
            context, mgmt_fip, conn, on_delete=True)
        try:
            if tenant_conns:
                self._ipsec_delete_tunnel(
                    context, mgmt_fip, conn)
            else:
                self._ipsec_delete_connection(
                    context, mgmt_fip, conn)
        except exc.ResourceErrorState as rex:
            raise rex
        except Exception as ex:
            msg = "IPSec: delete ipsec conn failed %s " % ex
            LOG.emit("error", msg)
            self._error_state(context, conn, msg)

    def check_status(self,  context, svc_context):
        fip = self._get_fip(svc_context)
        sconns = svc_context['siteconns']
        for sconn in sconns:
            conn = sconn['connection']
            try:
                state, changed = self._ipsec_is_state_changed(
                    svc_context, conn, fip)
            except Exception as err:
                msg = ("Failed to check if IPSEC state is changed. %s"
                       % str(err).capitalize())
                LOG.emit("error", msg)
                continue
            if changed:
                self.agent.update_conn_status(
                    context,
                    const.SERVICE_TYPE,
                    conn,
                    state)

    def vpnservice_updated(self, context,  **kwargs):
        """Handle VPNaaS service driver change notifications."""
        LOG.info(_("SSL: Handling VPN service update notification '%s'"),
                 kwargs.get('reason', ''))

        resource = kwargs.get('resource')
        tenant_id = resource['tenant_id']
        # Synchronize the update operation per tenant.
        # Resources under tenant have inter dependencies.

        @lockutils.synchronized(tenant_id)
        def _vpnservice_updated(context, **kwargs):
            reason = kwargs.get('reason')
            rsrc = kwargs.get('rsrc_type')

            if rsrc not in self.handlers.keys():
                raise exc.UnknownResourceException(resource=rsrc)
            if reason not in self.handlers[rsrc].keys():
                raise exc.UnknownReasonException(reason=reason)

            self.handlers[rsrc][reason](context, **kwargs)

        return _vpnservice_updated(context, **kwargs)

