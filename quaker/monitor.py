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
from payload.cache import api
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
            'QueueMemberAdded', self._handle_queue_member_added)
        self.ami.register_event(
            'QueueMemberPaused', self._handle_queue_member_paused)
        self.ami.register_event(
            'QueueMemberRemoved', self._handle_queue_member_removed)
        self.ami.register_event(
            'UserEvent', self._handle_user_event)
        self.redis = api.get_instance()
        self.callers = dict()

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
            'number': variables['called_number']
        }
        return json

    def _get_caller(self, variables):
        try:
            data = self.redis.get_queue_caller(
                queue_id=variables['queue_name'], uuid=variables['caller_id'])
            json = {
                'uuid': data.uuid,
                'created_at': data.created_at,
                'name': data.name,
                'number': data.number,
                'position': data.position,
                'queue_id': data.queue_id,
            }
        except Exception as e:
            json = {
                'uuid': variables['caller_id'],
                'created_at': None,
                'name': variables['caller_name'],
                'number': variables['caller_number'],
                'position': None,
                'queue_id': variables['queue_name'],
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

    def _handle_user_event(self, data):
        if data['userevent'] == 'QueueMemberCancel':
            self._handle_queue_member_cancel(data)
        elif data['userevent'] == 'QueueCallerCreate':
            self._handle_queue_caller_create(data)
        else:
            self._handle_queue_caller_delete(data)

    def _handle_queue_caller_delete(self, data):
        try:
            res = self.redis.get_queue_caller(
                queue_id=data['quaker_queue_name'],
                uuid=data['quaker_caller_id'])

            self.redis.delete_queue_caller(
                res.queue_id, uuid=res.uuid)
        except Exception as e:
            pass

    def _handle_queue_member_cancel(self, data):
        json = {}
        json['caller'] = {
            'uuid': data['quaker_caller_id'],
            'name': None,
            'number': None,
        }
        json['queue'] = {
            'id': None,
            'name': data['quaker_queue_name'],
            'number': data['quaker_queue_number'],
        }
        json['member'] = {
            'id': None,
            'name': data['agentname'],
            'number': self._get_member_number(data['agentname']),
        }
        json['reason'] = '19'

        self.redis.update_queue_member(
            queue_id=data['quaker_queue_name'],
            uuid=data['agentname'], status=1)

        try:
            self.redis.update_queue_caller(
                queue_id=data['quaker_queue_name'], uuid=data['agentname'],
                status=1)
        except Exception as e:
            pass

        LOG.info(json)
        _send_notification('member.cancel', json)

    def _handle_agent_called(self, data):
        variables = self._get_quaker_vars(data['variable'])

        json = self._get_common_headers(variables)
        json['member'] = {
            'id': None,
            'name': data['agentname'],
            'number': self._get_member_number(data['agentcalled']),
        }

        self.redis.update_queue_caller(
            queue_id=json['queue']['name'], uuid=json['caller']['uuid'],
            member_uuid=json['member']['name'], status=2)

        self.redis.update_queue_member(
            queue_id=json['queue']['name'], uuid=json['member']['name'],
            status=6)

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

        self.redis.update_queue_member(
            queue_id=json['queue']['name'], uuid=json['member']['name'],
            status=1)

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

        self.redis.update_queue_caller(
            queue_id=json['queue']['name'], uuid=json['caller']['uuid'],
            status=3)

        self.redis.delete_queue_caller(
            json['queue']['name'], uuid=json['caller']['uuid'])

        self.redis.update_queue_member(
            queue_id=json['queue']['name'], uuid=json['member']['name'],
            status=2)

        LOG.info(json)
        _send_notification('member.connect', json)

    def _handle_queue_caller_create(self, data):
        res = self.redis.create_queue_caller(
            data['quaker_queue_name'], uuid=data['quaker_caller_id'],
            name=data['quaker_caller_name'], number=data['quaker_caller_number'],
            status=1)

    def _handle_queue_member_added(self, data):
        json = {
            'member': {
                'id': data['membername'],
                'name': data['membername'],
                'number': data['membername'],
            },
        }

        if data['queue'] == '_CSRs':
            LOG.info(json)
            _send_notification('member.login', json)
            return

        json['queue'] = {
            'id': data['queue'],
            'name': data['queue'],
            'number': None,
        }

        self.redis.create_queue_member(
            queue_id=json['queue']['id'], uuid=json['member']['id'],
            number=json['member']['number'], status=1)

        LOG.info(json)

    def _handle_queue_member_removed(self, data):
        json = {
            'member': {
                'id': data['membername'],
                'name': data['membername'],
                'number': data['membername'],
            },
        }

        if data['queue'] == '_CSRs':
            LOG.info(json)
            _send_notification('member.logout', json)
            return

        json['queue'] = {
            'id': data['queue'],
            'name': data['queue'],
            'number': None,
        }

        self.redis.delete_queue_member(
            queue_id=json['queue']['id'], uuid=json['member']['id'])

        LOG.info(json)

    def _handle_queue_member_paused(self, data):
        paused = 0
        if 'reason' in data:
            paused = data['reason']

        self.redis.update_queue_member(
            queue_id=data['queue'], uuid=data['membername'],
            paused=paused)

    def run(self):
        self.ami.connect(
            hostname=CONF.hostname, username=CONF.username,
            password=CONF.password, callback=self.on_connect)
        IOLoop.instance().start()
