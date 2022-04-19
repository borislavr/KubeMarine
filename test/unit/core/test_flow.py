#!/usr/bin/env python3
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
import os
import random
import socket
import unittest
import ast
from typing import Optional
from unittest import mock

import invoke

from kubemarine.core import flow
from kubemarine import demo

test_msg = "test_function_return_result"


def test_func(cluster):
    try:
        # Need to fill values in cluster context in some tests to know that function was called
        current_value = cluster.context.get("test_info")
        if current_value is None:
            cluster.context["test_info"] = 1
        else:
            cluster.context["test_info"] = current_value + 1
    except Exception as ex:
        print(ex)
    return test_msg


tasks = {
    "deploy": {
        "loadbalancer": {
            "haproxy": test_func,
            "keepalived": test_func
        },
        "accounts": test_func
    },
    "overview": test_func
}


def replace_a_func_in_dict(test_res):
    test_res_str = str(test_res).replace(str(test_func), "'a'")
    return ast.literal_eval(test_res_str)


class FlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cluster: Optional[demo.FakeKubernetesCluster] = None
        self.light_fake_shell = demo.FakeShell()

    def test_filter_flow_1(self):
        test_tasks = ["deploy.loadbalancer.haproxy"]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, [])
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {'deploy': {'loadbalancer': {'haproxy': 'a'}}}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_filter_flow_2(self):
        test_tasks = ["deploy"]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, [])
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {'deploy': {'accounts': 'a', 'loadbalancer': {'haproxy': 'a', 'keepalived': 'a'}}}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_filter_flow_3(self):
        test_tasks = ["deploy.loadbalancer.haproxy", "overview"]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, [])
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {'deploy': {'loadbalancer': {'haproxy': 'a'}}, 'overview': 'a'}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_filter_flow_excluded(self):
        test_tasks = ["deploy"]
        excluded_tasks = ["deploy.loadbalancer"]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, excluded_tasks)
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {'deploy': {'accounts': 'a'}}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_filter_flow_excluded_whitespaces(self):
        test_tasks = ["deploy"]
        excluded_tasks = ["  deploy.loadbalancer  "]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, excluded_tasks)
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {'deploy': {'accounts': 'a'}}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_filter_flow_excluded_all_subtree(self):
        test_tasks = ["deploy"]
        excluded_tasks = ["deploy.loadbalancer", "deploy.accounts"]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, excluded_tasks)
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_incorrect_task_endswith_correct(self):
        test_tasks = ["my.deploy.loadbalancer.haproxy"]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, [])
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_incorrect_task_startswith_correct(self):
        test_tasks = ["deploy.loadbalancer.haproxy.xxx"]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, [])
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_union_of_incorrect_tasks_is_incorrect(self):
        for test_tasks in [["my.deploy"], ["loadbalancer"], ["my.deploy", "loadbalancer"]]:

            test_res, final_list = flow.filter_flow(tasks, test_tasks, [])
            test_res = replace_a_func_in_dict(test_res)

            expected_res = {}
            self.assertEqual(expected_res, test_res, f"Incorrect filtered flow for initial tasks {test_tasks}.")

    def test_incorrect_group_and_task_substring_of_correct(self):
        test_tasks = ["deploy.loadbalancer.h"]

        test_res, final_list = flow.filter_flow(tasks, test_tasks, [])
        test_res = replace_a_func_in_dict(test_res)

        expected_res = {}
        self.assertEqual(expected_res, test_res, "Incorrect filtered flow.")

    def test_schedule_cumulative_point(self):
        cluster = demo.new_cluster(demo.generate_inventory(**demo.FULLHA))
        flow.schedule_cumulative_point(cluster, test_func)
        points = cluster.context["scheduled_cumulative_points"]
        self.assertIn(test_func, points, "Test cumulative point was not added to cluster context")

    def test_add_task_to_proceeded_list(self):
        cluster = demo.new_cluster(demo.generate_inventory(**demo.FULLHA))
        task_path = "prepare"
        flow.add_task_to_proceeded_list(cluster, task_path)
        proceeded_tasks = cluster.context["proceeded_tasks"]
        self.assertIn(task_path, proceeded_tasks, "Test proceeded task was not added to cluster context")

    def test_proceed_cumulative_point(self):
        cluster = demo.new_cluster(demo.generate_inventory(**demo.FULLHA))
        method_full_name = test_func.__module__ + '.' + test_func.__qualname__
        cumulative_points = {
            method_full_name: ['prepare.system.modprobe']
        }
        flow.schedule_cumulative_point(cluster, test_func)
        res = flow.proceed_cumulative_point(cluster, cumulative_points, "prepare.system.modprobe")
        self.assertIn(test_msg, str(res.get(method_full_name)))

    def test_run_flow(self):
        cluster = demo.new_cluster(demo.generate_inventory(**demo.FULLHA))
        flow.run_flow(tasks, cluster, {})

        self.assertEqual(4, cluster.context["test_info"], "Here should be 4 calls of test_func for: \
         deploy.loadbalancer.haproxy, deploy.loadbalancer.keepalived, deploy.accounts, overview.")

    @mock.patch('kubemarine.core.flow.load_inventory', return_value=demo.new_cluster(demo.generate_inventory(**demo.FULLHA)))
    def test_run(self, patched_func):
        test_tasks = ["deploy.loadbalancer.haproxy"]
        args = flow.new_parser("Help text").parse_args(['-v', '--disable-dump'])
        flow.run(tasks, test_tasks, [], {}, flow.create_context(args))
        cluster = patched_func.return_value
        self.assertEqual(1, cluster.context["test_info"],
                         "It had to be one call of test_func for deploy.loadbalancer.haproxy action")

    @mock.patch('kubemarine.core.flow._provide_cluster')
    def test_detect_nodes_context(self, patched_func):
        inventory = demo.generate_inventory(**demo.FULLHA)
        hosts = [node["address"] for node in inventory["nodes"]]
        self._stub_detect_nodes_context(inventory, hosts, hosts)
        patched_func.side_effect = lambda *args, **kw: self._provide_cluster(*args, **kw)
        args = flow.new_parser("Help text").parse_args(['-v', '--disable-dump'])
        # not throws any exception during cluster initialization
        flow.run(tasks, [], [], inventory, flow.create_context(args))
        self.assertEqual(4, self.cluster.context["test_info"],
                         "Here should be all 4 calls of test_func")

        self.assertEqual("rhel", self.cluster.context["os"])
        for host, node_context in self.cluster.context["nodes"].items():
            self.assertEqual({'online': True, 'accessible': True, 'sudo': 'Root'}, node_context["access"])
            self.assertEqual({'name': 'centos', 'version': '7.6', 'family': 'rhel'}, node_context["os"])
            self.assertEqual('eth0', node_context["active_interface"])

    @mock.patch('kubemarine.core.flow._provide_cluster')
    def test_not_sudoer_does_not_interrupt_enrichment(self, patched_func):
        inventory = demo.generate_inventory(**demo.FULLHA)
        hosts = [node["address"] for node in inventory["nodes"]]
        self._stub_detect_nodes_context(inventory, hosts, [])
        patched_func.side_effect = lambda *args, **kw: self._provide_cluster(*args, **kw)
        args = flow.new_parser("Help text").parse_args(['-v', '--disable-dump'])
        flow.run(tasks, [], [], inventory, flow.create_context(args))
        self.assertEqual(4, self.cluster.context["test_info"],
                         "Here should be all 4 calls of test_func")

        self.assertEqual("rhel", self.cluster.context["os"])
        for host, node_context in self.cluster.context["nodes"].items():
            self.assertEqual({'online': True, 'accessible': True, 'sudo': 'No'}, node_context["access"])
            # continue to collect info
            self.assertEqual({'name': 'centos', 'version': '7.6', 'family': 'rhel'}, node_context["os"])
            self.assertEqual('eth0', node_context["active_interface"])

    @mock.patch('kubemarine.core.flow._provide_cluster')
    @mock.patch('kubemarine.core.utils.do_fail')
    def test_any_offline_node_interrupts(self, do_fail, _provide_cluster):
        def rethrow(*args, **kw):
            raise args[1]
        do_fail.side_effect = rethrow

        inventory = demo.generate_inventory(**demo.FULLHA)
        online_hosts = [node["address"] for node in inventory["nodes"]]
        offline = online_hosts.pop(random.randrange(len(online_hosts)))
        self._stub_detect_nodes_context(inventory, online_hosts, [])
        _provide_cluster.side_effect = lambda *args, **kw: self._provide_cluster(*args, **kw)
        args = flow.new_parser("Help text").parse_args(['-v', '--disable-dump'])

        exc = None
        try:
            flow.run(tasks, [], [], inventory, flow.create_context(args))
        except Exception as e:
            exc = e

        self.assertIsNotNone(exc, msg="Exception should be raised")
        self.assertTrue(f"['{offline}'] are not reachable." in str(exc))

    @mock.patch('kubemarine.core.flow._provide_cluster')
    def test_removed_node_can_be_offline(self, _provide_cluster):
        inventory = demo.generate_inventory(**demo.FULLHA)
        online_hosts = [node["address"] for node in inventory["nodes"]]

        i = random.randrange(len(online_hosts))
        online_hosts.pop(i)
        procedure_inventory = {"nodes": [{"name": inventory["nodes"][i]["name"]}]}

        self._stub_detect_nodes_context(inventory, online_hosts, [])
        _provide_cluster.side_effect = lambda *args, **kw: self._provide_cluster(*args, **kw)

        args = flow.new_parser("Help text").parse_args(['-v', '--disable-dump'])

        # no exception should occur
        flow.run(tasks, [], [], inventory, flow.create_context(args, procedure='remove_node'),
                 procedure_inventory_filepath=procedure_inventory)

    def _provide_cluster(self, *args, **kw) -> demo.FakeKubernetesCluster:
        is_light = "shallow_copy_env_from" in kw
        if is_light:
            kw["fake_shell"] = self.light_fake_shell
            cluster = demo.FakeKubernetesCluster(*args, **kw)
            cluster.globals["nodes"]["remove"]["check_active_timeout"] = 0
        else:
            cluster = demo.FakeKubernetesCluster(*args, **kw)
            self.cluster = cluster

        return cluster

    def _stub_detect_nodes_context(self, inventory: dict, online_nodes: list, sudoer_nodes: list):
        hosts = [node["address"] for node in inventory["nodes"]]

        self._stub_result(hosts, sudoer_nodes, online_nodes, "sudo", ['last reboot'], 'some reboot info')
        self._stub_result(hosts, sudoer_nodes, online_nodes, "sudo", ['whoami'], 'root')

        for node in inventory["nodes"]:
            self._stub_result([node["address"]], sudoer_nodes, online_nodes, "run",
                              ["/usr/sbin/ip -o a | grep %s | awk '{print $2}'" % node["internal_address"]], 'eth0')

        with open(os.path.dirname(__file__) + "/../../resources/fetch_os_versions_example.txt") as f:
            fetch_os_versions = f.read()

        self._stub_result(hosts, sudoer_nodes, online_nodes, "run",
                          ["cat /etc/*elease; "
                           "cat /etc/debian_version 2> /dev/null | sed 's/\\(.\\+\\)/DEBIAN_VERSION=\"\\1\"/' || true"],
                          fetch_os_versions)

    def _stub_result(self, hosts, sudoer_hosts, online_hosts, do_type, command, stdout):
        results = {}
        for host in hosts:
            if host not in online_hosts:
                results[host] = socket.timeout()
            elif host not in sudoer_hosts and do_type == 'sudo':
                results[host] = invoke.AuthFailure(None, None)
            else:
                results[host] = demo.create_result(stdout=stdout)
        self.light_fake_shell.add(results, do_type, command)


if __name__ == '__main__':
    unittest.main()
