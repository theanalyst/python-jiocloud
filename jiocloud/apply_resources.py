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

def get_nova_client():
    return novaclient.Client("1.1", **get_nova_creds_from_env())

def get_resource_file_path(path, env):
    return os.path.join(path, env + ".yaml")

def read_resources(path):
    fp = file(path)
    return yaml.load(fp)['resources']

def get_existing_servers(nova_client, project_tag=None, attr_name='name'):
    """
    This method accepts an option project tag
    """
    # NOTE we should check for servers only in a certain state
    servers = nova_client.servers.list()
    if project_tag:
        servers = [elem for elem in servers if elem.name.endswith('_' + project_tag) ]
    return [getattr(s, attr_name) for s in servers]


def generate_desired_servers(resources, project_tag=None):
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

def servers_to_create(nova_client, resource_file, project_tag=None):
    resources = read_resources(resource_file)
    existing_servers = get_existing_servers(nova_client, project_tag=project_tag)
    desired_servers = generate_desired_servers(resources, project_tag)
    return [elem for elem in desired_servers if elem['name'] not in existing_servers ]

def create_servers(nova_client, servers, userdata):
    userdata_file = file(userdata)
    for s in servers:
        create_server(nova_client, userdata_file, **s)

images={}
flavors={}
def create_server(nova_client, userdata_file, name, flavor, image, networks, **keys):
    print "Creating server %s"%(name)
    images[image] = images.get(image, nova_client.images.find(name=image))
    flavors[flavor] = flavors.get(flavor, nova_client.flavors.find(name=flavor))
    net_list=[{'net-id': n} for n in networks]
    instance = nova_client.servers.create(
      name=name,
      image=images[image],
      flavor=flavors[flavor],
      nics=net_list,
      userdata=userdata_file,
    )

    # Poll at 5 second intervals, until the status is no longer 'BUILD'
    status = instance.status
    while status == 'BUILD':
        time.sleep(5)
        # Retrieve the instance again so the status field updates
        instance = nova_client.servers.get(instance.id)
        status = instance.status
        print "status: %s" % status

def delete_servers(nova_client, project_tag):
    servers = get_existing_servers(nova_client, project_tag=project_tag, attr_name='id')
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

    delete_parser = subparsers.add_parser('delete', help='Delete a project')
    delete_parser.add_argument('project_tag', help='Id of project to delete')

    args = argparser.parse_args()
    nova_client = get_nova_client()
    if args.action == 'apply':
        servers = servers_to_create(get_nova_client(),
                                    args.resource_file_path,
                                    project_tag=args.project_tag)
        create_servers(nova_client, servers, args.userdata)
    elif args.action == 'delete':
        if not args.project_tag:
            argparser.error("Must set project tag when action is delete")
        delete_servers(nova_client, project_tag=args.project_tag)
