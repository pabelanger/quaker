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

from ami import client
from oslo.config import cfg
from payload import messaging
from payload.openstack.common import context
from tornado.ioloop import IOLoop

from quaker.openstack.common import log as logging

OPTS = [
    cfg.StrOpt(
        'hostname', default='127.0.0.1',
        help='Hostname of the Asterisk manager interface.'),
    cfg.StrOpt(
        'username', default=None,
        help='Username of the Asterisk manager interface.'),
    cfg.StrOpt(
        'password', default=None,
        help='Password of the Asterisk manager interface.'),
]

CONF = cfg.CONF
CONF.register_opts(OPTS)
LOG = logging.getLogger(__name__)


def _send_notification(event, payload):
    notification = event.replace(" ", "_")
    notification = "queue.%s" % notification
    notifier = messaging.get_notifier(publisher_id='payload')
    notifier.info(context.RequestContext(), notification, payload)


class Monitor(object):
    def __init__(self):
        self.ami = client.AMIClient()
        self.ami.register_event('AgentCalled', self._handle_agent_called)
#        self.ami.register_event('AgentRingNoAnswer', self.process_event)
#        self.ami.register_event('Join', self.process_event)
#        self.ami.register_event('QueueCallerAbandon', self.process_event)

    def on_connect(self, data):
        LOG.info('Connected to AMI')

    def process_event(self, data):
        print data

    def _handle_agent_called(self, data):
        vars = data['variable'].split(',')
        callid = data['uniqueid']
        for var in vars:
            key, value = var.split('=', 1)
            if key == 'SIPCALLID':
                callid = value
        json = {
            'caller': {
                'id': callid,
                'name': data['connectedlinename'],
                'number': data['connectedlinenum'],
            },
        }

        LOG.info(json)
        _send_notification('Alerting', json)

    def run(self):
        self.ami.connect(
            hostname=CONF.hostname, username=CONF.username,
            password=CONF.password, callback=self.on_connect)
        IOLoop.instance().start()
