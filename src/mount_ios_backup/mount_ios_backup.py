#!/usr/bin/env python

import os
import sys
import getpass
import biplist
import argparse
from fuse import FUSE
from .standard_backup import BackupFS
from .encrypted_backup import EncryptedBackupFS

def main():
    arg_parser = PrintUsageParser(description="""
    Mount the specified iPhone backup at the specified mount point.
    
    If the backup is encrypted and no password is supplied,
    it will be interactively requested. The password can be
    supplied using the --password flag, or the BACKUP_PASSWORD
    environment variable.
    """)
    arg_parser.add_argument("backup", help="the backup folder to read (include device UID)")
    arg_parser.add_argument("mountpoint", help="the folder to mount the backup in")
    arg_parser.add_argument("-p", "--password", help="the backup password, if encrypted")
    arg_parser.add_argument("-f", "--foreground", action="store_true", help="keep the process in the foreground")
    arg_parser.add_argument("--list-size-anomalies", action="store_true", help="find files whose sizes do not match the size in the manifest")
    args = arg_parser.parse_args()
    root = os.path.abspath(args.backup)
    mountpoint = os.path.abspath(args.mountpoint)
    password = args.password
    foreground = args.foreground
    anomalies = args.list_size_anomalies
    if password is None and "BACKUP_PASSWORD" in os.environ:
        password = os.environ["BACKUP_PASSWORD"]

    plist = biplist.readPlist(os.path.join(root, "Manifest.plist"))
    if plist["IsEncrypted"]:
        print("This is an encrypted backup.")
        if password is None:
            password = getpass.getpass(prompt="Enter the backup password: ")
        fs = EncryptedBackupFS(root, password)
    else:
        print("This is an unencrypted backup.")
        fs = BackupFS(root)
    if anomalies:
        fs.list_size_anomalies()
        return
    if foreground:
        print("Staying in foreground, press Ctrl-C to unmount")
    else:
        print(f"Switching to background, use 'fusermount -u {mountpoint}' to unmount")
    FUSE(fs, mountpoint, nothreads=True, foreground=foreground)

class PrintUsageParser(argparse.ArgumentParser):
    def error(self, message):
        print(f"Error: {message}", file=sys.stderr)
        self.print_help()
        sys.exit(2)

if __name__ == '__main__':
    main()
