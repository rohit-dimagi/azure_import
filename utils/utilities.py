import os
import subprocess
from loguru import logger
import sys
from jinja2 import Environment, FileSystemLoader
import os
from enum import Enum
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.resource import ResourceManagementClient


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
            subscription_id = subscription_id
            if resource == "vms":
                client = ComputeManagementClient(credential, subscription_id)
            elif resource == "aks":
                client = ContainerServiceClient(credential, subscription_id)
            elif resource == "resource_group":
                client = ResourceManagementClient(credential, subscription_id)
            else:
                raise ValueError(f"Unsupported resource type: {resource}")

            return client
        except Exception as e:
            logger.error(f"Error occured: {e}")
            sys.exit(1)
       
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
    def generate_tf_provider(local_repo_path, region):
        output_file_path = f"{local_repo_path}/providers.tf"

        if os.path.exists(output_file_path):
            logger.info(f"File {output_file_path} already exists.")
            return
        logger.info(f"Creating providers.tf file inside {local_repo_path}")
        tmpl = Environment(loader=FileSystemLoader("templates"))
        template = tmpl.get_template("providers.tf.j2")
        context = {"cloud_provider_region": region}

        rendered_template = template.render(context)

        with open(output_file_path, "w") as f:
            f.write(rendered_template)
