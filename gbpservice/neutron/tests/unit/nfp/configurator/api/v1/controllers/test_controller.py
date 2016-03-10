import mock
import unittest
import json

from pecan import make_app
from pecan import rest
from webtest import TestApp

from gbpservice.neutron.nfp.configurator.api import root_controller
from gbpservice.neutron.nfp.configurator.api.v1.controllers import controller


class ControllerTestCase(unittest.TestCase, rest.RestController):

    def setUp(self):
        RootController = root_controller.RootController()
        self.app = TestApp(make_app(RootController))
        self.data = json.dumps(
            {'request_data': {'info': {},
                              'config': [{'resource': 'Res',
                                          'kwargs': {'context': 'context'}
                                          }]}})

    def test_get_notifications(self):
        controller_object = controller.Controller("module_name")
        with mock.patch.object(
            controller_object.rpcclient.client, 'call') as rpc_mock,\
            mock.patch.object(
                controller_object.rpcclient.client, 'prepare') as (
                    prepare_mock):
            prepare_mock.return_value = controller_object.rpcclient.client
            rpc_mock.return_value = True
            value = controller_object.get()
        rpc_mock.assert_called_once_with(
            controller_object.rpcclient,
            'get_notifications')
        self.assertEqual(value, 'true')

    def test_post_create_network_function_device_config(self):
        response = self.app.post(
            '/v1/nfp/create_network_function_device_config',
            self.data)

        self.assertEqual(response.status_code, 200)

    def test_post_create_network_function_config(self):
        response = self.app.post(
            '/v1/nfp/create_network_function_config',
            self.data)

        self.assertEqual(response.status_code, 200)

    def test_post_delete_network_function_device_config(self):
        response = self.app.post(
            '/v1/nfp/delete_network_function_device_config',
            self.data)

        self.assertEqual(response.status_code, 200)

    def test_post_delete_network_function_config(self):

        response = self.app.post(
            '/v1/nfp/delete_network_function_config',
            self.data)

        self.assertEqual(response.status_code, 200)

    def test_put_update_network_function_device_config(self):

        response = self.app.put(
            '/v1/nfp/update_network_function_device_config',
            self.data)

        self.assertEqual(response.status_code, 200)

    def test_put_update_network_function_config(self):

        response = self.app.put(
            '/v1/nfp/update_network_function_config',
            self.data)

        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()

