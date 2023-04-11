# mount-ios-backup
A tool to mount iOS backups as a FUSE filesystem

## Dependencies
(I haven't tried to create a requirements file yet)
- `pyfuse`
- `biplist`
- `sqlite3`

## General information
- Tested on a backup from a device running iOS 16, created by `libimobiledevice`. I don't think backup formats have changed in several iOS versions, and `libimobiledevice` backups should be identical to iTunes backups, so it should work on those as well, but I haven't tested it.
- The mounted backup will be read-only. I don't forsee this changing because I don't want to deal with writing backup files when reading them is complex enough. Plus, a bug in a function that does writes is MUCH more likely to cause damage than a function that only does reads.
- Mounting is done via FUSE, meaning you can unmount it by stopping the script or running `fusermount -u <mountpoint>`
- This tool is not super focused on performance, and simply using `ls -l` may take a couple seconds on a directory with hundreds of items, such as the AppDomain folders, because that requires it to get file properties from the database (`Manifest.db`). File transfer speed shouldn't be impacted much, however.
- When mounting the filesystem, `Manifest.db` is loaded into memory to avoid hitting the disk whenever possible. The largest manifest file I've seen is 240M, which shouldn't be a huge burden on most systems as it's less than I would expect any web browser to use, but I plan to make a flag to disable it.

## Todo
- Handle symlinks in some fashion, since they apparently appear in some places
- Avoid hitting the database for every call to `getattr` to improve performance?
- Add command-line options, including:
  - `foreground`
  - `allow_other`
  - Disable RAM-caching manifest
  - Standard mounting options?
- Support encrypted backups with https://github.com/jsharkey13/iphone_backup_decrypt
- Return something more useful from `statfs`
  - Currently returns stats of filesystem at mount point
- Figure out how to make it installable?
