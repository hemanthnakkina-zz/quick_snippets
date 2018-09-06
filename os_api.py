/*

This script will take OpenStack GET requests as inout testcases 
and run them for 'n' number of times.

Command: python3 <filename.py>

*/

import json
import requests
import timeit

from string import Template
from functools import wraps
from time import time


OPENSTACK_TOKEN="""
{
    "auth": {
        "identity": {
            "methods": [
                "password"
            ],
            "password": {
                "user": {
                    "name": "$username",
                    "domain": {
                        "name": "$user_domain_name"
                    },
                    "password": "$password"
                }
            }
        },
        "scope": {
            "project": {
                "name": "$project_name",
                "domain": { "id": "$project_domain_name" }
            }
        }
    }
}
"""


def timing(f):
    @wraps(f)
    def wrap(*args, **kw):
        ts = time()
        result = f(*args, **kw)
        te = time()
        #print('func:%r args:[%r, %r] took: %2.4f sec' % \
        #  (f.__name__, args, kw, te-ts))
        return result, te-ts
    return wrap


class Runner(object):
    """Placeholder to run the tasks concurrently"""

    def __init__(self, concurrency=1, repeat=1):
        # These values can be overrided per testcase
        # Concurrency is not handled yet
        self.concurrency = concurrency
        self.repeat = repeat

    def execute(self, auth, testcases):
        gc = GenericClient(auth)
        token = gc.get_openstack_token()

        for tc in testcases:
            headers = {
                'X-Auth-Token': token,
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            data = None

            url = gc.get_endpoint(service=tc['service_type'])
            url += tc['url']
            url = url.replace('%(tenant_id)s', gc.tenant_id)

            if 'headers' in tc:
                headers.update(json.loads(tc['headers']))

            if 'data' in tc:
                data.update(json.loads(tc['data']))

            repeat = tc.get('repeat', self.repeat)

            op = getattr(gc, tc['operation'])
            count = 0
            while True:
                # Negative value will make this run infinte
                # number of times, as required.
                if count == repeat:
                    break
                (result, time_lapse) = op(url, headers, data=data)
                tc_status = 'PASS' if result.status_code < 400 else 'FAIL'
                print("Test Case: %-20s Status: %4s Time lapsed: %2.4f" % \
                    (tc['name']+'-'+str(count + 1), tc_status, time_lapse))
                count += 1


class GenericClient(object):
    """Generic client for REST operations"""

    def __init__(self, auth):
        self.auth = auth
        self.token = None
        self.tenant_id = None

    def get_openstack_token(self):
        data_template = Template(OPENSTACK_TOKEN)
        data = data_template.substitute(self.auth)
        headers = {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
        url = self.auth['auth_url'] + '/auth/tokens'
        response = requests.post(url, headers=headers, data=data, verify=False)
        token = response.headers.get('X-Subject-Token', None)
        response_dict = json.loads(response.text)
        # Handle error in case token fails
        self.tenant_id = response_dict['token']['project']['id']
        return token

    def get_endpoint(self, service='keystone', interface='public'):
        if self.token is None:
            self.token = self.get_openstack_token()
        url = self.auth['auth_url'] + '/services'
        params = { 'type': service }
        headers = {
          'X-Auth-Token': self.token,
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers, params=params, verify=False)
        service_dict = json.loads(response.text)
        services = service_dict.get('services', None)

        if services is None:
            return None

        service_id = services[0]['id']
        url = self.auth['auth_url'] + '/endpoints'
        params = {
            'service_id': service_id,
            'interface': interface
        }
        headers = {
          'X-Auth-Token': self.token,
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers, params=params, verify=False)
        endpoint_dict = json.loads(response.text)
        endpoints = endpoint_dict.get('endpoints', None)

        if endpoints is None:
            return None

        endpoint = endpoints[0]['url']
        return endpoint

    @timing
    def GET(self, url, headers, data=None):
        response = requests.get(url, headers=headers, data=data)
        #print(response.__dict__)
        return response


if __name__ == '__main__':
    auth = {
      'auth_url': 'https://openstack.local/v3',
      'username': 'admin',
      'password': 'admin',
      'project_name': 'admin',
      'project_domain_name': 'default',
      'user_domain_name': 'default'
    }

    testcases = [
      {
        'name': 'nova_list',
        'service_type': 'compute',
        'operation': 'GET',
        'url': '/servers',
        'concurrency': 1,
        'repeat': 30000
      },
#      {
#        'name': 'glance_image_list',
#        'service_type': 'image',
#        'operation': 'GET',
#        'url': '/v2/images',
#        'concurrency': 1,
#        'repeat': 1
#      }
    ]

    run = Runner()
    run.execute(auth, testcases)

