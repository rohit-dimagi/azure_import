from utils.utilities import Utilities, SkipTag
from utils.cleanup import cleanup_tf_plan_file
from jinja2 import Environment, FileSystemLoader
from azure.mgmt.compute.models import InstanceViewTypes
from loguru import logger
import os
import sys
import re


class VMSImportSetUp:
    """
    Import Block for VMS Import.
    Supoprted resources: VMS, DISK, DISK ATTACHMENTS, EXTENTIONS
    """

    def __init__(self, subscription_id, region, resource, local_repo_path, filters):
        self.resource = resource
        self.client = Utilities.create_client(subscription_id = subscription_id, resource=self.resource)
        self.network_client = Utilities.create_client(subscription_id=subscription_id, resource="lb")
        self.tmpl = Environment(loader=FileSystemLoader("templates"))
        self.region = region   
        self.local_repo_path = local_repo_path
        self.subscription_id = subscription_id
        self.tag_filters = {key: value for key, value in filters} if filters else {}

    def sanitize_name(self, filename):
        # Replace invalid characters with an underscore
        return re.sub(r'[<>:"/\\|?*]', "_", filename)

    def describe_vms(self):
        """
        Get VMS details
        """
        vms = self.client.virtual_machines.list_all()
        vms_details = []

        for vm in vms:
            resource_group_name = vm.id.split('/')[4]
            instance_view = self.client.virtual_machines.instance_view(resource_group_name, vm.name)
            statuses = instance_view.statuses
            vm_state = None

            for status in statuses:
                if 'PowerState' in status.code:
                    vm_state = status.display_status

            # Skip terminated VMs
            if vm_state in ["VM deallocated", "VM deallocating", "VM stopping", "VM stopped"]:
                continue

            # Check tags
            tags_match = all(vm.tags.get(key) == value for key, value in self.tag_filters.items())

            if tags_match:
                os_type = "windows" if vm.storage_profile.os_disk.os_type == "Windows" else "linux"
                
                # Get NIC information
                nic_ids = [nic.id for nic in vm.network_profile.network_interfaces]
                nics = []
                for nic_id in nic_ids:
                    nic_name = nic_id.split('/')[-1]
                    nic = self.network_client.network_interfaces.get(resource_group_name, nic_name)
                    nics.append({
                        'name': nic.name,
                        'id': nic.id,
                    })
                    
                # Get Data Disks
                data_disks = [
                    {
                        'name': disk.name,
                        'id': disk.managed_disk.id,
                        'attachment_id': disk.vhd.uri if disk.vhd else disk.managed_disk.id
                    }
                    for disk in vm.storage_profile.data_disks
                ]
                # Get Extensions
                extensions = self.client.virtual_machine_extensions.list(resource_group_name, vm.name).value
                vm_extensions = [
                    {
                        'name': ext.name,
                        'id': ext.id
                    }
                    for ext in extensions
                ]
                vm_detail = {
                    'vm_name': self.sanitize_name(vm.name),
                    'vm_id': vm.id,
                    'data_disks': data_disks,
                    'nics': nics,
                    'extensions': vm_extensions,
                    'os_type': os_type
                }
                vms_details.append(vm_detail)

        logger.info(f"Total VMS to Import: {len(vms_details)}")  
        return vms_details

    
    def generate_import_blocks(self, vms_details):
        """
        Generate Import Blocks, Generate Terraform code, Cleanup Terraform code
        """
        if not vms_details:
            logger.info("No VM found: Nothing to do. Exitting")
            sys.exit(1)
        template = self.tmpl.get_template("vm_import.tf.j2")

        for vm in vms_details:
            logger.info(f"Importing VM: {vm}")

            context = {
                "vm_name": vm['vm_name'],
                "vm_id": vm['vm_id'],
                "os_type": vm['os_type'],
                "data_disks": vm["data_disks"],
                "nics": vm["nics"],
                "extensions": vm["extensions"]
            }

            rendered_template = template.render(context)

            output_file_path = f"{self.local_repo_path}/import-{vm['vm_name']}.tf"
            with open(output_file_path, "w") as f:
                f.write(rendered_template)

            Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan", f"-generate-config-out=generated-plan-import-{vm['vm_name']}.tf"])
            os.rename(output_file_path, f"{output_file_path}.imported")
            cleanup_tf_plan_file(input_tf_file=f"{self.local_repo_path}/generated-plan-import-{vm['vm_name']}.tf")

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
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "init"])

        instances = self.describe_vms()
        self.generate_import_blocks(instances)
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "fmt"])
        Utilities.run_terraform_cmd(["terraform", f"-chdir={self.local_repo_path}", "plan"])
