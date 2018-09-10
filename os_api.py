#
#
# This script will take OpenStack GET requests as inout testcases
# and run them for 'n' number of times.
#
# Command: python3 <filename.py>
#
#

import json
import logging
import requests
import sys
import timeit
import urllib3

from string import Template
from functools import wraps
from time import time


OPENSTACK_TOKEN = """
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


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger('os_api')
log_level = 20
logger.setLevel(log_level)
# set console logging. Change to file by changing to FileHandler
stream_handle = logging.StreamHandler()
# Set logging format
formatter = logging.Formatter('(%(name)s)[%(levelname)s]%(filename)s' +
                              '[%(lineno)d]:(%(funcName)s)\n:%(message)s')
stream_handle.setFormatter(formatter)
logger.addHandler(stream_handle)


def timing(f):
    @wraps(f)
    def wrap(*args, **kw):
        ts = time()
        result = f(*args, **kw)
        te = time()
        # print('func:%r args:[%r, %r] took: %2.4f sec' % \
        #  (f.__name__, args, kw, te-ts))
        return result, te-ts
    return wrap


class Base(object):
    """ Base class """
    def __init__(self):
        pass

    def load_json_data(self, data):
        try:
            return json.loads(data)
        except json.decoder.JSONDecodeError:
            logger.error(
                'Unable to convert following data to json: \n{}'.format(data)
            )
            sys.exit(1)


class Runner(Base):
    """Placeholder to run the tasks concurrently"""

    def __init__(self, concurrency=1, repeat=1):
        # These values can be overriden per testcase
        # Concurrency is not handled yet
        self.concurrency = concurrency
        self.repeat = repeat

    def execute(self, auth, testcases):
        """
        Execute the test cases
        """
        gc = GenericClient(auth)
        token = gc.get_openstack_token()

        for tc in testcases:
            logger.info(
                'Executing test case: {}'.format(tc)
            )
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
                headers.update(self.load_json_data(tc['headers']))

            if 'data' in tc:
                data.update(self.load_json_data(tc['data']))

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
                logger.info("Test Case: %-20s Status: %4s Time lapsed: "
                            "%2.4f" % (tc['name']+'-'+str(count + 1),
                                       tc_status, time_lapse)
                            )
                count += 1


class GenericClient(Base):
    """Generic client for REST operations"""

    def __init__(self, auth):
        self.auth = auth
        self.token = None
        self.tenant_id = None

    def get_openstack_token(self):
        """ Get openstack token """
        logger.info(
            'Get openstack token started'
            )
        data_template = Template(OPENSTACK_TOKEN)
        data = data_template.substitute(self.auth)
        headers = {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
        url = self.auth['auth_url'] + '/auth/tokens'
        response = requests.post(url, headers=headers, data=data, verify=False)
        token = response.headers.get('X-Subject-Token', None)
        response_dict = self.load_json_data(response.text)
        # Handle error in case token fails
        self.tenant_id = response_dict['token']['project']['id']
        logger.info(
            'Get openstack token completed successfully'
            )
        return token

    def get_endpoint(self, service='keystone', interface='public'):
        """ Get openstack endpoints """
        logger.info(
            'Get openstack endpoints started'
            )
        if self.token is None:
            self.token = self.get_openstack_token()
        url = self.auth['auth_url'] + '/services'
        params = {'type': service}
        headers = {
          'X-Auth-Token': self.token,
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers, params=params,
                                verify=False)
        service_dict = self.load_json_data(response.text)
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
        response = requests.get(url, headers=headers, params=params,
                                verify=False)
        endpoint_dict = self.load_json_data(response.text)
        endpoints = endpoint_dict.get('endpoints', None)

        if endpoints is None:
            return None

        endpoint = endpoints[0]['url']
        logger.info(
            'Get openstack endpoints completed successfully'
            )
        return endpoint

    @timing
    def GET(self, url, headers, data=None):
        """ Hit a get request on passed url """
        response = requests.get(url, headers=headers, data=data)
        # print(response.__dict__)
        return response


def main(password):
    """ Main method """
    auth = {
      'auth_url': 'https://openstack.local/v3',
      'username': 'admin',
      'password': password,
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
        'repeat': 30000,
      },
      {
       'name': 'glance_image_list',
       'service_type': 'image',
       'operation': 'GET',
       'url': '/v2/images',
       'concurrency': 1,
       'repeat': 100,
       },
    ]

    run = Runner()
    logger.info('Starting with test case execution')
    run.execute(auth, testcases)


if __name__ == '__main__':
    main(sys.argv[1])
