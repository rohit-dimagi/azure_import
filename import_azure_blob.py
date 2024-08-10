from utils.utilities import Utilities, SkipTag
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from utils.cleanup import cleanup_tf_plan_file
import sys


class StorageAccountImportSetUp:
    """
    Import Block for Azure Storage Account.
    """

    def __init__(self, subscription_id, resource, local_repo_path, filters):
        self.resource = resource
        self.az_storage_client = Utilities.create_client(subscription_id=subscription_id, resource=self.resource)
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

    def get_storage_account_details(self):
        """
        Get details of all Azure Storage Account in the subscription, applying tag filters.
        """

        storage_account_details = []

        # List all Storage accounts  in the subscription
        storage_accounts = self.az_storage_client.storage_accounts.list()

        for item in storage_accounts:
            item_tags = item.tags or {}
            if not self._tags_match(item_tags):
                continue

            storage_account = {
                "storage_account_name": item.name,
                "storage_account_id": item.id
            }
            storage_account_details.append(storage_account)
        logger.info(f"Total Azure Storage Account to Import: {len(storage_account_details)}")
        return storage_account_details

    def generate_import_blocks(self, storage_accounts):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not storage_accounts:
            logger.info(f"No {(self.resource).upper()} found: Nothing to do. Exitting")
            sys.exit(1)

        template = self.tmpl.get_template("azure_blob_import.tf.j2")

        for storage_account in storage_accounts:
            logger.info(f"Importing : {storage_account}")

            context = {
                "storage_account_name": storage_account["storage_account_name"],
                "storage_account_id": storage_account["storage_account_id"]
            }

            rendered_template = template.render(context)

            output_file_path = (
                f"{self.local_repo_path}/import-{storage_account['storage_account_name']}.tf"
            )
            with open(output_file_path, "w") as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(
                [
                    "terraform",
                    f"-chdir={self.local_repo_path}",
                    "plan",
                    f"-generate-config-out=generated-plan-import-{storage_account['storage_account_name']}.tf",
                ]
            )
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(
                input_tf_file=f"{self.local_repo_path}/generated-plan-import-{storage_account['storage_account_name']}.tf"
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

        storage_accounts = self.get_storage_account_details()

        self.generate_import_blocks(storage_accounts)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
