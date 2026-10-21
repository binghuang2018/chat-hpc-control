"""Trusted workflow helper: record actual upload outputs with API readback."""
import argparse
import json
import os
from pathlib import Path
from chat_hpc_control.core.config import load_site
from chat_hpc_control.publishers.admin import operate
from chat_hpc_control.contracts.codec import decode_json
from chat_hpc_control.contracts.results import PublishReceipt


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--site',type=Path,required=True)
    parser.add_argument('--target',required=True);parser.add_argument('--collection-root',type=Path,required=True)
    parser.add_argument('--previous-receipt',type=Path)
    args=parser.parse_args()
    upload={'artifact_id':int(os.environ['CHC_ARTIFACT_ID']),'artifact_digest':os.environ['CHC_ARTIFACT_DIGEST'],
            'artifact_url':os.environ['CHC_ARTIFACT_URL'],'archive_sha256':os.environ['CHC_ARCHIVE_SHA256']}
    previous=PublishReceipt(**decode_json(args.previous_receipt.read_bytes())) if args.previous_receipt else None
    print(json.dumps(operate(load_site(args.site),operation='record-upload',target=args.target,
          collection_root=args.collection_root,upload_result=upload,previous=previous),allow_nan=False))


if __name__=='__main__':main()
