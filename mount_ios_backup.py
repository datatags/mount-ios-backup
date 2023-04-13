#!/usr/bin/env python

import os
import sys
import getpass
import biplist
import argparse
from fuse import FUSE
from standard_backup import BackupFS
from encrypted_backup import EncryptedBackupFS

def main(mountpoint, root, password=None):
    plist = biplist.readPlist(os.path.join(root, "Manifest.plist"))
    if not plist["IsEncrypted"]:
        print("This is an unencrypted backup.")
        FUSE(BackupFS(root), mountpoint, nothreads=True, foreground=True)
        return
    print("This is an encrypted backup.")
    if password is None:
        password = getpass.getpass(prompt="Enter the backup password: ")
    FUSE(EncryptedBackupFS(root, password), mountpoint, nothreads=True, foreground=True)

class PrintUsageParser(argparse.ArgumentParser):
    def error(self, message):
        print(f"Error: {message}", file=sys.stderr)
        self.print_help()
        sys.exit(2)

if __name__ == '__main__':
    arg_parser = PrintUsageParser(description="""
    Mount the specified iPhone backup at the specified mount point.
    
    If the backup is encrypted and no password is supplied,
    it will be interactively requested. The password can be
    supplied using the --password flag, or the BACKUP_PASSWORD
    environment variable.
    """)
    arg_parser.add_argument("backup")
    arg_parser.add_argument("mountpoint")
    arg_parser.add_argument("-p", "--password", help="the backup password, if encrypted")
    args = arg_parser.parse_args()
    root = args.backup
    mountpoint = args.mountpoint
    password = args.password
    if password is None and "BACKUP_PASSWORD" in os.environ:
        password = os.environ["BACKUP_PASSWORD"]
    main(mountpoint, root, password)
