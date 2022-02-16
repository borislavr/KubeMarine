# Copyright 2021-2022 NetCracker Technology Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io

from kubemarine.core import utils
from kubemarine.core.group import NodeGroup


def verify_inventory(inventory, _):
    if inventory["plugins"]["nginx-ingress-controller"]["install"] is not True:
        return inventory

    nginx_plugin = inventory["plugins"]["nginx-ingress-controller"]

    # verify default certificate config
    if nginx_plugin["controller"]["ssl"].get("default-certificate"):
        default_cert = nginx_plugin["controller"]["ssl"]["default-certificate"]

        if default_cert.get("data") is None and default_cert.get("paths") is None:
            raise Exception("Default ingress certificate is specified, but no certificate and private key provided")
        if default_cert.get("data") and default_cert.get("paths"):
            raise Exception("Default ingress certificate and key should be provided either as raw data, "
                            "or either as paths, but not both at the same time")

        cert = default_cert.get("data", default_cert.get("paths"))
        if cert.get("cert") is None or cert.get("key") is None:
            raise Exception("Default ingress certificate should have both certificate and private key specified, "
                            "but one of them is missing")

    return inventory


def enrich_inventory(inventory, _):
    if inventory["plugins"]["nginx-ingress-controller"]["install"] is not True:
        return inventory

    if inventory["plugins"]["nginx-ingress-controller"].get('custom_headers'):
        if not inventory["plugins"]["nginx-ingress-controller"].get('config_map'):
            inventory["plugins"]["nginx-ingress-controller"]['config_map'] = {}
        if not inventory["plugins"]["nginx-ingress-controller"]['config_map'].get('proxy-set-headers'):
            inventory["plugins"]["nginx-ingress-controller"]['config_map']['proxy-set-headers'] = 'ingress-nginx/custom-headers'

    return inventory


def cert_renew_enrichment(inventory, cluster):
    # check that renewal is required for nginx
    if not cluster.procedure_inventory.get("nginx-ingress-controller"):
        return inventory

    nginx_plugin = inventory["plugins"]["nginx-ingress-controller"]

    # check that renewal is possible
    if nginx_plugin["install"] is not True:
        raise Exception("Certificates can not be renewed for nginx plugin since it is not installed")

    # update certificates in inventory, other check will be performed in "verify_inventory" function
    nginx_plugin["controller"]["ssl"]["default-certificate"] = cluster.procedure_inventory["nginx-ingress-controller"]

    return inventory


def finalize_inventory(cluster, inventory_to_finalize):
    # check that renewal is required for nginx
    if not cluster.procedure_inventory.get("nginx-ingress-controller"):
        return inventory_to_finalize

    if not inventory_to_finalize["plugins"].get("nginx-ingress-controller"):
        inventory_to_finalize["plugins"]["nginx-ingress-controller"] = {}

    if not inventory_to_finalize["plugins"]["nginx-ingress-controller"].get("controller"):
        inventory_to_finalize["plugins"]["nginx-ingress-controller"]["controller"] = {}

    if not inventory_to_finalize["plugins"]["nginx-ingress-controller"]["controller"].get("ssl"):
        inventory_to_finalize["plugins"]["nginx-ingress-controller"]["controller"]["ssl"] = {}

    nginx_plugin = inventory_to_finalize["plugins"]["nginx-ingress-controller"]
    nginx_plugin["controller"]["ssl"]["default-certificate"] = cluster.procedure_inventory["nginx-ingress-controller"]

    return inventory_to_finalize


def manage_custom_certificate(cluster):
    if not cluster.inventory["plugins"]["nginx-ingress-controller"]["controller"]["ssl"].get("default-certificate"):
        cluster.log.debug("No custom default ingress certificate specified, skipping...")
        return

    base_path = "/etc/kubernetes/custom-certs"
    certificate_path = base_path + "/cert"
    private_key_path = base_path + "/key"
    secret_name = "default-ingress-cert"
    secret_namespace = "kube-system"

    first_master = cluster.nodes["master"].get_first_member()
    default_cert = cluster.inventory["plugins"]["nginx-ingress-controller"]["controller"]["ssl"]["default-certificate"]

    # first, we need to load cert and key files to first master to known locations
    first_master.sudo(f"mkdir -p {base_path}")
    try:
        first_master.call(put_custom_certificate,
                          default_cert=default_cert,
                          crt_path=certificate_path,
                          key_path=private_key_path)

        # second, we need to validate cert and key using openssl
        first_master.call(verify_certificate_and_key, crt_path=certificate_path, key_path=private_key_path)

        # third, we need to create tls secret under well-known name
        # this certificate is already configured to be used by controller
        first_master.call(create_tls_secret,
                          crt_path=certificate_path,
                          key_path=private_key_path,
                          name=secret_name,
                          namespace=secret_namespace)
    finally:
        # fourth, we need to remove base path dir
        first_master.sudo(f"rm -rf {base_path}")


def put_custom_certificate(first_master: NodeGroup, default_cert, crt_path, key_path):
    if default_cert.get("data"):
        cert = io.StringIO(default_cert["data"]["cert"])
        key = io.StringIO(default_cert["data"]["key"])
    else:
        cert = utils.get_resource_absolute_path(default_cert["paths"]["cert"])
        key = utils.get_resource_absolute_path(default_cert["paths"]["key"])

    first_master.put(cert, crt_path, sudo=True, binary=False)
    first_master.put(key, key_path, sudo=True, binary=False)


def verify_certificate_and_key(first_master: NodeGroup, crt_path, key_path):
    crt_md5 = first_master.sudo(f"openssl x509 -noout -modulus -in {crt_path} | openssl md5").get_simple_out()
    key_md5 = first_master.sudo(f"openssl rsa -noout -modulus -in {key_path} | openssl md5").get_simple_out()
    if crt_md5 != key_md5:
        raise Exception("Custom default ingress certificate and key are not compatible!")


def create_tls_secret(first_master, crt_path, key_path, name, namespace):
    first_master.sudo(f"kubectl create secret tls {name} --key {key_path} --cert {crt_path} -n {namespace} "
                      f"--dry-run -o yaml | sudo kubectl apply -f -", timeout=300)