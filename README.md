# mount-ios-backup
A tool to mount iOS backups as a FUSE filesystem. Useful for things such as:
- Recovering photos from a backup without having to completely restore it to a phone.
- Copying photos even from a working phone if the normal USB interface doesn't work well for you. (It certainly doesn't for me.)
- Reading app data not normally accessible without a rooted phone.

## Dependencies
- `pyfuse`
- `biplist`
- `sqlite3` (built-in)
- `fastpbkdf2`
- `pycryptodome`

## Usage

```mount_ios_backup.py <backup> <mountpoint>```

## General information
- Tested on a backup from a device running iOS 16, created by `libimobiledevice`. I don't think backup formats have changed in several iOS versions, and `libimobiledevice` backups should be identical to iTunes backups, so it should work on those as well, but I haven't tested it.
- The mounted backup will be read-only. I don't forsee this changing because I don't want to deal with writing backup files when reading them is complex enough. Plus, it's more difficult to cause catastrophic issues on a read-only filesystem.
- Mounting is done via FUSE, meaning you can unmount it by stopping the script or running `fusermount -u <mountpoint>`
- This tool is not super focused on performance, and simply using `ls -l` may take a couple seconds on a directory with hundreds of items, such as the AppDomain folders, because that requires it to get file properties from the database (`Manifest.db`). File transfer speed shouldn't be impacted much, however.
- When mounting the filesystem, `Manifest.db` is loaded into memory to avoid hitting the disk whenever possible. The largest manifest file I've seen is 240M, which shouldn't be a huge burden on most systems as it's less than I would expect any web browser to use, but I plan to make a flag to disable it.
  - With RAM-caching, the script shouldn't take more than 1.25x - 1.5x the size of the manifest in memory usage.

## Encrypted backups
- This tool can mount encrypted backups as well (with the password of course.)
- The password can be supplied through an environment variable (`BACKUP_PASSWORD`,) a flag (`--password`,) or interactively. The password will remain in memory until the script exits.
- Due to limitations of the `sqlite3` library, the `Manifest.db` must be decrypted and written to disk before it can be opened.
  - If RAM-caching is enabled, the file will be deleted after being loaded into memory, but without full-disk encryption, it may be recoverable.
- Transfer speed is slower from encrypted backups.
  - When transferring a single large file, I'm able to get about 100MB/s from an unencrypted backup, and 50MB/s from an encrypted backup on my machine.
  - Smaller block sizes may hurt transfer speed more, as each read call needs to read data before and sometimes after the requested area.

## Todo
- ~~Handle symlinks in some fashion, since they apparently appear in some places~~
- Avoid hitting the database for every call to `getattr` to improve performance?
- Add command-line options, including:
  - ~~`foreground`~~
  - `allow_other`
  - Disable RAM-caching manifest
  - Standard mounting options?
  - ~~`password`~~
- ~~Support encrypted backups with https://github.com/jsharkey13/iphone_backup_decrypt~~
- Return something more useful from `statfs`
  - Currently returns stats of filesystem at mount point
- ~~Figure out how to make it installable?~~
