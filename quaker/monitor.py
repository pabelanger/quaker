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

import re

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
    notifier = messaging.get_notifier(publisher_id='quaker')
    notifier.info(context.RequestContext(), notification, payload)


class Monitor(object):
    def __init__(self):
        self.ami = client.AMIClient()
        self.ami.register_event('AgentCalled', self._handle_agent_called)
        self.ami.register_event('AgentComplete', self._handle_agent_complete)
        self.ami.register_event('AgentConnect', self._handle_agent_connect)
        self.ami.register_event(
            'AgentRingNoAnswer', self._handle_agent_ring_no_answer)
        self.ami.register_event('Join', self._handle_join)
        self.ami.register_event(
            'QueueCallerAbandon', self._handle_queue_caller_abandon)
        self.ami.register_event(
            'QueueMemberAdded', self._handle_queue_member_added)
        self.ami.register_event(
            'QueueMemberPaused', self._handle_queue_member_paused)
        self.ami.register_event(
            'QueueMemberRemoved', self._handle_queue_member_removed)
        self.ami.register_event(
            'QueueMemberStatus', self._handle_queue_member_state)

    def on_connect(self, data):
        LOG.info('Connected to AMI')

    def process_event(self, data):
        print data

    def _get_quaker_vars(self, variables):
        res = {}
        for var in variables.split(','):
            key, value = var.split('=', 1)
            if key.startswith('QUAKER_'):
                res[key[7:].lower()] = value

        return res

    def _get_called(self, variables):
        json = {
            'number': variables['called_number'],
        }
        return json

    def _get_caller(self, variables):
        json = {
            'id': variables['caller_id'],
            'name': variables['caller_name'],
            'number': variables['caller_number'],
        }
        return json

    def _get_queue(self, variables):
        json = {
            'id': None,
            'name': variables['queue_name'],
            'number': variables['queue_number'],
        }
        return json

    def _get_member_number(self, data):
        res = re.search('\d+(^@)?', data)

        return res.group()

    def _get_common_headers(self, data):
        res = {}
        res['called'] = self._get_called(data)
        res['caller'] = self._get_caller(data)
        res['queue'] = self._get_queue(data)

        return res

    def _handle_agent_ring_no_answer(self, data):
        variables = self._get_quaker_vars(data['variable'])

        json = self._get_common_headers(variables)
        json['id'] = data['uniqueid']
        json['reason'] = '19'

        LOG.info(json)
        _send_notification('member.cancel', json)

    def _handle_agent_called(self, data):
        variables = self._get_quaker_vars(data['variable'])

        json = self._get_common_headers(variables)
        json['id'] = data['uniqueid']
        json['member'] = {
            'id': None,
            'name': data['agentname'],
            'number': self._get_member_number(data['agentcalled']),
        }

        LOG.info(json)
        _send_notification('member.alert', json)

    def _handle_agent_complete(self, data):
        variables = self._get_quaker_vars(data['variable'])

        json = self._get_common_headers(variables)
        json['id'] = data['uniqueid']
        json['member'] = {
            'id': None,
            'name': data['membername'],
            'number': self._get_member_number(data['member']),
        }

        LOG.info(json)
        _send_notification('member.complete', json)

    def _handle_agent_connect(self, data):
        variables = self._get_quaker_vars(data['variable'])

        json = self._get_common_headers(variables)
        json['id'] = data['uniqueid']
        json['member'] = {
            'id': None,
            'name': data['membername'],
            'number': self._get_member_number(data['member']),
        }

        LOG.info(json)
        _send_notification('member.connect', json)

    def _handle_join(self, data):
        variables = self._get_quaker_vars(data['variable'])

        json = self._get_common_headers(variables)
        json['id'] = data['uniqueid']
        json['position'] = data['position']

        LOG.info(json)
        _send_notification('enter', json)

    def _handle_queue_caller_abandon(self, data):
        json = {
            'queue': {
                'id': None,
                'name': data['queue'],
                'number': None,
            },
        }

        json['id'] = data['uniqueid']
        json['position'] = data['position']
        json['reason'] = '0'

        LOG.info(json)
        _send_notification('exit', json)

    def _handle_queue_member_added(self, data):
        if data['queue'] == '_CSRs':
            self._handle_queue_member_login(data)

    def _handle_queue_member_login(self, data):
        json = {
            'member': {
                'id': None,
                'name': data['membername'],
                'number': self._get_member_number(data['location']),
            },
        }

        LOG.info(json)
        _send_notification('member.login', json)

    def _handle_queue_member_logout(self, data):
        json = {
            'member': {
                'id': None,
                'name': data['membername'],
                'number': self._get_member_number(data['location']),
            },
        }

        LOG.info(json)
        _send_notification('member.logout', json)

    def _handle_queue_member_removed(self, data):
        if data['queue'] == '_CSRs':
            self._handle_queue_member_logout(data)

    def _handle_queue_member_state(self, data):
        json = {
            'queue': {
                'id': None,
                'name': data['queue'],
                'number': None,
            },
        }
        json['member'] = {
            'id': None,
            'name': data['membername'],
            'number': self._get_member_number(data['location']),
        }
        json['status'] = data['status']

        LOG.info(json)
        _send_notification('member.state', json)

    def _handle_queue_member_paused(self, data):
        json = {
            'queue': {
                'id': None,
                'name': data['queue'],
                'number': None,
            },
        }
        json['member'] = {
            'id': None,
            'name': data['membername'],
            'number': self._get_member_number(data['location']),
        }
        json['reason'] = data['paused']

        LOG.info(json)
        _send_notification('member.pause', json)

    def run(self):
        self.ami.connect(
            hostname=CONF.hostname, username=CONF.username,
            password=CONF.password, callback=self.on_connect)
        IOLoop.instance().start()
