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


class FwaasRpcSender(object):
    """ RPC APIs to FWaaS Plugin.
    """
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, topic, host):
        ''' [DEE]: Modified according to the inheriting library (RPC/filter)
        super(FwPluginApi,
              self).__init__(topic=topic,
                             default_version=self.RPC_API_VERSION)
        '''
        self.host = host

    def set_firewall_status(self, context, firewall_id, status):
        """Make a RPC to set the status of a firewall."""
        '''ENQUEUE:return self.call(context,
                         self.make_msg('set_firewall_status', host=self.host,
                                       firewall_id=firewall_id, status=status))
        '''

    def firewall_deleted(self, context, firewall_id):
        """Make a RPC to indicate that the firewall resources are deleted."""
        '''ENQUEUE:return self.call(context,
                         self.make_msg('firewall_deleted', host=self.host,
                                       firewall_id=firewall_id))
        '''


class FwGenericConfigRpcReceiver(object):
    """
    APIs for receiving RPC messages from Orchestrator.
    """
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
    Handler class for demultiplexing firewall configuration
    requests from Orchestrator and sending to appropriate driver.

    """

    def __init__(self, sc, drivers):
        self._sc = sc
        self.drivers = drivers

    def _get_driver(self, data):
        ''' TO DO: Do demultiplexing logic based on vendor
                   when a different vendor comes.
        '''
        return self.drivers["vyos_config"]

    def handle_event(self, ev):
        try:
            msg = ("Worker process with ID: %s starting "
                   "to handle task: %s of topic: %s. "
                   % (os.getpid(), ev.id,
                      const.FIREWALL_GENERIC_CONFIG_RPC_TOPIC))
            LOG.debug(msg)

            driver = self._get_driver(ev.data)
            method = getattr(driver, "%s" % (ev.id.lower()))
            method(ev)
        except Exception as err:
            LOG.error("Failed to perform the operation: %s. %s"
                      % (ev.id, str(err).capitalize()))
        finally:
            self._sc.event_done(ev)


class FwaasRpcReceiver(object):
    """
    APIs for receiving RPC messages from Firewall plugin.
    """
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, conf, sc):
        self.conf = conf
        self._sc = sc

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


class FwaasHandler(object):
    """
    Handler class for demultiplexing firewall configuration
    requests from Fwaas Plugin and sending to appropriate driver.
    """

    def __init__(self, sc, drivers):
        self._sc = sc
        self.drivers = drivers

    def _get_driver(self, data):
        ''' TO DO: Do demultiplexing logic based on vendor
                   when a new vendor comes.
        '''
        return self.drivers['vyos_fwaas']()

    def handle_event(self, ev):
        try:
            msg = ("Worker process with ID: %s starting "
                   "to handle task: %s of topic: %s. "
                   % (os.getpid(), ev.id, const.FIREWALL_RPC_TOPIC))
            LOG.debug(msg)

            driver = self._get_driver(ev.data)
            method = getattr(driver, "%s" % (ev.id.lower()))
            method(ev)
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
    fw_rpc_mgr = FwaasRpcReceiver(conf, sc)
    fw_generic_rpc_mgr = FwGenericConfigRpcReceiver(conf, sc)

    fw_agent = _create_rpc_agent(sc, const.FIREWALL_RPC_TOPIC, fw_rpc_mgr)
    fw_generic_agent = _create_rpc_agent(
                                    sc,
                                    const.FIREWALL_GENERIC_CONFIG_RPC_TOPIC,
                                    fw_generic_rpc_mgr)

    sc.register_rpc_agents([fw_agent, fw_generic_agent])


def events_init(sc, drivers):
    evs = [
        Event(id='CONFIGURE_FIREWALL', handler=FwaasHandler(sc, drivers)),
        Event(id='UPDATE_FIREWALL', handler=FwaasHandler(sc, drivers)),
        Event(id='DELETE_FIREWALL', handler=FwaasHandler(sc, drivers)),

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
    ''' Create objects of firewall drivers.

        TODO: We need to make load_drivers() work by dynamic class detection
        from the driver directory and instantiate objects out of it.
    '''
    drivers = {"vyos_fwaas": FwaasDriver(),
               "vyos_config": FwGenericConfigDriver()}
    return drivers


def module_init(sc, conf):
    try:
        drivers = load_drivers()
    except Exception as err:
        LOG.error("Failed to load drivers. %s"
                  % (str(err).capitalize()))
        raise err
    else:
        LOG.debug("Loaded drivers successfully.")
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
              const.FIREWALL_GENERIC_CONFIG_RPC_TOPIC))
    try:
        rpc_init(sc, conf)
    except Exception as err:
        LOG.error("RPC initialization unsuccessful. " +
                  msg + " %s." % str(err).capitalize())
        raise err
    else:
        LOG.debug("RPC initialization successful. " + msg)

    msg = ("FIREWALL as a Service Module Initialized.")
    LOG.info(msg)
