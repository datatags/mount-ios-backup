import os

class FileInfo():
    def __init__(self, root, hash, domain, relative_path, plist, flags, virtual=False):
        self.root = root
        self.hash = hash
        self.domain = domain
        self.relative_path = relative_path
        self.plist = plist
        self.flags = flags
        self.virtual = virtual
        self.size = None
    
    @property
    def properties(self):
        # Borrowed from _decrypt_inner_file in iphone_backup.py
        return self.plist['$objects'][self.plist['$top']['root'].integer]
    
    def is_file(self):
        return self.flags == 1
    
    def is_directory(self):
        return self.flags == 2
    
    def is_symlink(self):
        return self.flags == 4
    
    def get_path(self):
        return os.path.join(self.root, self.hash[:2], self.hash)

    def get_size(self):
        if self.size is None:
            self.size = os.path.getsize(self.get_path())
        return self.size
