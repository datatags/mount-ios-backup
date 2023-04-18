import os
import errno
import biplist
import sqlite3
from file_info import FileInfo
from fuse import FuseOSError, Operations

def debug(message):
    if False:
        print(message)

class BackupFS(Operations):
    # Source: "file creation flags" in https://man7.org/linux/man-pages/man2/open.2.html#DESCRIPTION
    # Except for O_DIRECTORY
    BAD_FILE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CLOEXEC | os.O_CREAT | os.O_EXCL | os.O_NOCTTY | os.O_NOFOLLOW | os.O_TMPFILE | os.O_TRUNC
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._db_connection = None
        self._domain_tree = {}
        self._generate_domain_tree()
        print("Init finished")

    # Helpers
    # =======

    def _get_file_info(self, partial):
        """
        Throws FuseOSError if the target does not exist.
        Returns a FileInfo corresponding to the file properties.
        
        The FileInfo will be "virtual" if the target is a virtual domain, i.e. AppInfo or root
        """
        if partial.startswith("/"):
            partial = partial[1:]
        if partial.endswith(os.sep):
            partial = partial[:-1]
        if len(partial) == 0:
            return FileInfo(self.root, None, "", None, None, 2, virtual=True)
        parts = partial.split(os.sep)
        try:
            domain_tree = self._domain_tree[parts[0]]
        except KeyError:
            debug(f"Invalid domain: {parts[0]}")
            raise FuseOSError(errno.ENOENT)
        domain_path = parts[0]
        domain_segments = 1
        # If the domain has "subdomains," try and find one
        if isinstance(domain_tree, dict):
            if len(parts) == 1:
                return FileInfo(self.root, None, domain_path, None, None, 2, virtual=True)
            try:
                domain_tree = domain_tree[parts[1]]
                domain_path += f"-{parts[1]}"
                domain_segments = 2
            except KeyError:
                debug(f"Invalid subdomain: {parts[0]} -> {parts[1]}")
                raise FuseOSError(errno.ENOENT)
        
        # If only a (full) domain path was supplied,
        # relativePath should be an empty string.
        relative_path = ""
        for (index,part) in enumerate(parts):
            if index < domain_segments:
                continue
            relative_path += f"{part}/"
        # Chop trailing slash
        relative_path = relative_path[:-1]
        
        cur = self._get_db_connection().cursor()
        cur.execute("SELECT `fileID`,`file`,`flags` FROM `Files` WHERE `domain` = ? AND `relativePath` = ?", (domain_path, relative_path))
        row = cur.fetchone()
        if row is None:
            debug(f"No matching row from database on domain '{domain_path}', relative '{relative_path}'")
            raise FuseOSError(errno.ENOENT)
        return FileInfo(self.root, row[0], domain_path, relative_path, biplist.readPlistFromString(row[1]), row[2])
    
    def _get_db_file(self):
        return os.path.join(self.root, "Manifest.db")
    
    def _generate_domain_tree(self):
        cur = self._get_db_connection().cursor()
        cur.execute("SELECT DISTINCT domain FROM Files")
        for row in cur:
            if row[0] is None:
                continue
            parts = row[0].split("-", 1)
            if len(parts) == 1:
                self._domain_tree[parts[0]] = 1
                continue
            if parts[0] in self._domain_tree:
                self._domain_tree[parts[0]][parts[1]] = 1
            else:
                self._domain_tree[parts[0]] = { parts[1]: 1 }
    
    # Borrowed from _open_temp_database from iphone_backup.py
    def _create_db_connection(self):
        db = self._get_db_file()
        if not os.path.exists(db):
            return False
        try:
            if self._db_connection is None:
                file_connection = sqlite3.connect(db)
                self._db_connection = sqlite3.connect(":memory:")
                print("Loading manifest into memory...")
                file_connection.backup(self._db_connection)
            # Check that it has the expected table structure and a list of files:
            cur = self._db_connection.cursor()
            cur.execute("SELECT count(*) FROM Files;")
            file_count = cur.fetchone()[0]
            cur.close()
            return file_count > 0
        except sqlite3.Error:
            return False
    
    def _get_db_connection(self):
        if self._db_connection is None:
            if not self._create_db_connection():
                raise ConnectionError("Could not load Manifest database!")
        return self._db_connection

    # Filesystem methods
    # ==================

    def getattr(self, path, fh=None):
        #st = os.lstat(real_path)
        info = self._get_file_info(path)
        if info.virtual:
            st = os.lstat(self.root)
            stats = dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                     'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
            stats["st_size"] = 0
            return stats
        attrs = info.properties
        return {
            'st_atime': attrs["LastStatusChange"],
            'st_ctime': attrs["Birth"],
            'st_gid':   attrs["GroupID"],
            'st_mode':  attrs["Mode"],
            'st_mtime': attrs["LastModified"],
            'st_nlink': 1,
            'st_size':  attrs["Size"],
            'st_uid':   attrs["UserID"],
        }

    def readdir(self, path, fh):
        file_info = None
        try:
            file_info = self._get_file_info(path)
        # Non-existing file or directory
        except FuseOSError:
            pass

        yield '.'
        yield '..'
        # If path doesn't exist or isn't a directory, return
        if file_info is None or not file_info.is_directory():
            return
        cursor = self._get_db_connection().cursor()
        if file_info.virtual:
            # Root
            if file_info.domain == "":
                for domain in self._domain_tree.keys():
                    yield domain
                return
            # Selects all existing domains that start with whatever is in `file_info.domain`
            cursor.execute("SELECT DISTINCT `domain` FROM `Files` WHERE `domain` LIKE ? || '-%'", (file_info.domain,))
            for row in cursor:
                # Chop domain prefix
                yield row[0][len(file_info.domain) + 1:]
            return
        target_path = file_info.relative_path
        # If the target path isn't a domain root, restrict results to
        # items that are actually inside the targeted folder and don't
        # simply start with the name of the targeted folder.
        if len(target_path) > 0:
            target_path += "/"
        # Filter by matching domain
        cursor.execute("SELECT `relativePath` FROM `Files` WHERE `domain` = :domain"
                    # Ignore anything where `relativePath` is an empty string
                    + " AND `relativePath` <> ''"
                    # Select anything where `relativePath` starts with whatever's in target_path
                    + " AND `relativePath` LIKE :path || '%'"
                    # Ignore anything that starts with target_path but contains a slash (to ignore subdirectories)
                    + " AND `relativePath` NOT LIKE :path || '%/%'", {"domain": file_info.domain, "path": target_path})
        for row in cursor:
            # Chop target_path from beginning of string
            yield row[0][len(target_path):]

    def statfs(self, path):
        stv = os.statvfs(self.root)
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
            'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))

    # This does not raise the EROFS error in the
    # default implementation like most other functions,
    # so we do it here.
    def utimens(self, path, times=None):
        raise FuseOSError(os.EROFS)

    # File methods
    # ============

    def open(self, path, flags):
        # If any flags that cause writing are present, throw an error
        if flags & self.BAD_FILE_FLAGS != 0:
            raise FuseOSError(os.EROFS)
        file_info = self._get_file_info(path)
        if file_info.is_directory():
            # Default implementation is just return 0, so I guess that's fine?
            return self.opendir(path)
        return os.open(file_info.get_path(), flags)

    def read(self, path, length, offset, fh):
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, length)
    
    def readlink(self, path):
        file_info = self._get_file_info(path)
        if "Target" not in file_info.properties:
            raise FuseOSError(os.EINVAL)
        return file_info.plist['$objects'][file_info.properties["Target"].integer]

    def release(self, path, fh):
        return os.close(fh)
