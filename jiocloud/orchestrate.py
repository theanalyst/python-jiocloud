#    Copyright Reliance Jio Infocomm, Ltd.
#    Author: Soren Hansen <Soren.Hansen@ril.com>
#
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
#
import argparse
import etcd
import errno
import socket
import sys
import time

class DeploymentOrchestrator(object):
    def __init__(self, host='127.0.0.1', port=4001):
        self.etcd = etcd.Client(host=host, port=port)

    def trigger_update(self, new_version):
        self.etcd.write('/current_version', new_version)

    def pending_update(self):
        return not (self.current_version() == self.get_currently_running_version())

    def current_version(self):
        return self.etcd.read('/current_version').value.strip()

    def update_own_info(self, hostname, interval=60):
        version_dir = '/running_version/%s' % self.get_currently_running_version()
        self.etcd.write(version_dir, None, dir=True, ttl=(interval*2+10))
        self.etcd.write('%s/%s' % (version_dir, socket.gethostname()),
                        str(time.time()))

    def get_currently_running_version(self):
        try:
            with open('/etc/current_version', 'r') as fp:
                return fp.read().strip()
        except IOError, e:
            if e.errno == errno.ENOENT:
                return ''
            raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Utility for orchestrating updates')
    parser.add_argument('--host', type=str, default='127.0.0.1', help="etcd host")
    parser.add_argument('--port', type=int, default=4001, help="etcd port")
    subparsers = parser.add_subparsers(dest='subcmd')

    trigger_parser = subparsers.add_parser('trigger_update', help='Trigger an update')
    trigger_parser.add_argument('version', type=str, help='Version to deploy')

    current_version_parser = subparsers.add_parser('current_version', help='Get available version')

    pending_update = subparsers.add_parser('pending_update', help='Check for pending update')

    update_own_info_parser = subparsers.add_parser('update_own_info', help="Update host's own info")
    update_own_info_parser.add_argument('--interval', type=int, default=60, help="Update interval")
    update_own_info_parser.add_argument('--hostname', type=str, default=socket.gethostname(),
                                        help="This system's hostname")
    args = parser.parse_args()

    do = DeploymentOrchestrator(args.host, args.port)
    if args.subcmd == 'trigger_update':
        do.trigger_update(args.version)
    elif args.subcmd == 'current_version':
        print do.current_version()
    elif args.subcmd == 'update_own_info':
        do.update_own_info(args.hostname)
    elif args.subcmd == 'pending_update':
        pending_update = do.pending_update()
        if pending_update:
            print 'Yes, there is an update pending'
        else:
            print 'No updates pending'
        sys.exit(not pending_update)

