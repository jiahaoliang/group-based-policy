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

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging

from neutron import manager

from gbpservice.neutron.nsf.configurator.lib import fw_constants as const
from gbpservice.neutron.nsf.core.main import Event
from gbpservice.neutron.nsf.core.main import RpcAgent
''' TO DO: Avoid the following imports. Do dynamic driver imports
'''
from gbpservice.neutron.nsf.configurator.drivers.firewall.\
                            vyos.vyos_fw_driver import FwaasDriver
from gbpservice.neutron.nsf.configurator.drivers.firewall.\
                            vyos.vyos_fw_driver import FwGenericConfigDriver

LOG = logging.getLogger(__name__)


class FwaasRpcReceiver(object):
    """
    This class implements requests to configure VYOS FW specific services.
    """
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, conf, sc):
        self.conf = conf
        self._sc = sc

    def init_host(self):
        ev = self._sc.event(id='INIT_HOST', data='')
        self._sc.poll_event(ev)

    def configure_firewall(self, context, firewall):
        arg_dict = {'context': context,
                    'firewall': firewall}
        ev = self._sc.event(id='CONFIGURE_FW', data=arg_dict)
        self._sc.rpc_event(ev)

    def update_firewall(self, context, firewall):
        arg_dict = {'context': context,
                    'firewall': firewall}
        ev = self._sc.event(id='UPDATE_FW', data=arg_dict)
        self._sc.rpc_event(ev)

    def delete_firewall(self, context, firewall):
        arg_dict = {'context': context,
                    'firewall': firewall}
        ev = self._sc.event(id='DELETE_FW', data=arg_dict)
        self._sc.rpc_event(ev)


class FwGenericConfigRpcReceiver(object):
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, conf, sc):
        self.conf = conf
        self._sc = sc

    def configure_interfaces(self, context, **kwargs):
        ''' In previous implementation, 'context' is not used '''
        arg_dict = {'kwargs': kwargs}
        ev = self._sc.event(id='CONFIGURE_INTERFACES', data=arg_dict)
        self._sc.rpc_event(ev)

    def clear_interfaces(self, context, vm_mgmt_ip, service_vendor,
                         provider_interface_position,
                         stitching_interface_position):
        arg_dict = {'context': context,
                    'vm_mgmt_ip': vm_mgmt_ip,
                    'service_vendor': service_vendor,
                    'provider_interface_position': provider_interface_position,
                    'stitching_interface_position':
                        stitching_interface_position}
        ev = self._sc.event(id='CLEAR_INTERFACES', data=arg_dict)
        self._sc.rpc_event(ev)

    def configure_license(self, context, vm_mgmt_ip,
                          service_vendor, license_key):
        arg_dict = {'context': context,
                    'vm_mgmt_ip': vm_mgmt_ip,
                    'service_vendor': service_vendor,
                    'license_key': license_key}
        ev = self._sc.event(id='CONFIGURE_LICENSE', data=arg_dict)
        self._sc.rpc_event(ev)

    def release_license(self, context, vm_mgmt_ip,
                        service_vendor, license_key):
        arg_dict = {'context': context,
                    'vm_mgmt_ip': vm_mgmt_ip,
                    'service_vendor': service_vendor,
                    'license_key': license_key}
        ev = self._sc.event(id='RELEASE_LICENSE', data=arg_dict)
        self._sc.rpc_event(ev)

    def configure_source_routes(self, context, vm_mgmt_ip, service_vendor,
                                source_cidrs, destination_cidr, gateway_ip,
                                provider_interface_position):
        arg_dict = {'context': context,
                    'vm_mgmt_ip': vm_mgmt_ip,
                    'service_vendor': service_vendor,
                    'source_cidrs': source_cidrs,
                    'destination_cidr': destination_cidr,
                    'gateway_ip': gateway_ip,
                    'provider_interface_position': (
                                        provider_interface_position),
                    'standby_floating_ip': None}
        ev = self._sc.event(id='CONFIGURE_SOURCE_ROUTES', data=arg_dict)
        self._sc.rpc_event(ev)

    def delete_source_routes(self, context, vm_mgmt_ip, service_vendor,
                             source_cidrs, provider_interface_position):
        arg_dict = {'context': context,
                    'vm_mgmt_ip': vm_mgmt_ip,
                    'service_vendor': service_vendor,
                    'source_cidrs': source_cidrs,
                    'provider_interface_position': (
                                    provider_interface_position)}
        ev = self._sc.event(id='DELETE_SOURCE_ROUTES', data=arg_dict)
        self._sc.rpc_event(ev)

    def add_persistent_rule(self, context, **kwargs):
        ''' In previous implementation, 'context' is not used '''
        arg_dict = {'kwargs': kwargs}
        ev = self._sc.event(id='ADD_PERSISTENT_RULE', data=arg_dict)
        self._sc.rpc_event(ev)

    def del_persistent_rule(self, context, **kwargs):
        ''' In previous implementation, 'context' is not used '''
        arg_dict = {'kwargs': kwargs}
        ev = self._sc.event(id='DELETE_PERSISTENT_RULE', data=arg_dict)
        self._sc.rpc_event(ev)


class FwGenericConfigHandler(object):
    """
    This class implements requests to configure VYOS services.
    """

    def __init__(self, sc, drivers):
        self._sc = sc
        self.drivers = drivers

    def _get_driver(self, data):
        ''' TO DO: Do demultiplexing logic based on vendor

            # LOGIC

        '''
        return self.drivers["vyos_config"]

    def handle_event(self, ev):
        try:
            msg = ("Worker process with ID: %s starting "
                   "to handle task: %s of topic: %s. "
                   % (os.getpid(), ev.id, const.VYOS_FIREWALL_RPC_TOPIC))
            LOG.debug(msg)

            driver = self._get_driver(ev.data)

            if ev.id == 'CONFIGURE_INTERFACES':
                driver.configure_interfaces(ev)
            elif ev.id == 'CLEAR_INTERFACES':
                driver.clear_interfaces(ev)
            elif ev.id == 'CONFIGURE_LICENSE':
                driver.configure_license(ev)
            elif ev.id == 'RELEASE_LICENSE':
                driver.release_license(ev),
            elif ev.id == 'CONFIGURE_SOURCE_ROUTES':
                driver.configure_source_routes(ev)
            elif ev.id == 'DELETE_SOURCE_ROUTES':
                driver.delete_source_routes(ev)
            elif ev.id == 'ADD_PERSISTENT_RULE':
                driver.add_persistent_rule(ev)
            elif ev.id == 'DEL_PERSISTENT_RULE':
                driver.del_persistent_rule(ev)
            else:
                msg = ("Wrong call to configure VYOS FIREWALL.")
                LOG.error(msg)
                raise Exception(msg)
        except Exception as err:
            LOG.error("Failed to perform the operation: %s. %s"
                      % (ev.id, str(err).capitalize()))
        finally:
            self._sc.event_done(ev)


class FwaasRpcSender(object):
    """ RPC APIs to FWaaS Plugin.
    """

    RPC_API_VERSION = '1.0'

    def __init__(self, topic, host):
        ''' [DEE]: Modified according to the inheriting library (RPC/filter)
        super(FwPluginApi,
              self).__init__(topic=topic,
                             default_version=self.RPC_API_VERSION)
        '''
        self.host = host

    def set_firewall_status(self, context, firewall_id, status):
        """Make a RPC to set the status of a firewall."""
        return self.call(context,
                         self.make_msg('set_firewall_status', host=self.host,
                                       firewall_id=firewall_id, status=status))

    def firewall_deleted(self, context, firewall_id):
        """Make a RPC to indicate that the firewall resources are deleted."""
        return self.call(context,
                         self.make_msg('firewall_deleted', host=self.host,
                                       firewall_id=firewall_id))


class FwaasHandler(manager.Manager):

    def __init__(self, sc, drivers):
        self._sc = sc
        self.drivers = drivers

    def _get_driver(self, data):
        ''' TO DO: Do demultiplexing logic based on vendor

            # LOGIC

        '''
        return self.drivers['vyos_fwaas']

    def handle_poll_event(self, ev):
        try:
            msg = ("Worker process with ID: %s starting "
                   "to handle task: %s for poll event of topic: %s. "
                   % (os.getpid(), ev.id, const.FIREWALL_RPC_TOPIC))
            LOG.debug(msg)

            if ev.id == 'INIT_HOST':
                self._init_host(ev)
            else:
                msg = ("Wrong poll event call for firewall.")
                LOG.error(msg)
                raise Exception(msg)
        except Exception as err:
            LOG.error("Failed to perform the poll operation: %s. %s"
                      % (ev.id, str(err).capitalize()))

    def handle_event(self, ev):
        try:
            msg = ("Worker process with ID: %s starting "
                   "to handle task: %s of topic: %s. "
                   % (os.getpid(), ev.id, const.FIREWALL_RPC_TOPIC))
            LOG.debug(msg)

            driver = self._get_driver(ev.data)

            if ev.id == 'CONFIGURE_FW':
                driver.configure_firewall(ev)
            elif ev.id == 'UPDATE_FW':
                driver.update_firewall(ev)
            elif ev.id == 'DELETE_FW':
                driver.delete_firewall(ev)
            else:
                msg = ("Wrong call to configure firewall.")
                LOG.error(msg)
                raise Exception(msg)
        except Exception as err:
            LOG.error("Failed to perform the operation: %s. %s"
                      % (ev.id, str(err).capitalize()))
        finally:
            self._sc.event_done(ev)


def _create_rpc_agent(sc, topic, manager):
    return RpcAgent(sc,
                    host=cfg.CONF.host,
                    topic,
                    manager)


def rpc_init(sc, conf):
    fwrpcmgr = FwaasRpcReceiver(conf, sc)
    vyosfwrpcmgr = FwGenericConfigRpcReceiver(conf, sc)

    fwagent = _create_rpc_agent(sc, const.FIREWALL_RPC_TOPIC, fwrpcmgr)
    vyosfwagent = _create_rpc_agent(sc, const.VYOS_FIREWALL_RPC_TOPIC,
                                    vyosfwrpcmgr)

    sc.register_rpc_agents([fwagent, vyosfwagent])


def events_init(sc, drivers):
    evs = [
        Event(id='CONFIGURE_FW', handler=FwaasHandler(sc, drivers)),
        Event(id='UPDATE_FW', handler=FwaasHandler(sc, drivers)),
        Event(id='DELETE_FW', handler=FwaasHandler(sc, drivers)),

        Event(id='CONFIGURE_INTERFACES', handler=FwGenericConfigHandler(
                                                                sc, drivers)),
        Event(id='CLEAR_INTERFACES', handler=FwGenericConfigHandler(
                                                                sc, drivers)),
        Event(id='CONFIGURE_LICENSE', handler=FwGenericConfigHandler(
                                                                sc, drivers)),
        Event(id='RELEASE_LICENSE', handler=FwGenericConfigHandler(
                                                                sc, drivers)),
        Event(id='CONFIGURE_SOURCE_ROUTES', handler=FwGenericConfigHandler(
                                                                sc, drivers)),
        Event(id='DELETE_SOURCE_ROUTES', handler=FwGenericConfigHandler(
                                                                sc, drivers)),
        Event(id='ADD_PERSISTENT_RULE', handler=FwGenericConfigHandler(
                                                                sc, drivers)),
        Event(id='DEL_PERSISTENT_RULE', handler=FwGenericConfigHandler(
                                                                sc, drivers))]
    sc.register_events(evs)


def load_drivers():
    ''' Create object of firewall drivers
    '''
    drivers = {"vyos_fwaas": FwaasDriver(),
               "vyos_config": FwGenericConfigDriver()}
    return drivers


def module_init(sc, conf):
    drivers = load_drivers()

    try:
        events_init(sc, drivers)
    except Exception as err:
        LOG.error("Events initialization unsuccessful. %s"
                  % (str(err).capitalize()))
        raise err
    else:
        LOG.debug("Events initialization successful.")

    msg = ("RPC topics are: %s and %s."
           % (const.FIREWALL_RPC_TOPIC,
              const.VYOS_FIREWALL_RPC_TOPIC))
    try:
        rpc_init(sc, conf)
    except Exception as err:
        LOG.error("RPC initialization unsuccessful. " +
                  msg + " %s." % str(err).capitalize())
        raise err
    else:
        LOG.debug("RPC initialization successful. " + msg)

    msg = ("VYOS FIREWALL module initialized.")
    LOG.info(msg)
