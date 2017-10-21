"""A meta-controller for projecting API resources onto the cluster."""

import json
from kubernetes import client, config, watch
import logging
import os

DOMAIN = "mattmoor.io"
VERSION = "v1"
PLURAL = "apis"

def main():
    config.load_incluster_config()

    crds = client.CustomObjectsApi()

    api_controller = os.environ["API_IMAGE"]

    def define_meta(obj):
        # TODO(mattmoor): If the object has a deployment with the wrong
        # api-controller image then trigger an update.  This is a sign we
        # are starting up.
        logging.error("TODO: CRUD a deployment for this API: %s", json.dumps(obj, indent=1))

    stream = watch.Watch().stream(crds.list_cluster_custom_object,
                                  DOMAIN, VERSION, PLURAL)
    for event in stream:
        try:
            define_meta(event["object"])
        except:
            logging.exception("Error handling event")

if __name__ == "__main__":
    main()
