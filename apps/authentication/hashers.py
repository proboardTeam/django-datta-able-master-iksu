from django.contrib.auth.hashers import ScryptPasswordHasher, PBKDF2PasswordHasher


class ScryptWrappedPasswordHasher(ScryptPasswordHasher):
    algorithm = "scrypt"

    def encode_pbkdf2_sha256_hash(self, password, salt, n=None, r=None, p=None):
        print(f'update after password : sha={password}, salt={salt}')

        return super().encode(password, salt, n, r, p)

    def encode(self, password, salt, n=None, r=None, p=None):
        pbkdf2_sha256_algorithm, pbkdf2_sha256_iterations, pbkdf2_sha256_salt, pbkdf2_sha256_hash = PBKDF2PasswordHasher().encode(
            password, salt, iterations=320000).split("$", 3)
        print(f'update before password : sha={password}, salt={salt}')

        return self.encode_pbkdf2_sha256_hash(pbkdf2_sha256_hash, pbkdf2_sha256_salt,)
