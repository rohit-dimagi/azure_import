from utils.utilities import Utilities, SkipTag
from jinja2 import Environment, FileSystemLoader
from loguru import logger
import os
from utils.cleanup import cleanup_tf_plan_file
import sys


class AzureDBImportSetUp:
    """
    Import Block for Azure DB Import.
    Supoprted resources: Azure Database for PAAS , IAAS
    """

    def __init__(self, subscription_id, resource, local_repo_path, filters):
        self.resource = resource
        if resource == "mysql":
            self.mysql_client, self.mysql_flexible_client = Utilities.create_client(subscription_id=subscription_id, resource='mysql')
        if resource == "postgresql":
            self.postgresql_client, self.postgresql_flexible_client = Utilities.create_client(subscription_id=subscription_id, resource='postgresql')
        if resource == "sql":
            self.sql_client = Utilities.create_client(subscription_id=subscription_id, resource=self.resource)
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

    def get_databases(self):
        """
        Get details of all Azure databases in the subscription, applying tag filters.
        """
        database_details = []

        if self.resource == "mysql":
            # MySQL Databases
            mysql_servers = self.mysql_client.servers.list()
            mysql_flexible_servers = self.mysql_flexible_client.servers.list()

            for server in mysql_servers:
                # Skip the server if it is stopped
                if server.user_visible_state.lower() == "stopped":
                    logger.info(f"Skipping stopped MySQL server: {server.name}")
                    continue

                # Check if the server matches the tag filters and skip if TF_IMPORTED=True
                server_tags = server.tags or {}
                if not self._tags_match(server_tags):
                    continue

                # Get the list of databases for the current server
                databases = self.mysql_client.databases.list_by_server(resource_group_name=(server.id).split('/')[4], server_name=server.name)
                db_list = []
                for db in databases:
                    if db.name not in ["mysql","sys","performance_schema", "information_schema", "tmp"]:
                        db_list.append({
                            "db_name": db.name,
                            "db_id": db.id
                        })

                database_details.append({
                    "instance_name": server.name,
                    "instance_id": server.id,
                    "type": "single",
                    "db_list": db_list
                })

            for server in mysql_flexible_servers:
                # Skip the server if it is stopped
                if server.state.lower() == "stopped":
                    logger.info(f"Skipping stopped MySQL server: {server.name}")
                    continue

                # Check if the server matches the tag filters and skip if TF_IMPORTED=True
                server_tags = server.tags or {}
                if not self._tags_match(server_tags):
                    continue

                # Get the list of databases for the current flexible server
                databases = self.mysql_flexible_client.databases.list_by_server(resource_group_name=(server.id).split('/')[4], server_name=server.name)
                db_list = []
                for db in databases:
                    if db.name not in ["mysql","sys","performance_schema", "information_schema", "tmp"]:
                        db_list.append({
                            "db_name": db.name,
                            "db_id": db.id
                        })

                database_details.append({
                    "instance_name": server.name,
                    "instance_id": server.id,
                    "type": "flexible",
                    "db_list": db_list
                })

        if self.resource == "postgresql":
            # PostgreSQL Single Server Databases
            postgresql_servers = self.postgresql_client.servers.list()
            postgresql_flexible_servers = self.postgresql_flexible_client.servers.list()

            for server in postgresql_servers:
                # Skip the server if it is stopped
                if server.user_visible_state.lower() == "stopped":
                    logger.info(f"Skipping stopped PostgreSQL server: {server.name}")
                    continue
                # Check if the server matches the tag filters and skip if TF_IMPORTED=True
                server_tags = server.tags or {}
                if not self._tags_match(server_tags):
                    continue

                # Get databases for the server
                databases = self.postgresql_client.databases.list_by_server(resource_group_name=(server.id).split('/')[4], server_name=server.name)
                db_list = []
                for db in databases:
                    if db.name not in ["postgres", "azure_maintenance", "azure_sys"]:  # Skip the system database for PostgreSQL
                        db_list.append({
                            "db_name": db.name,
                            "db_id": db.id
                        })

                database_details.append({
                    "instance_name": server.name,
                    "instance_id": server.id,
                    "type": "single",
                    "db_list": db_list
                })

            # PostgreSQL Flexible Server Databases
            for server in postgresql_flexible_servers:
                # Skip the server if it is stopped
                if server.state.lower() == "stopped":
                    logger.info(f"Skipping stopped PostgreSQL Flexible server: {server.name}")
                    continue

                # Check if the server matches the tag filters and skip if TF_IMPORTED=True
                server_tags = server.tags or {}
                if not self._tags_match(server_tags):
                    continue

                # Get databases for the flexible server
                databases = self.postgresql_flexible_client.databases.list_by_server(resource_group_name=(server.id).split('/')[4], server_name=server.name)
                db_list = []
                for db in databases:
                    if db.name not in ["postgres", "azure_maintenance", "azure_sys"]:  # Skip the system database for PostgreSQL
                        db_list.append({
                            "db_name": db.name,
                            "db_id": db.id
                        })

                database_details.append({
                    "instance_name": server.name,
                    "instance_id": server.id,
                    "type": "flexible",
                    "db_list": db_list
                })

        if self.resource == "sql":
            # Azure SQL Databases
            sql_servers = self.sql_client.servers.list()
            for server in sql_servers:
                # Skip the server if it is stopped
                if server.state.lower() == "stopped":
                    logger.info(f"Skipping stopped SQL server: {server.name}")
                    continue

                # Check if the server matches the tag filters and skip if TF_IMPORTED=True
                server_tags = server.tags or {}
                if not self._tags_match(server_tags):
                    continue

                # Get databases for the server
                databases = self.sql_client.databases.list_by_server(resource_group_name=(server.id).split('/')[4], server_name=server.name)
                db_list = []
                for db in databases:
                    if db.name != "master":  # Assuming "master" is the system database for Azure SQL
                        db_list.append({
                            "db_name": db.name,
                            "db_id": db.id
                        })

                database_details.append({
                    "instance_name": server.name,
                    "instance_id": server.id,
                    "type": "single",
                    "db_list": db_list
                })

        logger.info(f"Total DataBase to Import {len(database_details)}")
        return database_details

    def generate_import_blocks(self, database_details):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not database_details:
            logger.info("No Database Instance found: Nothing to do. Exitting")
            sys.exit(1)

        template = self.tmpl.get_template("azuredb_import.tf.j2")

        for databse_instance in database_details:
            logger.info(f"Importing : {databse_instance}")

            context = {
                "instance_name": databse_instance["instance_name"],
                "instance_id": databse_instance["instance_id"],
                "type": databse_instance["type"],
                "db_list": databse_instance["db_list"],
                "platform": self.resource
            }

            rendered_template = template.render(context)

            output_file_path = (
                f"{self.local_repo_path}/import-{databse_instance['instance_name']}.tf"
            )
            with open(output_file_path, "w") as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(
                [
                    "terraform",
                    f"-chdir={self.local_repo_path}",
                    "plan",
                    f"-generate-config-out=generated-plan-import-{databse_instance['instance_name']}.tf",
                ]
            )
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(
                input_tf_file=f"{self.local_repo_path}/generated-plan-import-{databse_instance['instance_name']}.tf"
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

        databases = self.get_databases()
        self.generate_import_blocks(databases)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
