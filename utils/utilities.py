import os
import subprocess
from loguru import logger
import sys
from jinja2 import Environment, FileSystemLoader
import os
from enum import Enum
from .settings import SKIP_RESOURCE
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.rdbms.mysql import MySQLManagementClient
from azure.mgmt.rdbms.mysql_flexibleservers import MySQLManagementClient as MySQLFlexibleManagementClient
from azure.mgmt.rdbms.postgresql import PostgreSQLManagementClient
from azure.mgmt.rdbms.postgresql_flexibleservers import PostgreSQLManagementClient as PostgreSQLFlexibleManagementClient
from azure.mgmt.network import NetworkManagementClient

class SkipTag(Enum):
    """
    SKip Resources Containg this tag
    """

    TF_IMPORTED = "true"


class Utilities:
    """
    Utilities for Imports
    """

    @staticmethod
    def create_client(subscription_id, resource):
        try:
            credential = DefaultAzureCredential()
            if resource == "vms":
                client = ComputeManagementClient(credential, subscription_id)
            elif resource == "aks":
                client = ContainerServiceClient(credential, subscription_id)
            elif resource == "sql":
                client = SqlManagementClient(credential, subscription_id)
            elif resource == "mysql":
                client, flxclient = [MySQLManagementClient(credential, subscription_id),MySQLFlexibleManagementClient(credential, subscription_id)]
                return client, flxclient
            elif resource == "postgresql":
                client, flxclient = [PostgreSQLManagementClient(credential, subscription_id),PostgreSQLFlexibleManagementClient(credential, subscription_id)]
                return client, flxclient
            elif resource in ["lbgw", "lb"]:
                client = NetworkManagementClient(credential, subscription_id)
            elif resource == "resource_group":
                client = ResourceManagementClient(credential, subscription_id)
            else:
                raise ValueError(f"Unsupported resource type: {resource}")

            return client
        except Exception as e:
            logger.error(f"Error occured: {e}")
            sys.exit(1)

    @staticmethod
    def get_subscription_name(subscription_id):
            """
            Get the name of the subscription from the subscription ID.
            """
            credential = DefaultAzureCredential()
            subscription_client = SubscriptionClient(credential)
            subscription = subscription_client.subscriptions.get(subscription_id)
            return subscription.display_name

    def run_terraform_cmd(cmd):
        print(cmd)
        try:
            completed_process = subprocess.run(cmd, text=True, capture_output=True)
            if completed_process.returncode == 0:
                logger.info(completed_process.stdout)
            else:
                logger.info(completed_process.stderr)
            return completed_process.stdout, completed_process.stderr
        except subprocess.CalledProcessError as e:
            logger.error(f"Error during terraform {cmd}: {e}")
            sys.exit(1)

    @staticmethod
    def generate_tf_provider(local_repo_path):
        output_file_path = f"{local_repo_path}/providers.tf"

        if os.path.exists(output_file_path):
            logger.info(f"File {output_file_path} already exists.")
            return
        logger.info(f"Creating providers.tf file inside {local_repo_path}")

        tmpl = Environment(loader=FileSystemLoader("templates"))
        template = tmpl.get_template("providers.tf.j2")
        rendered_template = template.render()

        with open(output_file_path, "w") as f:
            f.write(rendered_template)

    @staticmethod
    def skip_resources_from_settings(subscription_name, resource):
        try:
            if subscription_name in SKIP_RESOURCE[resource]:
                return True
        except KeyError:
            return False
        return False
