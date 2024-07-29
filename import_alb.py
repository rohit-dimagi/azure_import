from utils.utilities import Utilities, SkipTag
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from utils.cleanup import cleanup_tf_plan_file
import sys


class ALBImportSetUp:
    """
    Import Block for Azure LB Import.
    Supoprted resources: Azure LB and GW.
    """

    def __init__(self, subscription_id, resource, local_repo_path, filters):
        self.resource = resource
        if resource in ["lbgw", "lb"]:
            self.lb_client = Utilities.create_client(subscription_id=subscription_id, resource=self.resource)
        self.subscription_name = Utilities.get_subscription_name(subscription_id=subscription_id)

        self.tmpl = Environment(loader=FileSystemLoader("templates"))
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

    def get_alb_details(self):
        """
        Get details of all Azure Application Gateways in the subscription, applying tag filters.
        """


        if self.resource == "lbgw":
            application_gateway_details = []

            # List all application gateways in the subscription
            app_gateways = self.lb_client.application_gateways.list_all()

            for gateway in app_gateways:
                gateway_tags = gateway.tags or {}
                if not self._tags_match(gateway_tags):
                    continue

                # Retrieve public IP information
                public_ip_info = []
                for ip_config in gateway.frontend_ip_configurations:
                    if ip_config.public_ip_address:
                        public_ip = self.lb_client.public_ip_addresses.get(
                            resource_group_name=gateway.resource_group,
                            public_ip_address_name=ip_config.public_ip_address.id.split('/')[-1]
                        )
                        public_ip_info.append({
                            "name": public_ip.name,
                            "id": public_ip.id,
                        })

                lbgw = {
                    "lb_name": gateway.name,
                    "lb_id": gateway.id,
                    "type": "gateway",
                    "public_ip": public_ip_info
                }
                application_gateway_details.append(lbgw)

            logger.info(f"Total Application Gateway to Import: {len(application_gateway_details)}")
            return application_gateway_details

        if self.resource == "lb":
            load_balancer_details = []

            # List all application gateways in the subscription
            lbs = self.lb_client.load_balancers.list_all()

            for load_balancer in lbs:
                load_balancer_tags = load_balancer.tags or {}
                if not self._tags_match(load_balancer_tags):
                    continue

                # if load balancer name contains kubernetes, skip it.
                if "kubernetes" in load_balancer.name:
                   logger.info(f"Skipping LoadBalancer: {load_balancer.name}, It's being Managed by Kubernetes Cluster")
                   continue

                backend_pools = [
                    {"name": pool.name, "id": pool.id}
                    for pool in load_balancer.backend_address_pools
                ]

                probes = [
                    {"name": probe.name, "id": probe.id}
                    for probe in load_balancer.probes
                ]

                rules = [
                    {"name": rule.name, "id": rule.id}
                    for rule in load_balancer.load_balancing_rules
                ]

                lb = {
                    "lb_name": load_balancer.name,
                    "lb_id": load_balancer.id,
                    "lb_backend_pools": backend_pools,
                    "lb_probes": probes,
                    "lb_rules": rules,
                    "type": "load-balancer"
                }
                load_balancer_details.append(lb)
            logger.info(f"Total Load Balancer to Import: {len(load_balancer_details)}")
            return load_balancer_details

    def generate_import_blocks(self, alb_details):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not alb_details:
            logger.info(f"No {(self.resource).upper()} found: Nothing to do. Exitting")
            sys.exit(1)

        template = self.tmpl.get_template("alb_import.tf.j2")

        for alb_detail in alb_details:
            logger.info(f"Importing : {alb_detail}")

            if self.resource == "lb":
                context = {
                    "lb_name": alb_detail["lb_name"],
                    "lb_id": alb_detail["lb_id"],
                    "lb_backend_pools": alb_detail["lb_backend_pools"],
                    "lb_rules": alb_detail["lb_rules"],
                    "lb_probes": alb_detail["lb_probes"],
                    "type": alb_detail["type"]
                }
            if self.resource == "lbgw":
                context = {
                    "lb_name": alb_detail["lb_name"],
                    "lb_id": alb_detail["lb_id"],
                    "public_ips": alb_detail["public_ip"],
                    "type": alb_detail["type"],
                }
            rendered_template = template.render(context)

            output_file_path = (
                f"{self.local_repo_path}/import-{alb_detail['lb_name']}.tf"
            )
            with open(output_file_path, "w") as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(
                [
                    "terraform",
                    f"-chdir={self.local_repo_path}",
                    "plan",
                    f"-generate-config-out=generated-plan-import-{alb_detail['lb_name']}.tf",
                ]
            )
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(
                input_tf_file=f"{self.local_repo_path}/generated-plan-import-{alb_detail['lb_name']}.tf"
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
        if Utilities.skip_resources_from_settings(self.subscription_name, self.resource):
            logger.info(f"Skipping Resources {self.resource} from subscription account {self.subscription_name}. For more info check utils/settings.py\n Exitting.")
            sys.exit(1)

        Utilities.generate_tf_provider(self.local_repo_path)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "init"])

        alb = self.get_alb_details()

        self.generate_import_blocks(alb)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
