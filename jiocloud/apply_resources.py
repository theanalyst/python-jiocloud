#!/usr/bin/env python
import argparse
import os
import time
import yaml
from novaclient import client as novaclient

"""
Parses a specification of nodes to install and makes it so
"""

def get_nova_creds_from_env():
    d = {}
    d['username'] = os.environ['OS_USERNAME']
    d['api_key'] = os.environ['OS_PASSWORD']
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['project_id'] = os.environ['OS_TENANT_NAME']
    d['region_name'] = os.environ.get('OS_REGION_NAME')
    return d

class ApplyResources(object):
    def __init__(self):
        self.nova_client = None
        self._images = {}
        self._flavors = {}

    def read_resources(self, path):
        fp = file(path)
        return yaml.load(fp)['resources']

    def get_nova_client(self):
        if not self.nova_client:
            self.nova_client = novaclient.Client("1.1", **get_nova_creds_from_env())
        return self.nova_client

    def get_existing_servers(self, project_tag=None, attr_name='name'):
        """
        This method accepts an option project tag
        """
        # NOTE we should check for servers only in a certain state
        nova_client = self.get_nova_client()
        servers = nova_client.servers.list()
        if project_tag:
            servers = [elem for elem in servers if elem.name.endswith('_' + project_tag) ]
        return [getattr(s, attr_name) for s in servers]


    def generate_desired_servers(self, resources, project_tag=None):
        """
        Convert from a hash of servers resources to the
        hash of all server names that should be created
        """
        suffix = (project_tag and ('_' + project_tag)) or ''

        servers_to_create = []
        for k,v in resources.iteritems():
            for i in range(int(v['number'])):
                # NOTE ideally, this would not contain the caridinatlity
                # b/c it is not needed by this hash
                server = {'name': "%s%d%s"%(k, i+1, suffix)}
                servers_to_create.append(dict(server.items() + v.items()))
        return servers_to_create

    def servers_to_create(self, resource_file, project_tag=None):
        resources = self.read_resources(resource_file)
        existing_servers = self.get_existing_servers(project_tag=project_tag)
        desired_servers = self.generate_desired_servers(resources, project_tag)
        return [elem for elem in desired_servers if elem['name'] not in existing_servers ]

    def create_servers(self, servers, userdata, key_name=None):
        ids = set()
        for s in servers:
            userdata_file = file(userdata)
            ids.add(self.create_server(userdata_file, key_name, **s))

        nova_client = self.get_nova_client()

        done = set()
        while ids:
            time.sleep(5)
            for id in ids:
                instance = nova_client.servers.get(id)
                print "%s: %s" % (id, instance.status)
                if instance.status != 'BUILD':
                    done.add(id)
            ids = ids.difference(done)

    def create_server(self,
                      userdata_file,
                      key_name,
                      name,
                      flavor,
                      image,
                      config_drive=False,
                      networks=None,
                      **keys):
        print "Creating server %s"%(name)
        nova_client = self.get_nova_client()
        self._images[image] = self._images.get(image, nova_client.images.get(image))
        self._flavors[flavor] = self._flavors.get(flavor, nova_client.flavors.get(flavor))
        net_list = networks and ([{'net-id': n} for n in networks])
        instance = nova_client.servers.create(
          name=name,
          image=self._images[image],
          flavor=self._flavors[flavor],
          nics=net_list,
          userdata=userdata_file,
          key_name=key_name,
          config_drive=config_drive,
        )

        return instance.id

    def delete_servers(self, project_tag):
        nova_client = self.get_nova_client()
        servers = self.get_existing_servers(project_tag=project_tag, attr_name='id')
        for uuid in servers:
            print "Deleting uuid: %s"%(uuid)
            nova_client.servers.delete(uuid)

if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    subparsers = argparser.add_subparsers(dest='action', help='Action to perform')

    apply_parser  = subparsers.add_parser('apply', help='Apply a resource file')
    apply_parser.add_argument('resource_file_path', help='Path to resource file')
    apply_parser.add_argument('userdata', help='Path of userdata to apply to all nodes')
    apply_parser.add_argument('--project_tag', help='Project tag')
    apply_parser.add_argument('--key_name', help='Name of key pair')

    delete_parser = subparsers.add_parser('delete', help='Delete a project')
    delete_parser.add_argument('project_tag', help='Id of project to delete')

    list_parser  = subparsers.add_parser('list', help='List servers described in resource file')
    list_parser.add_argument('resource_file_path', help='Path to resource file')
    list_parser.add_argument('--project_tag', help='Project tag')

    args = argparser.parse_args()
    if args.action == 'apply':
        apply_resources = ApplyResources()
        servers = apply_resources.servers_to_create(args.resource_file_path,
                                                     project_tag=args.project_tag)
        apply_resources.create_servers(servers, args.userdata, key_name=args.key_name)
    elif args.action == 'delete':
        if not args.project_tag:
            argparser.error("Must set project tag when action is delete")
        ApplyResources().delete_servers(project_tag=args.project_tag)
    elif args.action == 'list':
        apply_resources = ApplyResources()
        resources = apply_resources.read_resources(args.resource_file_path)
        desired_servers = apply_resources.generate_desired_servers(resources, args.project_tag)
        print '\n'.join([s['name'] for s in desired_servers])
