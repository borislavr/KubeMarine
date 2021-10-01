#!/usr/bin/env python3

from collections import OrderedDict

from kubetool import plugins, k8s_certs
from kubetool.core import flow


def renew_nginx_ingress_certs_task(cluster):
    # check that renewal is required for nginx
    if not cluster.procedure_inventory.get("nginx-ingress-controller"):
        cluster.log.debug("Skipped: nginx ingress controller certs renewal is not required")
        return

    cluster.log.debug("Starting certificate renewal for nginx ingress controller, plugin will be reinstalled")
    plugin = cluster.inventory["plugins"]["nginx-ingress-controller"]
    plugins.install_plugin(cluster, "nginx-ingress-controller", plugin["installation"]['procedures'])


def k8s_certs_renew_task(cluster):
    if not cluster.procedure_inventory.get("kubernetes"):
        cluster.log.debug("Skipped: kubernetes certs renewal is not required")
        return

    cluster.log.debug("Starting certificate renewal for kubernetes")
    cluster.nodes['master'].call(k8s_certs.renew_apply)


def k8s_certs_overview_task(cluster):
    cluster.nodes['master'].call(k8s_certs.k8s_certs_overview)


tasks = OrderedDict({
    "kubernetes": k8s_certs_renew_task,
    "nginx_ingress_controller": renew_nginx_ingress_certs_task,
    "certs_overview": k8s_certs_overview_task
})


def main(cli_arguments=None):

    cli_help = '''
    Script for certificates renewal on existing Kubernetes cluster.

    How to use:

    '''

    parser = flow.new_parser(cli_help)
    parser.add_argument('--tasks',
                        default='',
                        help='define comma-separated tasks to be executed')

    parser.add_argument('--exclude',
                        default='',
                        help='exclude comma-separated tasks from execution')

    parser.add_argument('procedure_config', metavar='procedure_config', type=str,
                        help='config file for add_node procedure')

    if cli_arguments is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(cli_arguments)

    defined_tasks = []
    defined_excludes = []

    if args.tasks != '':
        defined_tasks = args.tasks.split(",")

    if args.exclude != '':
        defined_excludes = args.exclude.split(",")

    context = flow.create_context(args, procedure='cert_renew')
    context['inventory_regenerate_required'] = True

    flow.run(
        tasks,
        defined_tasks,
        defined_excludes,
        args.config,
        context,
        procedure_inventory_filepath=args.procedure_config,
    )


if __name__ == '__main__':
    main()