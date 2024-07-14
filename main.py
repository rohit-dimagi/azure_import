#!/usr/bin/env python3
import argparse
from import_vm import VMSImportSetUp
from import_aks import AKSImportSetUp

from loguru import logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TF Import Script")
    parser.add_argument("--subscription-id", dest="subscription_id", help="Azure Subscription ID ", type=str, required=True)
    parser.add_argument("--local-repo-path", dest="local_repo_path", help="Local Repo Path", type=str, required=True)
    parser.add_argument("--resource", dest="resource", help="Azure Resource", type=str, required=True)
    parser.add_argument("--region", dest="region", help="AWS Region", type=str, required=True)
    parser.add_argument("--tag", action="append", nargs=2, metavar=("key", "value"), help="Specify a tag filter as key value pair, e.g. -t TF_MANAGED true -t env dev")
    args = parser.parse_args()


    if args.resource == "vms":
        vms_import = VMSImportSetUp(subscription_id=args.subscription_id, region=args.region, resource=args.resource, local_repo_path=args.local_repo_path,filters=args.tag)
        vms_import.set_everything()
    elif args.resource == "aks":
        vms_import = AKSImportSetUp(subscription_id=args.subscription_id, region=args.region, resource=args.resource, local_repo_path=args.local_repo_path,filters=args.tag)
        vms_import.set_everything()
    else:
        logger.info(f"Import Not currently supported for {args.resource}")
