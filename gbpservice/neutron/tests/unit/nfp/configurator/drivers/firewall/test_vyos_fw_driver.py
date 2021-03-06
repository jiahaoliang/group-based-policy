#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import requests
import unittest

from oslo_config import cfg
from oslo_serialization import jsonutils

from gbpservice.neutron.tests.unit.nfp.configurator.test_data import (
                                                        fw_test_data as fo)
from gbpservice.nfp.configurator.drivers.firewall.vyos import (
                                                    vyos_fw_driver as fw_dvr)


STATUS_ACTIVE = "ACTIVE"

""" Implements test cases for driver methods
of generic config.

"""


class FwGenericConfigDriverTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(FwGenericConfigDriverTestCase, self).__init__(*args, **kwargs)
        self.fo = fo.FakeObjects()
        with mock.patch.object(cfg, 'CONF') as mock_cfg:
            mock_cfg.configure_mock(rest_timeout=120, host='foo')
            self.driver = fw_dvr.FwaasDriver(mock_cfg)
        self.resp = mock.Mock()
        self.fake_resp_dict = {'status': True}
        self.kwargs = self.fo._fake_resource_data()

    def test_configure_interfaces(self):
        """ Implements test case for configure interfaces method
        of generic config driver.

        Returns: none

        """

        with mock.patch.object(
                requests, 'post', return_value=self.resp) as mock_post, \
            mock.patch.object(
                self.resp, 'json', return_value=self.fake_resp_dict):
            self.driver.configure_interfaces(self.fo.context, self.kwargs)

            mock_post.assert_called_with(self.fo.url_for_add_inte,
                                         self.fo.data_for_interface,
                                         timeout=self.fo.timeout)

    def test_clear_interfaces(self):
        """ Implements test case for clear interfaces method
        of generic config driver.

        Returns: none

        """

        self.resp = mock.Mock(status_code=200)
        with mock.patch.object(
                requests, 'delete', return_value=self.resp) as mock_delete, \
            mock.patch.object(
                self.resp, 'json', return_value=self.fake_resp_dict):
            self.driver.clear_interfaces(self.fo.context, self.kwargs)

            mock_delete.assert_called_with(
                                self.fo.url_for_del_inte,
                                data=self.fo.data_for_interface,
                                timeout=self.fo.timeout)

    def test_configure_source_routes(self):
        """ Implements test case for configure routes method
        of generic config driver.

        Returns: none

        """

        with mock.patch.object(
                requests, 'post', return_value=self.resp) as mock_post, \
            mock.patch.object(
                self.resp, 'json', return_value=self.fake_resp_dict):
            self.driver.configure_routes(
                self.fo.context, self.kwargs)

            mock_post.assert_called_with(self.fo.url_for_add_src_route,
                                         data=self.fo.data_for_add_src_route,
                                         timeout=self.fo.timeout)

    def test_delete_source_routes(self):
        """ Implements test case for clear routes method
        of generic config driver.

        Returns: none

        """

        with mock.patch.object(
                requests, 'delete', return_value=self.resp) as mock_delete, \
            mock.patch.object(
                self.resp, 'json', return_value=self.fake_resp_dict):
            self.driver.clear_routes(
                self.fo.context, self.kwargs)

            mock_delete.assert_called_with(
                                self.fo.url_for_del_src_route,
                                data=self.fo.data_for_del_src_route,
                                timeout=self.fo.timeout)

""" Implements test cases for driver methods
of firewall.

"""


class FwaasDriverTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(FwaasDriverTestCase, self).__init__(*args, **kwargs)
        self.fo = fo.FakeObjects()
        with mock.patch.object(cfg, 'CONF') as mock_cfg:
            mock_cfg.configure_mock(rest_timeout=self.fo.timeout, host='foo')
            self.driver = fw_dvr.FwaasDriver(mock_cfg)
        self.resp = mock.Mock()
        self.fake_resp_dict = {'status': True,
                               'config_success': True,
                               'delete_success': True}
        self.fo.firewall = self.fo._fake_firewall_obj()
        self.firewall = jsonutils.dumps(self.fo.firewall)

    def test_create_firewall_fwaasdriver(self):
        """ Implements test case for create firewall method
        of firewall's drivers.

        Returns: none

        """

        with mock.patch.object(
                requests, 'post', return_value=self.resp) as mock_post, \
            mock.patch.object(
                self.resp, 'json', return_value=self.fake_resp_dict):
            self.driver.create_firewall(self.fo.context,
                                        self.fo.firewall, self.fo.host)
            mock_post.assert_called_with(self.fo.url_for_config_fw,
                                         self.firewall,
                                         timeout=self.fo.timeout)

    def test_create_firewall_key_error_fwaasdriver(self):
        """ Implements test case for catching key error in
        create firewall method of firewall's drivers.

        Returns: none

        """

        self.fo.firewall.pop('description')
        with self.assertRaises(KeyError):
            self.driver.create_firewall(self.fo.context,
                                        self.fo.firewall, self.fo.host)

    def test_update_firewall_fwaasdriver(self):
        """ Implements test case for update firewall method
        of firewall's drivers.

        Returns: none

        """

        with mock.patch.object(
                requests, 'put', return_value=self.resp) as mock_put, \
            mock.patch.object(
                self.resp, 'json', return_value=self.fake_resp_dict):
            self.driver.update_firewall(self.fo.context,
                                        self.fo.firewall, self.fo.host)
            mock_put.assert_called_with(self.fo.url_for_update_fw,
                                        data=self.firewall,
                                        timeout=self.fo.timeout)

    def test_update_firewall_key_error_fwaasdriver(self):
        """ Implements test case for catching key error in
        update firewall method of firewall's drivers.

        Returns: none

        """

        self.fo.firewall.pop('description')
        with self.assertRaises(KeyError):
            self.driver.update_firewall(self.fo.context,
                                        self.fo.firewall, self.fo.host)

    def test_delete_firewall_fwaasdriver(self):
        """ Implements test case for delete firewall method
        of firewall's drivers.

        Returns: none

        """

        with mock.patch.object(
                requests, 'delete', return_value=self.resp) as mock_delete, \
            mock.patch.object(
                self.resp, 'json', return_value=self.fake_resp_dict):
            self.driver.delete_firewall(self.fo.context,
                                        self.fo.firewall, self.fo.host)
            mock_delete.assert_called_with(self.fo.url_for_delete_fw,
                                           data=self.firewall,
                                           timeout=self.fo.timeout)

    def test_delete_firewall_key_error_fwaasdriver(self):
        """ Implements test case for catching key error in
        delete firewall method of firewall's drivers.

        Returns: none

        """

        self.fo.firewall.pop('description')
        with self.assertRaises(KeyError):
            self.driver.delete_firewall(self.fo.context,
                                        self.fo.firewall, self.fo.host)


if __name__ == '__main__':
    unittest.main()
