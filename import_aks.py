from utils.utilities import Utilities, SkipTag
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from utils.cleanup import cleanup_tf_plan_file
import sys


class AKSImportSetUp:
    """
    Import Block for AKS Import.
    Supoprted resources: AKS, Addons, NodePools, ScaleSet
    """

    def __init__(self, subscription_id, region, resource, local_repo_path, filters):
        self.aks_client = Utilities.create_client(
            subscription_id=subscription_id,
            resource=resource,
        )
        self.resource_client = Utilities.create_client(
            subscription_id, resource="resource_group"
        )
        self.tmpl = Environment(loader=FileSystemLoader("templates"))
        self.region = region
        self.local_repo_path = local_repo_path
        self.subscription_id = subscription_id
        self.tag_filters = {key: value for key, value in filters} if filters else {}

    def _tags_match(self, resource_tags):
        """
        Check if resource tags match the filters.
        """
        if resource_tags.get("TF_IMPORTED") == "True":
            return False

        for key, value in self.tag_filters.items():
            if key not in resource_tags or resource_tags[key] != value:
                return False
        return True

    def describe_aks_cluster(self):
        """
        Get Cluster details for all AKS clusters in the subscription
        """
        cluster_details = []

        resource_groups = self.resource_client.resource_groups.list()

        for rg in resource_groups:
            clusters = self.aks_client.managed_clusters.list_by_resource_group(rg.name)

            for cluster in clusters:
                # Check if the cluster matches the tag filters
                cluster_tags = cluster.tags or {}
                if not self._tags_match(cluster_tags):
                    continue

                cluster_detail = self.aks_client.managed_clusters.get(
                    rg.name, cluster.name
                )

                node_pools = []
                for pool in cluster_detail.agent_pool_profiles:

                    if (
                        pool.mode == "System"
                    ):  # Skip nodepool if mode of nodepool is "System"
                        continue
                    node_pools.append(pool.name)

                cluster_info = {
                    "cluster_name": cluster_detail.name,
                    "location": cluster_detail.location,
                    "dns_prefix": cluster_detail.dns_prefix,
                    "node_pools": node_pools,
                    "node_resource_group": cluster_detail.node_resource_group,
                    "resource_group": rg.name,
                }
                cluster_details.append(cluster_info)
        logger.info(f"Total AKS Cluster Found: { len(cluster_details) }")

        return cluster_details

    def generate_import_blocks(self, aks_cluster_details):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not aks_cluster_details:
            logger.info("No AKS Cluster found: Nothing to do. Exitting")
            sys.exit(1)

        template = self.tmpl.get_template("aks_import.tf.j2")

        for aks_cluster in aks_cluster_details:
            logger.info(f"Importing : {aks_cluster}")

            context = {
                "cluster_name": aks_cluster["cluster_name"],
                "subscription_id": self.subscription_id,
                "resource_group": aks_cluster["resource_group"],
                "node_pools": aks_cluster["node_pools"],
            }

            rendered_template = template.render(context)

            output_file_path = (
                f"{self.local_repo_path}/import-{aks_cluster['cluster_name']}.tf"
            )
            with open(output_file_path, "w") as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(
                [
                    "terraform",
                    f"-chdir={self.local_repo_path}",
                    "plan",
                    f"-generate-config-out=generated-plan-import-{aks_cluster['cluster_name']}.tf",
                ]
            )
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(
                input_tf_file=f"{self.local_repo_path}/generated-plan-import-{aks_cluster['cluster_name']}.tf"
            )

        for filename in os.listdir(self.local_repo_path):
            if filename.endswith(".imported"):
                new_filename = filename.replace(".imported", "")
                old_file = os.path.join(self.local_repo_path, filename)
                new_file = os.path.join(self.local_repo_path, new_filename)
                os.rename(old_file, new_file)

    def set_everything(self):
        """
        Setup the WorkFlow Steps.
        """
        Utilities.generate_tf_provider(self.local_repo_path, region=self.region)
        Utilities.run_terraform_cmd(
            ["terraform", f"-chdir={self.local_repo_path}", "init"]
        )

        aks_clusters = self.describe_aks_cluster()
        self.generate_import_blocks(aks_clusters)
        Utilities.run_terraform_cmd(
            ["terraform", f"-chdir={self.local_repo_path}", "fmt"]
        )
        Utilities.run_terraform_cmd(
            ["terraform", f"-chdir={self.local_repo_path}", "plan"]
        )
