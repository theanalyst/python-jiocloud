#!/usr/bin/env python
import argparse
import keystoneclient.v2_0.client as ksclient
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

def read_resources(path):
    fp = file(path)
    return yaml.load(fp)['resources']

class ApplyResources(object):
    def __init__(self):
        self.nova_client = None

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
        resources = read_resources(resource_file)
        existing_servers = get_existing_servers(project_tag=project_tag)
        desired_servers = generate_desired_servers(resources, project_tag)
        return [elem for elem in desired_servers if elem['name'] not in existing_servers ]

    def create_servers(self, servers, userdata):
        for s in servers:
            userdata_file = file(userdata)
            create_server(userdata_file, key_name, **s)

    images={}
    flavors={}
    def create_server(self,
                      userdata_file,
                      key_name,
                      name,
                      flavor,
                      image,
                      networks,
                      **keys):
        print "Creating server %s"%(name)
        nova_client = self.get_nova_client()
        images[image] = images.get(image, nova_client.images.get(image))
        flavors[flavor] = flavors.get(flavor, nova_client.flavors.get(flavor))
        net_list=[{'net-id': n} for n in networks]
        instance = nova_client.servers.create(
          name=name,
          image=images[image],
          flavor=flavors[flavor],
          nics=net_list,
          userdata=userdata_file,
          key_name=key_name,
        )

        # Poll at 5 second intervals, until the status is no longer 'BUILD'
        status = instance.status
        while status == 'BUILD':
            time.sleep(5)
            # Retrieve the instance again so the status field updates
            instance = nova_client.servers.get(instance.id)
            status = instance.status
            print "status: %s" % status

    def delete_servers(self, project_tag):
        nova_client = self.get_nova_client()
        servers = get_existing_servers(project_tag=project_tag, attr_name='id')
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
        servers = ApplyResources().servers_to_create(args.resource_file_path,
                                                     project_tag=args.project_tag)
        create_servers(servers, args.userdata, key_name=args.key_name)
    elif args.action == 'delete':
        if not args.project_tag:
            argparser.error("Must set project tag when action is delete")
        ApplyResources().delete_servers(project_tag=args.project_tag)
    elif args.action == 'list':
        resources = read_resources(args.resource_file_path)
        desired_servers = ApplyResources().generate_desired_servers(resources, args.project_tag)
        print '\n'.join([s['name'] for s in desired_servers])
