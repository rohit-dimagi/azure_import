#!/usr/bin/env python3
import argparse
from import_vm import VMSImportSetUp
from import_aks import AKSImportSetUp
from import_azuredb import AzureDBImportSetUp
from import_alb import ALBImportSetUp
from loguru import logger

if __name__ == "__main__":
    supported_resources = ["vms", "aks", "lb", "lbgw", "sql", "mysql", "postgresql"]
    parser = argparse.ArgumentParser(description="TF Import Script")
    parser.add_argument( "--subscription-id",dest="subscription_id",help="Azure Subscription ID ",type=str,required=True,)
    parser.add_argument("--local-repo-path",dest="local_repo_path",help="Local Repo Path",type=str,required=True,)
    parser.add_argument("--resource", dest="resource", help="Azure Resource", type=str, required=True, choices=supported_resources)
    parser.add_argument("--tag",action="append",nargs=2, metavar=("key", "value"),help="Specify a tag filter as key value pair, e.g. -t TF_MANAGED true -t env dev")

    args = parser.parse_args()

    if args.resource == "vms":
        vms_import = VMSImportSetUp(subscription_id=args.subscription_id, resource=args.resource, local_repo_path=args.local_repo_path, filters=args.tag)
        vms_import.set_everything()
    elif args.resource == "aks":
        aks_import = AKSImportSetUp(subscription_id=args.subscription_id, resource=args.resource, local_repo_path=args.local_repo_path, filters=args.tag)
        aks_import.set_everything()
    elif args.resource in ["mysql", "postgresql", "sql"]:
        azuredb_import = AzureDBImportSetUp(subscription_id=args.subscription_id, resource=args.resource, local_repo_path=args.local_repo_path, filters=args.tag)
        azuredb_import.set_everything()
    elif args.resource in ["lbgw", "lb"]:
        alb_import = ALBImportSetUp(subscription_id=args.subscription_id, resource=args.resource, local_repo_path=args.local_repo_path, filters=args.tag)
        alb_import.set_everything()
    else:
        logger.info(f"Import Currently not Supported for {args.resource}")
