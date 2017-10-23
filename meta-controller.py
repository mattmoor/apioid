"""A meta-controller for projecting API resources onto the cluster."""

import json
from kubernetes import client, config, watch
import logging
import os

DOMAIN = "mattmoor.io"
VERSION = "v1"
PLURAL = "apis"

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

    def name(self):
        return self.plural() + "." + self._api.hostname()

    def group(self):
        return self._api.hostname()

    def version(self):
        return self._api.version()

    def controller_namespace(self):
        return self._api.annotations().get(
            self.name() + "/controller-namespace")

    def controller_deployment(self):
        return self._api.annotations().get(
            self.name() + "/controller-deployment")

    def annotate(self, obj, namespace):
        annotations = obj["metadata"].get("annotations", {})
        annotations[self.name() + "/controller-namespace"] = namespace
        annotations[self.name() + "/controller-deployment"] = self.group()
        obj["metadata"]["annotations"] = annotations

    def definition(self, owner_refs):
        """The CRD for this API resource."""
        return {
            "apiVersion": "apiextensions.k8s.io/v1beta1",
            "kind": "CustomResourceDefinition",
            "metadata": {
                "name": self.name(),
                "ownerReferences": owner_refs,
            },
            "spec": {
                "group": self.group(),
                "version": self.version(),
                "scope": "Cluster",
                "names": {
                    "plural": self.plural(),
                    "singular": self.singular(),
                    "kind": self.kind(),
                },
            },
        }

    def controller(self, image, owner_refs):
        """The controller for this resource's CRD."""
        return {
            "apiVersion": "apps/v1beta1",
            "kind": "Deployment",
            "metadata": {
                "name": self.group(),
                "ownerReferences": owner_refs,
            },
            "spec": {
                "replicas": 1,
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "api-controller",
                            "api": self._api.api_name(),
                            "version": self.version(),
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
                                "value": self.version(),
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
        self._annotations = self._metadata.get("annotations") or {}
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

    api_ext = client.ApiextensionsV1beta1Api()
    apps = client.AppsV1beta1Api()
    crds = client.CustomObjectsApi()

    # Create API controllers within our namespace, which we
    # get through the downward API.
    namespace = os.environ["MY_NAMESPACE"]
    api_controller_image = os.environ["API_IMAGE"]

    owner = apps.read_namespaced_deployment(os.environ["OWNER_NAME"], namespace)

    # Define our OwnerReference that we will add to the metadata of
    # objects we create so that they are garbage collected when this
    # controller is deleted.
    controller_ref = {
        "apiVersion": owner.api_version,
        "blockOwnerDeletion": True,
        "controller": True,
        "kind": owner.kind,
        "name": os.environ["OWNER_NAME"],
        "uid": owner.metadata.uid,
    }

    def owner_ref(obj, controller=False):
        return {
            "apiVersion": obj["apiVersion"],
            "blockOwnerDeletion": True,
            "controller": controller,
            "kind": obj["kind"],
            "name": obj["metadata"]["name"],
            "uid": obj["metadata"]["uid"],
        }

    def delete_meta(api, resource):
        logging.error("Deleting deployment: %s", resource.group())
        apps.delete_namespaced_deployment(
            resource.group(), namespace, body=client.V1DeleteOptions(
                propagation_policy='Foreground', grace_period_seconds=5))

        logging.error("Deleting CRD: %s", resource.name())
        api_ext.delete_custom_resource_definition(
            resource.name(), body=client.V1DeleteOptions(
                propagation_policy='Foreground', grace_period_seconds=5))

    def update_meta(api, resource):
        # TODO(mattmoor): Establish a better way to diff the actual/desired
        # object states and reconcile them.  For now, just check the image.
        controller = apps.read_namespaced_deployment(resource.group(), namespace)
        if controller.spec.template.spec.containers[0].image == api_controller_image:
            logging.warn("Image for %s controller is up-to-date!", resource.name())
            return
        logging.warn("Updating image for %s controller", resource.name())
        controller.spec.template.spec.containers[0].image = api_controller_image
        apps.replace_namespaced_deployment(resource.group(), namespace, controller)

    def create_meta(api, resource):
        api_ext.create_custom_resource_definition(
            resource.definition([controller_ref]))
        apps.create_namespaced_deployment(
            namespace, resource.controller(api_controller_image, [controller_ref]))

    def process_meta(t, api, obj):
        if t == "DELETED":
            logging.error("Delete event: %s", json.dumps(obj, indent=1))
            for resource in api.resources():
                delete_meta(api, resource)
        elif t == "MODIFIED" or t == "ADDED":
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

                # TODO(mattmoor): See if we can make the api-controller owned
                # by the CRD that spawned it.  Right now, this seems ineffective.
                # crd_ref = owner_ref(obj)
                # This has not been processed yet.
                create_meta(api, resource)

                # Annotate our object with our resource (and namespace)
                resource.annotate(obj, namespace)
                obj = crds.replace_namespaced_custom_object(DOMAIN, VERSION, namespace, PLURAL,
                                                      obj["metadata"]["name"], obj)
        else:
            logging.error("Unrecognized type: %s", t)

    resource_version = ""
    while True:
        stream = watch.Watch().stream(crds.list_cluster_custom_object,
                                      DOMAIN, VERSION, PLURAL,
                                      resource_version=resource_version)
        for event in stream:
            try:
                t = event["type"]
                obj = event["object"]
                api = Api(obj)
                process_meta(t, api, obj)

                # Configure where to resume streaming.
                metadata = obj.get("metadata")
                if metadata:
                    resource_version = metadata["resourceVersion"]
            except:
                logging.exception("Error handling event")

if __name__ == "__main__":
    main()
