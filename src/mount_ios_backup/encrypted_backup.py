from . import google_iphone_dataprotection
from .standard_backup import BackupFS
from fuse import FuseOSError
import tempfile
import biplist
import struct
import errno
import math
import os

# Some functions and code borrowed from iphone_backup.py: https://github.com/jsharkey13/iphone_backup_decrypt
AES_BLOCK_SIZE = 16

class EncryptedBackupFS(BackupFS):
    def __init__(self, root, raw_password):
        self._password = raw_password if type(raw_password) is bytes else raw_password.encode("utf-8")
        self._open_files_info = {}
        super().__init__(root)

    def _get_db_file(self):
        return self._temp_db

    def _create_db_connection(self):
        with tempfile.TemporaryDirectory() as tempdir:
            self._temp_db = os.path.join(tempdir, "Manifest.db")
            self._decrypt_manifest_db_file()
            result = super()._create_db_connection()
            self._temp_db = None
            return result

    def _expected_source_size(self, file_size):
        # Encrypted files are padded out to the AES block size, but files whose sizes are already
        # divisible by the block size already are padded out another block.
        return math.ceil((file_size + 1) / AES_BLOCK_SIZE) * AES_BLOCK_SIZE

    # Modified from iphone_backup.py
    # Returns ManifestKey from Manifest.plist
    def _read_and_unlock_keybag(self):
        # Open the Manifest.plist file to access the Keybag:
        with open(os.path.join(self.root, "Manifest.plist"), 'rb') as infile:
            manifest_plist = biplist.readPlist(infile)
        self._keybag = google_iphone_dataprotection.Keybag(manifest_plist['BackupKeyBag'])
        # Attempt to unlock the Keybag:
        if not self._keybag.unlockWithPassphrase(self._password):
            raise ValueError("Failed to decrypt keys: incorrect passphrase?")
        return manifest_plist['ManifestKey']
    
    def _decrypt_manifest_db_file(self):
        # Decrypt the Manifest.db index database:
        print("Loading decryption keys...")
        manifest_key = self._read_and_unlock_keybag()
        manifest_class = struct.unpack('<l', manifest_key[:4])[0]
        key = self._keybag.unwrapKeyForClass(manifest_class, manifest_key[4:])
        iv = b"\x00" * 16
        print("Decrypting manifest...")
        with open(os.path.join(self.root, "Manifest.db"), 'rb') as encrypted_db_filehandle, open(self._temp_db, 'wb') as decrypted_db_filehandle:
            while True:
                # Read in arbitrary block sizes
                encrypted_data = encrypted_db_filehandle.read(65536)
                if not encrypted_data:
                    break
                decrypted_data = google_iphone_dataprotection.AESdecryptCBC(encrypted_data, key, iv=iv)
                decrypted_db_filehandle.write(decrypted_data)
                # Last block of ciphertext = next block IV
                iv = encrypted_data[-16:]
    
    def _decrypt(self, file_info, iv, data):
        protection_class = file_info.properties["ProtectionClass"]
        encryption_key = file_info.plist['$objects'][file_info.properties['EncryptionKey'].integer]['NS.data'][4:]
        inner_key = self._keybag.unwrapKeyForClass(protection_class, encryption_key)
        return google_iphone_dataprotection.AESdecryptCBC(data, inner_key, iv=iv)
    
    # File methods
    # ============

    def open(self, path, flags):
        # If any flags that cause writing are present, throw an error
        if flags & self.BAD_FILE_FLAGS != 0:
            raise FuseOSError(errno.EROFS)
        file_info = self._get_file_info(path)
        if file_info.is_directory():
            # Default implementation is just return 0, so I guess that's fine?
            return self.opendir(path)
        fh = os.open(file_info.get_path(), flags)
        # Caching the file info avoids hitting the database for each read call
        self._open_files_info[fh] = file_info
        return fh

    def read(self, path, req_length, req_offset, fh):
        file_info = self._open_files_info[fh]
        # If file is not encrypted, handle it like a normal file
        if not "EncryptionKey" in file_info.properties:
            return super().read(path, req_length, req_offset, fh)

        # This next section looks really confusing and I'm not really sure how to make it better.
        #
        # Basically, the rest of this function works around the fact that we can't just read
        # a single byte in the file, even if that's all that the caller requested, because
        # we have to decrypt it first, and AES is a block cipher.
        #
        # So what ends up happening is we need to find the start and end positions of the
        # block(s) the caller requested, then back up one block from the first of those to
        # find the IV for decryption. (Use zeroes if we're already at the beginning of the file.)
        #
        # We can then pass this information off to the decryption function and get the result.
        #
        # If we read to the end of the file, some AES padding needs to be trimmed, so we do that next.
        #
        # Finally, we need to trim the decrypted data back down to what the caller actually requested,
        # in case the caller requested partial block(s).

        # Requested end byte
        req_end = req_offset + req_length
        # The start of the block that req_offset lands in
        req_block_boundary = AES_BLOCK_SIZE * int(req_offset / AES_BLOCK_SIZE)
        # The end of the block that req_length lands in
        req_end_block_boundary = (math.ceil(req_end / AES_BLOCK_SIZE) * AES_BLOCK_SIZE)
        # Number of bytes that need to be removed from the beginning before returning
        block_start_offset = req_offset - req_block_boundary
        # Number of bytes that need to be removed from the end before returning
        block_end_offset = req_end_block_boundary - req_end
        # Block before first requested block, to determine the IV
        prev_block_boundary = req_block_boundary - AES_BLOCK_SIZE
        if prev_block_boundary < 0:
            os.lseek(fh, 0, os.SEEK_SET)
            iv = b"\x00" * 16
        else:
            os.lseek(fh, prev_block_boundary, os.SEEK_SET)
            iv = os.read(fh, AES_BLOCK_SIZE)
            # If a program is attempting to read past the end of a file, this may occur.
            if len(iv) == 0:
                return b""
        data = os.read(fh, req_end_block_boundary - req_block_boundary)
        decrypted = self._decrypt(file_info, iv, data)
        # If we're reading the last byte in the file
        if req_end_block_boundary - 1 >= file_info.get_size():
            decrypted = google_iphone_dataprotection.removePadding(decrypted)
        if block_start_offset > 0:
            decrypted = decrypted[block_start_offset:]
        if len(decrypted) > req_length:
            decrypted = decrypted[:req_length - len(decrypted)]
        return decrypted

    def release(self, path, fh):
        # Remove file_info cache if it exists
        self._open_files_info.pop(fh, None)
        super().release(path, fh)
