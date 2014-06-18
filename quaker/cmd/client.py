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

from quaker import config
from quaker.openstack.common import log as logging
import requests

from oslo.config import cfg
from oslo import messaging

OPTS = [
    cfg.StrOpt(
        'faye', default='http://127.0.0.1:4000/faye',
        help='URL for faye pub/sub messaging bus.'),
]
INFLUXDB_OPTS = [
    cfg.StrOpt(
        'url', default='http://127.0.0.1:8086',
        help='URL for influxdb service.'),
    cfg.StrOpt(
        'username', default=None,
        help='Username for the influxdb service.'),
    cfg.StrOpt(
        'password', default=None,
        help='Password for the influxdb service.'),
    cfg.StrOpt(
        'database', default='payload',
        help='Database name of the influxdb service.'),
]
INFLUXDB_GROUP = cfg.OptGroup(
    name='influxdb', title='Options for the influxdb service api.')

CONF = cfg.CONF
CONF.register_opts(OPTS)
CONF.register_group(INFLUXDB_GROUP)
CONF.register_opts(INFLUXDB_OPTS, INFLUXDB_GROUP)
LOG = logging.getLogger(__name__)


class NotificationEndpoint(object):

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        event = event_type.replace(".", "_")
        self.__influx(event, payload, metadata)

        headers = {
            'Content-type': 'application/json',
            'Accept': 'text/plain'
        }
        channel = "/%s" % event
        data = {
            'channel': channel,
            'data': {
                'event_type': event_type,
                'metadata': metadata,
                'payload': payload,
            }
        }
        r = requests.post(
            CONF.faye, data=simplejson.dumps(data), headers=headers)

    def __influx(self, event_type, payload, metadata):
        data = [
            {
                'name': event_type,
                'columns': [
                    'caller_id',
                    'caller_name',
                    'caller_number',
                    'queue_id',
                    'queue_name',
                    'queue_number',
                ],
                'points': [
                    [
                        payload['caller']['id'],
                        payload['caller']['name'],
                        payload['caller']['number'],
                        payload['queue']['id'],
                        payload['queue']['name'],
                        payload['queue']['number'],
                    ],
                ],
            }
        ]
        payload = {
            'p': CONF.influxdb.password,
            'u': CONF.influxdb.username,
        }
        url = CONF.influxdb.url
        headers = {
            'Content-type': 'application/json',
            'Accept': 'text/plain'
        }
        r = requests.post(
            url, data=simplejson.dumps(data), headers=headers, params=payload)


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
