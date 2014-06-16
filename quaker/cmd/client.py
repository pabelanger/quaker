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

import simplejson
import sys
import urllib2

from quaker import config
from quaker.openstack.common import log as logging

from oslo.config import cfg
from oslo import messaging

OPTS = [
    cfg.StrOpt(
        'faye', default='http://127.0.0.1:4000/faye',
        help='URL for faye pub/sub messaging bus.'),
]

CONF = cfg.CONF
CONF.register_opts(OPTS)
LOG = logging.getLogger(__name__)


class NotificationEndpoint(object):

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        data = {
            'event_type': event_type,
            'metadata': metadata,
            'payload': payload,
        }
        channel = "/%s" % event_type.replace(".", "_")
        req = urllib2.Request(CONF.faye, simplejson.dumps([{
            'channel': channel,
            'data': data,
        }]), headers={
            'Content-Type': 'application/json'
        })
        urllib2.urlopen(req)


def main():
    config.parse_args(sys.argv)
    logging.setup('quaker')

    messaging.set_transport_defaults('payload')
    transport = messaging.get_transport(cfg.CONF)
    targets = [
        messaging.Target(topic='notifications')
    ]
    endpoints = [
        NotificationEndpoint(),
    ]
    server = messaging.get_notification_listener(transport, targets, endpoints)
    server.start()
    server.wait()
