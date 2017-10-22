"""A meta-controller for projecting API resources onto the cluster."""

import json
from kubernetes import client, config, watch
import logging
import os

DOMAIN = "mattmoor.io"
VERSION = "v1"
PLURAL = "apis"

HOST = PLURAL + "." + DOMAIN
NAMESPACE_ANNOTATION = HOST + "/controller-namespace"
DEPLOYMENT_ANNOTATION = HOST + "/controller-deployment"

# TODO(mattmoor): Move these into a library, and reuse them
# in the api controller.
class Resource(object):
    def __init__(self, api, resource):
        self._api = api
        self._resource = resource

    def kind(self):
        return self._resource

    def singular(self):
        return self._resource.lower()

    def plural(self):
        return self.singular() + "s"

    def group(self):
        return self.plural() + "." + self._api.hostname()

    def controller_namespace(self):
        return self._api.annotations().get(
            self.group() + "/controller-namespace")

    def controller_deployment(self):
        return self._api.annotations().get(
            self.group() + "/controller-deployment")

    def definition(self):
        """The CRD for this API resource."""
        return {
            "apiVersion": "apiextensions.k8s.io/v1beta1",
            "kind": "CustomResourceDefinition",
            "metadata": {
                "name": self.group(),
            },
            "spec": {
                "group": self._api.hostname(),
                "version": self._api.version(),
                "scope": "Cluster",
                "names": {
                    "plural": self.plural(),
                    "singular": self.singular(),
                    "kind": self.kind(),
                },
            },
        }

    def controller(self, image):
        """The controller for this resource's CRD."""
        return {
            "apiVersion": "apps/v1beta1",
            "kind": "Deployment",
            "metadata": {
                "name": self.group(),
            },
            "spec": {
                "replicas": 1,
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "api-controller",
                            "api": self._api.api_name(),
                            "version": self._api.version(),
                            "resource": self.singular(),
                        },
                    },
                    "spec": {
                        "containers": [{
                            "name": "api-controller",
                            "image": image,
                            "env": [{
                                "name": "API_NAME",
                                "value": self._api.api_name(),
                            }, {
                                "name": "API_VERSION",
                                "value": self._api.version(),
                            }, {
                                "name": "API_RESOURCE",
                                "value": self.kind(),
                            }],
                        }],
                    },
                },
            },
        }

# TODO(mattmoor): Create a more structured representation for reasoning
# about the API CRD than a dict.
class Api(object):
    def __init__(self, obj):
        self._obj = obj
        self._metadata = obj["metadata"]
        self._annotations = obj.get("annotations") or {}
        spec = obj["spec"]
        self._api = spec["name"]
        self._version = spec["version"]
        self._resources = spec["resources"]

    def name(self):
        return self._metadata["name"]

    def api_name(self):
        return self._api

    def version(self):
        return self._version

    def annotations(self):
        return self._annotations

    # TODO(mattmoor): Expose a method for adding annotations?

    def hostname(self):
        return self.api_name() + ".googleapis.com"

    def resources(self):
        for r in self._resources:
            yield Resource(self, r)

    def __str__(self):
        return json.dumps(self._obj, indent=1)

def main():
    config.load_incluster_config()

    crds = client.CustomObjectsApi()

    # Create API controllers within our namespace, which we
    # get through the downward API.
    namespace = os.environ["MY_NAMESPACE"]
    api_controller_image = os.environ["API_IMAGE"]

    def update_meta(api, resource):
        # TODO(mattmoor): Fetch the named deployment, make sure the api-controller
        # image name is accurate, and then replace the object if anything changed.
        logging.error("TODO: update the CRD/Controller for this API/Resource: %s", api)

    def create_meta(api, resource):
        # TODO(mattmoor): Create the deployment object given by
        # deployment(obj) in our own namespace.
        definition = resource.definition()
        controller = resource.controller(api_controller_image)
        logging.error("TODO: create the CRD %s", json.dumps(definition, indent=1))
        logging.error("TODO: create the Controller %s", json.dumps(controller, indent=1))

    def process_meta(api, obj):
        for resource in api.resources():
            controller_namespace = resource.controller_namespace()
            if controller_namespace:
                if controller_namespace != namespace:
                    # This is being controlled by a controller in another namespace.
                    logging.warn("Found resourced being managed by another "
                                 "meta-controller, this is bound to create "
                                 "contention.  Skipping %s", api.name())
                    return
                else:
                    # This is being controlled by us, make sure it is up to date.
                    update_meta(api, resource)
                    continue

            # This has not been processed yet.
            create_meta(api, resource)
            # TODO(mattmoor): Reflect the things we create via annotations.


    resource_version = ''
    while True:
        stream = watch.Watch().stream(crds.list_cluster_custom_object,
                                      DOMAIN, VERSION, PLURAL,
                                      resource_version=resource_version)
        for event in stream:
            try:
                obj = event["object"]
                api = Api(obj)
                process_meta(api, obj)

                # Configure where to resume streaming.
                metadata = obj.get("metadata")
                if metadata:
                    resource_version = metadata["resourceVersion"]
            except:
                logging.exception("Error handling event")

if __name__ == "__main__":
    main()
