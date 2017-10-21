"""An API controller."""

from oauth2client.contrib.gce import AppAssertionCredentials
from apiclient.discovery import build as discovery_build

import hashlib
import json
from kubernetes import client, config, watch
import logging
import os
import time

def main():
    config.load_incluster_config()

    crds = client.CustomObjectsApi()

    name = os.environ['API_NAME']
    domain = '%s.googleapis.com' % name
    version = os.environ['API_VERSION']
    resource = os.environ['API_RESOURCE']

    # TODO(mattmoor): Share a library with the meta controller
    plural = resource.lower() + 's'

    creds = AppAssertionCredentials()
    api = discovery_build(name, version, credentials=creds)

    def call(obj):
        spec = obj["spec"]
        logging.error("TODO call %s/%s %s on %s", name, version, resource,
                      json.dumps(obj, indent=1))

    stream = watch.Watch().stream(
        crds.list_cluster_custom_object, domain, version, plural)
    for event in stream:
        # TODO(mattmoor): Execute in a threadpool.
        try:
            call(event["object"])
        except:
            logging.exception("Error handling event")

if __name__ == "__main__":
    main()
