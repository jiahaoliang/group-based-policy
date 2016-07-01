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

import shlex
import subprocess

import netifaces


def initiate_dhclient():
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        cmd = "sudo dhclient %s" % interface
        args = shlex.split(cmd)
        if not netifaces.ifaddresses(interface).get(netifaces.AF_INET):
            output, error = subprocess.Popen(
                args, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE).communicate()
            if error:
                raise
