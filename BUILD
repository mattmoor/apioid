package(default_visibility = ["//visibility:public"])

load("@apioid_pip//:requirements.bzl", "requirement")
load("@io_bazel_rules_docker//python:image.bzl", "py_image")

py_image(
    name = "meta-controller",
    srcs = ["meta-controller.py"],
    main = "meta-controller.py",
    deps = [requirement("kubernetes")],
)

py_image(
    name = "api-controller",
    srcs = ["api-controller.py"],
    main = "api-controller.py",
    deps = [
        requirement("kubernetes"),
        requirement("google-api-python-client"),
    ],
)

load("@k8s_crd//:defaults.bzl", "k8s_crd")

k8s_crd(
    name = "apioid-crd",
    template = ":apioid.yaml",
)

load("@k8s_deployment//:defaults.bzl", "k8s_deployment")

k8s_deployment(
    name = "meta-deployment",
    images = {
        "gcr.io/convoy-adapter/meta-controller:staging": ":meta-controller",
        "gcr.io/convoy-adapter/api-controller:staging": ":api-controller",
    },
    template = ":meta-controller.yaml",
)

load("@io_bazel_rules_k8s//k8s:objects.bzl", "k8s_objects")

k8s_objects(
    name = "everything",
    objects = [
        ":apioid-crd",
        ":meta-deployment",
    ],
)

load("@k8s_object//:defaults.bzl", "k8s_object")

k8s_object(
    name = "example-api-crd",
    template = ":example-api.yaml",
)
