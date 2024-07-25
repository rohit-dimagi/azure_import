import re
import sys
from loguru import logger
import os
import subprocess

# Define the RESOURCE_CLEANUP dictionary with patterns properly escaped
RESOURCE_CLEANUP = {
    "global": ["null"],
    "multiline_pattern": [],
    "azurerm_windows_virtual_machine": ["= 0", "os_profile {} # sensitive", "platform_fault_domain"],
    "azurerm_linux_virtual_machine": ["= 0", "os_profile {} # sensitive", "platform_fault_domain"],
    "azurerm_managed_disk": ["= 0"],
    "azurerm_network_interface": ["= \[\]"],
    "azurerm_virtual_machine_extension": ["= \[\]","\{\}"],
    "azurerm_kubernetes_cluster": [
        "= 0",
        "= \[\]",
    ],
    "azurerm_kubernetes_cluster_node_pool": [
        "= 0",
        "= \[\]",
    ],
    "azurerm_mssql_database": ["= 0", "\[\]", "max_size_gb", "transparent_data_encryption_key_automatic_rotation_enabled"],
    "azurerm_mssql_server": ["= 0", "administrator_login"],
    "azurerm_application_gateway": ["= 0", "ssl_certificate {} # sensitive"]
}


def remove_global_lines(tf_file, list_to_cleanup):
    output_file = tf_file
    logger.info(f"Removing lines containing following items: {list_to_cleanup}")

    with open(tf_file, "r") as readfile:
        lines = readfile.readlines()
        filtered_lines = []

        for line in lines:
            if "admin_password" in line: # Skip the null value for admin_password for windows
                filtered_lines.append(line)
                continue
            if "client_secret = null # sensitive" in line: # Skip the null value for client_secret for AKS
                filtered_lines.append(line)
                continue
            if any(element in line for element in list_to_cleanup):
                continue
            filtered_lines.append(line)

    with open(output_file, "w") as write_file:
        write_file.writelines(filtered_lines)

    logger.info(f"Generated intermediate file to process: {output_file}")
    return output_file


def remove_multiline(file, patterns):
    with open(file, "r") as readfile:
        content = readfile.read()

        for pattern in patterns:
            matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
            # Remove the matches from the content
            content = re.sub(pattern, "", content, flags=re.MULTILINE | re.DOTALL)

    with open(file, "w") as writefile:
        writefile.write(content)


def should_remove_line(line, resource_type, custom_pattern=[]):
    """
    Determine if a line should be removed based on the resource type and global patterns.
    """
    if not custom_pattern:
        patterns = RESOURCE_CLEANUP.get(resource_type, [])
    else:
        patterns = custom_pattern

    for pattern in patterns:
        if re.search(pattern, line):
            return True
    return False

def process_terraform_plan(input_file):
    with open(input_file, "r") as file:
        lines = file.readlines()

    new_lines = []
    in_resource_block = False
    current_resource_type = None

    for line in lines:
        # Check if the line starts a new resource block
        resource_block_match = re.match(r'\s*resource\s+"(\w+)"\s+"[^"]+"\s+{', line)
        if resource_block_match:
            in_resource_block = True
            current_resource_type = resource_block_match.group(1)

            new_lines.append(line)
            continue

        # Check if the line ends a resource block
        if in_resource_block and re.match(r"\s*}$\n#", line):
            in_resource_block = False
            current_resource_type = None
            new_lines.append(line)
            continue

        # Process lines within a resource block
        if in_resource_block and current_resource_type:
            if current_resource_type == "azurerm_mssql_server": #Special Case for Jsonencode Skipping decimal in version number fix
                if "jsonencode(12)" in line:
                    line = 'version      = "12.0"\n'

            if current_resource_type == "azurerm_application_gateway": #Special Case for Jsonencode Skipping decimal in version number fix
                if "jsonencode(3)" in line:
                    line = 'rule_set_version      = "3.0"\n'

            if current_resource_type == "azurerm_application_gateway": #Special Case for preserving min_capacity = 0
                if "min_capacity" in line:
                    new_lines.append(line)
                    continue

            if current_resource_type == "azurerm_windows_virtual_machine":
                if "admin_password" in line:
                    logger.error(f"admin_password is set to a random value :- Ericsson@123. Please Change it correct value before Running apply")
                    line = 'admin_password      = "Ericsson@123"\n'

            if current_resource_type == "azurerm_kubernetes_cluster":
                if "client_secret" in line:
                    logger.error(f"client_secret is set to a random value :- Ericsson@123. Please Change it correct value before Running apply")
                    line = 'client_secret      = "Ericsson@123"\n'
                if "identity_ids" in line:
                    new_lines.append(line)
                    continue
                if "idle_timeout_in_minutes" in line:
                    line = 'idle_timeout_in_minutes = 30\n'

            if current_resource_type == "azurerm_virtual_machine_extension":
                if "jsonencode(1)" in line:
                    line = 'type_handler_version      = "1.0"\n'
                if "jsonencode(2)" in line:
                    line = 'type_handler_version      = "2.0"\n'
                if "jsonencode(3)" in line:
                    line = 'type_handler_version      = "3.0"\n'

            if should_remove_line(line, current_resource_type):
                continue
        new_lines.append(line)

    # Write the cleaned content to a new file
    with open(input_file, "w") as new_file:
        new_file.writelines(new_lines)

    logger.info(f"Generated Cleaned up File: {input_file}")


def cleanup_tf_plan_file(input_tf_file):

    # Process the Global defaults vaules
    level1_cleanup_file = remove_global_lines(input_tf_file, RESOURCE_CLEANUP["global"])

    # Process resource Specific Blocks
    process_terraform_plan(level1_cleanup_file)

    remove_multiline(input_tf_file, RESOURCE_CLEANUP["multiline_pattern"])
