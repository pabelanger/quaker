# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import sys

import eventlet
eventlet.monkey_patch(socket=True, select=True, thread=True)

from quaker import config
from quaker import monitor
from quaker.openstack.common import log as logging


def main():
    config.parse_args(sys.argv)
    logging.setup('quaker')
    srv = monitor.Monitor()
    srv.run()
